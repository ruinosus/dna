"""i-103 — the raw relevance score, and the floor that is POLICY not default.

Three things are pinned here, and the third is the one that will look wrong to
somebody later:

1. :func:`cosine_similarity` — the single definition both stores report through.
2. :func:`apply_similarity_floor` — drops on score, KEEPS the unscored.
3. ⚠️ **No floor runs unless a caller asks for one.** A future reader who thinks
   "search should obviously reject nonsense by default" is invited to
   ``dna.kernel.query.relevance``'s measurement first: on the real corpus the
   relevant and irrelevant populations OVERLAP on every statistic tried, so a
   default would delete true positives to hide false ones.
"""
from __future__ import annotations

import math

import pytest

from dna.kernel.query.relevance import (
    RANKED_NOT_FILTERED,
    apply_similarity_floor,
    cosine_similarity,
)


# ── cosine_similarity ──────────────────────────────────────────────────────


def test_cosine_of_identical_vectors_is_one():
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_ignores_magnitude():
    """The point of cosine: direction only. A doubled vector is the SAME
    direction, which is why an L2 distance (which doubles too) is a different
    quantity and cannot be relabelled as this one."""
    assert cosine_similarity([1.0, 0.0], [7.0, 0.0]) == pytest.approx(1.0)


def test_cosine_of_orthogonal_is_zero_and_opposite_is_minus_one():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_of_zero_vector_is_zero_not_an_error():
    """A zero vector has no direction, so it has no angle to anything. The
    all-zero query is real (the providers skip the dense plane for it), and it
    must not raise or claim a perfect match."""
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0


def test_cosine_refuses_mismatched_widths():
    with pytest.raises(ValueError, match="equal width"):
        cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])


def test_cosine_matches_l2_conversion_only_for_normalised_vectors():
    """Why the sqlite provider recomputes instead of converting its L2 distance.

    For UNIT vectors, ``cos = 1 - d²/2`` holds. For un-normalised ones — which
    the deterministic fake embedder produces — it does not, so a provider that
    converted would be right in production and quietly wrong in every test.
    """
    unit_a, unit_b = [1.0, 0.0], [0.6, 0.8]
    d = math.dist(unit_a, unit_b)
    assert cosine_similarity(unit_a, unit_b) == pytest.approx(1 - d * d / 2)

    big_a, big_b = [3.0, 0.0], [1.8, 2.4]  # same directions, magnitude 3
    d_big = math.dist(big_a, big_b)
    assert cosine_similarity(big_a, big_b) == pytest.approx(0.6)
    assert 1 - d_big * d_big / 2 != pytest.approx(0.6)  # the conversion breaks


# ── apply_similarity_floor ─────────────────────────────────────────────────


def _hits():
    return [
        {"name": "high", "similarity": 0.80},
        {"name": "mid", "similarity": 0.42},
        {"name": "low", "similarity": 0.11},
        {"name": "lexical-only"},  # no dense plane → no similarity
    ]


def test_no_floor_is_the_default_and_drops_nothing():
    kept, dropped, unscored = apply_similarity_floor(_hits(), None)
    assert [h["name"] for h in kept] == ["high", "mid", "low", "lexical-only"]
    assert (dropped, unscored) == (0, 0)


def test_floor_drops_below_and_keeps_at_the_boundary():
    kept, dropped, _ = apply_similarity_floor(_hits(), 0.42)
    assert [h["name"] for h in kept] == ["high", "mid", "lexical-only"]
    assert dropped == 1


def test_unscored_hit_is_kept_and_counted():
    """Fail OPEN on a hit with no similarity — it is lexical-only (literal token
    evidence) or came from a provider that does not report the field. Dropping a
    result on the basis of a score you do not have is fabrication in the other
    direction."""
    kept, dropped, unscored = apply_similarity_floor(_hits(), 0.99)
    assert [h["name"] for h in kept] == ["lexical-only"]
    assert (dropped, unscored) == (3, 1)


def test_dropped_count_is_returned_so_the_door_can_say_so():
    """A filter that silently shortens a list teaches its reader that the corpus
    is smaller than it is."""
    _, dropped, _ = apply_similarity_floor(_hits(), 0.5)
    assert dropped == 2


def test_the_standing_caveat_names_what_it_is_warning_about():
    """The prose is the product here — it is what an agent actually reads — so
    it is pinned against being quietly hollowed out into boilerplate."""
    assert "RANKED, not FILTERED" in RANKED_NOT_FILTERED
    assert "LEAST DISSIMILAR" in RANKED_NOT_FILTERED
    # It must keep saying that a non-empty result is not proof of existence —
    # the exact inference i-103 is about.
    assert "NOT evidence" in RANKED_NOT_FILTERED
    # And it must keep telling the caller how to check, not just to worry.
    assert "get_instance" in RANKED_NOT_FILTERED
