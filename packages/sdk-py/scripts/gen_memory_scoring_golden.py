"""Regenerate the memory-scoring golden fixture (s-memory-verbs).

The fixture (``packages/sdk-py/tests/goldens/memory-scoring.json``) freezes
the canonical outputs of the pure memory-scoring core, asserted by
``tests/test_memory_scoring_golden.py``.

Regenerating is a DELIBERATE act: a diff here means a scoring constant or
formula changed, which changes what an agent recalls and in what order.
Review the diff, do not just commit it.

Run from ``packages/sdk-py``:  ``python scripts/gen_memory_scoring_golden.py``
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from dna.memory.decay import (
    confidence_score_numeric,
    currently_valid,
    ebbinghaus_retention,
    stability_from_spec,
)
from dna.kernel.embedding import fake_embed_one
from dna.memory.ecphory import EngramRef, score_engram
from dna.memory.encoding_context import time_of_day
from dna.memory.memory_type import classify_memory_type
from dna.memory.semantic import (
    cosine_similarity,
    engram_text,
    fuse_semantic_recall,
    semantic_scores_from_vectors,
)

NOW = "2026-07-09T15:00:00+00:00"
_NOW = datetime.fromisoformat(NOW)

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "goldens" / "memory-scoring.json"


def build() -> dict:
    fx: dict = {
        "_note": (
            "Golden fixture for dna.memory pure scoring. "
            "Regenerate via packages/sdk-py/scripts/gen_memory_scoring_golden.py"
        )
    }
    fx["ebbinghaus_retention"] = [
        {"stability_days": s, "days_since_recall": d, "expected": ebbinghaus_retention(s, d)}
        for s, d in [(15, None), (15, 0), (15, 15), (15, 30), (45, 15), (5, 15), (30, 7)]
    ]
    fx["currently_valid"] = [
        {"valid_to": v, "now": NOW, "expected": currently_valid(v, now=_NOW)}
        for v in [
            None, "", "2099-01-01T00:00:00+00:00", "2000-01-01T00:00:00+00:00",
            "not-a-date", "2026-07-09T14:59:59+00:00", "2026-07-09T15:00:01+00:00",
        ]
    ]
    fx["stability_from_spec"] = [
        {"spec": s, "expected": stability_from_spec(s)}
        for s in [
            {"confidence_score": "faint"}, {"confidence_score": "firm"},
            {"confidence_score": "burning"}, {"confidence_score": 1.0},
            {"confidence_score": 5.0}, {"confidence_score": 10.0}, {},
            {"engram_stability_days": 100},
        ]
    ]
    fx["confidence_score_numeric"] = [
        {"spec": s, "expected": confidence_score_numeric(s)}
        for s in [
            {"confidence_score": 3.5}, {"confidence_score": "firm"},
            {"confidence_score": "faint"}, {"confidence_score": "burning"}, {},
        ]
    ]
    fx["classify_memory_type"] = [
        {"spec": s, "expected": classify_memory_type(s)}
        for s in [
            {"summary": "always deep-copy the cache"},
            {"summary": "nunca faça hard-delete"},
            {"area": "Feature/x", "summary": "shipped it"},
            {"summary": "the sky tends to be blue"},
            {"memory_type": "episodic", "summary": "always"},
        ]
    ]
    fx["time_of_day"] = [
        {"hour": h, "expected": time_of_day(datetime(2026, 1, 1, h, tzinfo=timezone.utc))}
        for h in [0, 5, 8, 11, 12, 14, 17, 18, 20, 21, 22, 23]
    ]

    se_cases = [
        {"engram": {"name": "e1", "spec": {"encoding_context": {"area": "Feature/memory"}}},
         "cue_ctx": {"area_inferred": "feature memory"}},
        {"engram": {"name": "e2", "spec": {"summary": "reciprocal rank fusion beats single top"}},
         "cue_ctx": {"query": "rank fusion"}},
        {"engram": {"name": "e3", "spec": {
            "encoding_context": {"area": "auth", "co_topics": ["login", "oauth"]},
            "source_refs": ["s-9"]}},
         "cue_ctx": {"query": "auth", "co_topics": ["login"], "source_refs": ["s-9"]}},
    ]
    out = []
    for c in se_cases:
        s = score_engram(EngramRef(c["engram"]["name"], c["engram"]["spec"]), c["cue_ctx"])
        out.append({**c, "expected_score": s.score, "expected_matched": s.matched_dims})
    fx["score_engram"] = out

    # ── semantic recall (s-memory-semantic-recall) ──────────────────────────
    # Both sides embed the raw TEXTS with their own fake embedder (bit-identical
    # by construction), so these cases pin cosine + engram_text + the full
    # fused ranking end to end.
    cos_cases = [
        ("mutating documents safely", "deep copy before mutating documents"),
        ("mutating documents safely", "banana tropical smoothie"),
        ("reciprocal rank fusion", "reciprocal rank fusion"),
        ("", "anything at all"),
    ]
    fx["cosine_similarity_fake"] = [
        {"text_a": a, "text_b": b,
         "expected": cosine_similarity(fake_embed_one(a), fake_embed_one(b))}
        for a, b in cos_cases
    ]

    et_specs = [
        {"area": "Feature/kernel", "summary": "deep-copy before mutating",
         "affect": "regret", "created_at": "2026-07-01T00:00:00+00:00"},
        {"title": "AAC apps", "body": "long body text", "summary": "short"},
        {},
    ]
    fx["engram_text"] = [{"spec": s, "expected": engram_text(s)} for s in et_specs]

    engrams = [
        {"name": "rem-target", "spec": {
            "area": "Feature/kernel", "summary": "deep-copy before mutating documents",
            "created_at": "2026-07-01T00:00:00+00:00"}},
        {"name": "rem-decoy", "spec": {
            "area": "Feature/ops", "summary": "safely archive old reports nightly",
            "created_at": "2026-07-01T00:00:00+00:00"}},
        {"name": "rem-noise", "spec": {
            "area": "Feature/food", "summary": "banana tropical smoothie recipe",
            "created_at": "2026-07-01T00:00:00+00:00"}},
    ]
    hits = [
        {"name": "rem-decoy", "score": 0.048},
        {"name": "rem-target", "score": 0.033},
        {"name": "rem-noise", "score": 0.020},
    ]
    query = "mutating documents safely"
    refs = [EngramRef(e["name"], e["spec"]) for e in engrams]
    sem = semantic_scores_from_vectors(
        [e["name"] for e in engrams],
        [fake_embed_one(engram_text(e["spec"])) for e in engrams],
        fake_embed_one(query),
    )
    fused = fuse_semantic_recall(hits, refs, query, sem, now=_NOW)
    fx["semantic_recall_fusion"] = [{
        "query": query, "now": NOW, "engrams": engrams, "hits": hits,
        "expected_order": [h["name"] for h in fused],
        "expected_scores": {h["name"]: h["score"] for h in fused},
        "expected_semantic": {h["name"]: h["semantic"] for h in fused if "semantic" in h},
        "expected_rank_ecphory": {
            h["name"]: h["rank_ecphory"] for h in fused if "rank_ecphory" in h
        },
    }]
    return fx


if __name__ == "__main__":
    FIXTURE.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE}")
