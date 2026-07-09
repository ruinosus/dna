"""Reciprocal Rank Fusion — the pure, deterministic hybrid-fusion core.

RRF (Cormack et al. 2009) fuses several independently-ranked result lists into
one, using only the RANK of each item within each list — never the raw scores,
which are incomparable across a cosine-distance dense list and a BM25 lexical
list. Each item accrues ``1 / (k + rank)`` from every list it appears in (rank
is 1-based); items are then ordered by descending fused score.

This function is intentionally pure and free of any SQLite/embedding dependency
so it is unit-testable in isolation with synthetic ranks (the story's
"RRF testado isolado com ranks sintéticos" gate) and is the SINGLE fusion
implementation the sqlite-vec provider (and any future pgvector provider) share.

Parity: bit-for-bit identical to the TypeScript ``reciprocalRankFusion``
(``src/adapters/search/rrf.ts``) — same ``k`` default, same ``1/(k+rank)``
accumulation, same deterministic tiebreak (fused score desc, then id asc).
"""
from __future__ import annotations

#: RRF smoothing constant. 60 is the value from the original paper and the de
#: facto default across search stacks; it damps the contribution of the very
#: top ranks just enough that a doc ranked #1 in one list doesn't automatically
#: dominate a doc ranked #2 in both.
DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]], *, k: int = DEFAULT_RRF_K,
) -> list[tuple[str, float]]:
    """Fuse ranked id-lists into one ranking via Reciprocal Rank Fusion.

    Args:
        ranked_lists: each inner list is item ids in rank order (best first).
            An id may appear in several lists; ids absent from a list simply
            contribute nothing from it. Duplicate ids WITHIN one list are
            scored at their first (best) rank only.
        k: RRF smoothing constant (``DEFAULT_RRF_K``). Must be > 0.

    Returns:
        ``(id, fused_score)`` pairs sorted by fused score descending, ties
        broken by id ascending (so the order is fully deterministic and
        Py↔TS identical). Empty input → empty list.
    """
    if k <= 0:
        raise ValueError(f"RRF k must be positive, got {k}")
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        seen: set[str] = set()
        for rank, doc_id in enumerate(ranked, start=1):
            if doc_id in seen:
                continue  # first (best) rank wins for a repeated id
            seen.add(doc_id)
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
