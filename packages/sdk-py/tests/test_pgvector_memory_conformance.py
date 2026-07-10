"""The public memory conformance kit × the pgvector provider
(s-memory-conformance-kit).

Runs the whole ``memory_conformance_suite`` with the memory verbs backed by
``PgVecRecordSearchProvider`` — offline fake embeddings, real Postgres. The
SAME ten cases the sqlite-vec stack passes (the no-provider case skips):
that's the point of the port — one contract, many stores.

Gated on a Postgres DSN via the shared ``requires_postgres`` marker
(``tests/conftest.py``): skips cleanly with no DB, runs FOR REAL in the CI
``postgres`` job (pgvector-enabled ``pgvector/pgvector:pg16`` image). Each
case gets a FRESH filesystem source AND a fresh, disposable Postgres schema
(``dna_memkit_ci_<uuid>``) created before and dropped after — same isolation
pattern as ``test_pgvector_search_conformance.py``.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import uuid

import pytest

pytestmark = pytest.mark.requires_postgres

asyncpg = pytest.importorskip(
    "asyncpg",
    reason="postgres extra not installed (pip install 'dna-sdk[search-pgvector]')",
)

from dna.testing import memory_conformance_suite, run_memory_conformance  # noqa: E402


def _dsn() -> str:
    for k in ("DATABASE_URL", "DNA_PG_TEST_URL", "DNA_PG_TEST_DSN"):
        v = os.environ.get(k)
        if v:
            return v
    raise RuntimeError("no Postgres DSN set")  # pragma: no cover — marker guards


async def _pgvector_kernel_factory():
    """Kernel over a fresh filesystem source, memory search backed by a
    PgVecRecordSearchProvider on a disposable schema."""
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.adapters.search.pgvector import PgVecRecordSearchProvider
    from dna.kernel import Kernel

    tmp = tempfile.mkdtemp(prefix="dna-memkit-pg-")
    kernel = Kernel.auto()  # no embedding provider → deterministic fake floor
    kernel.source(FilesystemWritableSource(base_dir=tmp))

    dsn = _dsn()
    schema = f"dna_memkit_ci_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(dsn)
    await admin.execute(f"CREATE SCHEMA {schema}")
    await admin.close()

    provider = PgVecRecordSearchProvider(kernel, dsn=dsn, schema=schema)
    kernel.record_search_provider(provider)

    async def cleanup() -> None:
        await provider.close()
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        finally:
            await conn.close()
        shutil.rmtree(tmp, ignore_errors=True)

    return kernel, cleanup


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    memory_conformance_suite(_pgvector_kernel_factory),
    ids=lambda c: c.name,
)
async def test_pgvector_memory_conformance(case):
    await case.run()


@pytest.mark.asyncio
async def test_programmatic_runner_reports_all_pass():
    report = await run_memory_conformance(_pgvector_kernel_factory)
    report.raise_if_failed()
    assert report.ok
    assert "semantic_fusion_activates" in report.passed
    assert "backfill_index_is_idempotent" in report.passed
    assert [n for n, _ in report.skipped] == ["lexical_fallback_degrades_honestly"]
