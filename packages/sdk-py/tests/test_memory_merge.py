"""Merge candidates — the pure half of the consolidate dry-run diff (i-050).

``dna.memory.merge`` proposes the fusion of overlapping memories with NO LLM:
lexical Jaccard detection, union-find grouping, a deterministic canonical
election, and a ``supersede`` proposal per group. The external synthesis seam
(``MergeScribe``) is exercised here as a plain callable — proving the contract
without any model near the kernel.
"""
from __future__ import annotations

from datetime import datetime, timezone

from dna.memory.merge import (
    DEFAULT_OVERLAP_FLOOR,
    canonical_name,
    merge_candidates_report,
    merge_groups,
    merge_tokens,
    overlap_score,
)

_NOW = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)


def _spec(summary: str, **extra) -> dict:
    return {"summary": summary, **extra}


# ── tokens + overlap ────────────────────────────────────────────────────────


def test_merge_tokens_normalize_the_semantic_planes():
    spec = _spec("Deploy broke the Cache!", area="Feature/kernel", body="L2 cache ref")
    toks = merge_tokens(spec)
    # lowercased, punctuation split, short tokens ("l2") dropped.
    assert {"deploy", "broke", "cache", "feature", "kernel", "ref"} <= toks
    assert "l2" not in toks
    assert "the" not in toks


def test_overlap_score_is_jaccard_and_empty_is_zero():
    a = frozenset({"cache", "deploy", "kernel"})
    b = frozenset({"cache", "deploy", "portal"})
    assert overlap_score(a, b) == 2 / 4
    # a memory with no comparable text overlaps with NOTHING, never everything.
    assert overlap_score(frozenset(), b) == 0.0
    assert overlap_score(a, frozenset()) == 0.0


# ── grouping (union-find) ───────────────────────────────────────────────────


def test_merge_groups_connects_transitively_and_skips_singletons():
    members = [
        ("rem-a", _spec("deploy broke cache invalidation kernel")),
        ("rem-b", _spec("deploy broke cache invalidation portal")),
        ("rem-c", _spec("banana tropical smoothie recipe")),
    ]
    groups = merge_groups(members, overlap_floor=0.4)
    assert len(groups) == 1
    assert groups[0]["names"] == ["rem-a", "rem-b"]
    (pair,) = groups[0]["pairs"]
    assert pair["a"] == "rem-a" and pair["b"] == "rem-b"
    assert pair["overlap"] > 0.4
    assert "cache" in pair["shared_terms"]


def test_merge_groups_floor_gates_the_edge():
    members = [
        ("rem-a", _spec("deploy broke cache invalidation kernel")),
        ("rem-b", _spec("deploy broke cache invalidation portal")),
    ]
    assert merge_groups(members, overlap_floor=0.99) == []
    # the default floor is the exported constant (a portal can lower it).
    assert 0.0 < DEFAULT_OVERLAP_FLOOR <= 1.0


# ── canonical election ──────────────────────────────────────────────────────


def test_canonical_prefers_confidence_then_recency_then_name():
    specs = {
        "rem-old-firm": _spec("x", confidence_score=3.0,
                              created_at="2026-01-01T00:00:00+00:00"),
        "rem-new-faint": _spec("x", confidence_score=1.0,
                               created_at="2026-08-01T00:00:00+00:00"),
    }
    # higher confidence wins over recency ...
    assert canonical_name(list(specs), specs, now=_NOW) == "rem-old-firm"
    # ... equal confidence → the NEWER memory wins ...
    specs["rem-new-faint"]["confidence_score"] = 3.0
    assert canonical_name(list(specs), specs, now=_NOW) == "rem-new-faint"
    # ... and a full tie falls back to the smallest name (total order).
    tied = {"rem-b": _spec("x"), "rem-a": _spec("x")}
    assert canonical_name(list(tied), tied, now=_NOW) == "rem-a"


# ── the structured report (the DiffBloco input) ─────────────────────────────


def test_report_proposes_supersede_deterministically():
    members = [
        ("rem-dup-1", _spec("deploy broke cache invalidation kernel",
                            confidence_score=5.0, tags=["deploy"])),
        ("rem-dup-2", _spec("deploy broke cache invalidation portal",
                            confidence_score=1.0, tags=["portal"])),
        ("rem-solo", _spec("banana tropical smoothie recipe")),
    ]
    report = merge_candidates_report(members, overlap_floor=0.4, now=_NOW)
    assert len(report) == 1
    grp = report[0]
    assert grp["names"] == ["rem-dup-1", "rem-dup-2"]
    assert grp["canonical"] == "rem-dup-1"          # highest confidence
    assert grp["superseded"] == ["rem-dup-2"]
    assert grp["strategy"] == "supersede"
    assert grp["synthesized"] is False
    # the proposal keeps the canonical's text and unions the group's tags.
    assert grp["proposed_text"] == "deploy broke cache invalidation kernel"
    assert grp["proposed_spec"]["tags"] == ["deploy", "portal"]
    # the members' own specs are untouched (proposal, never application).
    assert members[0][1]["tags"] == ["deploy"]


def test_report_scribe_synthesizes_and_fails_soft():
    members = [
        ("rem-dup-1", _spec("deploy broke cache invalidation kernel")),
        ("rem-dup-2", _spec("deploy broke cache invalidation portal")),
    ]

    def scribe(group):
        # the MergeScribe contract: specs in, fused spec (with summary) out.
        assert group[0]["summary"].endswith("kernel")  # canonical first
        return {"summary": "deploy broke cache invalidation (kernel + portal)"}

    fused = merge_candidates_report(members, overlap_floor=0.4, scribe=scribe, now=_NOW)
    assert fused[0]["strategy"] == "synthesize"
    assert fused[0]["synthesized"] is True
    assert fused[0]["proposed_text"] == "deploy broke cache invalidation (kernel + portal)"

    def broken(group):
        raise RuntimeError("model unavailable")

    degraded = merge_candidates_report(
        members, overlap_floor=0.4, scribe=broken, now=_NOW)
    # a raising scribe degrades to the deterministic proposal — never breaks.
    assert degraded[0]["strategy"] == "supersede"
    assert degraded[0]["synthesized"] is False
    assert "RuntimeError" in degraded[0]["scribe_error"]
