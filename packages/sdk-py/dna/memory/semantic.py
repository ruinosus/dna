"""Semantic recall — embedding similarity fed into the EXISTING ecphory ranking.

s-memory-semantic-recall. The ecphory core shipped with a semantic hook that
nothing fed: ``score_engram``'s Path 3 blends an embedding cosine into the
primary content score (``RecallPolicy.cosine_weight``), but the deterministic
core "never sees a live embedding" (``policy.py``) — the hook was inert. This
module activates it, composing ONLY machinery the SDK already practices:

  * **cosine** over vectors from ``kernel.embed()`` (any ``EmbeddingPort`` —
    the deterministic fake floor, ONNX all-MiniLM, ...);
  * **score-blend** inside ``score_engram`` (Path 3, already written + twinned);
  * **RRF** (``reciprocal_rank_fusion``) to fuse the existing recall ranking
    with the ecphory ranking — the same fusion the search provider uses for
    its dense + lexical planes.

Everything here is PURE (no kernel, no IO) so the TypeScript twin
(``src/memory/semantic.ts``) is 1:1 and the ranking is parity-pinned by the
shared ``memory-scoring-parity.json`` fixture. The kernel-bound wiring (embed
the cue + candidates, then call :func:`fuse_semantic_recall`) lives in the
verb layer (``dna.memory.verbs.recall``), Py-only like the other verbs.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from dna.adapters.search.rrf import DEFAULT_RRF_K, reciprocal_rank_fusion
from dna.memory.ecphory import EcphoryScore, EngramRef, apply_semon_adjustments, score_engram
from dna.memory.policy import DEFAULT_RECALL_POLICY, RecallPolicy


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity between two vectors. 0.0 when either has no signal
    (all-zero — the fake embedder's honest "no tokens" vector). Accumulation
    order is index order, so the result is bit-identical to the TS twin."""
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / math.sqrt(norm_a) / math.sqrt(norm_b)


#: The spec fields that carry an engram's semantic payload — the SAME planes
#: the ecphory content paths score (``area`` for Path 1; ``summary``/``title``/
#: ``body`` for Path 2). The cue-side cosine embeds exactly this text, NOT the
#: index's full ``document_text`` blob: names, dates, affect labels and other
#: metadata strings would dilute the similarity without carrying meaning.
ENGRAM_TEXT_FIELDS: tuple[str, ...] = ("area", "title", "summary", "body")


def engram_text(spec: dict[str, Any]) -> str:
    """The text a memory means, for cue-side embedding (see
    :data:`ENGRAM_TEXT_FIELDS`). Missing fields contribute nothing."""
    return " ".join(
        str(spec.get(f) or "") for f in ENGRAM_TEXT_FIELDS if spec.get(f)
    ).strip()


def semantic_scores_from_vectors(
    names: Sequence[str],
    vectors: Sequence[Sequence[float]],
    query_vector: Sequence[float],
) -> dict[str, float]:
    """Per-name cosine against the cue vector, in the shape ``score_engram``'s
    Path 3 consumes. Non-positive cosines are dropped (no signal, never a
    penalty). On a duplicate name the FIRST vector wins (deterministic)."""
    scores: dict[str, float] = {}
    for name, vec in zip(names, vectors):
        if name in scores:
            continue
        cos = cosine_similarity(query_vector, vec)
        if cos > 0.0:
            scores[name] = cos
    return scores


def ecphory_rank(
    engrams: Iterable[EngramRef],
    query: str,
    semantic_scores: dict[str, float] | None = None,
    *,
    policy: RecallPolicy | None = None,
    now: datetime | None = None,
) -> list[EcphoryScore]:
    """The existing ecphory ranking over candidate engrams, with the semantic
    hook fed. ``score_engram`` (cue = the query) + Semon adjustments, gated by
    ``RecallPolicy.direct_threshold``, sorted (score desc, name asc — fully
    deterministic, Py↔TS identical). Pure — the shared parity core."""
    pol = policy or DEFAULT_RECALL_POLICY
    now = now or datetime.now(timezone.utc)
    cue_ctx = {"query": query}
    ranked: list[EcphoryScore] = []
    for engram in engrams:
        s = score_engram(engram, cue_ctx, semantic_scores=semantic_scores, policy=pol)
        s = apply_semon_adjustments(s, now=now, policy=pol)
        if s.score >= pol.direct_threshold:
            ranked.append(s)
    ranked.sort(key=lambda s: (-s.score, s.engram.name))
    return ranked


def fuse_semantic_recall(
    hits: Sequence[dict[str, Any]],
    engrams: Sequence[EngramRef],
    query: str,
    semantic_scores: dict[str, float],
    *,
    policy: RecallPolicy | None = None,
    now: datetime | None = None,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[dict[str, Any]]:
    """Fuse the existing recall ranking with the semantic ecphory ranking.

    ``hits`` is the recall verb's ranking (best-first, already bi-temporal
    filtered + retention × affect re-scored); ``engrams`` are the same
    candidates as ``EngramRef`` views. The two rank lists are fused with
    ``reciprocal_rank_fusion`` — a candidate below the ecphory threshold keeps
    its recall rank (one-list RRF), never disappears. Returns NEW hit dicts in
    fused order, annotated: ``score`` = fused RRF score, ``score_recall`` = the
    pre-fusion score, ``rank_recall`` / ``rank_ecphory`` (1-based),
    ``score_ecphory`` and ``semantic`` (cue↔memory cosine) when present.

    Rankings are keyed by hit ``name``; on a duplicate name the first (best)
    hit wins — memory names are content-hashed (``rem-<sha>``), so collisions
    are theoretical. Pure; the caller owns truncation to top-k.
    """
    if not hits:
        return []
    recall_order: list[str] = []
    first_by_name: dict[str, dict[str, Any]] = {}
    for hit in hits:
        name = str(hit.get("name") or "")
        if not name or name in first_by_name:
            continue
        first_by_name[name] = hit
        recall_order.append(name)

    directs = ecphory_rank(engrams, query, semantic_scores, policy=policy, now=now)
    ecphory_order = [s.engram.name for s in directs]

    fused = reciprocal_rank_fusion([recall_order, ecphory_order], k=rrf_k)
    recall_pos = {name: i + 1 for i, name in enumerate(recall_order)}
    ecphory_pos = {name: i + 1 for i, name in enumerate(ecphory_order)}
    ecphory_score = {s.engram.name: s.score for s in directs}

    out: list[dict[str, Any]] = []
    for name, fused_score in fused:
        src = first_by_name.get(name)
        if src is None:  # ecphory-only name — impossible when engrams ⊆ hits
            continue
        hit = dict(src)
        hit["score_recall"] = float(hit.get("score", 0.0) or 0.0)
        hit["score"] = fused_score
        hit["rank_recall"] = recall_pos[name]
        if name in ecphory_pos:
            hit["rank_ecphory"] = ecphory_pos[name]
            hit["score_ecphory"] = ecphory_score[name]
        cos = semantic_scores.get(name, 0.0)
        if cos > 0.0:
            hit["semantic"] = cos
        out.append(hit)
    return out


__all__ = [
    "ENGRAM_TEXT_FIELDS",
    "engram_text",
    "cosine_similarity",
    "semantic_scores_from_vectors",
    "ecphory_rank",
    "fuse_semantic_recall",
]
