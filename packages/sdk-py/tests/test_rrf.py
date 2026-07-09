"""Reciprocal Rank Fusion — pure-function tests with synthetic ranks.

RRF is the deterministic fusion core shared by every hybrid provider; it must
be correct and Py↔TS identical independent of any store. These tests exercise
it with hand-built ranked lists (no sqlite-vec, no embeddings).
"""
from __future__ import annotations

import pytest

from dna.adapters.search.rrf import DEFAULT_RRF_K, reciprocal_rank_fusion


def test_empty_input_is_empty():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_single_list_preserves_order():
    fused = reciprocal_rank_fusion([["a", "b", "c"]])
    assert [doc for doc, _ in fused] == ["a", "b", "c"]
    # scores strictly decreasing with rank
    scores = [s for _, s in fused]
    assert scores[0] > scores[1] > scores[2]


def test_agreement_beats_single_top():
    """A doc ranked #2 in BOTH lists beats a doc ranked #1 in only one."""
    dense = ["x", "shared"]
    lexical = ["y", "shared"]
    fused = dict(reciprocal_rank_fusion([dense, lexical]))
    assert fused["shared"] > fused["x"]
    assert fused["shared"] > fused["y"]


def test_score_formula_matches_definition():
    k = DEFAULT_RRF_K
    fused = dict(reciprocal_rank_fusion([["a", "b"], ["b", "a"]]))
    # a: rank1 in list0, rank2 in list1; b: rank2, rank1 → symmetric, equal.
    expected = 1.0 / (k + 1) + 1.0 / (k + 2)
    assert fused["a"] == pytest.approx(expected)
    assert fused["b"] == pytest.approx(expected)


def test_deterministic_tiebreak_by_id():
    # a and b tie → id ascending
    fused = reciprocal_rank_fusion([["b", "a"], ["a", "b"]])
    assert [doc for doc, _ in fused] == ["a", "b"]


def test_duplicate_in_one_list_scored_at_best_rank():
    fused = dict(reciprocal_rank_fusion([["a", "a", "b"]]))
    k = DEFAULT_RRF_K
    assert fused["a"] == pytest.approx(1.0 / (k + 1))  # first rank only
    assert fused["b"] == pytest.approx(1.0 / (k + 3))


def test_custom_k_smooths_more():
    high = dict(reciprocal_rank_fusion([["a", "b"]], k=1000))
    low = dict(reciprocal_rank_fusion([["a", "b"]], k=1))
    # larger k → rank1 and rank2 closer together
    assert (high["a"] - high["b"]) < (low["a"] - low["b"])


def test_non_positive_k_rejected():
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([["a"]], k=0)
