# Aprovar no card — approval over MCP, app-only

Branch `feat/mcp-aprovar-no-card`, worktree `/Users/jefferson.barnabe/projects/dna-wt-approve`.
No PR, no version bump.

---

## 1. How `visibility` is declared, and what the installed runtime actually supports

**Declared** in `packages/cli/dna_cli/_mcp_kinds.py`:

```python
approve_only_from_the_card = AppConfig(visibility=["app"])

@server.tool(name=APPROVE_TOOL, run_in_thread=False, app=approve_only_from_the_card)
async def approve_kind(kind: str, tenant: str | None = None) -> dict[str, Any]:
```

No `resource_uri` — this tool renders nothing; it is pressed by a button on
another tool's card, so it needs the visibility half of the declaration and not
the renderer half.

**What the installed runtime supports — measured, not assumed.**
FastMCP **3.4.5**, `mcp` types from the same lockstep:

| question | answer (measured) |
|---|---|
| `mcp.types.Tool` has a `visibility` field? | **No.** Fields are `annotations, description, execution, icons, inputSchema, meta, name, outputSchema, title`. |
| `Tool.from_function(...)` takes `visibility=`? | **No.** |
| `fastmcp.apps.AppConfig` has `visibility`? | **Yes** — `list[Literal["app","model"]] | None`, tools only (it raises if set on a resource). |
| What lands on the wire? | `_meta = {"ui": {"visibility": ["app"]}, "fastmcp": {"tags": []}}` — verified through a real `fastmcp.Client` against `build_server()`. |
| Does FastMCP itself hide it from `tools/list`? | **No, not for this shape.** `server._is_backend_tool()` requires *both* `meta.fastmcp.app` (set only by the `FastMCPApp` provider) *and* `meta.ui.visibility == ["app"]`. A plain `@server.tool(app=AppConfig(...))` has the second and not the first, so the tool stays in `tools/list`. |
| Is that a problem? | **No — it is the spec-correct outcome.** FastMCP's own source carries the note `FIXME: the latter isn't correct behavior according to the mcp-apps spec` on its hiding. SEP-1865 keeps the tool in `tools/list` *with the marker*; the **host** is what must not pass it to the model. |
| Still callable by display name? | **Yes** (measured), which is what lets `app.callServerTool("approve_kind")` work without hashed-name addressing. |

So the installed runtime **can** express `visibility` on a tool, exactly as the
task requires. Nothing was approximated.

**One hole found and closed while doing this.** `_mcp_server._ui_capability_middleware`
strips the entire `ui` meta block for a client that declared it cannot render MCP
Apps — and `visibility` lives *inside* that block. A UI-blind client would
therefore have been handed `approve_kind` **wearing no marker at all**: an
approval tool indistinguishable from `author_kind`, straight into the model's
list. Such a tool is now **withheld entirely** from that client (new
`_mcp_server.app_only()` predicate), which costs nothing — a host that cannot
render has no button to press it with. Pinned by
`test_a_host_that_cannot_render_is_not_handed_the_approval_tool`.

**The trust boundary is stated in the code**, three places, in the terms the
brief asked for — the server *cannot* distinguish a UI-initiated `tools/call`
from a model-initiated one, so this is a declaration a host enforces and not our
mechanism: `_mcp_cards.py` module docstring, `_mcp_kinds.py` module docstring
("Whose fence this is"), and the `approve_only_from_the_card` comment
("AND IT IS NOT OUR FENCE").

---

## 2. The two re-aimed guards, and their RED under the mutant

### Guard 1 — `test_there_is_no_approval_tool` → `test_the_model_is_not_offered_the_approval_tool`

Restated as the property it was always buying: *the tool may exist and must be
absent from the model's list*. It reads the advertised list and applies the
spec's own rule (`_mcp_server.app_only` — declared visibility that omits
`"model"`), i.e. the tool list **the way a model would see it**, not the
server's registry. Both halves are asserted, because either alone passes for the
wrong reason:

1. `approve_kind` **is** registered and **is** app-only (a missing tool would
   make the second assertion vacuously true);
2. no `approve`-ish name survives into the model's half.

### Guard 2 — the source scan → `test_no_tool_the_model_can_see_reaches_the_approval_capability`

The old form pinned that no MCP-face module imports `approve_kind_impl`. That
import now exists on purpose, and deleting the test would have been easy and
looked harmless. It was re-aimed to the capability *and made behavioural*:

- a live spy replaces `dna_cli._mcp_kinds.approve_kind_impl`;
- **every tool the model can see** whose input schema takes a `kind` is driven
  with one (`author_kind`, `review_kind` today — asserted non-empty, so the loop
  cannot prove nothing);
- none may reach the spy;
- **the spy is proven live in the same test** — the app-only tool reaches it, so
  a guard that passed because the monkeypatch never took fails here instead;
- the source half is **kept, narrowed** to an allow-list of exactly one module
  (`_mcp_kinds.py`), so a *second* path to the act is still caught even if the
  loop cannot call it.

### RED under the mutants — measured, twice

Mutant A — `AppConfig(visibility=["model", "app"])`:

```
FAILED tests/test_mcp_kind_authoring.py::test_the_model_is_not_offered_the_approval_tool
FAILED tests/test_mcp_kind_authoring.py::test_a_host_that_cannot_render_is_not_handed_the_approval_tool
FAILED tests/test_mcp_kind_authoring.py::test_no_tool_the_model_can_see_reaches_the_approval_capability
FAILED tests/test_mcp_cards.py::test_the_card_button_targets_a_tool_the_model_cannot_see
4 failed, 32 passed
```

Mutant B — declaration dropped entirely (`app=None`, i.e. visibility defaults to
both): **the same four failures**, `4 failed, 32 passed`.

Restored: `36 passed`.

Both re-aimed guards go red, and guard 2 goes red *behaviourally* — the loop
calls the now-model-visible `approve_kind` and the spy fires. Two further
guards, added on this branch, are red under the same mutants (the card's button
target and the UI-blind listing), so the property is fenced at four points.

### A third guard also had to be re-aimed

`test_no_card_wires_an_action` asserted display-only cards, with the reason named:
"a button that acts without a way to take the grant back is the wrong thing to
ship first." Revocation shipped, so it became
`test_exactly_one_card_acts_and_it_is_the_approval_one` — pinned in **both**
directions, because "one" is a weaker rule than "none": no other card may grow an
action, the review card wires exactly one `toolCall`, its target is
`C.APPROVE_TOOL`, and its arguments are exactly `{"kind"}` (a workspace or an
approver a card could name would be one a caller can name).

---

## 3. Zero-token and contrast evidence

**No new colour was introduced.** Every hue the new/changed cards paint is one of
the four measured semantic variables the theme bridge already declares
(`--destructive` / `--warning` / `--success` / `--info`), reached through the
renderer's `Badge` variants and `text-*` utilities — all four of which exist in
the bundled renderer (`text-destructive` ×5, `text-warning` ×2, `text-success`
×3, `text-muted-foreground` ×55). No new host token is read, so
`C.HOST_TOKENS` is unchanged and `test_the_bridge_targets_the_host_token_vocabulary`
still pins the exact key union.

**Zero-token render:** `test_zero_token_render_stays_legible` passes unchanged —
with not one host variable set, every `var()` resolves, nothing collapses to
empty, `color-scheme: light dark` is declared, ground ≠ ink, no ink paints on its
own ground, each semantic hue resolves to a *different* measured value per mode,
and the retired 2.14:1 SDLC amber is still absent.

**Contrast, computed on the zero-token fallbacks** (worst case: host provides
nothing), on the plain ground *and* on the badge tint (10% light / 20% dark),
both modes. WCAG AA needs 4.5:1:

| colour | mode | on ground | on badge tint |
|---|---|---|---|
| `--destructive` (revoked badge) | light | 7.68:1 | 6.48:1 |
| `--destructive` (revoked badge) | dark | 8.86:1 | 5.83:1 |
| `--warning` (unapproved badge) | light | 6.64:1 | 5.73:1 |
| `--warning` (unapproved badge) | dark | 8.36:1 | 5.58:1 |
| `--success` (approved badge) | light | 7.51:1 | 6.43:1 |
| `--success` (approved badge) | dark | 8.87:1 | 5.85:1 |
| `--info` | light | 8.99:1 | 7.65:1 |
| `--info` | dark | 9.17:1 | 5.95:1 |
| muted-foreground (actor lines) | light / dark | 7.81:1 / 8.58:1 | — |
| foreground (body + schema `Code`) | light / dark | 21.00:1 / 17.40:1 | — |
| **Approve button** (`--primary-foreground` on `--primary`) | light / dark | 21.00:1 / 17.40:1 | — |
| `.dna-mark` accent | light / dark | 6.38:1 / 5.50:1 | — |

Lowest measured value anywhere: **5.50:1**. Everything clears AA on light and
dark, on plain and tinted grounds.

---

## 4. What was built

**`approve_kind(kind, tenant?)`** — app-only. Actor from `actor_from_context()`
(the verified identity of the connection), never from arguments; delegates to
`approve_kind_impl`, so the guarded read-modify-write (i-083), the
ownership-scoped lookup, the revocation clear (i-085) and the both-actors
response are the REST route's, not a second implementation.

**`review_kind(kind, scope?, tenant?)`** — model-visible, carries the card. Reads
`get_authored_kind_impl`: the roster's own projection **plus the schema** and the
traits. The card shows the schema (pretty-printed JSON in a `Code` block), both
(all three) actors, a sentence saying what the current state costs, and the
button. `list_my_kinds` deliberately does **not** grow a button: a row button is
pressed against a schema the reviewer has not seen, which is the i-076 hole.

The button is shown only where it changes something: on `unapproved` and on
`revoked` (approving again is the documented one-act undo, and it says so —
"Approve again — restore this Kind"), never on `approved`.

**An envelope, and why.** `review_kind` returns `{"scope", "declaration"}`. Flat,
it collides: the projection's own `state` field (i-085) is also a Prefab wire
key, and `with_card`'s collision guard refused it — loudly, exactly as designed.
The envelope makes the collision structurally impossible for this field and every
future one, and costs no vocabulary (`declaration` holds
`_authored_kind_summary` unchanged).

---

## 5. How revoked renders

`kinds_app` now renders the core's own three-value `state` instead of a
two-value `status` derived from the `approved` boolean, plus a `Revoked by` /
`Revoked at` pair of columns and a **second headline badge** in the danger hue
counting the revoked rows.

Two facts kept apart, deliberately:

- the revoked count is **not** folded into the amber "awaiting approval" one —
  "1 awaiting approval" is a true sentence about a roster where nothing is
  awaiting anything and one Kind is refusing every write;
- `_STATE_VARIANT["revoked"] == "destructive"` ≠ `_STATE_VARIANT["unapproved"] ==
  "warning"`, asserted, because these are the *tightest* and the *loosest*
  states in the system and the boolean showed them as the same word.

**The fallback that was refused.** `_state_of()` reads `state` and never derives
it. "No `state`? fall back to `approved`" would print `unapproved` over a revoked
row — `approved: false` is true of both — and it would look completely fine. That
is the exact shape of the most recent bug this project shipped, so an unknown or
missing state renders the em dash instead, and `_STATE_VARIANT` is a closed map
so a *fourth* state fails visibly rather than painting itself grey. Pinned by
`test_the_state_cell_is_never_derived_from_the_boolean`.

The review card carries the same discipline: `revoked` gets its own line, its own
badge hue, and a `meaning` sentence that states what revocation does to documents
*and* that nothing was deleted.

**Fixture note (deliberate, and the sentence the suite forbids is respected).**
`payloads.json`'s `list_my_kinds` had drifted from its own impl — i-085 added
`state`/`revoked_by`/`revoked_at` to `_authored_kind_summary` and the fixture
never grew them, so the card was being proven against a shape the tool can no
longer return. It was updated to the real 13-field shape with a third, revoked
row, and `review_kind` was added. The two `.content.txt` baselines were re-frozen
by running the payload through a **bare** FastMCP tool (no `app=`, no
`with_card`) — the pre-card path itself, not the path under test — and the
procedure was validated by reproducing the two **untouched** baselines
(`list_stories`, `sdlc_digest`) **byte for byte** first. Re-freezing through
`with_card` would have made the byte-identity test tautological.

---

## 6. Suite results

```
packages/cli   : 1360 passed, 19 skipped          (uv run --no-project pytest tests -q)
packages/sdk-py: 4450 passed, 234 skipped, 4 xfailed, 2 FAILED
```

Both sdk-py failures are **pre-existing and environmental**, proven by stashing
every change on this branch and re-running them (`2 failed in 10.47s` on the
untouched tree). `git diff --stat` also shows **zero** files changed under
`packages/sdk-py/`.

| test | cause |
|---|---|
| `tests/test_emit_agent_framework.py::test_emitted_yaml_loads_into_agent_framework` | `TypeError: PropertySchema.__init__() got an unexpected keyword argument 'required'` — third-party `agent_framework` serialization drift. |
| `tests/runtime/test_langchain_adapter.py::test_attach_registers_the_agui_route` | `ModuleNotFoundError: No module named 'ag_ui_langgraph'` — optional dep absent even under `uv sync --all-extras`. |

Repo guards: `scripts/brand_guard.py` → clean. `scripts/docs_coverage_guard.py`
→ clean (100 public items, 47 prose pages). No raw `yaml.safe_load` added; no
test under `packages/sdk-py/tests/` added or touched; nothing vendor-specific in
`packages/sdk-py` or `packages/cli`.

Docs: `docs/guides/mcp-server.md` rewritten — the "There is deliberately no
`approve_kind` tool, and there will not be one" paragraph is replaced by the
mechanism that now buys the same rule, including whose enforcement `visibility`
is and what the residual risk is.

---

## 7. Concerns

1. **The residual is a third party's.** Nothing in this repo can prove a host
   honours `visibility`. An incomplete host puts `approve_kind` in the model's
   list and the model can approve. The mitigations are the ones the brief
   accepted (revocation, two verified actors, a UI-blind client not being handed
   the tool at all), and they are mitigations, not a fence.
2. **FastMCP does not filter this shape from `tools/list`**, and its own source
   says its filtering of the other shape is *not* spec-correct. We rely on the
   spec's reading, which is also FastMCP's stated intent. If a future FastMCP
   starts hiding `AppConfig(visibility=["app"])` tools from `tools/list`, the
   card's `callServerTool` by display name would break — `get_tool()` already
   returns `None` for *backend* app-only tools today. Worth watching on a bump.
3. **`approve_kind` resolves the workspace server-side and the button passes
   only `kind`.** On a `--auth none` stdio self-host nothing resolves a tenant,
   so the button would refuse in words. That is the same behaviour `author_kind`
   already has on that lane, and the alternative (a tenant the card names) is
   the thing this face exists not to do.
4. **No SDLC story was opened.** `AGENTS.md` asks for one before non-trivial
   work; the brief said no PR and named its own deliverables, so no board
   document was invented and the commits carry no `Work-Item:` trailer.
