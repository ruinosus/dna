# `spec.presentation` — one declaration of how a Kind's data reads

Branch `feat/kind-presentation`, worktree `dna-wt-present`. No PR, no version bump.

---

## 1. What the protocol already carried

`KindPresentation` (`dna/kernel/protocols.py`) was already the typed home for the
optional presentation surface, and four of its members are about how a Kind reads:

| member | what it already answered |
|---|---|
| `display_label` | the Kind's plural human label ("Stories") — declared by ~15 descriptors |
| `ascii_icon` | one glyph for compact views |
| `graph_style` | fill/stroke/text colours for mermaid graphs |
| `description_fallback_field` | which spec field stands in for a missing description |
| `ui_schema` | per-field **form** hints: `widget`, `label`, `help`, `language`, `height`, `order` |
| `docs`, `visible_in_backend`, `preview()`, `graph_meta()` | the rest of the surface |

Beside them, off the protocol but on the descriptor: `summary` (a list-endpoint
projection, `{field: default}`) and `describe` (a per-doc one-liner template).

So the Kind could already say *what it is called*, and *which fields a list
projects*.

## 2. What a card and a screen need that none of that carried

Measured against the four cards and `list_stories_impl`, four things were missing
and were consequently spelled out per surface:

1. **a per-field human label for a READ.** `ui_schema[f].label` exists, but it is
   documented and consumed as a Studio *form* hint — the edit direction. Nothing
   labelled a column.
2. **field order for a read.** `ui_schema[f].order` is a form order; `summary`'s
   key order is incidental.
3. **which field is the headline / the identifier.** Nothing.
4. **which field is the status, and which fields are machinery.** Nothing.

The drift was not hypothetical. `list_stories_impl` projected
`name/title/status/feature/priority`; `stories_app` restated the same five as
columns — and had already diverged on the first one, heading it **"Story"** where
the impl called the field **`name`**. Two descriptions of one thing, nothing
reconciling them.

## 3. What was added, and why it belongs on the Kind

One new member: **`presentation`** (`dna/kernel/kinds/presentation.py`).

```yaml
presentation:
  fields:
  - {field: name,     label: Story, role: identifier}
  - {field: title,                  role: title}
  - {field: status,                 role: status}
  - {field: feature,  label: Feature, role: parent}
  - {field: priority,               role: rank}
  hidden: [created_at, updated_at, closed_at]
```

Shorthand: `presentation: [name, title, status]` (mirrors `summary`'s list form).
An undeclared label is derived — `spec_refs` → `Spec refs`.

`role` is a **closed** vocabulary of eleven words, each evidenced by a field a Kind
in this repo already carries: `identifier, title, subtitle, status, owner, parent,
rank, tag, timestamp, metric, body`. The first four may be declared at most once.

### The line, and where I put it

**On the Kind** — reading order, human label, semantic role, hidden fields. These
are facts about the data and are true on every surface.

**On the surface** — that the roster is a table at all, that every column sorts,
that it paginates at ten, that it offers search, that `status` renders as text
rather than a badge, and the sentence shown when it is empty. None of that is
declared anywhere in the schema.

The failure mode named in the brief — *a schema that says how a card looks* — is
guarded structurally, not by convention: unknown keys are **refused**, so `width`,
`column`, `variant`, `widget` and `colour` cannot arrive later as a de-facto
extension. There is a test for exactly those five words.

The clearest statement of the split: the Story Kind declares `role: status`, and
the card deliberately renders it as **plain text**. The status *value* vocabulary
is open (any workflow defines its own words), so a colour map would be either
incomplete or invented. The Kind saying "this field is my state" does not oblige a
surface to paint it — and this surface declines. That is the line working.

`hidden` is the one entry that could be argued onto the surface. It is on the Kind
because "`updated_at` is a write stamp, not information" is a fact about the field,
not about the screen.

`ui_schema` was deliberately not extended. It answers how a human **edits** a
field; this answers what the value **means** when a human **reads** one. They
overlap on `label` only, and folding a read vocabulary into a permissive,
untyped, form-owned bag would have made both harder to trust.

### Where it lives

- `KindPresentation.presentation` (typing-only, **never** on the runtime_checkable
  `KindPort` — the `is_runtime_artifact` precedent; there is a ratchet).
- `KindBase.presentation = None` — absence is meaningful, surfaces fall back.
- `KindDefinitionSpec.presentation`, normalized in `from_raw`.
- `DeclarativeKindPort.presentation`, same attribute name, so one `getattr` reads
  a descriptor Kind and a hand-written one.
- Both copies of `kind-definition.schema.json`, byte-identical (there is a test).
  The role `enum` in the schema is asserted equal to the normalizer's frozenset —
  two lists that drifted would let a document validate and then fail to load.

## 4. How a TENANT Kind declares it

Identically. `KindDefinition.spec.presentation`, same words, same normalizer, same
port attribute. Wired end to end:

- `author_kind_impl(..., presentation=)` — validates and stores the **declaration**
  form (`to_declaration()`, which omits a null role and an empty `hidden`, because
  the schema's own role enum would reject a null).
- MCP `author_kind(presentation=...)` — the tool docstring teaches the shorthand,
  the full form, and states that colour/column/width are *not* declarable.
- REST `POST /v1/kinds` — a malformed declaration is a **400 naming the offending
  key**, at the door, not a card that breaks later in front of a user.
- `GET /v1/kinds/{kind}` returns `presentation` beside `schema` and `traits`, in
  the wire envelope (`{label, icon, fields, hidden}`), composed with the document's
  own `display_label`/`ascii_icon`. `null`, never `{}`, for a Kind that declares
  none — and also for one whose stored declaration no longer normalizes, because
  "this Kind declares no reading I can read" beats a 500 on the review screen.
- `docs/openapi.json` regenerated; `client-ts/src/schema.ts` regenerated;
  `client-py` `author_kind(presentation=)` + docstrings updated. Drift test green.

## 5. Card content: derived vs. still surface-specific

### Derived from the Kind now

| card | what became derived |
|---|---|
| `list_stories` | **every column, its order, its heading**, the card's title and glyph, the empty-state wording, and the sort keys (grouped by the field the Kind *calls* its status, broken by the one it calls its identifier). `list_stories_impl` projects the rows from the same declaration, so the impl and the card can no longer disagree. |
| `review_kind` | a new block: *"documents of this Kind will read as X, in this order"* — the reviewed Kind's own field/label/role rows plus its hidden set. The approval confers how documents read exactly as it confers what they may contain; only the second half was visible before. |

`stories_app` is now three lines delegating to a new generic **`documents_app`**.

### Still surface-specific, and correctly so

- **`sdlc_digest`** — not a projection of one Kind. It is a computed dashboard over
  many (a RAG verdict, counts, heterogeneous attention buckets whose *reason* lives
  in a different field per bucket). There is no Kind whose presentation could
  describe it, and inventing one would be the layout language by another route.
- **`list_my_kinds` columns** — `proposed_by`, `approved_at`, `revoked_by`, `state`
  are facts about the **approval act**, not about any Kind's data. They belong to
  the audit surface.
- **`kind_review_app`'s three headings** ("Reads as" / "Field" / "Means") — they
  describe *the declaration itself*, not a Kind's data.
- **Table-ness, sortability, pagination, search, the em-dash for a missing value,
  and status-as-text** — the surface's decisions throughout.

### The measure

`documents_app` is generic: `test_a_new_kind_gets_a_usable_card_with_no_new_card_code`
renders a tenant's `Contrato` — Portuguese labels, its own order, its own heading,
its own empty state — through the same builder. No branch in `_mcp_cards.py` knows
the word.

## 6. The provenance tests

The brief's false green: *asserting a card renders "Status" passes whether the
label came from the Kind or from a literal in the builder* — which is exactly what
it was. Every test below **changes the declaration and requires the output to
change with it**.

| test | what it proves |
|---|---|
| `test_list_stories_projects_the_fields_the_kind_declares` | re-declares Story's presentation on the live port (different fields, different order, `label: Fichas`) and asserts the payload follows. A hardcoded projection cannot pass. |
| `test_the_story_cards_columns_come_from_the_kind` | same rows, two declarations → two different column sets, orders and headings, read off the wire the host receives (the view tree is walked; the builder's locals are never inspected). |
| `test_a_new_kind_gets_a_usable_card_with_no_new_card_code` | a Kind nothing in the repo has heard of renders correctly. |
| `test_the_review_card_shows_how_the_kinds_documents_will_read` | the review card's rows are the reviewed Kind's declaration. |
| `test_a_tenant_authors_a_presentation_and_reads_it_back` / `..._full_declaration_survives_the_round_trip` | REST round trip: the shorthand goes in, the fully normalized form comes back — labels derived, role slot present — rather than echoed. |
| `test_a_layout_word_in_a_tenants_presentation_is_a_400_not_a_broken_card` | `width` and role `badge` are 400s naming the key, and nothing was written. |
| `test_a_payload_with_no_presentation_still_renders_every_column` | the fallback is not a blank table. |
| `test_presentation_is_a_capability_never_a_requirement` | the H1 ratchet. |

**Watched failing.** The new SDK suite first failed on `ModuleNotFoundError` for
the module that did not exist. Then, with the module in place, the four
Story-facing tests were re-run with `runtime.py` and `story.kind.yaml` stashed out
and failed for their stated reasons (`KeyError: 'presentation'`, missing
declaration) before being restored. The six card tests were written and watched
failing (`headers == ["Story","Title","Status","Feature","Priority"]` where the
Kind said `["Story","Status"]`; `KeyError: 'has_presentation'`; no `documents_app`)
before `_mcp_cards.py` was touched.

## 7. Constraints

- **Vendor-neutral** — `scripts/brand_guard.py`: clean.
- No `packages/sdk-py/tests/` file imports `dna_cli`.
- **No new colour anywhere.** `documents_app` reuses the existing `dna-mark` /
  `text-muted-foreground` classes; the `HOST_DESIGN_TOKENS` vocabulary is
  untouched, so the drift test and the contrast measurements stand unchanged.
- YAML read through `dna._yaml.safe_load` (the loader ratchet).
- Regenerated: `docs/openapi.json`, `client-ts/src/schema.ts`,
  `docs/reference/kinds/{index,composition}.md` (`gen_kinds_docs.py`),
  `docs/reference/data-model.md`, `docs/reference/cli/`. Guards clean:
  `brand_guard`, `data_model_guard`, `docs_coverage_guard`,
  `dump_openapi.py --check`. Prose added to `docs/guides/add-a-kind.md` §7.
- Golden re-frozen in the same change: `tests/golden-fixtures/port-surface.json`
  gains the `presentation` member of the `KindPresentation` port.
- Generated `uv.lock`s deleted.

## 8. Where I stopped, and why

**`list_documents` did not get a card.** It is the tool where "any Kind, no new
card code" would be literally true, and I left it alone on purpose: its projected
rows travel in the kernel's own shape (`{"name": …, "spec": {…}}`, not flat), and
its docstring makes an explicit promise that `fields=None` returns byte-identical
results. Wiring a roster card needs a flattening decision about the query contract
that is a separate change with its own risk, not a rider on this one.

**The REST face has no route for a REGISTERED Kind's presentation.**
`GET /v1/kinds/{kind}` — the route the brief named, and the one now carrying
presentation — serves **tenant-authored** `KindDefinition` documents only. There is
no `/v1/...` route that returns a builtin Kind's schema or presentation at all, so
a portal rendering a *Story* roster cannot read Story's declaration over REST; it
reads it out of the `list_stories` payload, which is what the card does. Closing
that means a new public route with its own auth and plan-gating decisions, which
the brief did not ask for and I did not invent.

**One builtin descriptor declares `presentation` (Story).** Enough to prove the
path end to end with a real Kind and a real card; extending it to the other ~90 is
mechanical and blast-radius-free, and each one is a small editorial judgement about
what its fields mean, which is better made per-Kind than in a sweep.

**Nothing about layout was declared.** No sections, no columns, no widths, no
colours, no variants, no widgets — and the schema refuses them by name.

## 9. Suites

- **`packages/sdk-py`** — `4498 passed, 244 skipped, 4 xfailed, 2 failed`.
  Both failures **pre-existing**, reproduced on a clean tree with the whole change
  stashed (`git stash push -u`):
  - `tests/runtime/test_langchain_adapter.py::test_attach_registers_the_agui_route`
    — `ModuleNotFoundError` at `dna/runtime/adapters/langchain_rt.py:63`.
  - `tests/test_emit_agent_framework.py::test_emitted_yaml_loads_into_agent_framework`
    — `dotnet/app-launch-failed` in this environment.
- **`packages/cli`** — `1369 passed, 19 skipped`, zero failures.
- **`packages/client-py`** — `21 passed` (includes the OpenAPI drift guard).
- **`packages/client-ts`** — `16 pass`, `tsc --noEmit` clean.
