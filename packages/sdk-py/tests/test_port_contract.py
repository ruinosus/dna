"""H4 — Cross-adapter Port Contract Test Suite.

The same set of assertions runs against every adapter. Catches
"adapter X silently missing capability Y" drift in CI — the kind of
bug that left SQLite without ``fetch_bundle_entry`` for a year.

Adapters parametrized:
  - ``FilesystemWritableSource`` (always runs)
  - ``SqliteSource`` (always runs, in-memory db)
  - ``PostgresSource`` (skipped unless ``DATABASE_URL`` is set)

Every adapter that implements ``WritableSourcePort`` must pass these
tests. Optional capability Protocols (``BundleEntryReadable``,
``KernelAttachable``) are tested separately so adapters can declare
they don't support them without the suite breaking — but a failure
here points to either a missing capability OR a bug in the
implementation.

Adding a new adapter:
  1. Add a builder fixture below.
  2. Add the builder to ``_source_factories``.
  3. Run ``pytest python/tests/test_port_contract.py -v`` — every test
     should pass or skip explicitly.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable

import pytest
import pytest_asyncio


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Source factories — one per adapter. Each yields (source, cleanup) tuples.
# ---------------------------------------------------------------------------


async def _build_fs_source() -> tuple[Any, Callable[[], Awaitable[None]]]:
    """Filesystem source rooted in a temp dir. Always available."""
    from dna.adapters.filesystem.writable import FilesystemWritableSource

    tmp = tempfile.mkdtemp(prefix="dna-port-contract-fs-")
    src = FilesystemWritableSource(base_dir=tmp)

    async def cleanup() -> None:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    return src, cleanup


async def _build_sqlite_source() -> tuple[Any, Callable[[], Awaitable[None]]]:
    """SQLite source on a temp .db file. Always available (aiosqlite is core)."""
    from dna.adapters.sqlite.source import SqliteSource

    fd, tmp = tempfile.mkstemp(prefix="dna-port-contract-sqlite-", suffix=".db")
    os.close(fd)
    src = SqliteSource(db_path=tmp)
    await src.connect()

    async def cleanup() -> None:
        await src.close()
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass

    return src, cleanup


async def _build_postgres_source() -> tuple[Any, Callable[[], Awaitable[None]]]:
    """Postgres source against ``DATABASE_URL``. Skipped when env unset."""
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("DATABASE_URL not set — skipping Postgres adapter")

    import asyncpg
    from dna.adapters.postgres import PostgresSource

    schema = f"dna_port_contract_{os.getpid()}_{id(asyncio):x}"
    conn = await asyncpg.connect(dsn)
    await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.close()

    pool = await asyncpg.create_pool(dsn)
    src = PostgresSource(pool, schema=schema)
    await src.init()

    async def cleanup() -> None:
        try:
            cleanup_conn = await asyncpg.connect(dsn)
            await cleanup_conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            await cleanup_conn.close()
        finally:
            await pool.close()

    return src, cleanup


async def _build_sqlalchemy_sqlite_source() -> tuple[Any, Callable[[], Awaitable[None]]]:
    """SqlAlchemySource[sqlite] — same tables as SqliteSource
    (s-sqlalchemy-source-production). Skips without the `sql` extra."""
    try:
        import sqlalchemy  # noqa: F401
    except ImportError:
        pytest.skip("`sql` extra not installed — skipping SqlAlchemySource")

    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    fd, tmp = tempfile.mkstemp(prefix="dna-port-contract-sa-", suffix=".db")
    os.close(fd)
    src = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp}")
    await src.connect()

    async def cleanup() -> None:
        await src.close()
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass

    return src, cleanup


async def _build_sqlalchemy_postgres_source() -> tuple[Any, Callable[[], Awaitable[None]]]:
    """SqlAlchemySource[postgres] — same tables as PostgresSource.
    Skips without the `sql` extra or ``DATABASE_URL``."""
    try:
        import sqlalchemy  # noqa: F401
    except ImportError:
        pytest.skip("`sql` extra not installed — skipping SqlAlchemySource")
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("DATABASE_URL not set — skipping SqlAlchemySource[postgres]")

    import asyncpg
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    schema = f"dna_port_contract_sa_{os.getpid()}_{id(asyncio):x}"
    conn = await asyncpg.connect(dsn)
    await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.close()

    src = SqlAlchemySource(
        dsn.replace("postgresql://", "postgresql+asyncpg://", 1), schema=schema,
    )
    await src.connect()

    async def cleanup() -> None:
        try:
            cleanup_conn = await asyncpg.connect(dsn)
            await cleanup_conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            await cleanup_conn.close()
        finally:
            await src.close()

    return src, cleanup


_source_factories = [
    pytest.param(_build_fs_source, id="filesystem"),
    pytest.param(_build_sqlite_source, id="sqlite"),
    pytest.param(_build_postgres_source, id="postgres"),
    pytest.param(_build_sqlalchemy_sqlite_source, id="sqlalchemy-sqlite"),
    pytest.param(_build_sqlalchemy_postgres_source, id="sqlalchemy-postgres"),
]


@pytest_asyncio.fixture(params=_source_factories)
async def source_with_kernel(request) -> AsyncIterator[tuple[Any, Any]]:
    """Yield (source, kernel) tuples wired via ``Kernel.auto``.

    Auto-wiring is part of what we're testing — so each adapter goes
    through the same ``Kernel.auto(source=...)`` path. After the test,
    cleanup runs (unlink files, drop schemas).
    """
    from dna.kernel import Kernel

    factory = request.param
    src, cleanup = await factory()
    try:
        k = Kernel.auto(source=src)
        # Seed a Module so scope queries don't fail
        await _seed_module(src, scope="contract-test")
        yield src, k
    finally:
        await cleanup()


async def _seed_module(src: Any, scope: str) -> None:
    """Insert a minimal ``Module`` so the scope exists for the test.

    Uses ``save_document`` + ``publish`` to bypass the
    draft/published distinction the SQL adapters maintain (FS publish
    is a no-op; SQL publish promotes a draft row from ``versions``
    into ``documents``). All adapters expose both methods on the
    WritableSourcePort.
    """
    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": scope},
        "spec": {"owner": "port-contract-test"},
    }
    await src.save_document(scope, "Genome", scope, raw)
    if hasattr(src, "publish"):
        await src.publish(scope, "Genome", scope)


# ---------------------------------------------------------------------------
# Capability conformance
# ---------------------------------------------------------------------------


async def test_implements_bundle_entry_readable(source_with_kernel):
    """Every adapter MUST implement BundleEntryReadable (Phase 14w +
    H2). The kernel routes ``fetch_bundle_entry`` through this
    capability; without it tools that read bundle payloads (graphify
    code-graph, ...) get NotImplementedError."""
    from dna.kernel.capabilities import BundleEntryReadable

    src, _ = source_with_kernel
    assert isinstance(src, BundleEntryReadable), (
        f"{type(src).__name__} must implement BundleEntryReadable. "
        f"See dna.kernel.capabilities for the contract."
    )


async def test_implements_kernel_attachable(source_with_kernel):
    """Every adapter MUST implement KernelAttachable so
    ``Kernel.auto(source=...)`` wires writers/readers uniformly.
    Without it bundle writes silently produce no rows in the source's
    backing store (the H2 footgun)."""
    from dna.kernel.capabilities import KernelAttachable

    src, _ = source_with_kernel
    assert isinstance(src, KernelAttachable)


async def test_kernel_auto_wires_writers(source_with_kernel):
    """After ``Kernel.auto(source=...)``, the source has the kernel's
    writers + readers attached (via ``attach_kernel``). Pre-H2 only
    Filesystem got this; SQLite/Postgres silently dropped bundle
    writes when used via ``Kernel.auto``."""
    src, k = source_with_kernel
    assert len(src._writers) > 0, (
        f"{type(src).__name__}: writers not wired by Kernel.auto. "
        f"Expected len(src._writers) > 0, got {len(src._writers)}."
    )
    assert len(src._readers) > 0


# ---------------------------------------------------------------------------
# Module round-trip
# ---------------------------------------------------------------------------


async def test_module_round_trip(source_with_kernel):
    """Module write → reload via mi → spec preserved."""
    src, k = source_with_kernel
    mi = await k.instance_async("contract-test")
    root = mi.root
    assert root is not None
    assert root.name == "contract-test"
    assert root.spec.get("owner") == "port-contract-test"


# ---------------------------------------------------------------------------
# Bundle round-trip — Skill is the canonical bundle Kind every adapter
# must handle (SKILL.md marker + scripts/).
# ---------------------------------------------------------------------------


async def test_skill_bundle_round_trip(source_with_kernel):
    """Write a Skill bundle, read it back via mi.all, content
    preserved including bundle entries."""
    src, k = source_with_kernel
    raw = {
        "apiVersion": "agentskills.io/v1",
        "kind": "Skill",
        "metadata": {"name": "contract-skill"},
        "spec": {
            "name": "contract-skill",
            "description": "port contract test skill",
            "instruction": "do the thing",
        },
    }
    await k.write_document("contract-test", "Skill", "contract-skill", raw)
    if hasattr(src, "publish"):
        await src.publish("contract-test", "Skill", "contract-skill")

    # Re-read via fresh mi (forces reload from source, not in-memory cache)
    mi = await k.instance_async("contract-test")
    skills = list([d for d in mi.documents if d.kind == "Skill"])
    assert len(skills) == 1
    sk = skills[0]
    assert sk.name == "contract-skill"
    # SkillReader splits frontmatter into spec + metadata. Description
    # lands in metadata (identity), instruction lands in spec (behavior).
    assert sk.spec.get("instruction") == "do the thing"


async def test_fetch_bundle_entry_hit(source_with_kernel):
    """After writing a Skill bundle, fetch_bundle_entry returns the
    SKILL.md bytes through the BundleEntryReadable capability."""
    src, k = source_with_kernel
    raw = {
        "apiVersion": "agentskills.io/v1",
        "kind": "Skill",
        "metadata": {"name": "fetch-test"},
        "spec": {
            "name": "fetch-test",
            "description": "fetch entry test",
            "instruction": "marker bytes",
        },
    }
    await k.write_document("contract-test", "Skill", "fetch-test", raw)
    if hasattr(src, "publish"):
        await src.publish("contract-test", "Skill", "fetch-test")

    payload = await k.fetch_bundle_entry_async(
        "contract-test", "Skill", "fetch-test", "SKILL.md",
    )
    assert isinstance(payload, bytes)
    assert b"fetch-test" in payload
    assert b"marker bytes" in payload


async def test_write_bundle_entry_text_and_binary_round_trip(source_with_kernel):
    """i-083 — write_bundle_entry accepts str (text entries) AND bytes
    (binary entries). Text must not be force-coerced into the binary column
    (the bug that buried instruction fragments / asset.json / scripts in
    content_binary). Both round-trip via fetch_bundle_entry as bytes."""
    src, k = source_with_kernel
    raw = {
        "apiVersion": "agentskills.io/v1",
        "kind": "Skill",
        "metadata": {"name": "rt-test"},
        "spec": {"name": "rt-test", "description": "round-trip", "instruction": "x"},
    }
    await k.write_document("contract-test", "Skill", "rt-test", raw)
    if hasattr(src, "publish"):
        await src.publish("contract-test", "Skill", "rt-test")

    # TEXT entry passed as str.
    await k.write_bundle_entry_async(
        "contract-test", "Skill", "rt-test", "notes.txt", "olá — texto",
    )
    # BINARY entry passed as bytes.
    await k.write_bundle_entry_async(
        "contract-test", "Skill", "rt-test", "blob.bin", b"\x00\x01\x02\xff",
    )

    txt = await k.fetch_bundle_entry_async(
        "contract-test", "Skill", "rt-test", "notes.txt",
    )
    assert txt == "olá — texto".encode("utf-8")
    binp = await k.fetch_bundle_entry_async(
        "contract-test", "Skill", "rt-test", "blob.bin",
    )
    assert binp == b"\x00\x01\x02\xff"


async def test_fetch_bundle_entry_miss_raises_filenotfound(source_with_kernel):
    """fetch_bundle_entry raises FileNotFoundError on miss — uniform
    error contract across all adapters."""
    src, k = source_with_kernel
    raw = {
        "apiVersion": "agentskills.io/v1",
        "kind": "Skill",
        "metadata": {"name": "miss-test"},
        "spec": {
            "name": "miss-test",
            "description": "miss test",
            "instruction": "x",
        },
    }
    await k.write_document("contract-test", "Skill", "miss-test", raw)
    if hasattr(src, "publish"):
        await src.publish("contract-test", "Skill", "miss-test")

    with pytest.raises(FileNotFoundError):
        await k.fetch_bundle_entry_async(
            "contract-test", "Skill", "miss-test", "nonexistent-entry.json",
        )


async def test_fetch_bundle_entry_kind_disambiguation(source_with_kernel):
    """Two bundles sharing a ``name`` in the same scope but in
    different Kinds (= different containers) must NOT collide.

    Pre-fix: SQL adapters resolved by ``(scope, name, entry_path)``
    only — a Skill ``foo`` and a hypothetical other-kind ``foo``
    with the same entry filename would race-match. The kernel now
    passes ``kind`` through ``BundleEntryReadable.fetch_bundle_entry``
    and SQL adapters filter on it, restoring the FS-level guarantee
    that container path namespaces bundles by Kind.

    The test forges this scenario at the storage layer for SQL
    adapters: write the legitimate Skill, then sideload a row with
    a different ``kind`` value but identical ``(scope, name,
    entry_path, tenant)`` and content marker. Without the kind
    filter, the fetch could return either row — with it, the Skill
    payload always wins.
    """
    src, k = source_with_kernel
    skill_raw = {
        "apiVersion": "agentskills.io/v1",
        "kind": "Skill",
        "metadata": {"name": "shared-name"},
        "spec": {
            "name": "shared-name",
            "description": "kind disambiguation test",
            "instruction": "skill-bytes-marker",
        },
    }
    await k.write_document("contract-test", "Skill", "shared-name", skill_raw)
    if hasattr(src, "publish"):
        await src.publish("contract-test", "Skill", "shared-name")

    # Sideload a competing row with a fake kind name + same
    # ``(scope, name, entry_path)`` so the SQL WHERE clause WITHOUT
    # the kind filter would have two candidates.
    fake_marker = b"COMPETING-KIND-PAYLOAD"
    if hasattr(src, "_pool"):
        # Postgres
        async with src._pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {src._schema}.dna_bundle_entries "
                "(scope, kind, name, entry_path, content, updated_at, tenant) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                "contract-test",
                "FakeOtherKind",
                "shared-name",
                "SKILL.md",
                fake_marker.decode("utf-8"),
                "2026-05-08T00:00:00",
                "",
            )
    elif hasattr(src, "_conn"):
        # SQLite
        await src._conn.execute(
            "INSERT INTO bundle_entries "
            "(scope, kind, name, entry_path, content, updated_at, tenant) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "contract-test",
                "FakeOtherKind",
                "shared-name",
                "SKILL.md",
                fake_marker.decode("utf-8"),
                "2026-05-08T00:00:00",
                "",  # base-layer sentinel — bundle_entries.tenant is NOT NULL (migration v8)
            ),
        )
        await src._conn.commit()
    else:
        # Filesystem can't have this collision (containers are
        # directory namespaces). Skip cleanly.
        pytest.skip(
            "FS adapter doesn't have the SQL-level row collision risk "
            "(container path already namespaces bundles)"
        )

    # Fetch through kernel — must hit the Skill row, not the fake.
    payload = await k.fetch_bundle_entry_async(
        "contract-test", "Skill", "shared-name", "SKILL.md",
    )
    assert b"skill-bytes-marker" in payload, (
        f"Wrong row returned. Expected the Skill content (with "
        f"'skill-bytes-marker'); got {payload!r}. The kind filter "
        f"isn't being applied."
    )
    assert fake_marker not in payload


# ---------------------------------------------------------------------------
# Boot-time validation (H1) — registration errors propagate uniformly
# ---------------------------------------------------------------------------


async def test_kernel_kind_collision_raises(source_with_kernel):
    """Registering two Kinds with the same (api_version, kind) tuple
    raises KindRegistrationError. H1 contract — uniform across
    adapters because it's enforced at the kernel level, not the
    source level (same code path runs regardless of source type)."""
    from dna.kernel.errors import KindRegistrationError
    from dna.kernel.protocols import StorageDescriptor

    _, k = source_with_kernel

    class _Duplicate:
        api_version = "agentskills.io/v1"
        kind = "Skill"  # collides with the already-registered Skill
        alias = "duplicate-test"
        model = dict
        origin = "tests/test_port_contract.py::_Duplicate"
        storage = StorageDescriptor.bundle("dup", "DUP.md")
        is_root = False
        is_prompt_target = False
        prompt_target_priority = 0
        flatten_in_context = False
        # ``is_runtime_artifact`` was added to the KindPort protocol
        # post-Phase 14w — without it, ``isinstance(_, KindPort)``
        # fails before the duplicate-registration guard we want to
        # exercise here.
        is_runtime_artifact = False
        def dep_filters(self): return None
        def dependencies(self): return None
        def schema(self): return None
        def get_default_agent_name(self, doc): return None
        def get_layer_policies(self, doc): return None
        def parse(self, raw): return raw
        def describe(self, doc): return None
        def summary(self, doc): return None
        def prompt_template(self): return None

    with pytest.raises(KindRegistrationError, match="already registered"):
        k.kind(_Duplicate())
