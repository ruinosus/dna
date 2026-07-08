# Port Contract

The contract every adapter that implements `WritableSourcePort` must
honor. Verified by `python/tests/test_port_contract.py`, parametrized
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
| **`Versionable`** | `get_version(scope, kind, name, version_id) -> dict`. Per-Kind semver versioning (Phase 10 catalog flow). Adapters that don't support this should omit the method; the harness REST surface returns 501 instead of crashing. |

### When to add a new capability

Adding `MyCapability` is a 4-step process:

1. Define `MyCapability(Protocol)` with `@runtime_checkable` in
   `python/dna/kernel/capabilities.py`.
2. Replace any `hasattr(adapter, "method")` in the kernel/harness
   with `isinstance(adapter, MyCapability)`.
3. Document the capability here.
4. Cover it in `python/tests/test_port_contract.py` so adapters
   either implement it or get explicitly skipped.

### Round-trip

| Operation | Acceptance |
|---|---|
| `save_document(scope, "Module", scope, raw)` then `publish(...)` | Module appears in `mi.root` after `kernel.instance_async(scope)`. |
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
cd python && uv run pytest tests/test_port_contract.py -v

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
2. Add a builder in `python/tests/test_port_contract.py` next to
   `_build_fs_source`, `_build_sqlite_source`, `_build_postgres_source`.
3. Run `uv run pytest tests/test_port_contract.py -v` — every test
   should pass or skip explicitly.
4. If a test fails, fix the adapter, NOT the test. The test encodes
   the contract; mutating it amounts to lying about what the adapter
   supports.
