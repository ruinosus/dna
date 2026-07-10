"""Version retention for record-plane Kinds (s-version-prune-record-plane-churn).

Record-plane Kinds (memories, eval runs, events) churn the version history — the
engrafia hook alone wrote 175k LessonLearned snapshots. The write path caps their
retained history to the last N versions (manifest-plane keeps full history), so a
single doc rewritten thousands of times doesn't drown the authored-content trail.

Tested at two levels:
  1. adapter — ``save_document(version_retention=N)`` keeps only the last N.
  2. kernel  — ``write_document`` of a record-plane Kind applies the cap; a
     manifest-plane Kind keeps everything.
"""
import pytest
import pytest_asyncio

from dna.adapters.sqlalchemy_ import SqlAlchemySource
from dna.kernel import (
    Kernel, VERSION_CHURN_RETENTION, VERSION_CHURN_KINDS,
)
from dna.kernel.capabilities import write_kwarg_support
from dna.kernel.kind_base import KindBase
from dna.kernel.protocols import StorageDescriptor


@pytest_asyncio.fixture
async def src(tmp_path):
    s = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp_path / 'ret.db'}")
    await s.connect()  # run migrations (creates the versions table)
    yield s
    await s.close()


# ── adapter level ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retention_keeps_only_last_n(src):
    for i in range(5):
        await src.save_document("s", "LessonLearned", "m", {"spec": {"i": i}},
                                version_retention=3)
    versions = await src.list_versions("s", "LessonLearned", "m")
    assert len(versions) == 3
    # the 3 kept are the most recent (highest version numbers)
    assert [v["version"] for v in versions] == [5, 4, 3]


@pytest.mark.asyncio
async def test_no_retention_keeps_full_history(src):
    for i in range(5):
        await src.save_document("s", "Agent", "bot", {"spec": {"i": i}})
    versions = await src.list_versions("s", "Agent", "bot")
    assert len(versions) == 5


@pytest.mark.asyncio
async def test_retention_keeps_the_latest_version(src):
    """Pruning keeps the most recent version (the current doc) — never the doc."""
    for i in range(6):
        await src.save_document("s", "LessonLearned", "m", {"spec": {"i": i}},
                                version_retention=3)
    versions = await src.list_versions("s", "LessonLearned", "m")
    assert max(v["version"] for v in versions) == 6  # the last write survives


# ── capability detection ───────────────────────────────────────────────────

def test_sqlite_source_advertises_version_retention(src):
    assert write_kwarg_support(src).version_retention is True


# ── kernel level ───────────────────────────────────────────────────────────

class _ChurnKind(KindBase):
    """A Kind that self-declares churn retention (the per-Kind opt-in path)."""
    api_version = "test.io/v1"
    kind = "TestChurn"
    alias = "test-churn"
    storage = StorageDescriptor.yaml("test-churns")
    version_retention = 3


class _AuthoredKind(KindBase):
    api_version = "test.io/v1"
    kind = "TestAuthored"
    alias = "test-authored"
    storage = StorageDescriptor.yaml("test-authored")


def test_churn_set_excludes_authored_kinds():
    # Story/Spec/ADR are record-plane but AUTHORED — their history must NOT be
    # capped (the bug the curated set fixes vs a blanket plane==record rule).
    for authored in ("Story", "Spec", "ADR", "Feature", "Plan"):
        assert authored not in VERSION_CHURN_KINDS


@pytest.mark.asyncio
async def test_kernel_caps_churn_kind_history(tmp_path):
    s = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp_path / 'k.db'}")
    await s.connect()
    k = Kernel()
    k.kind(_ChurnKind())
    k.kind(_AuthoredKind())
    k.source(s)
    try:
        for i in range(5):
            await k.write_document("s", "TestChurn", "r", {"spec": {"i": i}})
            await k.write_document("s", "TestAuthored", "m", {"spec": {"i": i}})
        churn = await s.list_versions("s", "TestChurn", "r")
        authored = await s.list_versions("s", "TestAuthored", "m")
        assert len(churn) == VERSION_CHURN_RETENTION  # capped via self-declared retention
        assert len(authored) == 5  # full history
    finally:
        await s.close()
