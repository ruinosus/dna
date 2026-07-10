"""The public memory conformance kit × the builtin stacks
(s-memory-conformance-kit).

Runs ``memory_conformance_suite`` exactly the way an adapter author would —
through the PUBLIC ``dna.testing`` surface, factories only — against:

* a filesystem-source kernel WITHOUT a search provider (the lexical/degraded
  branch; provider-requiring cases skip);
* the same kernel WITH the embeddable sqlite-vec provider (the hybrid +
  semantic branch; the no-provider case skips). Skips cleanly when the
  ``search-sqlite`` extra is absent — the python CI job installs it.

Plus the pure scoring suite (``memory_scoring_conformance_suite``) on its
default fake floor AND on a trivial custom embedder, proving the
embedder-factory surface. Everything offline, all timestamps simulated.
The pgvector leg lives in ``test_pgvector_memory_conformance.py``
(``requires_postgres``, same pattern as the search kit's pgvector leg).
"""
from __future__ import annotations

import shutil
import tempfile

import pytest

from dna.testing import (
    memory_conformance_suite,
    memory_scoring_conformance_suite,
    run_memory_conformance,
    run_memory_scoring_conformance,
)


async def _fs_kernel_factory():
    """Kernel over a fresh writable filesystem source — NO search provider."""
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.kernel import Kernel

    tmp = tempfile.mkdtemp(prefix="dna-memkit-fs-")
    kernel = Kernel.auto()
    kernel.source(FilesystemWritableSource(base_dir=tmp))

    async def cleanup() -> None:
        shutil.rmtree(tmp, ignore_errors=True)

    return kernel, cleanup


async def _sqlite_vec_kernel_factory():
    """Kernel over a fresh filesystem source + the sqlite-vec provider
    (deterministic fake embedding floor — fully offline)."""
    from dna.adapters.search.sqlite_vec import SqliteVecRecordSearchProvider

    kernel, fs_cleanup = await _fs_kernel_factory()
    tmp = tempfile.mkdtemp(prefix="dna-memkit-vec-")
    provider = SqliteVecRecordSearchProvider(kernel, db_dir=tmp)
    kernel.record_search_provider(provider)

    async def cleanup() -> None:
        provider.close()
        shutil.rmtree(tmp, ignore_errors=True)
        await fs_cleanup()

    return kernel, cleanup


# ---------------------------------------------------------------------------
# verb suite × filesystem kernel (lexical branch)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    memory_conformance_suite(_fs_kernel_factory),
    ids=lambda c: c.name,
)
async def test_memory_conformance_lexical(case):
    await case.run()


# ---------------------------------------------------------------------------
# verb suite × sqlite-vec kernel (hybrid + semantic branch)
# ---------------------------------------------------------------------------

sqlite_vec = pytest.importorskip(
    "sqlite_vec",
    reason="search-sqlite extra not installed (pip install 'dna-sdk[search-sqlite]')",
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    memory_conformance_suite(_sqlite_vec_kernel_factory),
    ids=lambda c: c.name,
)
async def test_memory_conformance_sqlite_vec(case):
    await case.run()


@pytest.mark.asyncio
async def test_programmatic_runner_covers_both_branches():
    """The programmatic runner reports every case; between the two builtin
    factories, ALL ten cases pass somewhere (capability skips are symmetric:
    what one branch skips, the other proves)."""
    lexical = await run_memory_conformance(_fs_kernel_factory)
    hybrid = await run_memory_conformance(_sqlite_vec_kernel_factory)
    lexical.raise_if_failed()
    hybrid.raise_if_failed()
    assert lexical.ok and hybrid.ok
    assert [n for n, _ in lexical.skipped] == [
        "semantic_fusion_activates", "backfill_index_is_idempotent",
    ]
    assert [n for n, _ in hybrid.skipped] == ["lexical_fallback_degrades_honestly"]
    from dna.testing.memory_conformance import _CASES  # internal: exhaustiveness pin
    assert set(lexical.passed) | set(hybrid.passed) == {n for n, _, _ in _CASES}


# ---------------------------------------------------------------------------
# pure scoring suite — fake floor + a custom embedder through the factory
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    memory_scoring_conformance_suite(),
    ids=lambda c: c.name,
)
async def test_memory_scoring_conformance_default_floor(case):
    await case.run()


async def _custom_embedder_factory():
    """A deliberately trivial custom embedder (EmbeddingPort-shaped) built on
    the deterministic fake floor — proves the factory surface end-to-end,
    including cleanup."""
    from dna.kernel.embedding import fake_embed_one

    class _TrivialEmbedder:
        model_id = "kit-trivial-v1"
        dims = 384
        closed = False

        async def embed(self, texts):
            return [fake_embed_one(t, self.dims) for t in texts]

    embedder = _TrivialEmbedder()

    async def cleanup() -> None:
        embedder.closed = True

    return embedder, cleanup


@pytest.mark.asyncio
async def test_memory_scoring_conformance_custom_embedder():
    report = await run_memory_scoring_conformance(_custom_embedder_factory)
    report.raise_if_failed()
    assert report.ok and not report.skipped
    assert "semantic_hook_lifts_paraphrase" in report.passed
