# i-088 — `delete_document` checked existence at the wrong coordinates

Branch `fix/i-088-delete-tenant` (worktree `/Users/jefferson.barnabe/projects/dna-wt-delete`).
No PR, no version bump.

## The reproduction, with its real error

Before any change, against three real stores — the filesystem writable source
and BOTH dialects of the SQL adapter — a document of a tenant-authored Kind
(`ProbeCheck`, namespace `ws-deadbeefcafe.dna.local/v1`, alias
`ws-deadbeefcafe-dna-local-probe-check`, approved and registered) was written
through `write_document_impl` with `tenant="ws-000000000000000000000001"`:

```
[FS]     WRITE tenant: ws-000000000000000000000001   LIST: [{'name': 'c1'}]   GET ok: c1
         DELETE FAILED: UnknownDocumentError ProbeCheck 'c1' not found in scope 'probe-scope' — nothing to delete
[sqlite] WRITE tenant: ws-000000000000000000000001   LIST: [{'name': 'c1'}]   GET ok: c1
         DELETE FAILED: UnknownDocumentError Agent 'a1' not found in scope 'probe-scope' — nothing to delete
[pg]     WRITE tenant: ws-000000000000000000000001   LIST: [{'name': 'c1'}]   GET ok: c1
         DELETE FAILED: UnknownDocumentError ProbeCheck 'c1' not found in scope 'probe-scope' — nothing to delete
         DELETE FAILED: UnknownDocumentError Agent 'c1' not found in scope 'probe-scope' — nothing to delete
```

The reported error, verbatim, on every store — and reproduced with a **builtin**
tenanted Kind (`Agent`) as well as the tenant-authored one, which is what proves
this was never anything peculiar to store-loaded Kinds.

**Cause** (`packages/sdk-py/dna/application/documents.py`): `delete_document_impl`'s
existence check read `get_document(sc, port.kind, name)` — no tenant — while the
delete two statements below targeted `tenant=write_tenant`, and the write that
created the row had used `write_tenant` too. The tenant participates in the lookup
key of every store:

* `SqlAlchemySource._load_one_on` builds `tenant_candidates = [tenant, None] if tenant else [None]`
  — reading with **no** tenant probes the base row **only**, so a tenant-overlay
  row is invisible to it (and on Postgres `tenant` is in the `documents` primary
  key besides);
* `FilesystemSource.load_one` consults the `("tenant", X)` layer first and only
  then the base — with no tenant it never looks at the overlay directory at all.

So the check queried a coordinate the row was never at, and the one operation
that could remove the document was the only one that could not see it.

**Fix:** the check reads at `write_tenant` — the exact coordinates the delete
will act on. Same one-line shape at both sites, plus the comment that says why.

## The `GLOBAL`-Kind twin — verdict: real asymmetry, benign today, aligned anyway

`write_document_impl` checked with `tenant=tenant` and wrote with
`tenant=_write_tenant(port, tenant)`, which is `None` for a `GLOBAL` Kind.

**Measurement (both stores, `Story` — a `GLOBAL` Kind):**

```
[FS] Story scope decl: global
[FS] get(tenant=WS) is not None: True; get(tenant=None) is not None: True; same: True
[PG] Story scope decl: global
[PG] get(tenant=WS) is not None: True; get(tenant=None) is not None: True; same: True
```

and

```
kernel REFUSED tenanted write for global kind PlanBinding:
TenantNotAllowed: Kind 'PlanBinding' is GLOBAL — must NOT pass a tenant.
```

Two facts, together: (1) `get_document(tenant=X)` on a `GLOBAL` Kind falls back to
the base layer and returns a **byte-identical** document to `get_document()` — the
overlay probe simply misses; (2) `WritePipeline._resolve_tenant_arg` raises
`TenantNotAllowed` for **any** effective tenant on a `GLOBAL` Kind (explicit kwarg
or `Kernel.tenant` binding), so no overlay row can exist for the check to find.
Hence the asymmetry has never produced a wrong answer — which is why it was
latent rather than reported.

It was **aligned anyway** rather than merely commented, because the equality is a
property of today's *declarations*, not of the code: a Kind whose declared scope
changes from tenanted to `GLOBAL` (a re-authored `KindDefinition`) leaves real
tenant rows behind, and the old reading would then have merged one of them into
the shared base every tenant inherits — a silent promotion, in the write path.
Substituting `write_tenant` is a provable no-op for every Kind today
(`write_tenant == tenant` for tenanted Kinds; measured identical for `GLOBAL`
ones) and closes that window. Three tests lock the measurement itself in place so
nobody has to re-derive it, and the comment at the call site records it.

## Neighbours audited

Every existence-check-then-act in the SDK and CLI, checked for "does it read at
the coordinates it will act on":

| Site | Verdict |
|---|---|
| `documents.py` `write_document_impl` | **fixed** (the `GLOBAL` twin above) |
| `documents.py` `delete_document_impl` | **fixed** (i-088) |
| `documents.py` `get_document_impl` / `list_documents_impl` / `list_kinds_impl` | no check-then-act — clean |
| `runtime.py` `revert_definition_impl` (:464) | no pre-check; deletes at `tenant=tenant` — clean |
| `runtime.py` `set_member_role`-style write (:1187) | reads `tenant=tenant`, writes through `kernel.with_tenant(tenant)`; the pipeline resolves the same effective tenant — clean |
| `runtime.py` `remove_member_impl` (:1248) | no pre-check at all — acts and interprets the adapter's own `not_found`. The strongest form of the principle |
| `runtime.py` `invite_workspace_member` (:2043), `revoke_workspace_scope_impl` (:3219), `revoke_workspace_member` (:3062), workspace-create compensations (:2732/2769/2775) | `Workspace*` Kinds are `GLOBAL`; check and act both untenanted — clean |
| `runtime.py` `ensure_workspace_scope_genome` (:2504) | `Genome` is bootstrap/`GLOBAL`; both untenanted — clean |
| `runtime.py` bundle-entry plane (`write_/revert_/list_/read_bundle_entry_impl`, `reconcile_forks_impl`) | `revert` has no pre-check; `write`'s LayerPolicy gate is evaluated at `("tenant", tenant)` — the same layer the write targets — clean |
| `kind_authoring.py` (:262, :579, :708, :933) | `KindDefinition` is `GLOBAL`+bootstrap; reads and writes both untenanted — clean |
| `sdlc.py` `set_status` (:780) / `comment` (:861) | the board Kinds are `GLOBAL`; check and write both untenanted (the module docstring says so explicitly) — clean |
| `extensions/sdlc/write_guards.py` (:47), `extensions/guardrails/write_guards.py` (:112) | both read at `ctx.tenant`, the write's own tenant — clean |
| `memory/verbs.py` (:292) | reads base at `tenant=None` *deliberately*, as the question ("did this item come from the personal overlay?"), against a merged read at `tenant`. Not a check-then-act — clean |
| `cli/_ctx.py` `delete` (:337), `cli/_rest_api.py` `delete_memory_impl` (:204) | no pre-check; both act through a tenant-bound kernel and map the store's `not_found` to 404 — clean |

`kernel.delete_bundle_entry` (filesystem + SQL) returns "existed" from the same
statement that performs the delete — check and act are one operation, so it has
no coordinate to get wrong.

Nothing else needed fixing.

## RED / GREEN

New: `packages/sdk-py/tests/test_delete_document_tenant_coordinates.py` — one
kernel fixture parametrized over **filesystem / sqlite / postgres** (the pg lane
skips itself with a reason when no DSN is set), each with the tenant-authored
Kind seeded and registration asserted.

| Test | RED (before) | GREEN (after) |
|---|---|---|
| `test_delete_finds_the_document_the_tenant_write_created` [fs, sqlite, pg] | 3 × `UnknownDocumentError: ProbeCheck 'c1' not found in scope 'probe-scope' — nothing to delete` | pass |
| `test_the_quartet_agrees_on_one_document` [3 stores × {tenant-authored, builtin tenanted}] | 6 × same `UnknownDocumentError` | pass |
| `test_the_existence_check_reads_at_the_delete_coordinates` [3 stores] | 3 × failed — check read `tenant=None`, delete acted on `ws-…001` | pass |
| `test_a_global_kind_checks_and_writes_at_the_same_coordinates` [3 stores] | 3 × failed — check read `ws-…001`, write landed at `None` | pass |
| `test_a_base_document_is_still_deletable_without_a_tenant` [3] | passed (no-regression control) | pass |
| `test_a_tenants_delete_does_not_reach_another_tenants_document` [3] | passed for the wrong reason (every delete missed) | pass — now for the right one |
| `test_a_global_kind_can_never_have_a_tenant_row` [3] | passed (the measurement) | pass |
| `test_a_global_kind_resolves_the_same_document_at_both_coordinates` [3] | passed (the measurement) | pass |
| `test_a_global_kind_still_merges_and_deletes` [3] | passed (behaviour control) | pass |

```
RED:   15 failed, 15 passed
GREEN: 30 passed
```

**The fake that hid it.** `tests/test_generic_delete.py`'s `_Kernel` keyed its
store on `(scope, kind, name)` and its `get_document` took **no `tenant` kwarg at
all** — the coordinate the defect confused was not represented, so all eleven
tests in that file were structurally incapable of failing on it. Four of them
raised `TypeError: _Kernel.get_document() got an unexpected keyword argument
'tenant'` the moment the fix passed one, which is the fake admitting what it had
been modelling. Re-keyed to `(scope, kind, name, tenant)` with a comment pointing
at the end-to-end file; 11 passed.

## Cross-adapter coverage

Reproduced and fixed on all three. Postgres is the only dialect whose `documents`
primary key carries `tenant` (sqlite's does not — i-092), but the tenant is in the
`WHERE` clause of **both** SQL dialects and selects the layer directory on the
filesystem, so all three exhibited the bug. The pg lane ran here against a
throwaway schema on a local Postgres; with no DSN configured it skips with an
explicit reason via the suite's `requires_postgres` convention.

## Suites

Run from each package directory after `uv sync --all-extras` (the generated
`uv.lock`s were deleted, not committed).

**`packages/sdk-py`, hermetic (no DSN — what CI runs):**
`2 failed, 4470 passed, 244 skipped, 4 xfailed in 128s`

Both failures **pre-existing**, evidence by `git stash -u` + re-run on clean
`origin/main`, where they fail identically:
`tests/test_emit_agent_framework.py::test_emitted_yaml_loads_into_agent_framework`
and `tests/runtime/test_langchain_adapter.py::test_attach_registers_the_agui_route`
(`ModuleNotFoundError: No module named 'ag_ui_langgraph'` — an optional runtime
dependency absent from this machine).

**`packages/sdk-py`, with `DATABASE_URL` set (129 extra pg tests, incl. this fix's
pg lane):** `17 failed, 4599 passed, 100 skipped, 4 xfailed in 89s` — the same two
plus 15 pgvector/eventbus ones, all **pre-existing** and environmental:
stashed + re-run on clean `origin/main` they fail identically with
`asyncpg.exceptions.FeatureNotSupportedError: extension "vector" is not available`
(this Homebrew Postgres has no pgvector).

**`packages/cli`:** `1360 passed, 19 skipped in 122s` — clean.

## Constraints

Vendor-neutral (`scripts/brand_guard.py`: **clean**); no `dna_cli` import in the
new sdk-py test; no raw `yaml.safe_load` anywhere in it (the Kind fixtures are
seeded through `kernel.write_document`, so the test needs no YAML at all).
Nothing that `AGENTS.md`/`CLAUDE.md` names as generated is affected — the change
touches no Kind schema, CLI surface, REST route or data model, so
`gen_kinds_docs` / `gen_cli_docs` / `gen_data_model_docs` / `dump_openapi` have
no new output; the goldens and doc guards pass inside the suite above.
