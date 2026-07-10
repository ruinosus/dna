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
        "kind": "LessonLearned",
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
    got = await kernel.get_document("demo", "LessonLearned", "rem-a")
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
    got = await kernel.get_document("demo", "LessonLearned", "rem-mem")
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
    got = await kernel.get_document("demo", "LessonLearned", "rem-x")
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
    got = await kernel.get_document("demo", "LessonLearned", "rem-old")
    assert got["spec"]["superseded_by_memory"] == "rem-new"


@pytest.mark.asyncio
async def test_consolidate_detects_stale_without_llm(kernel_with_provider):
    kernel = kernel_with_provider
    await remember(kernel, "demo", **_ll("rem-fresh", "Feature/memory", "fresh memory"))
    await remember(kernel, "demo", **_ll("rem-ancient", "Feature/memory", "ancient memory"))

    # age one memory into oblivion (deterministic — no wall clock in assertions)
    old = await kernel.get_document("demo", "LessonLearned", "rem-ancient")
    old["spec"]["last_surfaced"] = "2000-01-01T00:00:00+00:00"
    # NOTE: was the string "faint" — a shape-broken value the write path used
    # to accept silently (i-008); the generic write validation now vetoes it
    # (confidence_score is `type: number` in the Kind schema).
    old["spec"]["confidence_score"] = 0.1
    await kernel.write_document("demo", "LessonLearned", "rem-ancient", old, invalidate_mode="doc")

    report = await consolidate(kernel, "demo", apply=False)
    stale_names = [s["name"] for s in report["stale"]]
    assert "rem-ancient" in stale_names
    assert "rem-fresh" not in stale_names
    assert report["archived"] == 0  # report-only

    # apply=True soft-forgets the stale ones (bi-temporal, still not deleted)
    report2 = await consolidate(kernel, "demo", apply=True)
    assert report2["archived"] >= 1
    got = await kernel.get_document("demo", "LessonLearned", "rem-ancient")
    assert got is not None  # NEVER deleted
    assert got["spec"].get("valid_to")  # invalidated


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
