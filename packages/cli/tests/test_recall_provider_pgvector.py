"""i-069 fix 3 — a Postgres source gets the pgvector search provider at boot.

Production forensics (2026-07-21): the hosted MCP image installs
``dna-sdk[search-pgvector,embed-onnx]`` for semantic recall, but NO boot path
ever registered ``PgVecRecordSearchProvider`` — ``_register_provider`` only
knew sqlite-vec, absent from the container. Hosted recall therefore ran
PERMANENTLY on the degraded lexical fallback, which is structurally blind to
any query sharing no literal token with the stored specs: the founder's
``recall("minhas memórias", personal=true)`` returned an honest ``[]`` with
both memories intact in their partition (repro'd byte-for-byte from the
production rows), while ``recall("Barna")`` found them — query-dependence,
never a partition/version defect.

Three pins:
  1. boot over a Postgres source registers the pgvector provider (unit, and
     for real under ``requires_postgres``) — removing the registration kills
     the meta-query test below;
  2. with the provider active, the exact production meta-query FINDS the
     personal memories (semantic, not token luck);
  3. without a provider the lexical fallback stays honestly blind to the
     meta-query while literal queries still hit — the 23:47 shape, pinned so
     the next regression hunt starts from knowledge, not archaeology.
OSS floor untouched: no Postgres and no extras → no provider, same as today.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from types import SimpleNamespace

import pytest

from conftest import pg_dsn

_OID = "59064647-9976-4bd7-b25c-e1eed545e07f"


# ── unit: the registration decision ────────────────────────────────────────


class _PgStubSource:
    def pg_search_binding(self):
        return ("postgresql://u@h/db", "public")


class _FsStubSource:  # no pg_search_binding — the filesystem/sqlite shape
    pass


class _StubKernel:
    def __init__(self, source):
        self._source = source
        self.registered = None
        self._embedding_provider = object()  # embedder wiring is not under test

    def record_search_provider(self, provider):
        self.registered = provider


def test_pg_source_registers_the_pgvector_provider():
    pytest.importorskip("asyncpg")
    from dna.adapters.search.pgvector import PgVecRecordSearchProvider
    from dna_cli.recall_cmd import _register_provider

    kernel = _StubKernel(_PgStubSource())
    provider = _register_provider(SimpleNamespace(kernel=kernel))
    assert isinstance(provider, PgVecRecordSearchProvider)
    assert kernel.registered is provider


def test_pg_branch_needs_the_extra(monkeypatch):
    """asyncpg blocked (no search-pgvector extra) → the PG branch declines and
    the floor is exactly today's: no sqlite_vec either → no provider at all."""
    monkeypatch.setitem(sys.modules, "asyncpg", None)
    monkeypatch.setitem(sys.modules, "sqlite_vec", None)
    from dna_cli.recall_cmd import _register_provider

    kernel = _StubKernel(_PgStubSource())
    assert _register_provider(SimpleNamespace(kernel=kernel)) is None
    assert kernel.registered is None


def test_non_pg_source_keeps_the_sqlite_path(monkeypatch):
    """A source without ``pg_search_binding`` never enters the PG branch —
    with sqlite_vec absent the result is today's ``None`` floor."""
    monkeypatch.setitem(sys.modules, "sqlite_vec", None)
    from dna_cli.recall_cmd import _register_provider

    kernel = _StubKernel(_FsStubSource())
    assert _register_provider(SimpleNamespace(kernel=kernel)) is None
    assert kernel.registered is None


# ── for real: Postgres + pgvector ───────────────────────────────────────────


def _driverless(dsn: str) -> str:
    return dsn.replace("postgresql+asyncpg://", "postgresql://", 1)


def _vector_extension_available(dsn: str) -> bool:
    import asyncpg

    async def probe() -> bool:
        conn = await asyncpg.connect(_driverless(dsn))
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            return True
        except Exception:  # noqa: BLE001 — no extension → honest skip
            return False
        finally:
            await conn.close()

    return asyncio.run(probe())


def _pg_env(monkeypatch, dsn: str) -> None:
    monkeypatch.setenv("DNA_SOURCE_URL", dsn)
    for var in ("DNA_BASE_DIR", "DNA_PERSONAL_ID", "DNA_VENDOR_WORKSPACE",
                "DNA_QUOTA_DSN", "DNA_QUOTA_REQUIRE_TIERS", "DNA_SEARCH_DIR"):
        monkeypatch.delenv(var, raising=False)


async def _seed_two_memories(live) -> None:
    """The two production memories, written the way production wrote them."""
    from dna.application.runtime import remember_impl

    await remember_impl(live, "Nome: Barna", None, area="identity",
                        tags=["nome", "Barna"], memory_scope="personal",
                        oid=_OID)
    await remember_impl(live, "Gosto do projeto DNA.", None, area="projects",
                        tags=["DNA", "gosto"], memory_scope="personal",
                        oid=_OID)


@pytest.mark.requires_postgres
def test_meta_query_finds_personal_memories_over_pg(monkeypatch):
    """The 23:47 call, cured: with the pgvector provider registered by boot,
    ``recall("minhas memórias", personal)`` surfaces BOTH personal memories —
    semantic recall is not hostage to literal token overlap. Reverting the
    ``_register_pg_provider`` wiring returns the empty and kills this test."""
    pytest.importorskip("asyncpg")
    dsn = pg_dsn()
    if not _vector_extension_available(dsn):
        pytest.skip("test Postgres has no pgvector extension")
    _pg_env(monkeypatch, dsn)
    scope = f"i069-{uuid.uuid4().hex[:8]}"

    async def flow():
        from dna.application.runtime import recall_impl
        from dna_cli import _mcp_server as M

        live = await M.boot_live(scope=scope)
        assert live.provider is not None, "PG boot must register a provider"
        assert type(live.provider).__name__ == "PgVecRecordSearchProvider"
        await _seed_two_memories(live)
        return await recall_impl(live, "minhas memórias", None, 2,
                                 memory_scope="personal", oid=_OID)

    res = asyncio.run(flow())
    assert res["degraded"] is False
    assert res["semantic"] is True
    names = sorted(h["name"] for h in res["hits"])
    assert len(names) == 2, res
    assert any("nome-barna" in n for n in names), names
    assert any("gosto-do-projeto-dna" in n for n in names), names
    assert all(h["personal"] is True for h in res["hits"])


@pytest.mark.requires_postgres
def test_lexical_fallback_stays_honestly_blind_to_meta_queries(monkeypatch):
    """The 23:47 shape as a permanent regression pin: NO provider (today's
    hosted floor before this fix) → the meta-query returns an honest empty
    over intact rows while a literal query still hits. If someone 'fixes' the
    lexical scanner into fuzzy matching, or the provider wiring silently stops
    mattering, this test notices."""
    pytest.importorskip("asyncpg")
    dsn = pg_dsn()
    _pg_env(monkeypatch, dsn)
    import dna_cli.recall_cmd as recall_cmd

    monkeypatch.setattr(recall_cmd, "_register_provider", lambda s: None)
    scope = f"i069-{uuid.uuid4().hex[:8]}"

    async def flow():
        from dna.application.runtime import recall_impl
        from dna_cli import _mcp_server as M

        live = await M.boot_live(scope=scope)
        assert live.provider is None
        await _seed_two_memories(live)
        meta = await recall_impl(live, "minhas memórias", None, 2,
                                 memory_scope="personal", oid=_OID)
        literal = await recall_impl(live, "Barna", None, 2,
                                    memory_scope="personal", oid=_OID)
        return meta, literal

    meta, literal = asyncio.run(flow())
    assert meta["degraded"] is True and meta["semantic"] is False
    assert meta["hits"] == []
    assert [h["name"] for h in literal["hits"]] and \
        "nome-barna" in literal["hits"][0]["name"]
