"""End-to-end tests for the memory verbs (s-memory-verbs).

Real kernel + filesystem source + the embeddable sqlite-vec provider (fake
embedder, offline). Proves remember→recall hybrid, reconsolidation side-effects,
bi-temporal forget (recall never resurfaces a forgotten memory), and the
deterministic consolidate pass.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

sqlite_vec = pytest.importorskip("sqlite_vec", reason="search-sqlite extra not installed")

from dna.adapters.filesystem.writable import FilesystemWritableSource  # noqa: E402
from dna.adapters.search.sqlite_vec import SqliteVecRecordSearchProvider  # noqa: E402
from dna.kernel import Kernel  # noqa: E402
from dna.memory import consolidate, forget, recall, remember  # noqa: E402

_REASON = "a concrete reason long enough for the affect validator to accept it in full"


def _ll(name: str, area: str, summary: str, affect: str = "triumph") -> dict:
    return {
        "kind": "Engram",
        "name": name,
        "spec": {
            "area": area,
            "surface_when": ["feature_touched"],
            "source_refs": ["s-1"],
            "affect": affect,
            "affect_reason": _REASON,
            "summary": summary,
        },
    }


@pytest.fixture
def kernel_with_provider(tmp_path):
    base = tmp_path / "src"
    base.mkdir()
    kernel = Kernel.auto()
    src = FilesystemWritableSource(base_dir=str(base))
    Kernel.auto(source=src)
    kernel.source(src)
    prov = SqliteVecRecordSearchProvider(kernel, db_path=str(tmp_path / "mem.db"))
    kernel.record_search_provider(prov)
    yield kernel
    prov.close()


@pytest.mark.asyncio
async def test_remember_stamps_and_indexes(kernel_with_provider):
    kernel = kernel_with_provider
    out = await remember(kernel, "demo", **_ll("rem-a", "Feature/memory", "memory recall works"))
    assert out["indexed"] is True
    got = await kernel.get_instance("demo", "Engram", "rem-a")
    spec = got["spec"]
    # deterministic enrichment
    assert spec["memory_type"] in ("episodic", "semantic", "procedural")
    assert spec.get("encoding_context", {}).get("area") == "Feature/memory"
    assert spec.get("valid_from")  # bi-temporal seed


@pytest.mark.asyncio
async def test_recall_hybrid_ranks_and_reconsolidates(kernel_with_provider):
    kernel = kernel_with_provider
    await remember(kernel, "demo", **_ll("rem-mem", "Feature/memory", "vector embedding recall cognitive memory"))
    await remember(kernel, "demo", **_ll("rem-banana", "Feature/food", "banana tropical yellow fruit smoothie"))
    await remember(kernel, "demo", **_ll("rem-fusion", "Feature/search", "hybrid search fusion reciprocal rank"))

    res = await recall(kernel, "demo", "memory recall cognitive", k=3, actor="claude-code")
    assert res["degraded"] is False  # provider present → hybrid
    assert res["hits"][0]["name"] == "rem-mem"

    # reconsolidation: cue appended + surface_count bumped on the surfaced memory
    got = await kernel.get_instance("demo", "Engram", "rem-mem")
    assert got["spec"]["surface_count"] == 1
    assert len(got["spec"]["cues_history"]) == 1
    assert got["spec"]["cues_history"][0]["actor"] == "claude-code"


@pytest.mark.asyncio
async def test_forget_is_bitemporal_never_deletes(kernel_with_provider):
    kernel = kernel_with_provider
    await remember(kernel, "demo", **_ll("rem-x", "Feature/memory", "memory recall cognitive"))

    out = await forget(kernel, "demo", "rem-x")
    assert out["valid_to"]
    assert out["already_forgotten"] is False

    # NOT deleted — still auditable on disk
    got = await kernel.get_instance("demo", "Engram", "rem-x")
    assert got is not None
    assert got["spec"]["valid_to"] == out["valid_to"]

    # recall never resurfaces a forgotten memory (bi-temporal correctness)
    res = await recall(kernel, "demo", "memory recall cognitive", k=5, reconsolidate=False)
    assert "rem-x" not in [h["name"] for h in res["hits"]]

    # idempotent — re-forget keeps the original valid_to
    again = await forget(kernel, "demo", "rem-x")
    assert again["already_forgotten"] is True
    assert again["valid_to"] == out["valid_to"]


@pytest.mark.asyncio
async def test_forget_records_supersession(kernel_with_provider):
    kernel = kernel_with_provider
    await remember(kernel, "demo", **_ll("rem-old", "Feature/memory", "old belief"))
    await forget(kernel, "demo", "rem-old", superseded_by="rem-new")
    got = await kernel.get_instance("demo", "Engram", "rem-old")
    assert got["spec"]["superseded_by_memory"] == "rem-new"


@pytest.mark.asyncio
async def test_consolidate_detects_stale_without_llm(kernel_with_provider):
    kernel = kernel_with_provider
    await remember(kernel, "demo", **_ll("rem-fresh", "Feature/memory", "fresh memory"))
    await remember(kernel, "demo", **_ll("rem-ancient", "Feature/memory", "ancient memory"))

    # age one memory into oblivion (deterministic — no wall clock in assertions)
    old = await kernel.get_instance("demo", "Engram", "rem-ancient")
    old["spec"]["last_surfaced"] = "2000-01-01T00:00:00+00:00"
    # NOTE: was the string "faint" — a shape-broken value the write path used
    # to accept silently (i-008); the generic write validation now vetoes it
    # (confidence_score is `type: number` in the Kind schema).
    old["spec"]["confidence_score"] = 0.1
    await kernel.write_instance("demo", "Engram", "rem-ancient", old, invalidate_mode="doc")

    report = await consolidate(kernel, "demo", apply=False)
    stale_names = [s["name"] for s in report["stale"]]
    assert "rem-ancient" in stale_names
    assert "rem-fresh" not in stale_names
    assert report["archived"] == 0  # report-only

    # apply=True soft-forgets the stale ones (bi-temporal, still not deleted)
    report2 = await consolidate(kernel, "demo", apply=True)
    assert report2["archived"] >= 1
    got = await kernel.get_instance("demo", "Engram", "rem-ancient")
    assert got is not None  # NEVER deleted
    assert got["spec"].get("valid_to")  # invalidated


@pytest.mark.asyncio
async def test_consolidate_without_dry_run_keeps_the_legacy_shape(kernel_with_provider):
    """Total backward compatibility: no ``dry_run`` → the report carries EXACTLY
    the pre-dry-run keys (no additive drift for existing consumers)."""
    kernel = kernel_with_provider
    await remember(kernel, "demo", **_ll("rem-shape", "Feature/memory", "shape memory"))
    report = await consolidate(kernel, "demo", apply=False)
    assert set(report) == {"evaluated", "stale", "archived", "applied"}


@pytest.mark.asyncio
async def test_consolidate_dry_run_reports_actions_with_zero_effect(kernel_with_provider):
    """``dry_run=True`` returns the per-memory diff (action + deterministic
    reason) and NEVER writes — even with ``apply=True`` in the same call."""
    kernel = kernel_with_provider
    await remember(kernel, "demo", **_ll("rem-keep", "Feature/memory", "fresh kept memory"))
    await remember(kernel, "demo", **_ll("rem-gone", "Feature/memory", "ancient stale memory"))
    old = await kernel.get_instance("demo", "Engram", "rem-gone")
    old["spec"]["last_surfaced"] = "2000-01-01T00:00:00+00:00"
    old["spec"]["confidence_score"] = 0.1
    await kernel.write_instance("demo", "Engram", "rem-gone", old, invalidate_mode="doc")
    await remember(kernel, "demo", **_ll("rem-dead", "Feature/memory", "already forgotten memory"))
    await forget(kernel, "demo", "rem-dead")

    report = await consolidate(kernel, "demo", apply=True, dry_run=True)

    # dry_run wins over apply: reported as not applied, and nothing was written.
    assert report["dry_run"] is True
    assert report["applied"] is False
    assert report["archived"] == 0
    still = await kernel.get_instance("demo", "Engram", "rem-gone")
    assert not still["spec"].get("valid_to")

    by_name = {a["name"]: a for a in report["actions"]}
    assert by_name["rem-keep"]["action"] == "retain"
    assert by_name["rem-gone"]["action"] == "expire"
    assert by_name["rem-dead"]["action"] == "already_expired"
    # deterministic reasons carry the numbers a diff UI shows.
    assert "floor 0.15" in by_name["rem-keep"]["reason"]
    assert by_name["rem-gone"]["retention"] < 0.15
    assert "valid_to" in by_name["rem-dead"]["reason"]
    # the legacy keys are still there (superset, not a new shape).
    assert [s["name"] for s in report["stale"]] == ["rem-gone"]
    # actions are sorted by name (stable for goldens/diffs).
    assert [a["name"] for a in report["actions"]] == sorted(by_name)


@pytest.mark.asyncio
async def test_consolidate_dry_run_surfaces_merge_candidates(kernel_with_provider):
    """Two lexically-overlapping memories show up as ONE merge group with a
    deterministic supersede proposal; the forgotten never participate."""
    kernel = kernel_with_provider
    await remember(kernel, "demo", **_ll(
        "rem-dup-a", "Feature/deploy", "deploy broke cache invalidation kernel"))
    await remember(kernel, "demo", **_ll(
        "rem-dup-b", "Feature/deploy", "deploy broke cache invalidation portal"))
    await remember(kernel, "demo", **_ll(
        "rem-other", "Feature/food", "banana tropical smoothie recipe"))

    report = await consolidate(kernel, "demo", dry_run=True, merge_overlap_floor=0.4)
    assert len(report["merge_candidates"]) == 1
    grp = report["merge_candidates"][0]
    assert grp["names"] == ["rem-dup-a", "rem-dup-b"]
    assert grp["canonical"] in grp["names"]
    assert grp["strategy"] == "supersede"
    assert grp["synthesized"] is False
    assert grp["proposed_text"]
    assert grp["pairs"][0]["overlap"] >= 0.4

    # a proposal is NOT an application: both memories are still valid.
    for name in ("rem-dup-a", "rem-dup-b"):
        doc = await kernel.get_instance("demo", "Engram", name)
        assert not doc["spec"].get("valid_to")


@pytest.mark.asyncio
async def test_recall_degrades_lexical_without_provider(tmp_path):
    """No provider registered → recall still works via the kernel's honest
    lexical fallback (degraded=True), and bi-temporality still holds."""
    base = tmp_path / "src"
    base.mkdir()
    kernel = Kernel.auto()
    src = FilesystemWritableSource(base_dir=str(base))
    Kernel.auto(source=src)
    kernel.source(src)  # NO provider

    await remember(kernel, "demo", **_ll("rem-lex", "Feature/memory", "memory recall cognitive"), index=False)
    res = await recall(kernel, "demo", "memory recall cognitive", k=5, reconsolidate=False)
    assert res["degraded"] is True
    assert "rem-lex" in [h["name"] for h in res["hits"]]
