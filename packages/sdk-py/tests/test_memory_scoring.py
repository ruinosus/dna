"""Deterministic tests for the pure memory-scoring core (s-memory-verbs).

The scoring is pure math — no kernel, no LLM, no time-of-wall-clock (every
function takes ``now``). These assertions pin the ported Semon/Ebbinghaus/BM25
behavior; the shared parity fixture (``test_memory_parity.py``) pins Py↔TS.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from dna.memory.decay import (
    confidence_score_numeric,
    currently_valid,
    days_since,
    decay_adjusted_score,
    ebbinghaus_retention,
    recall_bump,
    stability_from_spec,
)
from dna.memory.ecphory import EngramRef, run_ecphory, score_engram
from dna.memory.encoding_context import (
    derive_encoding_context,
    stamp_encoding_context_if_absent,
    time_of_day,
)
from dna.memory.memory_type import classify_memory_type
from dna.memory.retrieval import Memory, rank_memories

NOW = datetime(2026, 7, 9, 15, 0, 0, tzinfo=timezone.utc)


# ───────────────────────── decay / Ebbinghaus ─────────────────────────


def test_ebbinghaus_fresh_is_one():
    assert ebbinghaus_retention(15, None) == 1.0
    assert ebbinghaus_retention(15, 0) == 1.0


def test_ebbinghaus_decays_exponentially():
    assert ebbinghaus_retention(15, 15) == pytest.approx(math.exp(-1.0))
    # monotonic decreasing in time
    assert ebbinghaus_retention(15, 30) < ebbinghaus_retention(15, 15)
    # higher stability → slower decay
    assert ebbinghaus_retention(45, 15) > ebbinghaus_retention(5, 15)


def test_stability_from_tier_and_numeric():
    assert stability_from_spec({"confidence_score": "faint"}) == 5.0
    assert stability_from_spec({"confidence_score": "burning"}) == 45.0
    assert stability_from_spec({"confidence_score": 1.0}) == 5.0
    assert stability_from_spec({"confidence_score": 10.0}) == 45.0
    assert stability_from_spec({}) == 15.0  # default
    assert stability_from_spec({"engram_stability_days": 100}) == 100.0


def test_confidence_score_numeric_shapes():
    assert confidence_score_numeric({"confidence_score": 3.5}) == 3.5
    assert confidence_score_numeric({"confidence_score": "firm"}) == 3.0
    assert confidence_score_numeric({}) == 1.0
    assert confidence_score_numeric(None) == 1.0


def test_recall_bump_grows_and_caps():
    bumped = recall_bump(15, None)  # fresh recall R=1 → 1.5×
    assert bumped == pytest.approx(22.5)
    assert recall_bump(1000, 1) == 60.0  # capped at max_stability_days


def test_days_since_and_decay_adjusted():
    spec = {"last_surfaced": (NOW - timedelta(days=15)).isoformat()}
    assert days_since(spec["last_surfaced"], now=NOW) == pytest.approx(15.0)
    adj, ret = decay_adjusted_score(1.0, {"confidence_score": "firm", **spec}, now=NOW)
    assert ret == pytest.approx(math.exp(-1.0))
    assert adj == pytest.approx(math.exp(-1.0))


def test_decay_adjusted_score_floor_keeps_ancient_discoverable():
    spec = {"confidence_score": "faint", "last_surfaced": "2000-01-01T00:00:00+00:00"}
    adj, ret = decay_adjusted_score(1.0, spec, now=NOW)
    assert ret < 0.001  # fully forgotten
    assert adj == pytest.approx(0.05)  # but floored, not zero


# ───────────────────────── bi-temporality ─────────────────────────


def test_currently_valid_semantics():
    assert currently_valid(None, now=NOW) is True
    assert currently_valid("", now=NOW) is True
    assert currently_valid("2099-01-01T00:00:00+00:00", now=NOW) is True
    assert currently_valid("2000-01-01T00:00:00+00:00", now=NOW) is False
    # unparseable → fail-open (never hide on a bad timestamp)
    assert currently_valid("not-a-date", now=NOW) is True


# ───────────────────────── CoALA memory_type ─────────────────────────


def test_classify_memory_type():
    assert classify_memory_type({"summary": "always deep-copy the cache"}) == "procedural"
    assert classify_memory_type({"summary": "nunca faça hard-delete"}) == "procedural"
    assert classify_memory_type({"area": "Feature/x", "summary": "shipped it"}) == "episodic"
    assert classify_memory_type({"summary": "the sky tends to be blue"}) == "semantic"
    # explicit wins
    assert classify_memory_type({"memory_type": "episodic", "summary": "always"}) == "episodic"


# ───────────────────────── encoding context ─────────────────────────


def test_time_of_day_buckets():
    def tod(h):
        return time_of_day(datetime(2026, 1, 1, h, tzinfo=timezone.utc))
    assert tod(8) == "morning"
    assert tod(14) == "afternoon"
    assert tod(20) == "evening"
    assert tod(2) == "night"


def test_derive_encoding_context_is_deterministic():
    spec = {
        "area": "Feature/memory",
        "affect": "triumph",
        "created_at": "2026-07-09T08:00:00+00:00",
        "tags": ["memory", "search", "memory"],  # dup collapses
        "source_refs": ["s-1"],
    }
    ec = derive_encoding_context(spec)
    assert ec["area"] == "Feature/memory"
    assert ec["affect"] == "triumph"
    assert ec["time_of_day"] == "morning"
    assert ec["co_topics"] == ["memory", "search"]
    assert ec["source_refs"] == ["s-1"]


def test_stamp_is_idempotent_and_non_destructive():
    spec = {"area": "x", "encoding_context": {"area": "preexisting"}}
    stamp_encoding_context_if_absent(spec)
    assert spec["encoding_context"] == {"area": "preexisting"}  # respected
    spec2 = {"area": "y"}
    stamp_encoding_context_if_absent(spec2)
    assert spec2["encoding_context"]["area"] == "y"


# ───────────────────────── ecphory ─────────────────────────


def _engram(name, spec):
    return EngramRef(name=name, spec=spec)


def test_score_engram_area_full_match():
    e = _engram("e1", {"encoding_context": {"area": "Feature/memory"}})
    s = score_engram(e, {"area_inferred": "feature memory"})
    assert s.score == pytest.approx(0.55)
    assert "area" in s.matched_dims


def test_score_engram_summary_verbatim():
    e = _engram("e2", {"summary": "reciprocal rank fusion beats single top"})
    s = score_engram(e, {"query": "rank fusion"})
    assert s.score == pytest.approx(0.55)
    assert "summary" in s.matched_dims


def test_score_engram_content_is_max_not_sum():
    # both area and summary match → still one 0.55 slot, not 1.10
    e = _engram("e3", {
        "encoding_context": {"area": "auth"},
        "summary": "auth flow migration",
    })
    s = score_engram(e, {"query": "auth"})
    assert s.score <= 0.55 + 1e-9


def test_run_ecphory_filters_by_threshold_and_ranks():
    engrams = [
        _engram("hit", {"encoding_context": {"area": "memory recall"}}),
        _engram("miss", {"encoding_context": {"area": "totally other"}}),
    ]
    res = run_ecphory(cue={"query": "memory recall"}, engrams=engrams, now=NOW)
    names = [d["name"] for d in res.direct]
    assert "hit" in names
    assert "miss" not in names
    assert res.partial is False


def test_run_ecphory_homophony_expansion():
    engrams = [
        _engram("a", {
            "encoding_context": {"area": "memory"},
            "homophonic_links": [{"target_name": "b", "resonance_score": 0.8, "basis": "co-area"}],
        }),
        _engram("b", {"encoding_context": {"area": "unrelated"}}),
    ]
    res = run_ecphory(cue={"query": "memory"}, engrams=engrams, now=NOW)
    assert [d["name"] for d in res.direct] == ["a"]
    assert [h["name"] for h in res.homophonic] == ["b"]


# ───────────────────────── BM25 retrieval ─────────────────────────


def test_rank_memories_orders_by_relevance():
    mems = [
        Memory("s-mem", {"area": "memory", "summary": "vector embedding recall cognitive"}),
        Memory("s-banana", {"area": "fruit", "summary": "banana tropical yellow smoothie"}),
        Memory("s-fusion", {"area": "search", "summary": "hybrid fusion reciprocal rank"}),
    ]
    ranked = rank_memories(mems, "memory recall cognitive", now=NOW)
    assert ranked[0].name == "s-mem"
    assert "s-banana" not in [r.name for r in ranked]


def test_rank_memories_affect_and_surface_factors():
    base = {"area": "memory", "summary": "memory recall"}
    surprise = Memory("s-surprise", {**base, "affect": "surprise"})
    wistful = Memory("s-wistful", {**base, "affect": "wistful"})
    ranked = rank_memories([wistful, surprise], "memory recall", now=NOW)
    # surprise (1.5) outranks wistful (1.0) with identical text
    assert ranked[0].name == "s-surprise"


def test_rank_memories_partial_prefix_floor():
    mems = [Memory("s-login", {"area": "auth", "summary": "login and logout flow"})]
    # exact-only: 'logi' has no exact token match → empty
    assert rank_memories(mems, "logi", now=NOW) == []
    # partial: prefix overlap 'logi'~'login' surfaces at the floor
    ranked = rank_memories(mems, "logi", now=NOW, partial=True)
    assert ranked and ranked[0].name == "s-login"
    assert ranked[0].factors["partial_match"] is True
