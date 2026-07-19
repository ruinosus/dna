"""Version retention for record-plane Kinds (s-version-prune-record-plane-churn).

Record-plane Kinds (memories, eval runs, events) churn the version history — the
engrafia hook alone wrote 175k Engram snapshots. The write path caps their
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
        await src.save_document("s", "Engram", "m", {"spec": {"i": i}},
                                version_retention=3)
    versions = await src.list_versions("s", "Engram", "m")
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
        await src.save_document("s", "Engram", "m", {"spec": {"i": i}},
                                version_retention=3)
    versions = await src.list_versions("s", "Engram", "m")
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


def test_version_churn_kinds_includes_engram():
    """s-engram-rename (2026-07-19) fail-open pin: forgetting to keep Engram
    in this curated set doesn't error anywhere — it silently reverts to full
    version history (the exact 175k-snapshot bug the set exists to prevent).
    See test_kernel_caps_engram_history_via_curated_set below for the
    functional (write-path) proof that this membership is actually load-
    bearing, not just a name in a set nothing reads."""
    assert "Engram" in VERSION_CHURN_KINDS


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


@pytest.mark.asyncio
async def test_kernel_caps_engram_history_via_curated_set(tmp_path):
    """Functional, end-to-end proof for the REAL Engram Kind — not the
    synthetic ``_ChurnKind`` above (which self-declares ``version_retention``
    on the class, the PER-KIND opt-in path). Engram's KindPort is a
    descriptor-synthesized ``DeclarativeKindPort`` (registered by
    HelixExtension from ``helix/kinds/engram.kind.yaml``) that carries no
    ``version_retention`` attribute at all — so
    ``write_pipeline.py``'s ``getattr(_kp, "version_retention", None)`` is
    always None for it, and the cap can ONLY come from the CURATED
    ``VERSION_CHURN_KINDS`` membership tested above. Writing the SAME Engram
    doc repeatedly through the real kernel + HelixExtension registration and
    asserting the retained version count is capped is the only test that
    actually exercises that code path (mirrors
    test_write_path_despecialize.py::
    test_bitemporal_guard_fires_through_write_document for the sibling
    bitemporal-guard fail-open set).
    """
    from dna.extensions.helix import HelixExtension

    s = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp_path / 'engram-churn.db'}")
    await s.connect()
    k = Kernel()
    k.load(HelixExtension())
    k.source(s)
    try:
        base_spec = {
            "area": "Feature/version-retention",
            "surface_when": ["feature_touched"],
            "source_refs": ["s-version-prune-record-plane-churn"],
            "affect": "triumph",
        }

        def _raw(i: int) -> dict:
            return {
                "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Engram",
                "metadata": {"name": "rem-churn"},
                "spec": {**base_spec, "summary": f"iteration {i}"},
            }

        total_writes = VERSION_CHURN_RETENTION + 4
        for i in range(total_writes):
            await k.write_document("s", "Engram", "rem-churn", _raw(i))

        versions = await s.list_versions("s", "Engram", "rem-churn")
        assert len(versions) == VERSION_CHURN_RETENTION, (
            f"Engram's version history must be capped at "
            f"VERSION_CHURN_RETENTION ({VERSION_CHURN_RETENTION}) via the "
            f"curated VERSION_CHURN_KINDS set, got {len(versions)} retained "
            f"versions after {total_writes} writes"
        )
        assert max(v["version"] for v in versions) == total_writes  # latest survives
    finally:
        await s.close()
