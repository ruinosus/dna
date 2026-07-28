"""i-091 — ``recall`` is read-your-writes on a TLS-shaped Postgres DSN.

The reported failure came from a hosted deployment whose source URL ends in
``?ssl=require``: ``recall`` returned ``index_refreshed: false`` with
``index_error: CantChangeRuntimeParamError: parameter "ssl" cannot be changed
now``, so nothing written since the last successful refresh could appear in the
results. The envelope was honest about it — that part is not the defect. The
defect is that the refresh failed at all.

The shape is the whole test: a DSN carrying an ``ssl=`` query param, the same
one the source engine is built from. ``ssl=prefer`` is used rather than
``require`` so the case runs against ANY Postgres (with or without TLS
configured) while still exercising the exact translation that broke —
``ssl`` is not part of asyncpg's DSN vocabulary, so as a *server setting* it
fails identically whether or not the server speaks TLS.

Gated on the shared ``requires_postgres`` marker (``tests/conftest.py``); a
fresh, disposable schema per case, same isolation pattern as the other pgvector
integration modules.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import uuid

import pytest
import pytest_asyncio

pytestmark = pytest.mark.requires_postgres

asyncpg = pytest.importorskip(
    "asyncpg",
    reason="postgres extra not installed (pip install 'dna-sdk[search-pgvector]')",
)

from dna.application.live import LiveDna  # noqa: E402
from dna.application.runtime import recall_impl, remember_impl  # noqa: E402


def _dsn() -> str:
    for k in ("DATABASE_URL", "DNA_PG_TEST_URL", "DNA_PG_TEST_DSN"):
        v = os.environ.get(k)
        if v:
            return v
    raise RuntimeError("no Postgres DSN set")  # pragma: no cover — marker guards


def _with_ssl_param(dsn: str) -> str:
    """The failing production shape: an ``ssl=`` query param on the DSN."""
    return dsn + ("&" if "?" in dsn else "?") + "ssl=prefer"


@pytest_asyncio.fixture
async def live_dna():
    """A live runtime whose search index lives in Postgres, reached by a DSN
    carrying an ``ssl=`` query param — memory itself on a throwaway FS source."""
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.adapters.search.pgvector import PgVecRecordSearchProvider
    from dna.kernel import Kernel

    tmp = tempfile.mkdtemp(prefix="dna-i091-")
    kernel = Kernel.auto()  # deterministic fake embeddings — offline
    kernel.source(FilesystemWritableSource(base_dir=tmp))

    admin_dsn = _dsn()
    schema = f"dna_i091_ci_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(admin_dsn)
    await admin.execute(f"CREATE SCHEMA {schema}")
    await admin.close()

    # One memory ALREADY on disk and NOT in the index — otherwise the refresh
    # has no work to do, never opens a connection, and the case would go green
    # with the bug fully present.
    from dna.memory import remember

    await remember(
        kernel, "i091", name="seed", index=False,
        spec={
            "summary": "a seeded memory", "area": "general",
            "surface_when": ["feature_touched"], "source_refs": ["general"],
            "affect": "triumph",
        },
    )

    provider = PgVecRecordSearchProvider(
        kernel, dsn=_with_ssl_param(admin_dsn), schema=schema,
    )
    kernel.record_search_provider(provider)
    try:
        yield LiveDna(base_scope="i091", kernel=kernel, provider=provider)
    finally:
        await provider.close()
        conn = await asyncpg.connect(admin_dsn)
        try:
            await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        finally:
            await conn.close()
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.asyncio
async def test_recall_refreshes_the_index_on_an_ssl_shaped_dsn(live_dna):
    res = await recall_impl(live_dna, "anything")

    assert res.get("index_error") is None, (
        "the search index could not be refreshed on an ssl= DSN: "
        f"{res.get('index_error')}"
    )
    assert res["index_refreshed"] is True
    assert res["degraded"] is False


@pytest.mark.asyncio
async def test_a_memory_written_a_moment_ago_is_recallable(live_dna):
    """Read-your-writes, the guarantee the swallowed refresh failure removed."""
    await remember_impl(live_dna, "the octopus rearranges its shells at dusk")

    res = await recall_impl(live_dna, "octopus shells")

    assert res["index_refreshed"] is True
    assert any("octopus" in (h.get("summary") or "") for h in res["hits"]), res["hits"]
