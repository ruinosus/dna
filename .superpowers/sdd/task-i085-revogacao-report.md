# i-085 — revocation is a mechanism now

Branch `feat/i-085-revogacao`, worktree `/Users/jefferson.barnabe/projects/dna-wt-revoke`.
Three commits, no PR, no version bump.

Venvs set up fresh in the worktree (the main checkout's were never touched):

```bash
cd packages/sdk-py    && uv venv && uv pip install -e ".[dev]"
cd packages/cli       && uv venv && uv pip install -e ../sdk-py -e ".[dev]"
cd packages/client-py && uv venv && uv pip install -e . -e ../sdk-py -e "../cli[api]" pytest
cd packages/client-ts && bun install

# running them
cd packages/sdk-py    && uv run --no-project pytest tests -q --timeout=120
cd packages/cli       && uv run --no-project pytest tests -q
cd packages/client-py && uv run --no-project pytest tests -q
cd packages/client-ts && bun test && bun run typecheck
```

---

## 1. The loosening trap — RED/GREEN, measured on the real codebase

The founder's discovery had to be proved before it could be defended against, so
the first thing written was the mutant: **revocation implemented as a plain
un-approval**, i.e. rewriting the `KindDefinition` with `approved_by` dropped and
nothing else. That is exactly what "revoking is the inverse of approving" means
in code, and it needs no code change at all — it is reachable today.

Setup: a `Widget` Kind with a schema that has something to violate
(`required: [size]`, `size: string`, `additionalProperties: false`). The
violating document is `{"size": 42, "unexpected": true}`. Every "did this take
effect?" probe runs on a **fresh kernel** over the same store.

**RED (mutant).** Control first — while APPROVED, the violating document is
refused with `SpecValidationError`. Then un-approve, boot fresh, write the same
document:

```
    async def still_refuses_after_revocation(fresh):
>       with pytest.raises(SpecValidationError):
E       Failed: DID NOT RAISE SpecValidationError

WARNING dna.kernel.kinds.registry: Kind 'Widget' in scope 'test-scope' is
        authored but not approved — parsed, not registered.
```

The document the approved Kind refused is **accepted**. Un-approving does not
close the gate, it switches it off. (A second run of the same mutant with the
assertions in the other order showed the cause directly:
`kind_port_for("Widget") is None` — the Kind is simply gone.)

**GREEN.** With the third state implemented, the same test asserts
`kind_port_for(...) is not None` *and* `pytest.raises(RevokedKindWrite)`, and
passes. The type is asserted exactly, not by its base: `RevokedKindWrite` and
`SpecValidationError` are both `ValueError`, so matching the base would have
gone green on the mutant's behaviour whenever the schema happened to still bite.

**The trap has a second door**, found while building the application layer:
`author_kind_impl` rebuilds the spec from scratch and persists it, deliberately
dropping `approved_by` (an edit changes the shape a human signed). Dropping
`revoked_by` the same way is perfectly symmetric and is the identical loosening —
an *edit* would un-revoke a Kind straight into the permissive row. So an edit
withdraws the approval and **carries the revocation forward**; only the approval
door clears it. Mutant D1 below is that door.

---

## 2. How the revoked state persists, and why that shape

`spec.revoked_by` + `spec.revoked_at` on the `KindDefinition`, beside
`proposed_by`/`approved_by` — each field carrying the verified identity of its
own act, which is the convention this document already had. Clearing
`approved_by` is byte-identical to never having approved (asserted directly), so
the fact had to be stored.

The founder's worry was that this becomes *one more field somebody forgets to
read*. Two things prevent it, and neither is discipline:

1. **One reader, returning a state rather than a field.**
   `dna/kernel/kinds/approval.py::approval_state(spec)` → `unapproved` |
   `approved` | `revoked`. There is no way to ask "is it approved?" that
   silently answers yes for a revoked Kind, because nothing reads `approved_by`
   directly any more. It accepts both shapes the funnels hold (raw dict and the
   typed dataclass), and a non-string names nobody — `revoked_by: true` does not
   revoke, the same rule `approved_by` already had.
2. **Downstream, nobody reads the document at all.** The registration funnel
   turns the state into a fact **on the registered port** (`__revoked__`,
   alongside the existing `__scopes__` / `__declarative__` / `__builtin_descriptor__`
   markers), read through `port_revoked(port)` — the sibling of `applies_to`. The
   registry is the surface the write pipeline, storage routing, parsing and the
   `ManifestInstance` *already* consult, so every one of them is one attribute
   away and no new call site exists to forget.

**A revoked Kind stays REGISTERED.** That is the counter-intuitive core: being
known is the mechanism, because unregistered is the permissive state.

**Mutual exclusion is maintained by the two acts, never by comparing
timestamps.** Approving clears the revocation; revoking stamps it and leaves
`approved_by` standing (the audit must keep who conferred effect in the first
place). Ordering `approved_at` against `revoked_at` would make the current state
depend on caller-supplied strings from possibly-skewed clocks in possibly-different
formats — a state machine arbitrated by data nobody validates.

Clearing is done by **removing** the keys, not writing `null`. Measured: the
`KindDefinition` port's schema is derived from the typed spec dataclass and
`str | None` derives to `{"type": "string"}`, so an explicit null vetoes the
approval at the write path (`spec.revoked_by: None is not of type 'string'`).

Revocation also **reaches an already-registered Kind without a restart** — the
issue's own trigger — and by the mechanism that was already there rather than a
new one: the markers live in `spec`, so they change the descriptor digest, and
the existing "different digest → replace the port in place" branch (i-080 item 3)
swaps the approved port for the revoked one on the next load.

---

## 3. What a read returns — and why no new surface

**There is no single read envelope to extend.** Measured, not assumed: the
kernel has three read shapes. `get_document`/`query` hand back **raw dicts**
(what every hosted face consumes); the sync wrappers and a `ManifestInstance`
hand back `Document`; `resolve_document` hands back `ResolvedDocument` — the only
real envelope, and the one nothing on a face's read path uses. A fourth shape
would have been seen only by code written to look for it, so the mark had to ride
**in** the document.

It rides as a top-level **`status`** key: the derived half of the Kubernetes
`spec`/`status` split that DNA's own one-line self-description already borrows,
and the half DNA had never used. Nothing needed inventing, and a reader who knows
CRDs needs no explanation of which half is authoritative.

```
status: {valid: false, reason: "kind_revoked", message: "the Kind …/Widget has
         been revoked, so this document is no longer valid. It is unchanged and
         still readable — nothing was deleted. Approving the Kind again restores
         its validity."}
```

- **The read returns the document, marked.** Never an error, never `None`, never
  a deletion. Asserted on content too: `spec.size == "large"` survives untouched.
- **Absent means "nothing to report", not "valid".** Only invalid documents are
  marked — stamping `valid: true` on every row would cost a dict copy per row on
  the hot path to carry no information.
- **It is derived, never a stamp.** Computed at read time from the registry, and
  `strip_derived_status` removes it on **every** write, so the read-modify-write
  pattern that is everywhere in the application layer (`{**raw, "spec": spec}`)
  cannot round-trip it into the store. Verified two ways: no `status:` in any
  YAML on disk after a deliberate round trip, and behaviourally — re-approve and
  nothing stale survives. This is what makes Decision 2 true with **nothing to
  migrate** in either direction.
- **Marked on a shallow COPY, never in place.** `get_document` serves from a
  bounded TTL cache; mutating would leave the mark on the cached object after
  re-approval — the exact stamp failure the module exists to avoid.
- All three read shapes agree: `Document` gained `.status` / `.is_valid`, and the
  `Document` test deliberately goes through the `ManifestInstance` path rather
  than `kernel.query`, or it would have re-asserted the raw-dict marking and
  passed with the `Document`-side marking deleted (mutant M5).

---

## 4. The query answer, and its consequence

**Rows APPEAR, marked. They never vanish.**

This was decided by measuring what the query path can express, not by taste:

- `limit` / `offset` are pushed **down** to the source, and `count()` is a
  *separate* push-down (`SELECT count(*)`). The revoked fact lives in the
  **registry**, not in any column, so it cannot be pushed with them.
- Filtering rows out after the push-down therefore hands back a page of 20 that
  renders 14 while `count()` still says 20. **"Vanish" is not implementable
  honestly on this path** — only approximately, and the approximation is a
  listing that disagrees with its own total. The test asserts exactly this:
  `len(after) == len(before)`, every row marked, and `count()["total"] ==
  len(rows)`.
- The third option — "it depends who is asking" — needs an authorization concept
  the vendor-neutral kernel does not have and must not grow: it knows nothing
  about approvers, reviewers or roles.

**The consequence, stated plainly.** Every listing surface has to learn to render
the mark, and one that does not will show a revoked Kind's documents as though
nothing happened. That failure mode is the status quo — *less alarming than the
truth, never less data*. The alternative would have made revocation a way to make
documents disappear without deleting them. Given a choice between a surface that
under-reports and a mechanism that can hide data, this takes the first.

**Not stopped for a product decision**, because it did not turn out to need one:
one option is unimplementable-honestly and one requires a concept the kernel is
forbidden to have. What *is* left open, and is genuinely product, is whether a
consumer-facing listing should hide invalid documents while an audit view shows
them — that needs an authorization concept and belongs above the kernel. Nothing
here forecloses it: the mark is present on every row, so a face can filter.

---

## 5. Every RED/GREEN pair

Each mutant was applied to the real source, the single named test run, and the
source restored. All fourteen went RED for the stated reason.

**Kernel (`tests/test_kind_revocation.py`, 14 tests)**

| # | Mutant | Test that went RED |
|---|---|---|
| M0 | revocation as a plain un-approval | `test_revoking_does_not_return_the_kind_to_accepting_anything` — violating doc **accepted** |
| M1 | `get_document` does not mark | `test_an_existing_document_reads_back_marked_never_erased` |
| M2 | `query` **hides** revoked rows instead of marking | `test_invalid_documents_appear_in_a_query_marked_and_never_vanish` |
| M3 | derived `status` not stripped on write | `test_the_mark_is_derived_and_never_reaches_the_store` |
| M4 | the refusal obeys `DNA_WRITE_VALIDATION=off` | `test_the_refusal_ignores_the_write_validation_knob` |
| M5 | the `Document` shape does not mark | `test_the_document_shape_carries_the_same_verdict` |
| M6 | a revoked Kind is **dropped** from the registry | `test_revoking_does_not_return_the_kind_to_accepting_anything` |
| M7 | `revoked_by: true` counts as a revoker | `test_a_revoker_that_names_no_one_does_not_revoke` |
| M8 | the port is never re-stamped `__revoked__` | `test_revocation_reaches_an_already_registered_kind_without_a_restart` |

Also in that file, without mutants of their own (controls and decisions):
`test_approval_state_is_three_states_and_revocation_is_not_absence` (a plain
un-approval is byte-identical to never approving),
`test_a_never_approved_kind_still_accepts_anything` (**the control that keeps the
whole suite meaningful** — the permissive row is pinned, not fixed),
`test_an_approved_kind_validates_and_a_revoked_one_refuses_even_conforming` (a
*conforming* document is refused too — a revoked Kind is a withdrawn Kind, not a
stricter schema; asserting only on a violating document would have let a mere
tightening pass), `test_the_revocation_is_logged_loudly`, and
`test_a_revoked_kinds_documents_can_still_be_deleted` (refusing deletes would
trap exactly the documents a workspace may now want to clear out).

**Application door (`tests/test_revoke_kind_door.py`, 8 tests)**

| # | Mutant | Test that went RED |
|---|---|---|
| D1 | an **edit** drops the revocation (the trap in the authoring door) | `test_an_edit_cannot_un_revoke_a_kind` |
| D2 | approving does not clear the revocation | `test_approving_again_clears_the_revocation` |
| D3 | revoke writes unguarded (no `if_match`) | `test_revoking_a_document_that_changed_since_it_was_read_is_refused` |
| D4 | revoking **erases** the approval | `test_revoking_stamps_the_revoker_and_keeps_the_approval` |
| D5 | the audit reports only the boolean | `test_the_audit_tells_revoked_apart_from_never_approved` |
| D6 | revocation accepts an unsigned actor | `test_revoking_records_a_verified_identity_or_refuses` |

Plus the two inherited refusals: a neighbour's Kind and a Kind nobody authored
are both 404, and the second creates nothing.

**REST (`packages/cli/tests/test_kind_approval_audit.py`, 4 new)** — over the
wire, probed on a fresh kernel: revocation leaves the port registered **and**
marked (not gone — gone is the loosening); re-approval clears it and the port
flips back; a Kind nobody authored is a 404 that creates nothing; a neighbour's
404 leaves the Kind **untouched** rather than revoking it anyway.

---

## 6. Suites

Baseline before any change: sdk-py **4394 passed**, cli **1328 passed**, both
clean. Neither of the two known pre-existing failures reproduced here (both are
skipped in this environment — the sdk-py one needs the embed extra, the cli one a
Postgres source), so there was no red to inherit and none was added.

Final:

```
packages/sdk-py     4417 passed, 237 skipped, 4 xfailed        (+23)
packages/cli        1332 passed,  19 skipped                   (+4)
packages/client-py    21 passed                                 (openapi drift + coverage)
packages/client-ts    16 pass, 0 fail  +  tsc --noEmit clean
```

Guards: `brand_guard` clean, `data_model_guard` clean, `docs_coverage_guard`
clean (100 public items), schema parity test green (both copies byte-identical,
sha `f806658…`), no raw `yaml.safe_load` added, no `dna_cli` import from
`packages/sdk-py/tests/`, no DNA-Cloud vocabulary in kernel or CLI.

Regenerated: `docs/openapi.json` (`scripts/dump_openapi.py`),
`packages/client-ts/src/schema.ts` (`bun run gen`),
`docs/reference/kinds/*` (`scripts/gen_kinds_docs.py`).

---

## 7. Concerns / left open

1. **Every listing surface must learn to render `status.valid == false`.** This
   is the accepted consequence of §4 and it is real work outside this repo — the
   portal's document lists, the Studio, anything that renders `kernel.query`
   rows. Until they do, a revoked Kind's documents render as before. That is
   under-reporting, never data loss, and it was chosen over the alternative.
2. **`custom_kinds` is weaker than `KindDefinition`, by construction.** Its ports
   are keyed `(apiVersion, kind)` with no per-scope port, so two scopes declaring
   the same custom Kind with different states cannot both be honoured and the
   last one loaded governs. That is the door's pre-existing shape, not a new
   compromise; it is documented in the method, and a workspace that needs its own
   answer authors a `KindDefinition`.
3. **No MCP tool for revoke, deliberately.** The MCP face has no `approve_kind`
   either — the issue's agreed order puts the conversational approve button (with
   `visibility: ['app']`) *after* this work. Adding a revoke tool now would put
   the undo on a surface whose do does not exist yet.
4. **No SDLC story was opened.** `dna sdlc story create` writes `.dna/` board YAML
   that is git-tracked and shared, another agent is active in the main checkout,
   and the task said no PR — so the commits carry `Refs: i-085` in the body
   instead of the `Work-Item:` trailer. If the trailer matters for
   `story commits`, a story can be opened and the branch re-stamped.
5. **`DNA_WRITE_VALIDATION` deliberately does not reach the revocation refusal.**
   That knob exists so an operator can bulk-load legacy data past a *shape* check;
   this is a workspace's decision about its own Kind. Worth knowing if someone
   later hits it during a migration and reaches for the escape hatch — the right
   answer there is to approve the Kind, load, and revoke again.
