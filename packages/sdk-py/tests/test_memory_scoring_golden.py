"""Memory scoring core — golden lock on ten pure surfaces (s-memory-verbs).

Runs every case in ``tests/goldens/memory-scoring.json`` against the Python
pure-scoring core. This is the numeric heart of recall — the values are
load-bearing for what an agent remembers and in what order:

  - ``ebbinghaus_retention`` — the forgetting curve
  - ``currently_valid`` — bitemporal validity
  - ``stability_from_spec`` / ``confidence_score_numeric``
  - ``classify_memory_type`` / ``time_of_day``
  - ``score_engram`` — ecphory scoring + matched dimensions
  - ``cosine_similarity`` / ``engram_text`` / ``fuse_semantic_recall``

History: this began as a Py↔TS parity harness and the fixture lived in
``packages/sdk-ts``. The TypeScript SDK was frozen (tag ``sdk-ts-final``), but
the suite never depended on TS for its value: every assertion above is a lock
on PYTHON behavior that TS merely rode along with. The fixture moved into this
package and the suite stayed.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from dna.memory.decay import (
    confidence_score_numeric,
    currently_valid,
    ebbinghaus_retention,
    stability_from_spec,
)
from dna.memory.ecphory import EngramRef, score_engram
from dna.memory.encoding_context import time_of_day
from dna.memory.memory_type import classify_memory_type

FIXTURE = Path(__file__).parent / "goldens" / "memory-scoring.json"

_FX = json.loads(FIXTURE.read_text(encoding="utf-8"))


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def test_ebbinghaus_retention_golden():
    for c in _FX["ebbinghaus_retention"]:
        got = ebbinghaus_retention(c["stability_days"], c["days_since_recall"])
        assert got == pytest.approx(c["expected"], abs=1e-12), c


def test_currently_valid_golden():
    for c in _FX["currently_valid"]:
        got = currently_valid(c["valid_to"], now=_dt(c["now"]))
        assert got == c["expected"], c


def test_stability_from_spec_golden():
    for c in _FX["stability_from_spec"]:
        assert stability_from_spec(c["spec"]) == pytest.approx(c["expected"], abs=1e-12), c


def test_confidence_score_numeric_golden():
    for c in _FX["confidence_score_numeric"]:
        assert confidence_score_numeric(c["spec"]) == pytest.approx(c["expected"], abs=1e-12), c


def test_classify_memory_type_golden():
    for c in _FX["classify_memory_type"]:
        assert classify_memory_type(c["spec"]) == c["expected"], c


def test_time_of_day_golden():
    for c in _FX["time_of_day"]:
        assert time_of_day(datetime(2026, 1, 1, c["hour"])) == c["expected"], c



def test_score_engram_golden():
    for c in _FX["score_engram"]:
        s = score_engram(EngramRef(c["engram"]["name"], c["engram"]["spec"]), c["cue_ctx"])
        assert s.score == pytest.approx(c["expected_score"], abs=1e-9), c
        assert s.matched_dims == c["expected_matched"], c


# ── semantic recall (s-memory-semantic-recall) ──────────────────────────────


def test_cosine_similarity_fake_golden():
    from dna.kernel.embedding import fake_embed_one
    from dna.memory.semantic import cosine_similarity

    for c in _FX["cosine_similarity_fake"]:
        got = cosine_similarity(fake_embed_one(c["text_a"]), fake_embed_one(c["text_b"]))
        assert got == pytest.approx(c["expected"], abs=1e-12), c


def test_engram_text_golden():
    from dna.memory.semantic import engram_text

    for c in _FX["engram_text"]:
        assert engram_text(c["spec"]) == c["expected"], c


def test_semantic_recall_fusion_golden():
    from dna.kernel.embedding import fake_embed_one
    from dna.memory.semantic import (
        engram_text,
        fuse_semantic_recall,
        semantic_scores_from_vectors,
    )

    for c in _FX["semantic_recall_fusion"]:
        refs = [EngramRef(e["name"], e["spec"]) for e in c["engrams"]]
        sem = semantic_scores_from_vectors(
            [e["name"] for e in c["engrams"]],
            [fake_embed_one(engram_text(e["spec"])) for e in c["engrams"]],
            fake_embed_one(c["query"]),
        )
        fused = fuse_semantic_recall(
            [dict(h) for h in c["hits"]], refs, c["query"], sem, now=_dt(c["now"]),
        )
        assert [h["name"] for h in fused] == c["expected_order"], c
        for h in fused:
            assert h["score"] == pytest.approx(c["expected_scores"][h["name"]], abs=1e-12), h
            if h["name"] in c["expected_semantic"]:
                assert h["semantic"] == pytest.approx(
                    c["expected_semantic"][h["name"]], abs=1e-12), h
            assert h.get("rank_ecphory") == c["expected_rank_ecphory"].get(h["name"]), h
