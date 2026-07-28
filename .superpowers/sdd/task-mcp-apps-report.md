# MCP Apps conformance — SEP-1865 final (2026-07-28)

Branch `feat/mcp-apps-conformidade`, off `origin/main` (`6471952`). Three commits,
one per part. No PR, no version bump, no `pyproject.toml` edit, no new dependency.

Worked in a detached worktree at `/Users/jefferson.barnabe/projects/dna-wt-mcpapps`
rather than the shared checkout: the parallel-tests agent had
`perf/testes-em-paralelo` checked out with uncommitted changes to the four files
it owns, and `git checkout -b` in place would have moved its HEAD and dragged its
work onto my branch. Tests ran against the worktree by putting its package dirs
on `PYTHONPATH` ahead of each venv's editable `.pth` (both venvs are
editable-installed against absolute paths in the main checkout, so this is what
makes the venv execute worktree code — verified before starting).

---

## Part 1 — the dead canvas renderer

### The caller, verified before deleting

The task's pointer ("a `memory_projection` module around line 140") does not
exist in this repo — there is no such module here, and nothing in
`packages/sdk-py` or `packages/cli` referenced the canvas renderer at all. The
only references inside the SDK were the module's own docstring, its `__all__`
entry, its own test, and a CHANGELOG line.

The live caller is in the **consuming repo**, not this one:

- `dna-cloud` → `apps/copilot/src/dna_cloud_copilot/middleware/memory_projection.py:32,140`
  — `MemoryTimelineMiddleware._project`, a LangGraph post-tool wrapper. It calls
  `memory_canvas_card_html(mems)` on **every** read-tool result
  (`list`/`list_memories`/`recall`) and pushes the HTML into the AG-UI
  shared-state key `memory_card_html`.

And nothing consumes it. `dna-cloud` → `apps/web/app/console/Console.tsx:426`:

> `// The MCP-App memory_card_html is not consumed here — that card is for external hosts (Claude/ChatGPT) via host->MCP.`

The panel reads the structured `memory_timeline` instead (`Console.tsx:428`).
The comment's stated reason is also wrong on its own terms: external hosts are
served `memory_list_card_html`, the *static* `ui://dna/memory-list` template —
never the canvas render. So the value was computed, serialized into the state
snapshot, streamed to the browser, and dropped. Deleting was correct.

### The size of the win

| | removed |
|---|---|
| `dna/emit/mcp_ui.py` | 108 lines gone, 22 rewritten (docstring, `__all__`, the section header) |
| `tests/test_emit_mcp_ui.py` | 4 canvas tests + the 26-line `_MEMORIES` fixture |
| goldens | `memory_list_card.html` (2 500 B), `memory_list_empty.html` (1 776 B) |
| commit total | **175 deletions / 22 insertions** across 4 files |

Three functions died, not two: `_esc` was reachable only from `_item_html` and
`memory_canvas_card_html` (verified — every one of its six call sites was inside
those two), so the `html` import went with them. `_CARD_CSS` stays: it is inlined
into the live template and frozen in its golden.

**What stops being computed per read-tool call:** a full standalone HTML document
— `<!doctype>` + the ~1.1 KB inline `_CARD_CSS` + one escaped `<li>` per memory
(summary, timestamp, area, affect, tag chips), each field through
`html.escape`. Measured on the deleted goldens: a **1 776-byte floor** on every
call regardless of result size, **+ ~240 bytes and 4–6 `html.escape` calls per
memory** (2 500 B for the 3-memory fixture). A 20-memory `list_memories` was
building and shipping roughly 6 KB of markup that no renderer ever read.

**Cross-repo consequence, deliberate and named in the commit body:** this is a
breaking change for the consumer. `apps/copilot/.../memory_projection.py` must
drop the `memory_canvas_card_html` import (and the `memory_card_html` state key,
plus `composer.py:55` and the two assertions in
`apps/copilot/tests/test_memory_projection_middleware.py:68-69`) in lockstep with
the SDK floor bump. `memory_timeline`, which the console actually renders, is
untouched.

---

## Part 2 — the extension negotiation

### What the installed FastMCP does and does not expose

Installed: **FastMCP 3.4.4**, **`mcp` SDK at protocol `2025-11-25`** (read from
the packages, not their docs).

**Does expose:**

- `fastmcp.apps.config.UI_EXTENSION_ID` = `"io.modelcontextprotocol/ui"`, and
  `AppConfig` → `_meta.ui.resourceUri` on the tool declaration
  (`fastmcp/server/server.py:1815`). Our mechanism was already right.
- `MiddlewareServerSession.client_supports_extension(id)`
  (`fastmcp/server/low_level.py:56-73`) and its `Context` wrapper
  (`fastmcp/server/context.py:586-611`). Both read
  `session._client_params.capabilities.model_extra["extensions"]` — i.e. the map
  the client sent at **`initialize`**. `ClientCapabilities` is `extra="allow"`,
  which is the only reason an extension field survives the older model at all.
- The server auto-declares the extension in its own capabilities
  (`low_level.py:216-231`).

**Does NOT expose:**

1. **The extension config it declares is empty.** Probed live:
   `{'extensions': {'io.modelcontextprotocol/ui': {}}}` — no `mimeTypes`. The
   final spec's shape is `{"mimeTypes": ["text/html;profile=mcp-app"]}`; a host
   that filters on advertised mimeTypes would never prefetch our card.
2. **Nothing reads capabilities from per-request `_meta`.** The 2026-07-28 core
   removed `initialize` and sessions and moved protocol version / client info /
   capabilities into `_meta` on every request. `RequestParams.Meta` in the
   installed SDK models only `progressToken` (it is `extra="allow"`, so the new
   fields would *arrive*, but nothing parses them). `client_supports_extension`
   reads only the handshake.
3. **`client_supports_extension` conflates "no" with "don't know."** It returns
   `False` for a client that declared nothing *and* for no session at all
   (stateless HTTP, outside a request context). Unusable as a gate — it cannot
   distinguish a client that can't render from a runtime that won't tell us.
4. **No per-call tool registration.** Tools are registered at build time, so the
   spec's literal "check before registering UI-enabled tools" has no direct
   FastMCP analogue.
5. **`on_initialize` middleware cannot change the declared capabilities.**
   `low_level.py:98-108` wraps `responder.respond` to *capture* the
   `InitializeResult` — but it forwards to the real `respond` first, so the
   result is already on the wire by the time middleware sees it. Read-only.
6. **The client SDK cannot declare an extension.** `mcp/client/session.py:188`
   hard-codes `ClientCapabilities(...)` with no seam. Probed: a stock
   `fastmcp.Client` sends `capabilities: {}`. The tests inject the `extensions`
   extra the way a real host sends it.

### What I implemented

All in `packages/cli/dna_cli/_mcp_server.py`, one commented section
("MCP Apps: the extension negotiation"), wired at the end of `build_server`.

**Outbound — `_declare_ui_extension(server)`.** Wraps the low-level server's
bound `get_capabilities` (the only writable seam, per finding 5) so our entry
becomes `{"mimeTypes": [MCP_APP_MIME]}`, merging rather than replacing so every
other capability the runtime computes survives. `MCP_APP_MIME` is imported from
`dna.emit.mcp_ui` — the module that *renders* the resource — so what we declare
and what we serve cannot drift.

**Inbound — `client_ui_extension(request_meta=, session_capabilities=)`,
tri-state on purpose:**

- `True` — the client declared the extension.
- `False` — it sent a capability map and the extension is not in it. It cannot
  render.
- `None` — neither channel carried a capability map. We do not know, and we say
  so. This is the answer that finding 3 makes necessary and the one that keeps
  this from being a fake check.

It reads the **per-request `_meta` first** (the 2026-07-28 shape: `_meta` →
`capabilities` → `extensions`, with a tolerated top-level `extensions`), then
falls back to the **`initialize` handshake** (what the pinned runtime speaks).
The per-request map wins — it is the fresher statement of the same fact. So the
day a client shows up speaking the new core, this already hears it, without an
SDK bump. `client_ui_extension_from_context` sources both from a live FastMCP
context and never raises: an unreadable shape is `None`, the reading that leaves
the client's experience unchanged.

**Application — `_ui_capability_middleware()`.** Since tools cannot be registered
per call (finding 4), the check lands on `tools/list`: a client that answered a
definite **`False`** is not offered `_meta.ui`. `_tool_without_ui_meta` returns a
`model_copy`, never a mutation — the tool objects are the server's shared
registry, and stripping in place would let the first UI-blind client permanently
withhold the card from everyone after it.

**The text answer is never touched.** The check gates the declaration only.
`_with_memory_card` already merges (`content` = the JSON text block,
`structured_content` = the mirror) instead of FastMCP's `app=True` placebo, and
the byte-identity tests against the frozen pre-feature fixtures still pass
unchanged. The `ui://` resource also stays readable by anyone — gating it would
break a host that prefetches before it declares.

### The gap that remains, stated plainly

**On `None` (unknown) we keep the pointer, we do not strip.** That is the
approximation, and it is deliberate:

- the runtime cannot yet surface a new-core client's per-request declaration
  through its own plumbing, so "unknown" will be the honest answer for real
  clients until the `mcp` SDK models `_meta` capabilities (our resolver already
  reads them — nothing else in the stack routes them to us);
- the UI declaration is additive `_meta` a non-supporting host ignores, so
  over-advertising costs approximately nothing, while under-advertising silently
  breaks a capable host.

So the SHOULD is honoured wherever the client actually speaks, and where it does
not, we fail toward the working feature rather than guessing. This is pinned as
behaviour by `test_an_unknown_client_keeps_the_inert_pointer` — flipping the
policy is a test failure, not a silent drift.

Second, smaller gap: `_declare_ui_extension` patches an instance attribute on
`server._mcp_server`. It is the only seam FastMCP offers today; if a future
FastMCP declares mimeTypes itself, the wrapper becomes a no-op merge and can be
deleted. It logs a warning rather than failing if the seam disappears.

---

## RED/GREEN pairs

Every one watched failing for its stated reason before the code existed.

### Part 1

| Test | RED (observed) | GREEN |
|---|---|---|
| `test_module_exposes_only_the_mcp_apps_template_surface` | `AssertionError: Left contains one more item: 'memory_canvas_card_html'` — `__all__` still carried the dead render | passes after the deletion; 7/7 in `test_emit_mcp_ui.py` |

**Mutant:** re-added a stub `memory_canvas_card_html` to the module →
`AssertionError: 'memory_canvas_card_html' is back — the dead canvas renderer
must stay deleted`. Killed.

### Part 2

Eight tests written first; all eight RED, then GREEN. The two that matter most
were RED for **behavioural** reasons, not missing attributes:

| Test | RED (observed) | GREEN |
|---|---|---|
| `test_server_declares_the_ui_extension_with_the_mimetype_it_serves` | extension declared as `{}` — no `mimeTypes` | `{"mimeTypes": ["text/html;profile=mcp-app"]}` |
| `test_client_ui_extension_reads_the_per_request_meta_first` | `client_ui_extension` did not exist | tri-state, `_meta` wins over handshake |
| `test_client_ui_extension_falls_back_to_the_initialize_handshake` | same | reads `_client_params.capabilities` |
| `test_client_ui_extension_says_unknown_rather_than_guessing` | same | `None`, not `True`, not `False` |
| `test_a_client_that_declares_nothing_is_not_offered_the_ui_pointer` | **`AssertionError: list_memories advertised its UI template to a client that cannot render it` — `assert not 'ui://dna/memory-list'`** | pointer withheld; tool + description still listed |
| `test_withholding_the_pointer_never_degrades_the_text_answer` | n/a (guard) | content byte-identical to the frozen baselines |
| `test_the_template_is_served_to_any_client` | `M.MCP_APP_MIME` did not exist | resource readable by a UI-blind client |
| `test_memory_tool_declarations_point_the_template` (rewritten) | client now declares the extension | pointer present for a UI-capable client |

Two more added after GREEN to cover policy branches nothing yet reached
(`test_an_unknown_client_keeps_the_inert_pointer`,
`test_withholding_for_one_client_does_not_poison_the_next`) — both proven by
mutants M3 and M5 below.

### Mutation runs — all six killed

| Mutant | Killed by |
|---|---|
| **M1** `client_ui_extension` → always `True` (*the fake check the brief forbids*) | 5 tests, including the integration one: `test_a_client_that_declares_nothing_is_not_offered_the_ui_pointer` |
| **M2** → always `False` | 5 tests, incl. `test_memory_tool_declarations_point_the_template` |
| **M3** middleware strips on unknown (`is not False` → `is True`) | `test_an_unknown_client_keeps_the_inert_pointer` |
| **M4** `_declare_ui_extension` returns early (no mimeTypes) | `test_server_declares_the_ui_extension_with_the_mimetype_it_serves` |
| **M5** `_tool_without_ui_meta` mutates in place (`del meta["ui"]`) | `test_withholding_for_one_client_does_not_poison_the_next` |
| **M6** per-request `_meta` ignored (handshake only) | `test_client_ui_extension_reads_the_per_request_meta_first` |

M1 is the load-bearing one: a capability check that always answers yes is killed
by the end-to-end protocol test, not only by the unit tests.

---

## Part 3 — the card wears the host's theme

### What was wrong

`dna/emit/mcp_ui.py` hardcoded seven colours and read zero host tokens. The card
painted a dark ink ground with light text and shipped it into whatever chat it
landed in, so a light-themed host got a dark rectangle. It was not ignoring the
theme; it had never been told one exists.

### What I changed

**Colour, type and shape now come from the host.** The retired constants
(`_INK`, `_INK_RAISED`, `_LINE`, `_TEXT`, `_MUTED`) are replaced by token
references: `--color-background-primary` / `-secondary`, `--color-text-primary` /
`-secondary`, `--color-border-primary`, `--font-sans`, `--text-sm` / `--text-xs`,
`--font-weight-semibold` / `-bold`, `--border-radius-lg` / `-full`. The host
changes their values when the user switches theme and the card follows, with no
media query and no attribute to watch.

**Every reference carries a fallback**, because hosts may provide any subset.
The fallbacks are the UA's own system colours — `Canvas` and `CanvasText`, a
contrasting pair by definition — plus `color-mix(in srgb, CanvasText …%, Canvas)`
for the derived muted-text and hairline values, so they are anchored to the ink
and can never resolve onto the ground. `:root{color-scheme:light dark}` is
declared so the system-colour fallback follows the user's light/dark preference
instead of being locked to white.

**Borders are split** — `border:1px solid` then a separate `border-color` — so
that if both a token and its fallback fail, the hairline degrades to
`currentColor` rather than to no border at all (a `var()` that is invalid at
computed-value time takes the whole shorthand with it, and `border-style`'s
initial value is `none`).

**Brand moved to the accent, and shrank by one colour.** The genome teal stays,
on the wordmark and the tag chips, as
`color-mix(in srgb, #2f8570 80%, var(--color-text-primary, CanvasText))` — mixed
toward the host's own ink so it darkens on a light ground and lightens on a dark
one. Measured: **6.4:1 on white, 5.7:1 on near-black**, versus 4.46:1 for the raw
teal on white (below AA). The chip fill and edge stay low-alpha teal, which
composites correctly over any ground.

**The SDLC amber is gone from this card.** It was on `.dna-when`, the timestamp,
where it measured **2.14:1 on white** — illegible on any light host, and no mix
ratio fixes it without either failing light (4.15:1 at 70%) or washing out on
dark. A timestamp is secondary metadata, not brand, so it now reads
`--color-text-secondary` like the rest of the meta row. The brief permitted amber
as an accent; it was not carrying brand here, it was carrying a contrast bug.

The golden `memory_list_template.html` was regenerated (the CSS is inlined in it).
The JS, the DOM structure, the `ui://` URI, the mimeType and the data path are
untouched.

### RED/GREEN — Part 3

Four tests written first, all four RED before any CSS changed.

| Test | RED (observed) | GREEN |
|---|---|---|
| `test_every_host_token_reference_carries_a_fallback` | "the card references no host design token at all" — zero `var()` calls existed | every reference has a fallback |
| `test_the_card_targets_the_host_token_vocabulary` | same — no token names to check | reads the five load-bearing host names, no private `--dna-*` |
| `test_the_card_no_longer_paints_its_own_surface` | the template still hardcoded `#12161c` | surface colours gone, accent kept |
| `test_zero_token_render_stays_legible` | **`AssertionError: assert '#12161c' == 'Canvas'`** — with no host tokens the ground was still our ink | ground `Canvas`, ink `CanvasText`, and no rule's colour equals its ground |

The legibility test does not eyeball anything: it lifts the stylesheet out of the
delivered template, resolves every `var()` down to its fallback with a
paren-balanced scanner (innermost first, so nested fallbacks resolve), then
parses the rules and asserts the ground/ink pair differs and that every rule
setting a colour differs from the surface behind it.

### Mutation runs — all six killed

| Mutant | Killed by |
|---|---|
| **N1** one fallback stripped (`var(--color-text-secondary)`) | the fallback test **and** the legibility test (it resolves to nothing → invisible) |
| **N2** ground fallback back to `#12161c` | the surface test + the legibility test |
| **N3** ink fallback set to `Canvas` (**invisible text**) | `test_zero_token_render_stays_legible` |
| **N4** `--color-border-primary` renamed `--dna-border` | the vocabulary test |
| **N5** `color-scheme:light dark` dropped | the legibility test |
| **N6** host tokens abandoned, surface hardcoded again | three tests |

Each mutant regenerated the golden before running, so the byte-golden test could
not mask the real signal.

---

## Suites

Both run in full at the end, against the worktree code.

- `packages/sdk-py/tests` — **4 393 passed**, 235 skipped, 4 xfailed, **1 failed**:
  `test_claude_export_roundtrip.py::test_imported_claude_fact_is_recallable_by_paraphrase`
  (the known pre-existing failure).
- `packages/cli/tests` — **1 321 passed**, 22 skipped, **1 failed**:
  `test_mcp_quota.py::test_store_from_env_selects_the_durable_store_for_a_postgres_source`
  (the known pre-existing failure).

**No new failures.** Repo guards clean: `brand_guard`, `docs_coverage_guard`
(100 public items covered), `data_model_guard`. No test under
`packages/sdk-py/tests/` imports `dna_cli`. Nothing vendor-specific entered
`packages/sdk-py` or `packages/cli` — the cross-repo consumer is named only here
and in the Part 1 commit body. Neither `CLAUDE.md` nor `AGENTS.md` names any
changed surface, so there was nothing to regenerate.

## Not done, on instruction

No `prefab-ui` dependency, no renderer conversion, no new cards, no
`pyproject.toml` edit — those need the dependency step currently held behind the
parallel-tests branch.
