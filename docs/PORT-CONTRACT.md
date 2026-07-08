# Port Contract

The contract every adapter that implements `WritableSourcePort` must
honor. Verified by `packages/sdk-py/tests/test_port_contract.py`, parametrized
over `[FilesystemWritableSource, SqliteSource, PostgresSource]`.

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
| `kernel.write_document(scope, "Skill", name, raw)` then `publish(...)` | Skill appears in `mi.all("Skill")`. Bundle entries (e.g. `SKILL.md`) persisted via the source's backing store. |
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
| Per-tenant layer overlay | Filesystem ✓, Postgres ✓, SQLite ✓ (Phase 2c) |
| Versioning + immutable releases | Filesystem ✓, Postgres ✓ (Phase 10), SQLite ✓ |
| Lockfile install/update flow | Filesystem ✓, Postgres ✓ (Phase 10), SQLite (partial) |
| Cross-process cache invalidation (LISTEN/NOTIFY) | Postgres ✓ (Phase 15.1); FS uses in-process events; SQLite is single-process |

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

`python/tests/test_source_conformance_kit.py` runs the kit over ALL
in-repo adapters (FS read-only, FS writable, Composite, SQLite,
Postgres, AsyncSourceAdapter, S3-via-moto). A new in-repo adapter adds a
factory there; known divergences get an explicit `xfail`/`skip` with an
Issue id — never a silent green.
