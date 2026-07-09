# How to write a source adapter

The contract every adapter that implements `WritableSourcePort` must
honor. Verified by `packages/sdk-py/tests/test_port_contract.py`, parametrized
over `[FilesystemWritableSource, SqliteSource, PostgresSource,
SqlAlchemySource[sqlite], SqlAlchemySource[postgres]]`.

A new adapter is considered **production-ready** only when its row in
the contract test suite is fully green (all tests pass or skip
explicitly with a documented reason — never fail).

## Mandatory contract (every WritableSource)

### Capability Protocols (dna.kernel.capabilities)

| Capability | What it covers |
|---|---|
| **`KernelAttachable`** | `attach_kernel(kernel)` — accept post-init wiring of `_writers` + `_readers` from the kernel. Idempotent. Raises `TypeError` if `kernel` is not a `Kernel` instance. |
| **`BundleEntryReadable`** | `fetch_bundle_entry(scope, container, name, entry, *, tenant) -> bytes \| Awaitable[bytes]`. Returns single bundle entry bytes; raises `FileNotFoundError` on miss. Honors tenant overlay. |
| **`Versionable`** | `get_version(scope, kind, name, version_id) -> dict`. Per-Kind semver versioning (Phase 10 catalog flow). Adapters that don't support this should omit the method; callers should degrade gracefully (report the capability as unsupported) instead of crashing. |

### When to add a new capability

Adding `MyCapability` is a 4-step process:

1. Define `MyCapability(Protocol)` with `@runtime_checkable` in
   `packages/sdk-py/dna/kernel/capabilities.py`.
2. Replace any `hasattr(adapter, "method")` in the kernel
   with `isinstance(adapter, MyCapability)`.
3. Document the capability here.
4. Cover it in `packages/sdk-py/tests/test_port_contract.py` so adapters
   either implement it or get explicitly skipped.

### Round-trip

| Operation | Acceptance |
|---|---|
| `save_document(scope, "Genome", scope, raw)` then `publish(...)` | The root Genome appears in `mi.root` after `kernel.instance_async(scope)`. |
| `kernel.write_document(scope, "Skill", name, raw)` then `publish(...)` | Skill appears in `mi.documents` / `kernel.query(scope, "Skill")`. Bundle entries (e.g. `SKILL.md`) persisted via the source's backing store. |
| `kernel.fetch_bundle_entry_async(scope, kind, name, entry)` | Returns `bytes` for existing entries; `FileNotFoundError` for missing entries (consistent across all adapters). |

### Boot-time validation (kernel-level, propagates uniformly)

| Trigger | Outcome |
|---|---|
| Two `KindPort`s with the same `(api_version, kind)` tuple | `KindRegistrationError` from `kernel.kind(port)` |
| Two `KindPort`s with the same `alias` | `KindRegistrationError` from `kernel.kind(port)` |
| Two BUNDLE-pattern Kinds with the same `(storage.container, storage.marker)` and neither has `marker_shared_allowed = True` | `KindRegistrationError` from `kernel.kind(port)` |
| Reader missing `detect()` or `read()` | `ReaderRegistrationError` from `kernel.reader(r)` |
| Writer missing `can_write()` or `write()` | `WriterRegistrationError` from `kernel.writer(w)` |
| Extension missing `register()` callable | `ExtensionLoadError` from `kernel.load(ext)` |

## Optional capabilities (declare or skip explicitly)

These are NOT required for v1.0. An adapter may declare it doesn't
support them by raising `NotImplementedError` on the corresponding
method — the contract test then skips the case.

| Capability | Adapter coverage today |
|---|---|
| Per-tenant layer overlay | Filesystem ✓, Postgres ✓, SQLite ✓ (Phase 2c), SQLAlchemy ✓ (sqlite dialect inherits the i-092 PK debt) |
| Versioning + immutable releases | Filesystem ✓, Postgres ✓ (Phase 10), SQLite ✓, SQLAlchemy ✓ |
| Lockfile install/update flow | Filesystem ✓, Postgres ✓ (Phase 10), SQLite (partial) |
| Cross-process cache invalidation (LISTEN/NOTIFY) | Postgres ✓ (Phase 15.1), SQLAlchemy[postgres] ✓ (same outbox/channel); FS uses in-process events; SQLite is single-process |

## Using the SQLAlchemy adapter (s-sqlalchemy-source-production)

`SqlAlchemySource` (`dna/adapters/sqlalchemy_/`) is ONE adapter over
SQLAlchemy Core 2.x async that speaks BOTH SQL dialects and binds to the
**exact same tables and migrations** the raw adapters own:

| dialect | driver | tables | control table |
|---|---|---|---|
| `sqlite+aiosqlite` | aiosqlite | `documents` / `versions` / `bundle_entries` / `layer_documents` | `schema_migrations` |
| `postgresql+asyncpg` | asyncpg | `{schema}.dna_documents` / `dna_versions` / `dna_bundle_entries` / `dna_layer_documents` / `dna_outbox` / `dna_versions_seq` | `{schema}.dna_schema_migrations` |

Because the storage is byte-identical, **switching between a raw adapter
and the SQLAlchemy adapter is pure instantiation — zero data migration,
in either direction**. A DB touched by one is indistinguishable from a DB
touched by the other.

### Install

```bash
pip install "dna-sdk[sql]"   # sqlalchemy[asyncio] + aiosqlite + asyncpg
```

Nothing in the default install imports sqlalchemy (guard:
`tests/test_sqlalchemy_source.py::test_default_import_never_pulls_sqlalchemy`).

### Wiring

```python
from dna.adapters.sqlalchemy_ import SqlAlchemySource
from dna.kernel import Kernel

# SQLite — drop-in replacement for SqliteSource(db_path=...):
src = SqlAlchemySource("sqlite+aiosqlite:///path/to.db")

# Postgres — drop-in replacement for PostgresSource(pool, schema=...):
src = SqlAlchemySource(
    "postgresql+asyncpg://user:pass@host:5432/db", schema="public",
)

await src.connect()               # runs the dialect's migrations (idempotent)
kernel = Kernel.auto(source=src)  # or kernel.source(src) on an existing kernel
```

### Behavior parity notes

- **Eventbus (pg dialect):** every write emits the Phase 15.1 outbox row
  + `dna_versions_seq` checkpoint + `pg_notify('kernel_writes', …)` in
  the same transaction as the data write. The payload is produced by the
  raw `PostgresSource`'s builder (imported), so `PostgresEventBus`
  subscribers work unchanged. `supports_cross_process_invalidation` is
  `True` on pg, `False` on sqlite.
- **View cache:** `load_all`/`load_layer(tenant)` are memoized per
  (scope, tenant) with deep-copy returns — same as raw PG — and
  invalidated on local writes AND via `kernel.on_write` (attach_kernel).
- **Auto-publish:** like raw PG (and unlike raw SQLite), `save_document`
  is the publish point — the doc is visible in `load_all` immediately;
  `publish()` remains available for the explicit draft→publish flow.
- **Known inherited limit:** the sqlite dialect inherits i-092 (documents
  PK lacks `tenant` → a tenant overlay publish clobbers the base row) —
  it binds to the existing schema by design. The pg dialect passes the
  same case (tenant-aware PK): schema debt, not adapter debt.
- **Perf (bench: `packages/sdk-py/scripts/bench_sources.py`):** sqlite
  gains pooling for free (save ~5×, load_all/query ~3-100× faster than
  the raw per-connection adapter). On pg, reads are parity-or-better;
  writes/queries carry ~1-1.6 ms of Core statement-construction overhead
  per operation (save 7.7 vs 6.1 ms/doc, query 2.3 vs 1.4 ms) —
  documented, acceptable for the config-plane write path.

## Running the suite

```bash
# Filesystem + SQLite (always available)
cd packages/sdk-py && uv run pytest tests/test_port_contract.py -v

# Add Postgres (requires running DB)
DATABASE_URL=postgresql://dna:dna@localhost:5432/dna \
  uv run pytest tests/test_port_contract.py -v
```

Expected result: **all green** for FS + SQLite. Postgres tests skip
when `DATABASE_URL` unset; otherwise they must be green too.

CI gate: any PR that breaks the contract test for any adapter is
blocked from merge — that's the structural change that gives
confidence to ship the SDK.

## Adding a new adapter

1. Implement `WritableSourcePort` (mandatory) + `KernelAttachable` +
   `BundleEntryReadable` (capability Protocols).
2. Add a builder in `packages/sdk-py/tests/test_port_contract.py` next to
   `_build_fs_source`, `_build_sqlite_source`, `_build_postgres_source`.
3. Run `uv run pytest tests/test_port_contract.py -v` — every test
   should pass or skip explicitly.
4. If a test fails, fix the adapter, NOT the test. The test encodes
   the contract; mutating it amounts to lying about what the adapter
   supports.

## Writing a Source adapter (s-dna-source-conformance-kit)

The end-to-end recipe for a NEW Source adapter — the conformance kit is
your safety net at every step.

### 1. Declare the contract in the class statement

Python adapters subclass the port Protocol explicitly (chosen pattern —
readable, statically checkable, mirrors the TS `implements` clause):

```python
from dna.kernel.protocols import SourcePort, WritableSourcePort

class MyReadOnlySource(SourcePort): ...
class MySource(WritableSourcePort): ...
```

Caveat to keep straight: inheriting a Protocol makes `isinstance` pass
*nominally* and inherits the Protocol's no-op method stubs — it cannot
prove behavior. That's the kit's job (below). The one deliberate
exception is `AsyncSourceAdapter`: it's a transparent `__getattr__`
proxy that mirrors whatever it wraps, so inheriting would both shadow
the forwarding and overclaim; its conformance is structural.

If your storage client is synchronous (like `S3Source`/boto3), keep the
adapter sync and hand the kernel `AsyncSourceAdapter(your_source)` —
never the raw sync object.

### 2. Declare `capabilities()` honestly

Return a literal `SourceCapabilities` (see `kernel/capabilities.py`).
The kit's `capabilities_declared_honestly` case asserts your declaration
matches the reflection oracle (`derive_capabilities`) — a declaration
that overclaims or underclaims fails.

### 3. Pass the boot gate

`kernel.source(src)` validates the CORE surface by name
(`supports_readers`, `load_bootstrap_docs`, `load_all`, `resolve_ref`,
`load_layer`, `close`) and raises `SourceRegistrationError` naming
what's missing. The capability-mediated members (`list_doc_refs`,
`load_one`, `query`, `count`) may be absent — the kernel serves them via
`load_all` fallbacks and logs a warning; implement them for production
workloads. **The gate checks NAMES only** (`runtime_checkable`
semantics) — passing it does not mean the adapter works.

For test doubles: subclass `dna.testing.CoreSourceStub` so your
fake passes the gate without hand-rolling the core surface.

### 4. Run the conformance kit — the real safety net

The kit ships in the package (`dna.testing`), not in this
repo's tests — external adapter authors run the exact same battery:

```python
import pytest
from dna.testing import source_conformance_suite, FIXTURE_SCOPE, fixture_docs

async def my_factory():
    src = MySource(...)          # fresh instance, isolated env
    async def cleanup():
        await src.close()
    return src, cleanup

CASES = source_conformance_suite(my_factory)

@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
async def test_my_source_conformance(case):
    await case.run()
```

Rules of the kit:

- The factory is called once PER CASE (fresh adapter each time) and owns
  the environment: temp dirs / schemas, kernel wiring
  (`Kernel.auto(source=src)`) if the adapter needs it, and — for
  READ-ONLY adapters — pre-seeding `fixture_docs()` under
  `FIXTURE_SCOPE` in the native storage. Writable adapters are seeded by
  the kit through their own `save_document`/`publish` (part of the test).
- Cases are capability-aware: they SKIP (`CaseNotApplicable`) what you
  don't declare and FAIL what you declare but don't honor.
- Non-pytest consumption: `await run_source_conformance(my_factory)`
  returns a `ConformanceReport` (`.ok`, `.failed`, `.raise_if_failed()`).

### 5. Add your adapter to the in-repo matrix

`packages/sdk-py/tests/test_source_conformance_kit.py` runs the kit over
ALL in-repo adapters (FS read-only, FS writable, Composite, SQLite,
Postgres, AsyncSourceAdapter, S3-via-moto, SqlAlchemySource × both
dialects). A new in-repo adapter adds a factory there; known divergences
get an explicit `xfail`/`skip` with an Issue id — never a silent green.

## Schema migrations (SQL-backed adapters, s-dna-migration-contract)

An adapter that owns SQL storage manages its own schema through the
shared forward-only runner
(`dna/adapters/_migrations.py::run_migrations`). The contract:

- **Forward-only, numbered.** Migrations are a `Mapping[int, payload]`
  keyed by positive integer version, applied in ascending numeric
  order. **Downgrade is not supported** — recovery from a bad migration
  is backup/re-seed, never a `down()` script.
- **Append-only.** A migration that has ever shipped is frozen: never
  edit an applied version's payload — append a new version that fixes
  forward (see SQLite v8 rebuilding the v3 table, or Postgres v9
  adding the column v-earlier forgot). The control table records what
  ran; editing history would desynchronize every existing DB.
- **Automatic upgrade on boot.** `SqliteSource.connect()` /
  `PostgresSource.init()` run pending migrations before serving —
  deploying new code upgrades the store, no separate migrate step.
  Booting an up-to-date store applies nothing (idempotent re-boot).
- **Control table per adapter, name/shape frozen.** SQLite:
  `schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT)`.
  Postgres: `{schema}.dna_schema_migrations(version, applied_at)`.
  These predate the shared runner and MUST stay byte-compatible — a DB
  created by any older release re-boots clean on current code
  (locked by `tests/test_schema_migrations_contract.py`).
- **Older binary vs newer store** doesn't crash: unknown recorded
  versions are left untouched and logged as a warning.
- **Atomicity is the adapter's.** The runner owns ordering/skip/
  reporting; the adapter's `apply_version` callable owns "apply +
  record" with its dialect's semantics — Postgres wraps each version's
  statements + control-table insert in ONE transaction; SQLite runs
  `executescript` (which self-commits) then records.

### Adopting the runner in a third-party adapter

Give the runner three async callables bound to your storage and expose
the public entrypoint:

```python
from dna.adapters._migrations import run_migrations

MIGRATIONS: dict[int, str] = {1: "CREATE TABLE ...", 2: "ALTER TABLE ..."}

class MySource(WritableSourcePort):
    async def run_schema_migrations(self) -> list[int]:
        """Public entrypoint — also call it from your boot path."""
        return await run_migrations(
            MIGRATIONS,
            ensure_control_table=self._ensure_control_table,  # CREATE TABLE IF NOT EXISTS my_control(version, applied_at)
            fetch_applied=self._fetch_applied,                # -> versions already recorded
            apply_version=self._apply_one,                    # apply payload + record version, atomically for YOUR dialect
            dialect="MyStore",
        )
```

The conformance kit picks the capability up by duck-typing (same
pattern as `list_scopes`): an adapter exposing `run_schema_migrations()`
gets the `schema_migrations_idempotent` case — after boot, a re-run
must return `[]` (the control table survived in the backing store).
Adapters without SQL storage simply don't implement the method and the
case skips.

### TypeScript parity (honest state)

The TS SDK has **no SQLite adapter**; its `PostgresSource`
(`packages/sdk-ts/src/adapters/postgres/`) keeps its **own** migration
mechanism — `MIGRATIONS: Record<number, string[]>` in `migrations.ts` +
an inline `_runMigrations()` in `source.ts`. The *algorithm* matches
this contract 1:1 (same `dna_schema_migrations` control table, numbered
forward-only, one transaction per version wrapping statements +
record, `{schema}` placeholder, auto-run on first use); it has NOT been
rewritten onto a shared helper because TS has a single SQL adapter —
there is nothing to unify yet.

**Known cross-language divergence (do not share a schema between the
two SDKs):** the version *numbering streams* differ — e.g. Py v3 is the
tenant column/PK migration while TS v3 is a different tenant variant,
Py's `dna_documents.content` is `TEXT` vs TS `JSONB`, and TS ships only
v1-v4 (no outbox/edges/hot-field-index migrations). Same control-table
name + different meaning per number means pointing both SDKs at the
SAME Postgres schema is unsupported: each would try to "complete" the
other's history with conflicting DDL. One schema belongs to one SDK.
