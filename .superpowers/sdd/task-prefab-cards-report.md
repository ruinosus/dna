# Prefab cards on the MCP read tools — SEP-1865

Branch `feat/mcp-apps-prefab`, off `origin/main` (`44a9373`). Two commits, one
per part. No PR, no version bump.

| Part | SHA | What |
|---|---|---|
| A | `952a812` | the `apps` extra, the shared renderer resource, the merge helper, the host-theme bridge |
| B | `6e264d7` | the three cards + the tool declarations |

---

## The venv invocation that worked in a worktree

A fresh worktree has no venvs, and the main checkout's venvs are
editable-installed against **absolute paths in the main checkout** — running
against them tests the wrong tree. What works, per package, is `uv sync`:

```bash
cd /Users/jefferson.barnabe/projects/dna-wt-prefab/packages/sdk-py && uv sync --all-extras
cd /Users/jefferson.barnabe/projects/dna-wt-prefab/packages/cli     && uv sync --all-extras
# then, from the package directory:
uv run pytest tests -q
uv run pytest tests/test_mcp_cards.py -n 0 -q     # -n 0 for timing / single-test work
```

`uv sync` creates `packages/<pkg>/.venv` **inside the worktree** and installs
`dna-sdk` from the worktree's own `../sdk-py` (the `[tool.uv.sources]` path
source), so both packages resolve to worktree code. Verified: the sdk-py venv
cannot import `dna_cli` or `prefab_ui` at all, which is also what makes the
sdk-py suite result below independent of this change.

Two notes:

- `uv sync` writes a **`uv.lock`** into each package. Neither is tracked and
  neither was committed; the repo's documented path
  (`uv venv && uv pip install -e ../sdk-py -e ".[dev]"`, AGENTS.md) does not
  create one. Delete them if a clean `git status` matters.
- `--all-extras` is required, not optional: without it `fastmcp[apps]` never
  arrives and `tests/test_mcp_cards.py` silently `importorskip`s — the cards
  would ship unproven.

---

## Part A — the setup, paid once

### The `apps` extra

`packages/cli/pyproject.toml`: `mcp = ["fastmcp>=3.2"]` → `["fastmcp[apps]>=3.4"]`,
and the same in `[dev]`. The extra brings `prefab-ui` (1.85 MB wheel,
`renderer/app.html` = 6 646 438 B).

It went into the **`mcp` extra rather than one of its own** because the failure
mode of a partial install is worse than the feature's absence: three tool
declarations point `ui://dna/prefab`, the host prefetches, and the resource
404s — a broken promise instead of an absent one.

**The Dockerfile needed no new line.** `deploy/azure/Dockerfile` installs
`"/src/packages/cli[mcp]"`, so the extra carries it. What was added is a
comment naming the ~6.6 MB image growth, so it is not a mystery on the next
build, plus the fact that the renderer is served from the package rather than
fetched, so the container needs no new egress.

### The shared resource

`ui://dna/prefab`, registered once in `build_server`, served with
`text/html;profile=mcp-app`. `AppConfig(resource_uri=UI_PREFAB_URI)` overrides
the default, which would mint `ui://prefab/tool/<hash>/renderer.html` per tool.
Mutation-verified: dropping the override produces **three** hashed URIs
(`63ac139eb8f5`, `38e672a949ee`, `890eda94af76`) — three separate 6.6 MB
documents.

**Bundled, never CDN.** `get_renderer_csp(mode="bundled")` returns
`{'resource_domains': []}`; the CDN mode returns
`{'resource_domains': ['https://cdn.jsdelivr.net']}`. Bundled is the only shape
that survives the MCP Apps deny-by-default CSP with nothing to declare, so the
resource declares no CSP at all.

> **Caveat found by measuring, not by reading.** The bundled document still
> *contains* a jsDelivr URL — `cdn.jsdelivr.net/pyodide/v0.27.4/...` — on the
> generative path the renderer enters only on `ontoolinputpartial`. No DNA tool
> streams a partial input, so it is inert, and the resource correctly declares
> the base CSP rather than `get_generative_renderer_csp`'s. It also means
> **grepping the document for a CDN hostname proves nothing**: my first version
> of the test did exactly that and failed. It now asks structurally — the served
> document equals `get_renderer_html("bundled")` with our `<style>` spliced in,
> and is not the stub.

### Merge, never replace — and why it holds by construction

```python
ToolResult(content=data, structured_content={**data, **app.to_json()})
```

Passing the **dict** as `content` runs it through FastMCP's own
`_convert_to_content` → `default_serializer` — the identical code path a tool
returning that dict would take. Byte-identity is therefore a property of the
construction, not of a hand-written serializer that could drift from FastMCP's.

Re-verified against the installed renderer's source (prefab-ui 0.20.2), not its
docs: `onToolResult` reads only `$prefab`, `version`, `view`, `defs`, `state`,
`_meta`, `keyBindings`, `mode`, `css`, `stylesheets`, and returns early on a
missing `structuredContent`. Every other top-level key is ignored — the
behaviour the additive merge rests on still holds.

A wire key colliding with a tool field **raises**. Which keys Prefab uses is
Prefab's to change; a future collision must break loudly rather than quietly
rewrite a field on a consumer's screen.

### Two theme subtleties that are invisible by reading

Both are pinned by their own test because both are silent failures.

1. **`:root:root`, not `:root`.** The renderer declares its palette in `:root`
   *and* swaps it in `.dark`. A `:root` rule ties with `.dark` on specificity
   and loses on order — the card would keep the renderer's own colours in dark
   mode. Doubling the pseudo-class outranks a class selector without
   `!important`, and the rule is unlayered, so it also beats anything the
   renderer puts in a cascade layer.
2. **The bridge never reads a token it also declares.** Several host token names
   collide *exactly* with the renderer's Tailwind theme names — `--font-sans`,
   `--font-mono`, `--font-weight-*`, `--text-sm`. Writing
   `--font-sans: var(--font-sans, …)` is a **cycle**, which makes the property
   guaranteed-invalid and takes every rule that uses it down. So those are not
   redeclared; `--default-font-family` is the seam that reads `--font-sans`
   without the cycle. The upside is that the colliding names are honoured
   **automatically**: a host injects them as inline styles on the document
   element, which outranks the renderer's layered `@theme` values.

---

## Part B — which tools were converted, and which were judged

**All three were converted. None met the bar for skipping** — the question asked
of each was whether it reads *better* as text, and none does.

| Tool | Shape returned | Verdict |
|---|---|---|
| `list_stories` | `{scope, count, stories[{name,title,status,feature,priority}]}` | **Card.** Five columns over N rows — a table, the shape JSON text reads worst. Sortable/searchable/paginated. |
| `sdlc_digest` | RAG + counts + four attention buckets + verdict + coverage, nested | **Card.** The only genuinely dashboard-shaped answer on this face; the headline facts are buried in an object a reader has to reassemble. |
| `list_my_kinds` | `{scope, kinds[10 fields each]}` | **Card, and the weakest case.** See below. |

`list_my_kinds` is the one I nearly skipped, and the honest reasoning is worth
recording. The argument against: its documented *human* act — approval — lives
on the REST face by design (`_mcp_kinds`'s own docstring says so twice), so the
MCP caller is usually the authoring agent, which reads `content` and cannot see
a card at all. The argument that won: `approved` is the fact this route exists
to publish — an unapproved Kind exists and has **no effect** — and in the text
answer it is one boolean among ten fields, per row. The module calls this route
"the audit surface the authoring door exists to produce", which is an argument
*for* a legible roster. So it ships, with the count still inert in the headline
and both actors kept visible.

Two deliberate restraints:

- **`list_stories`' status column is plain text, not a coloured badge.** The
  status vocabulary is open — any workflow may define its own — so a colour map
  would be either incomplete or invented. Colour is only used where the
  vocabulary is closed and owned (`rag_status`, `approved`).
- **No actions, anywhere.** A test greps every view for `CallTool`,
  `SendMessage`, `OpenLink`, `onClick`, `onRowClick`, `action`, `actions`,
  `onSubmit`. On the Kinds card this is doubly load-bearing: an agent able to
  approve could approve its own proposal, which is the one thing that module
  exists to make impossible.

### The real per-card cost

Lines are Python after the docstring, excluding blanks and comments. Bytes are
compact JSON added to `structured_content`, against the pinned fixtures.

| card | lines | JS | view + `$prefab` (constant) | `state` (scales) | total added | content | structured ÷ content |
|---|---|---|---|---|---|---|---|
| `list_stories` | 58 | 0 | 992 B | 374 B | 1 375 B | 358 B | ×4.84 |
| `sdlc_digest` | 83 | 0 | 1 383 B | 582 B | 1 974 B | 941 B | ×3.10 |
| `list_my_kinds` | 77 | 0 | 1 441 B | 552 B | 1 993 B | 521 B | ×4.84 |

The ratios are worst-case: the fixtures are tiny (2–3 rows). At realistic
volume the constant view amortises and the marginal cost is the `state`
projection — a **50-Story** result measures 6 884 B of `content` + 7 885 B of
card (992 B view + 6 893 B state) = **×2.15** on the structured channel. The
`content` channel — the one every non-rendering client reads — is unchanged at
every size.

Shared, one-time: the theme bridge is **1 904 B**, baked into the `<head>` of
the 6 648 357 B resource (vendor bundle 6 646 438 B + our `<style>`). Because it
rides the resource rather than the wire, it costs **zero per call** and there is
no unthemed first paint. For comparison, the hand-written memory card template
is 381 023 B, ~100 lines of JS, and one 381 KB golden **per card**.

### Zero-token evidence, per card

`test_zero_token_render_stays_legible` uses the memory card's own scanner —
copied verbatim, not reimplemented, because a cli test cannot import from
`packages/sdk-py/tests` and a second, looser way of asking the same question is
exactly what the memory card's conversion was told not to introduce. It resolves
every `var()` down to its fallback (paren-balanced, innermost first) and asserts
on the result.

Because the theme is **one bridge shared by all three cards**, the zero-token
proof is one computation that covers every card — there is no per-card
stylesheet that could diverge. What it proves with no host token set:

- `var(` no longer appears anywhere — every reference resolved;
- **no property resolves to empty** (the failure that makes a card disappear);
- `--background` = `Canvas`, `--foreground` = `CanvasText`, and they differ;
- no ink resolves onto its own ground, checked for the four pairs the renderer
  actually composites: `--foreground`/`--background`,
  `--card-foreground`/`--card`, `--muted-foreground`/`--muted`,
  `--primary-foreground`/`--primary`;
- `color-scheme: light dark` is declared, so the system-colour fallback follows
  the user's preference (and the renderer's own `style.colorScheme` assignment
  when a host declares a theme without variables);
- each semantic hue resolves to a **different value per mode**;
- `#e0a838` appears nowhere.

Mutants that kill it: a stripped fallback (`--muted-foreground` resolves to
nothing), `:root` for `:root:root`, one value for both modes, and the amber
restored.

### Contrast, every colour introduced

Measured with the WCAG 2.x sRGB relative-luminance formula, on a **white**
ground and a **`#1a1a1a`** ground. Prefab badges paint the label in the hue and
the ground in a **10%** tint of the same hue (**20%** in dark mode), so both
pairs are reported — the tinted one is the real one.

| token | light fallback | on `Canvas` | on the 10% tint | dark fallback | on `Canvas` | on the 20% tint |
|---|---|---|---|---|---|---|
| `--destructive` | `#9d2622` | 7.68:1 | **6.48:1** | `#f0a6a3` | 8.86:1 | **5.83:1** |
| `--warning` | `#785707` | 6.64:1 | **5.73:1** | `#d1b060` | 8.36:1 | **5.58:1** |
| `--success` | `#166135` | 7.51:1 | **6.43:1** | `#8fc5a6` | 8.87:1 | **5.85:1** |
| `--info` | `#1f4887` | 8.99:1 | **7.65:1** | `#a1beea` | 9.17:1 | **5.95:1** |

| token | value | light | dark |
|---|---|---|---|
| accent (genome teal, `color-mix(#2f8570 80%, ink)`) | `#266a5a` / `#599d8d` | **6.38:1** | **5.50:1** |
| `--muted-foreground` (`CanvasText 68%`) | `#525252` / `#b6b6b6` | **7.81:1** | **8.58:1** |

Non-text surfaces, reported for completeness and deliberately low —
they carry no text: `--border` (`CanvasText 22%`) 1.69:1 / 2.03:1,
`--muted` (`CanvasText 6%`) 1.14:1 / 1.18:1.

**Every text value clears AA (≥4.5:1) on both grounds and on both tints.**

Two things worth stating about the amber, since the brief singled it out:

1. The SDLC amber `#e0a838` measures **2.14:1** on white and **3.30:1** at the
   80% ink mix the accent uses. There is no mix ratio that clears AA on the
   light tint without washing out on dark — the best symmetric ratio for
   `#b8860b` is 0.65, at 5.73:1 / 5.58:1, and for `#e0a838` itself the best is
   0.65 at 4.73:1 / 10.70:1, which is AA by a hair on light and badly
   desaturated on dark. That asymmetry is **why the semantic hues use
   `light-dark()` rather than the memory card's `color-mix(… CanvasText …%)`
   recipe.** The neutrals keep the memory card's recipe exactly.
2. These are **fallbacks**. A host that ships `--color-text-warning` gets its
   own value; the measured pair is what a host that ships nothing sees.

`light-dark()` degrades the same way `color-mix()` does — an unsupported
function makes the custom property invalid, the badge's `color` falls back to
inherited and its tint to transparent, so the label stays legible in the host's
ink. Same risk profile as the recipe already in production.

---

## RED/GREEN and mutation

`packages/cli/tests/test_mcp_cards.py` — 8 tests at Part A, 16 at Part B.

**Honest note on order.** I built a throwaway prototype of the two view builders
while learning the prefab API, then set it aside and wrote the tests. So the
RED I observed was: a collection `ImportError`, then — with the prototype
restored — six tests failing for their own stated reasons (`no '$prefab' — no
card at all`, `list_stories declares no card template`, `the shared renderer is
not listed once`, `Resource not found: 'ui://dna/prefab'`, `no attribute
'kinds_app'` ×2). The two prototype-covered card tests
(`test_the_stories_card_…`, `test_the_digest_card_…`) and the five theme tests
did **not** get an observed RED; they are proven by mutation instead, which is
the stronger check and the one this project's twelve wrong-reason tests argue
for. Both are recorded rather than dressed up.

The two the brief asked to prove specifically:

- **`content` unchanged for a client that renders nothing** —
  `test_content_is_byte_identical_to_the_pre_card_baseline`, against fixtures
  captured from the tools *before* any wiring existed. It passes trivially
  pre-feature, so it is a guard, not a RED/GREEN pair; its value is entirely in
  M1 and M2 below. M2 matters: a plain `json.dumps(data)` (spaces after `:` and
  `,`) dies on it, which is the drift a hand-written serializer introduces.
- **A card survives with zero host tokens** — `test_zero_token_render_stays_legible`,
  detailed above.

### Mutants — 18 planted, 18 killed

| # | Mutation | Killed by |
|---|---|---|
| M1 | `app=True`'s `_prefab_to_tool_result` instead of the hand-built merge | byte-identity (`b'[Rendered Prefab UI]' != b'{"scope":…'`) + superset |
| M2 | hand-rolled `json.dumps(data)` instead of FastMCP's converter | byte-identity (`At index 9 diff: b' ' != b'"'`) |
| M3 | drop the `resource_uri` override | shared-renderer (3 hashed URIs) |
| M4 | strip one fallback (`--color-text-secondary`) | fallback test **and** zero-token (`--muted-foreground` resolves to nothing) |
| M5 | `:root` instead of `:root:root` | cascade test + cycle test + zero-token |
| M6 | `--font-sans: var(--font-sans, …)` (a CSS cycle) | cycle test |
| M7 | `#e0a838` as the whole warning fallback | zero-token (one value for both modes) |
| M7b | `#e0a838` as the *light* half only, pair intact | zero-token (`the illegible SDLC amber is back`) |
| M8 | one value instead of the measured `light-dark()` pair | zero-token |
| M9 | `on_row_click=CallTool(...)` on the Stories table | no-action test |
| M10 | `_text` returns `str(None)` | Stories card (`'None' == '—'`) |
| M11 | an unapproved Kind reads as approved | Kinds card |
| M12 | `amber → success` in the RAG map | digest card |
| M13 | theme bridge shipped in the wire, not the resource | resource test |
| M14 | a colliding wire key overwrites instead of raising | collision test (`DID NOT RAISE`) |
| M15 | one tool loses its `app=` declaration | shared-renderer test |
| M16 | a tool returns bare data, skipping the card | superset test |

M13 needed the test tightened first: it originally asked for
`--color-background-primary` in the served HTML, which the *bundle itself*
contains (in the zod schema it validates the host context against), so the
mutant survived the intended assertion. It now asks for `.dna-mark{` — a string
only we write.

---

## Suites

Run in full, from the worktree venvs, at the Part B state.

- **`packages/cli/tests`** — **1 344 passed**, 19 skipped, **0 failed** (95 s).
- **`packages/sdk-py/tests`** — **4 426 passed**, 234 skipped, 4 xfailed,
  **2 failed** (229 s).

### The two sdk-py failures are pre-existing, and provably not mine

Neither is one of the two the brief named — both of *those* passed in this
worktree, which is itself a venv-composition difference, not a code change.

| Failure | Cause |
|---|---|
| `test_emit_agent_framework.py::test_emitted_yaml_loads_into_agent_framework` | `TypeError: PropertySchema.__init__() got an unexpected keyword argument 'required'` — a third-party signature change. `agent-framework` is pinned `==1.12.1`, so this comes from an unpinned transitive (`agent-framework-declarative` and friends resolve fresh in a new lock). |
| `runtime/test_langchain_adapter.py::test_attach_registers_the_agui_route` | `ModuleNotFoundError: No module named 'ag_ui_langgraph'`. That package is **not declared anywhere** in `packages/sdk-py/pyproject.toml`, so this test cannot pass in any freshly-provisioned venv — a real gap in the dev extras, unrelated to this work. |

The proof that neither is mine: the diff touches **no file under
`packages/sdk-py`**, and the sdk-py venv cannot import `dna_cli` or `prefab_ui`
at all (verified with `importlib.util.find_spec`).

### Guards and constraints

- `brand_guard` clean; `docs_coverage_guard` clean (100 public items);
  `data_model_guard` clean.
- No test under `packages/sdk-py/tests/` imports `dna_cli` — nothing there was
  touched.
- No YAML was touched, so no `yaml.safe_load` ratchet applies; grep confirms
  neither new file contains one.
- No rule-3 token (`TODO` / `deferred` / `follow-up` / `coming soon`) in either
  new file.
- Vendor-neutral: no host, workspace id, product or commercial name entered
  `packages/sdk-py` or `packages/cli`.
- `CLAUDE.md` / `AGENTS.md` name none of the changed surfaces (checked by grep;
  neither is generated by a script), so there was nothing to regenerate.

---

## Concerns

1. **`--text-sm` / `--text-xs` in the existing memory card are not host tokens.**
   The real MCP Apps names are `--font-text-sm-size` / `--font-text-xs-size` —
   I extracted the full 76-name vocabulary from the renderer's own zod schema.
   `dna/emit/mcp_ui.py` reads `--text-sm`/`--text-xs`, which no host sets, so
   those two fallbacks (14px/12px) always apply and the card silently ignores
   the host's type scale. The sdk test's `_HOST_TOKEN_FAMILIES` allows
   `--text-` so it does not catch it. **Not fixed here** — it changes a frozen
   golden another agent may be mid-flight on, and it is outside this task. The
   fix is two constants plus a golden regeneration. The new cards use the
   correct names.
2. **`prefab-ui` is pre-1.0 (0.20.2) and the wire protocol is `0.3`.** The
   renderer warns on an unrecognized version. We emit whatever the installed
   `PROTOCOL_VERSION` is, so a `prefab-ui` bump could change the wire without
   any change here. Nothing pins the protocol version we emit; a floor on the
   *feature* is `fastmcp[apps]>=3.4`, which does not constrain `prefab-ui`.
3. **`mode` is deliberately never set on a `PrefabApp`.** Reading the renderer:
   if `mode` is set, the host-context handler takes the branch that only toggles
   the dark class and **skips `osr()`**, which is the function that injects the
   host's `styles.variables` and sets `colorScheme`. Setting `mode` would
   therefore silently discard the host's design tokens. Nothing in the code
   sets it and no test forbids it — a plausible future "let me force dark"
   would break the theme without failing anything.
4. **The `state` projection duplicates data on the wire** (×2.15 at realistic
   volume). That is inherent to a bindable view: the renderer resolves
   `{{ … }}` against `state` only, and `content` must stay byte-identical, so
   the data appears at the top level *and* under `state`. Baking rows into the
   view instead would cost the same bytes. Worth revisiting only if a very large
   `list_stories` result becomes common.
5. **The cards are unrendered.** Everything here is verified against the
   renderer's source, its CSP contract and computed contrast — no browser was
   driven. The cascade reasoning (`:root:root` beating both `:root` and `.dark`,
   unlayered beating layered) and the `light-dark()`/`color-mix()` degradation
   paths are argued from the spec, not observed. First host render is the place
   a wrong assumption would show up.
6. **`test_mcp_cards.py` duplicates ~70 lines of CSS-scanner** from
   `packages/sdk-py/tests/test_emit_mcp_ui.py`. Copied verbatim rather than
   reimplemented, but the constraint that a cli test cannot import from the
   sdk-py suite means the two can drift.
