"""The public RecordSearchProvider conformance kit × the sqlite-vec provider.

Runs the whole ``record_search_conformance_suite`` against
``SqliteVecRecordSearchProvider`` with the deterministic ``FakeEmbeddingProvider``
floor — fully offline, no network, no ONNX. Skips cleanly when the
``search-sqlite`` extra (the ``sqlite-vec`` package) is not installed, so the
default CI install without the extra doesn't fail; the python CI job installs
the extra so these run for real.
"""
from __future__ import annotations

import os
import shutil
import tempfile

import pytest

sqlite_vec = pytest.importorskip(
    "sqlite_vec",
    reason="search-sqlite extra not installed (pip install 'dna-sdk[search-sqlite]')",
)

from dna.testing import record_search_conformance_suite  # noqa: E402


async def _sqlite_vec_factory():
    from dna.kernel import Kernel
    from dna.adapters.search.sqlite_vec import SqliteVecRecordSearchProvider

    kernel = Kernel.auto()  # no embedding provider registered → fake floor
    tmp = tempfile.mkdtemp(prefix="dna-search-kit-")
    provider = SqliteVecRecordSearchProvider(kernel, db_dir=tmp)

    async def cleanup() -> None:
        provider.close()
        shutil.rmtree(tmp, ignore_errors=True)

    return provider, cleanup


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    record_search_conformance_suite(_sqlite_vec_factory),
    ids=lambda c: c.name,
)
async def test_record_search_conformance(case):
    await case.run()


@pytest.mark.asyncio
async def test_programmatic_runner_reports_all_pass():
    from dna.testing import run_record_search_conformance

    report = await run_record_search_conformance(_sqlite_vec_factory)
    report.raise_if_failed()
    assert report.ok
    assert "index_search_round_trip" in report.passed
    assert "tenant_overlay_shadows_base" in report.passed


@pytest.mark.asyncio
async def test_migration_owns_schema_and_is_idempotent():
    """The store schema is migration-owned (closes f-embeddings-ddl-debt): the
    control table records the applied version, and a second connect against the
    same file applies nothing."""
    from dna.kernel import Kernel
    from dna.adapters.search.sqlite_vec import SqliteVecRecordSearchProvider
    from dna.adapters.search.migrations import build_migrations

    kernel = Kernel.auto()
    fd, path = tempfile.mkstemp(prefix="dna-search-mig-", suffix=".db")
    os.close(fd)
    try:
        p1 = SqliteVecRecordSearchProvider(kernel, db_path=path)
        await p1.index([{  # forces connect → migrate
            "scope": "s", "kind": "Story", "name": "a", "text": "hello world",
        }])
        conn = p1._cached_conn("s")
        applied = [r["version"] for r in conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()]
        assert applied == sorted(build_migrations(kernel.embedding_dims)), (
            "every migration version must be recorded in the control table"
        )
        # identity pinned
        meta = {r["key"]: r["value"] for r in conn.execute(
            "SELECT key, value FROM search_meta"
        ).fetchall()}
        assert meta["embedding_dims"] == str(kernel.embedding_dims)
        assert meta["embedding_model_id"] == kernel.embedding_model_id
        p1.close()

        # Re-open the SAME file: migrations already applied → no re-apply, and
        # previously indexed data is still searchable.
        p2 = SqliteVecRecordSearchProvider(kernel, db_path=path)
        hits = await p2.search(scope="s", query_text="hello world", k=5)
        assert any(h["name"] == "a" for h in hits)
        p2.close()
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


@pytest.mark.asyncio
async def test_identity_mismatch_refuses_incomparable_vectors():
    """A store built for one embedding space refuses a provider on another —
    never silently mixes incomparable vectors."""
    from dna.kernel import Kernel
    from dna.adapters.search.sqlite_vec import SqliteVecRecordSearchProvider

    class _WideFake:
        model_id = "dna-fake-hash-v1"
        dims = 999

        async def embed(self, texts):
            return [[0.0] * self.dims for _ in texts]

    kernel = Kernel.auto()
    fd, path = tempfile.mkstemp(prefix="dna-search-id-", suffix=".db")
    os.close(fd)
    try:
        p1 = SqliteVecRecordSearchProvider(kernel, db_path=path)
        await p1.index([{"scope": "s", "kind": "Story", "name": "a", "text": "x"}])
        p1.close()

        kernel2 = Kernel.auto()
        kernel2.embedding_provider(_WideFake())
        p2 = SqliteVecRecordSearchProvider(kernel2, db_path=path)
        with pytest.raises(ValueError, match="incomparable"):
            await p2.search(scope="s", query_text="x", k=1)
        p2.close()
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
