"""s-sqlalchemy-source-production — production behaviors of SqlAlchemySource.

The conformance kit (test_source_conformance_kit.py) is the judge for the
port surface; THIS file covers the behaviors promoted on top of the i-216
spike:

  - packaging guard: the default install never imports sqlalchemy;
  - PG eventbus strategy: outbox + versions_seq + pg_notify in the SAME
    transaction, payload byte-identical to the raw PostgresSource (the
    builder is imported, and the test listens on the live channel);
  - memo-cached ``_load_view`` (single-flight, deep copies, invalidation
    on local writes + kernel wiring);
  - FrontmatterParseWarning net (corrupt marker → canonical row);
  - kind-agnostic ``spec.source_files`` net;
  - auto-publish (save_document is the publish point);
  - Genome catalog + layer/tenant surfaces;
  - preserve-binary bundle semantics on the pg dialect.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import uuid
import warnings

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Packaging guard — runs WITHOUT the `sql` extra too (no importorskip here).
# ---------------------------------------------------------------------------


def test_default_import_never_pulls_sqlalchemy():
    """`sqlalchemy` is an optional dependency (`sql` extra): importing the
    SDK, the adapters namespace and booting a kernel must never pull it.
    Fresh interpreter so this suite's own imports don't contaminate."""
    code = (
        "import sys\n"
        "import dna\n"
        "import dna.adapters\n"
        "from dna.kernel import Kernel\n"
        "Kernel.auto()\n"
        "assert 'sqlalchemy' not in sys.modules, "
        "'default install must not import sqlalchemy'\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr


# ---------------------------------------------------------------------------
# Everything below exercises the adapter — requires the `sql` extra.
# ---------------------------------------------------------------------------


def _require_sqlalchemy():
    pytest.importorskip("sqlalchemy", reason="`sql` extra not installed")


def _story(name: str, **spec) -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Story",
        "metadata": {"name": name},
        "spec": {"title": name, **spec},
    }


@pytest_asyncio.fixture
async def sa_sqlite():
    """Connected SqlAlchemySource over a temp-file sqlite DB (no kernel)."""
    _require_sqlalchemy()
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    fd, tmp = tempfile.mkstemp(prefix="dna-sa-prod-", suffix=".db")
    os.close(fd)
    src = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp}")
    await src.connect()
    yield src
    await src.close()
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass


def test_notify_payload_builder_is_shared():
    """Byte-parity by construction: the SA adapter uses the raw Postgres
    adapter's payload builder + channel constant (imported, not copied)."""
    _require_sqlalchemy()
    from dna.adapters import sqlalchemy_ as sam
    from dna.adapters.postgres import source as pgm

    assert sam.source._build_notify_payload is pgm._build_notify_payload
    assert sam.source.KERNEL_EVENTBUS_CHANNEL == pgm.KERNEL_EVENTBUS_CHANNEL


def test_cross_process_invalidation_flag_follows_dialect():
    """pg dialect propagates writes cross-process (outbox emitter) →
    True; sqlite has no bus → False. No connection is opened."""
    _require_sqlalchemy()
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    sqlite_src = SqlAlchemySource("sqlite+aiosqlite:///:memory:")
    assert sqlite_src.supports_cross_process_invalidation is False

    pg_src = SqlAlchemySource(
        "postgresql+asyncpg://u:p@nowhere.invalid/db", schema="public",
    )
    assert pg_src.supports_cross_process_invalidation is True


# ─── auto-publish ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_document_auto_publishes(sa_sqlite):
    """save_document is the publish point (raw-PG contract) —
    kernel.write_document never calls publish(), so the doc must be
    visible in load_all right after save."""
    await sa_sqlite.save_document(
        "auto-pub", "Story", "s-auto", _story("s-auto"),
    )
    docs = await sa_sqlite.load_all("auto-pub", None)
    assert [d["metadata"]["name"] for d in docs] == ["s-auto"]
    # ... while still leaving a draft trail (publish flips it later).
    drafts = await sa_sqlite.load_drafts("auto-pub")
    assert [d["name"] for d in drafts] == ["s-auto"]


# ─── memo-cached _load_view ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_view_cache_memoizes_and_local_writes_invalidate(sa_sqlite):
    calls = {"n": 0}
    real = sa_sqlite._load_view_uncached

    async def counting(*a, **kw):
        calls["n"] += 1
        return await real(*a, **kw)

    sa_sqlite._load_view_uncached = counting

    await sa_sqlite.save_document("memo", "Story", "s-1", _story("s-1"))
    assert await sa_sqlite.load_all("memo", None)
    assert await sa_sqlite.load_all("memo", None)
    assert calls["n"] == 1, "second load_all must be a cache hit"

    # A local write through THIS source invalidates the scope's views.
    await sa_sqlite.save_document("memo", "Story", "s-2", _story("s-2"))
    docs = await sa_sqlite.load_all("memo", None)
    assert {d["metadata"]["name"] for d in docs} == {"s-1", "s-2"}
    assert calls["n"] == 2

    # delete_document invalidates too.
    await sa_sqlite.delete_document("memo", "Story", "s-1")
    docs = await sa_sqlite.load_all("memo", None)
    assert {d["metadata"]["name"] for d in docs} == {"s-2"}
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_view_cache_returns_deep_copies(sa_sqlite):
    """Callers may mutate returned rows (kinds-api stamps inherited_from)
    without corrupting the cache."""
    await sa_sqlite.save_document("deep", "Story", "s-x", _story("s-x"))
    first = await sa_sqlite.load_all("deep", None)
    first[0]["spec"]["title"] = "MUTATED"
    second = await sa_sqlite.load_all("deep", None)
    assert second[0]["spec"]["title"] == "s-x"


@pytest.mark.asyncio
async def test_attach_kernel_wires_view_invalidation(sa_sqlite):
    """attach_kernel registers an on_write observer so kernel-path and
    cross-process (EventBus → kernel.invalidate → observer fan-out)
    writes drop the cached views."""
    from dna.kernel import Kernel

    kernel = Kernel.auto(source=sa_sqlite)
    assert sa_sqlite._view_invalidation_wired is True

    await sa_sqlite.save_document("wired", "Story", "s-a", _story("s-a"))
    assert await sa_sqlite.load_all("wired", None)
    assert ("wired", "") in sa_sqlite._view_cache

    # Simulate a write announced through the kernel bus (e.g. another
    # process's write relayed by PostgresEventBus).
    kernel._fire_write_observers("wired", "Story", "s-b", "write")
    assert ("wired", "") not in sa_sqlite._view_cache


# ─── FrontmatterParseWarning net ─────────────────────────────────────


class _CorruptMarkerReader:
    """Reader whose marker parse 'fails': emits FrontmatterParseWarning
    and returns an anemic doc — exactly what GenericBundleReader does on
    corrupt YAML frontmatter."""

    _kind = "Story"

    def detect(self, handle) -> bool:
        return handle.exists("STORY.md")

    def read(self, handle) -> dict:
        from dna.kernel.generic_rw import FrontmatterParseWarning
        warnings.warn("bad frontmatter", FrontmatterParseWarning, stacklevel=2)
        return {
            "apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Story",
            "metadata": {"name": handle.name}, "spec": {"body": "anemic"},
        }


class _HealthyMarkerReader(_CorruptMarkerReader):
    def read(self, handle) -> dict:
        return {
            "apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Story",
            "metadata": {"name": handle.name}, "spec": {"body": "from-marker"},
        }


@pytest.mark.asyncio
async def test_frontmatter_net_falls_back_to_canonical_row(sa_sqlite):
    from dna.kernel.generic_rw import FrontmatterParseWarning

    raw = _story("s-fm", description="precious spec field")
    await sa_sqlite.save_document("fmnet", "Story", "s-fm", raw)
    await sa_sqlite.write_bundle_entry(
        "fmnet", "Story", "s-fm", "STORY.md", "---\n:bad yaml\n---\nbody",
        kind="Story",
    )

    # Corrupt marker → warning surfaced, canonical content row served.
    with pytest.warns(FrontmatterParseWarning):
        doc = await sa_sqlite.load_one(
            "fmnet", "Story", "s-fm", readers=[_CorruptMarkerReader()],
        )
    assert doc["spec"]["description"] == "precious spec field"

    with pytest.warns(FrontmatterParseWarning):
        docs = await sa_sqlite.load_all("fmnet", readers=[_CorruptMarkerReader()])
    assert docs[0]["spec"]["description"] == "precious spec field"

    # Healthy marker → reader output wins (the net only fires on warning).
    sa_sqlite.invalidate_view("fmnet")
    doc = await sa_sqlite.load_one(
        "fmnet", "Story", "s-fm", readers=[_HealthyMarkerReader()],
    )
    assert doc["spec"] == {"body": "from-marker"}


# ─── spec.source_files net ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_source_files_net_persists_entries_and_depollutes_spec(sa_sqlite):
    raw = _story("s-net")
    raw["spec"]["source_files"] = {
        "notes.txt": "olá net", "blob.bin": b"\x00\x01\xff",
    }
    await sa_sqlite.save_document("netscope", "Story", "s-net", raw)

    txt = await sa_sqlite.fetch_bundle_entry(
        "netscope", "Story", "s-net", "notes.txt", kind="Story",
    )
    assert txt == "olá net".encode("utf-8")
    blob = await sa_sqlite.fetch_bundle_entry(
        "netscope", "Story", "s-net", "blob.bin", kind="Story",
    )
    assert blob == b"\x00\x01\xff"

    # Stored content is bloat-free: source_files popped before persist.
    doc = await sa_sqlite.load_one("netscope", "Story", "s-net")
    assert "source_files" not in doc["spec"]
    ver = await sa_sqlite.get_version("netscope", "Story", "s-net", "1")
    assert "source_files" not in ver["content"]["spec"]


# ─── Genome catalog surface ──────────────────────────────────────────


def _genome(scope: str, version: str) -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": scope},
        "spec": {"owner": "sa-prod", "version": version},
    }


@pytest.mark.asyncio
async def test_genome_catalog_surface(sa_sqlite):
    from dna.kernel.protocols import VersionAlreadyPublished

    scope = "sa-catalog"
    await sa_sqlite.save_document(scope, "Genome", scope, _genome(scope, "0.1.0"))
    await sa_sqlite.save_document(scope, "Genome", scope, _genome(scope, "0.2.0"))

    # Immutable releases: same semver twice → typed exception.
    with pytest.raises(VersionAlreadyPublished):
        await sa_sqlite.save_document(scope, "Genome", scope, _genome(scope, "0.2.0"))

    versions = await sa_sqlite.list_module_versions(scope)
    assert [v["version"] for v in versions] == ["0.1.0", "0.2.0"]
    assert all(v["deprecated"] is False for v in versions)

    frozen = await sa_sqlite.get_module_version(scope, "0.1.0")
    assert frozen["spec"]["version"] == "0.1.0"
    assert await sa_sqlite.get_module_version(scope, "9.9.9") is None

    # Deprecate the LATEST → archived row flips AND the documents pointer
    # mirrors (it currently points at 0.2.0).
    assert await sa_sqlite.deprecate_module_version(
        scope, "0.2.0", message="use 0.3",
    ) is True
    versions = await sa_sqlite.list_module_versions(scope)
    assert [(v["version"], v["deprecated"]) for v in versions] == [
        ("0.1.0", False), ("0.2.0", True),
    ]
    latest = await sa_sqlite.load_one(scope, "Genome", scope)
    assert latest["spec"]["deprecated"] is True
    assert latest["spec"]["deprecated_message"] == "use 0.3"

    assert await sa_sqlite.deprecate_module_version(scope, "9.9.9") is False


# ─── layer + tenant surfaces ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_layer_documents_round_trip_and_listing(sa_sqlite):
    scope = "sa-layers"
    await sa_sqlite.save_document(scope, "Story", "s-base", _story("s-base"))

    await sa_sqlite.save_layer_document(
        scope, "env", "prod", "Story", "s-base", _story("s-base", env="prod"),
    )
    overlay = await sa_sqlite.load_layer(scope, "env", "prod")
    assert overlay[0]["spec"]["env"] == "prod"

    # Tenant overlays observed in documents.tenant also surface.
    await sa_sqlite.save_document(
        scope, "Story", "s-t", _story("s-t"), tenant="acme",
    )
    layers = await sa_sqlite.list_layers(scope)
    assert {"layer_id": "env", "layer_value": "prod"} in layers
    assert {"layer_id": "tenant", "layer_value": "acme"} in layers
    assert await sa_sqlite.list_tenants(scope) == ["acme"]
    assert await sa_sqlite.list_tenants() == ["acme"]

    await sa_sqlite.delete_layer_document(scope, "env", "prod", "Story", "s-base")
    assert await sa_sqlite.load_layer(scope, "env", "prod") == []


# ─── PG dialect: outbox + NOTIFY in the write transaction ────────────

pgmark = pytest.mark.requires_postgres


def _dsn() -> str:
    return (
        os.environ.get("DATABASE_URL")
        or os.environ.get("DNA_PG_TEST_URL")
        or os.environ.get("DNA_PG_TEST_DSN")
    )


@pytest_asyncio.fixture
async def sa_pg():
    """Connected SqlAlchemySource[postgres] on a throwaway schema."""
    _require_sqlalchemy()
    import asyncpg
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    dsn = _dsn()
    schema = f"dna_sa_prod_{uuid.uuid4().hex[:12]}"
    conn = await asyncpg.connect(dsn)
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.close()

    src = SqlAlchemySource(
        dsn.replace("postgresql://", "postgresql+asyncpg://", 1), schema=schema,
    )
    await src.connect()
    yield {"src": src, "dsn": dsn, "schema": schema}
    import contextlib
    with contextlib.suppress(Exception):
        await src.close()
    with contextlib.suppress(Exception):
        c = await asyncpg.connect(dsn)
        await c.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        await c.close()


@pgmark
@pytest.mark.asyncio
async def test_pg_write_emits_outbox_seq_and_notify_with_raw_parity(sa_pg):
    """save_document on the pg dialect appends dna_outbox + checkpoints
    dna_versions_seq + fires pg_notify — and the received payload is
    byte-identical to what the raw adapter's builder produces."""
    import asyncpg
    from dna.adapters.postgres.source import (
        KERNEL_EVENTBUS_CHANNEL, _build_notify_payload,
    )

    src, dsn, schema = sa_pg["src"], sa_pg["dsn"], sa_pg["schema"]

    listener = await asyncpg.connect(dsn)
    got: list[str] = []
    event = asyncio.Event()

    def _on_notify(_c, _pid, _ch, payload):
        # The channel is database-wide — other tests' adapters NOTIFY on
        # it too. Keep only OUR scope's events so parallel runs stay
        # deterministic.
        try:
            if json.loads(payload).get("scope") != "evb-sa":
                return
        except Exception:
            return
        got.append(payload)
        event.set()

    await listener.add_listener(KERNEL_EVENTBUS_CHANNEL, _on_notify)
    try:
        await src.save_document(
            "evb-sa", "Story", "s-ev", _story("s-ev"), author="sa-tester",
            write_class="substantive",
        )
        await asyncio.wait_for(event.wait(), timeout=5)

        check = await asyncpg.connect(dsn)
        try:
            rows = await check.fetch(
                f"SELECT id, scope, tenant, kind, name, op, doc_version, actor "
                f"FROM {schema}.dna_outbox ORDER BY id",
            )
            assert len(rows) == 1
            row = rows[0]
            assert (row["scope"], row["kind"], row["name"]) == ("evb-sa", "Story", "s-ev")
            assert (row["op"], row["doc_version"], row["tenant"]) == ("write", 1, "")
            assert row["actor"] == "sa-tester"

            seq = await check.fetchrow(
                f"SELECT last_id FROM {schema}.dna_versions_seq "
                "WHERE scope='evb-sa' AND tenant=''",
            )
            assert seq["last_id"] == row["id"]

            expected = _build_notify_payload(
                row["id"], "evb-sa", "", "Story", "s-ev", "write", 1,
                "sa-tester", "substantive",
            )
            assert got == [expected]
        finally:
            await check.close()
    finally:
        await listener.close()


@pgmark
@pytest.mark.asyncio
async def test_pg_delete_emits_delete_event_and_failed_write_emits_nothing(sa_pg):
    import asyncpg

    src, dsn, schema = sa_pg["src"], sa_pg["dsn"], sa_pg["schema"]
    await src.save_document("evb-sa2", "Genome", "evb-sa2", _genome("evb-sa2", "1.0.0"))
    await src.delete_document("evb-sa2", "Genome", "evb-sa2")

    check = await asyncpg.connect(dsn)
    try:
        ops = [
            (r["op"], r["doc_version"]) for r in await check.fetch(
                f"SELECT op, doc_version FROM {schema}.dna_outbox ORDER BY id",
            )
        ]
        assert ops == [("write", 1), ("delete", 0)]

        # A vetoed write (duplicate semver) rolls back atomically — no
        # phantom event survives the failed transaction.
        from dna.kernel.protocols import VersionAlreadyPublished
        await src.save_document("evb-sa2", "Genome", "evb-sa2", _genome("evb-sa2", "2.0.0"))
        with pytest.raises(VersionAlreadyPublished):
            await src.save_document(
                "evb-sa2", "Genome", "evb-sa2", _genome("evb-sa2", "2.0.0"),
            )
        n = await check.fetchval(f"SELECT count(*) FROM {schema}.dna_outbox")
        assert n == 3  # write + delete + the successful 2.0.0 write ONLY
    finally:
        await check.close()


@pgmark
@pytest.mark.asyncio
async def test_pg_save_preserves_binary_bundle_entries(sa_pg):
    """Phase 16-pre parity: writers can't round-trip binary blobs, so a
    spec re-save must NOT wipe binaries written via write_bundle_entry."""
    from dna.kernel import Kernel

    src = sa_pg["src"]
    Kernel.auto(source=src)  # wires writers (Skill writer emits SKILL.md)

    raw = {
        "apiVersion": "agentskills.io/v1", "kind": "Skill",
        "metadata": {"name": "bin-keeper"},
        "spec": {"name": "bin-keeper", "description": "v1", "instruction": "x"},
    }
    await src.save_document("evb-sa3", "Skill", "bin-keeper", raw)
    await src.write_bundle_entry(
        "evb-sa3", "Skill", "bin-keeper", "output.png", b"\x89PNG-fake",
        kind="Skill",
    )

    raw2 = dict(raw, spec={**raw["spec"], "description": "v2 edited"})
    await src.save_document("evb-sa3", "Skill", "bin-keeper", raw2)

    blob = await src.fetch_bundle_entry(
        "evb-sa3", "Skill", "bin-keeper", "output.png", kind="Skill",
    )
    assert blob == b"\x89PNG-fake"
