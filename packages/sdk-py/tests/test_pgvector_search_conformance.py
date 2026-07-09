"""The public RecordSearchProvider conformance kit × the pgvector provider.

Runs the whole ``record_search_conformance_suite`` against
``PgVecRecordSearchProvider`` with the deterministic ``FakeEmbeddingProvider``
floor — offline embeddings, real Postgres. The SAME 8 cases the sqlite-vec
provider passes: that's the point of the port — one contract, many stores.

Gated on a Postgres DSN via the shared ``requires_postgres`` marker
(``tests/conftest.py``): skips cleanly with no DB (local without Postgres), and
runs FOR REAL in the CI ``postgres`` job — which MUST use a pgvector-enabled
image (``pgvector/pgvector:pg16``) so ``CREATE EXTENSION vector`` succeeds.

Each case gets a FRESH, DISPOSABLE schema (``dna_search_ci_<uuid>``) that is
created before and dropped after — never touching another project's tables (the
CI database is a throwaway ``dna_test``). The pgvector extension is created at
the database level (idempotent) by migration 1.
"""
from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.requires_postgres

asyncpg = pytest.importorskip(
    "asyncpg",
    reason="postgres extra not installed (pip install 'dna-sdk[search-pgvector]')",
)

from dna.testing import record_search_conformance_suite  # noqa: E402


def _dsn() -> str:
    for k in ("DATABASE_URL", "DNA_PG_TEST_URL", "DNA_PG_TEST_DSN"):
        v = os.environ.get(k)
        if v:
            return v
    raise RuntimeError("no Postgres DSN set")  # pragma: no cover — marker guards


async def _pgvector_factory():
    """Build a fresh PgVecRecordSearchProvider on a disposable schema.

    Each case is isolated in its own schema so index/delete state never bleeds
    across cases. The provider owns its own pool (built from the DSN); cleanup
    closes it and drops the schema.
    """
    from dna.kernel import Kernel
    from dna.adapters.search.pgvector import PgVecRecordSearchProvider

    kernel = Kernel.auto()  # no embedding provider → deterministic fake floor
    dsn = _dsn()
    schema = f"dna_search_ci_{uuid.uuid4().hex[:12]}"

    admin = await asyncpg.connect(dsn)
    await admin.execute(f"CREATE SCHEMA {schema}")
    await admin.close()

    provider = PgVecRecordSearchProvider(kernel, dsn=dsn, schema=schema)

    async def cleanup() -> None:
        await provider.close()
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        finally:
            await conn.close()

    return provider, cleanup


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    record_search_conformance_suite(_pgvector_factory),
    ids=lambda c: c.name,
)
async def test_pgvector_record_search_conformance(case):
    await case.run()


@pytest.mark.asyncio
async def test_programmatic_runner_reports_all_pass():
    from dna.testing import run_record_search_conformance

    report = await run_record_search_conformance(_pgvector_factory)
    report.raise_if_failed()
    assert report.ok
    assert "index_search_round_trip" in report.passed
    assert "tenant_overlay_shadows_base" in report.passed


@pytest.mark.asyncio
async def test_migration_owns_schema_and_is_idempotent():
    """The store schema is migration-owned (closes f-embeddings-ddl-debt): the
    control table records the applied version, ``vector`` is installed, and a
    second boot against the same schema applies nothing (idempotent re-boot)."""
    from dna.kernel import Kernel
    from dna.adapters.search.pgvector import PgVecRecordSearchProvider
    from dna.adapters.search.pgvector_migrations import build_pg_migrations

    kernel = Kernel.auto()
    dsn = _dsn()
    schema = f"dna_search_ci_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(dsn)
    await admin.execute(f"CREATE SCHEMA {schema}")
    await admin.close()
    try:
        p1 = PgVecRecordSearchProvider(kernel, dsn=dsn, schema=schema)
        await p1.index([{  # forces connect → migrate
            "scope": "s", "kind": "Story", "name": "a", "text": "hello world",
        }])
        conn = await asyncpg.connect(dsn)
        try:
            applied = [r["version"] for r in await conn.fetch(
                f"SELECT version FROM {schema}.dna_search_migrations ORDER BY version"
            )]
            assert applied == sorted(build_pg_migrations(kernel.embedding_dims)), (
                "every migration version must be recorded in the control table"
            )
            # pgvector really installed at the database level.
            ext = await conn.fetchval(
                "SELECT extname FROM pg_extension WHERE extname='vector'"
            )
            assert ext == "vector"
            # identity pinned
            meta = {r["key"]: r["value"] for r in await conn.fetch(
                f"SELECT key, value FROM {schema}.dna_search_meta"
            )}
            assert meta["embedding_dims"] == str(kernel.embedding_dims)
            assert meta["embedding_model_id"] == kernel.embedding_model_id
        finally:
            await conn.close()
        await p1.close()

        # Second boot against the SAME schema: migrations already applied → the
        # runner applies NOTHING; previously indexed data still searchable.
        p2 = PgVecRecordSearchProvider(kernel, dsn=dsn, schema=schema)
        applied_now = await p2._migrate()
        assert applied_now == [], "idempotent re-boot must apply no migrations"
        hits = await p2.search(scope="s", query_text="hello world", k=5)
        assert any(h["name"] == "a" for h in hits)
        await p2.close()
    finally:
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        finally:
            await conn.close()


@pytest.mark.asyncio
async def test_identity_mismatch_refuses_incomparable_vectors():
    """A schema built for one embedding space refuses a provider on another —
    never silently mixes incomparable vectors."""
    from dna.kernel import Kernel
    from dna.adapters.search.pgvector import PgVecRecordSearchProvider

    class _WideFake:
        model_id = "dna-fake-hash-v1"
        dims = 999

        async def embed(self, texts):
            return [[0.0] * self.dims for _ in texts]

    dsn = _dsn()
    schema = f"dna_search_ci_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(dsn)
    await admin.execute(f"CREATE SCHEMA {schema}")
    await admin.close()
    try:
        kernel = Kernel.auto()
        p1 = PgVecRecordSearchProvider(kernel, dsn=dsn, schema=schema)
        await p1.index([{"scope": "s", "kind": "Story", "name": "a", "text": "x"}])
        await p1.close()

        kernel2 = Kernel.auto()
        kernel2.embedding_provider(_WideFake())
        p2 = PgVecRecordSearchProvider(kernel2, dsn=dsn, schema=schema)
        with pytest.raises(ValueError, match="incomparable"):
            await p2.search(scope="s", query_text="x", k=1)
        await p2.close()
    finally:
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        finally:
            await conn.close()
