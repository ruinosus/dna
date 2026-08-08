"""Relevance — the RAW score behind a rank, and why this module ships NO floor.

The defect this closes (i-103): **RRF orders by RANK, and rank exists over
noise.** ``reciprocal_rank_fusion`` gives a doc ``1/(k + rank)`` from every list
it appears in; nothing in that expression knows whether the doc has anything to
do with the query. A search therefore never comes back empty for irrelevance —
it comes back with the LEAST irrelevant instance, at ``degraded: False``. The
lexical plane at least admitted it had found nothing; the hybrid plane answers
with the face of a hit.

That matters because "search before you build" became a capability here: the App
and Solution creators search before they propose. An agent that asks *"does this
already exist?"* and ALWAYS hears *"yes, this"* is worse than one that never
asks — it stops proposing new things, or it learns to ignore the answer.

⭐ What ships is the raw score (option **b** of the issue). What does NOT ship is
a floor constant (option **a**), and the measurement below is the reason.

──────────────────────────────────────────────────────────────────────────────
⚠️  MEASURED 08/08/2026 — there is no floor value, and this is not an opinion
──────────────────────────────────────────────────────────────────────────────

Corpus: the REAL dna-cloud dev index — 141 ``Issue`` instances of actual prose
(avg 5 015 chars) + 9 ``App``. Embedder: the shipped ``all-MiniLM-L6-v2`` ONNX.
Exact KNN (IVFFlat disabled — under a ``WHERE`` it post-filters and silently
returns fewer rows than ``LIMIT``, which would have made these numbers an
artifact of the index rather than of the model).

12 queries whose answer IS in the corpus vs 12 whose answer is NOT (cake
recipes, bicycle tyres, tax deadlines, Pelé's goals in 1970). Top-1 similarity:

    relevant     min 0.3525   max 0.6342
    irrelevant   min 0.1593   max 0.5274
    → 8 of 12 IRRELEVANT queries score at or above the WORST relevant one.

"prazo para entregar a declaracao de imposto de renda" scores **0.5274** against
a board about MCP doors and billing — higher than 10 of the 12 genuine hits. Any
floor that rejects it rejects almost every true positive.

Two corpus-DERIVED statistics were measured next, precisely because a derived
threshold is what this house asks for instead of a hardcoded one. Both are
WORSE — they do not separate at all:

    z-score of top-1 over the corpus   relevant 1.82–4.77 | irrelevant 1.89–3.01
    margin of top-1 over top-2         relevant 0.0006–0.1258 | irrelevant 0.0024–0.0712
    → 12 of 12 overlap, on both.

⭐ So the conclusion is not "we have not found the number yet". It is that the
dense plane's own numbers — absolute, normalized, or relative — **do not carry
the information a floor would need**. A bi-encoder cosine is not a calibrated
relevance probability, and this corpus makes that visible: the documents are
long (truncated at the model's 512 tokens), same-domain and same-register, so
every one of them is mildly close to every plausible technical question.

A shipped constant here would therefore be worse than the hardcoded model price
this house already refused: that one was at least approximately right.

What WOULD work is named rather than guessed, so the next person does not
re-derive it: a **cross-encoder reranker** scores the (query, document) PAIR
jointly and does produce a calibrated relevance logit — the market-standard
answer to exactly this problem (``BAAI/bge-reranker-v2-m3``,
``cross-encoder/mmarco-mMiniLMv2-*`` for multilingual). It was NOT measured here
only because it could not be: the shared venv pins ``transformers 4.17`` (2022,
pre-safetensors) and the discipline forbids installing into it. That is the
recommended next step, and it is a MODEL decision with a cost, not a constant.

──────────────────────────────────────────────────────────────────────────────
What this module ships instead
──────────────────────────────────────────────────────────────────────────────

* :func:`cosine_similarity` — the one definition of the number, so the pgvector
  provider (whose ``<=>`` is already cosine) and the sqlite-vec provider (whose
  ``vec0`` distance is **L2**, not cosine) report the SAME quantity on the SAME
  scale. Two providers reporting a field called ``similarity`` on two different
  metrics is the kind of contract that fails only when somebody compares them.
* :func:`apply_similarity_floor` — the floor as POLICY, applied only when a
  CALLER passes a value. Never a default; the caller has the context the engine
  does not.
* :data:`RANKED_NOT_FILTERED` — the standing caveat, in prose, for the
  ``degraded: False`` path. The envelope already says the honest thing when
  something FAILED; it said nothing at all when everything worked, and that
  silence is what the false positive was wearing.
"""
from __future__ import annotations

from math import sqrt
from typing import Any, Iterable

__all__ = [
    "RANKED_NOT_FILTERED",
    "apply_similarity_floor",
    "cosine_similarity",
]


#: The caveat that belongs on a HEALTHY hybrid answer — the one case the
#: envelope used to leave silent.
#:
#: Deliberately NOT routed through ``degraded`` / ``degraded_reason`` /
#: ``notice``: those three mean "something did not run", a live consumer
#: (dna-cloud's ``search_instances``) branches on them, and widening them to
#: also mean "this ran fine, just read it carefully" would make the honest
#: signal ambiguous. This is a separate field for a separate statement.
RANKED_NOT_FILTERED = (
    "These hits are RANKED, not FILTERED. Reciprocal Rank Fusion orders "
    "candidates by their rank within each plane, and a rank exists over noise: "
    "the top hit is the LEAST DISSIMILAR instance in this Kind, which is not "
    "the same as a SIMILAR one. A non-empty result is therefore NOT evidence "
    "that something like the query already exists. Each hit carries "
    "`similarity` (cosine, dense plane) and `lexical_score` (token overlap) so "
    "you can judge for yourself — but read `similarity` as an ordering signal, "
    "NOT as a calibrated relevance score: measured on this deployment's own "
    "corpus, unrelated queries reach 0.53 while genuine matches start at 0.35, "
    "so no single cutoff separates them. When it matters that the answer may be "
    "'nothing like this exists', corroborate a hit by READING it "
    "(`get_instance`) before reporting it as prior art."
)


def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    """Cosine similarity of two vectors, in ``[-1.0, 1.0]``.

    The SINGLE definition of the number every provider reports as
    ``similarity``. It exists because the two shipped stores do not agree on a
    metric: pgvector's ``<=>`` operator IS cosine distance (so its similarity is
    ``1 - distance``), while sqlite-vec's ``vec0`` virtual table defaults to
    **L2** — ``float[dims]`` with no ``distance_metric``, and changing that would
    be a migration plus a full re-index. Deriving cosine from an L2 distance is
    only valid for L2-NORMALIZED vectors, which the ONNX embedder happens to
    produce and the deterministic fake floor does not, so the conversion would
    be right in production and quietly wrong in every test.

    Computing it explicitly over the ≤40 fused candidates costs a few thousand
    multiplications and removes the whole class of question.

    A zero-magnitude vector has no direction and therefore no angle to anything:
    the answer is ``0.0``, not a ``ZeroDivisionError`` and not ``1.0``. The
    all-zero query is a real case (the providers already skip the dense plane
    for it).
    """
    va = list(a)
    vb = list(b)
    if len(va) != len(vb):
        raise ValueError(
            f"cosine_similarity needs vectors of equal width, got "
            f"{len(va)} and {len(vb)}"
        )
    dot = na = nb = 0.0
    for x, y in zip(va, vb):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (sqrt(na) * sqrt(nb))


def apply_similarity_floor(
    hits: list[dict[str, Any]], min_similarity: float | None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Drop hits whose dense ``similarity`` is below ``min_similarity``.

    Returns ``(kept, dropped, unscored_kept)``.

    ``min_similarity`` is ``None`` (the default everywhere) → nothing is
    dropped and this is a no-op. There is no shipped default and there must not
    be one; see this module's docstring for the measurement that refuses it.
    The floor is the CALLER's policy because the caller is the one with the
    context — a creator asking "does this already exist?" wants to be told no,
    while a human browsing wants the near misses.

    **A hit with no ``similarity`` is KEPT**, and counted in ``unscored_kept``.
    Two ways that happens, and both must fail OPEN: the hit came only from the
    LEXICAL plane (literal token evidence, and a floor over a number it does not
    have would delete the better-evidenced result), or the provider is a
    third-party one that does not report the field. Dropping a result on the
    basis of a score you do not have is fabrication in the other direction —
    the same sin as reporting a rank as a relevance.

    ``dropped`` is returned rather than logged so the door can SAY how many were
    removed. A filter that silently shortens a list teaches its reader that the
    corpus is smaller than it is.
    """
    if min_similarity is None:
        return hits, 0, 0
    floor = float(min_similarity)
    kept: list[dict[str, Any]] = []
    dropped = 0
    unscored = 0
    for hit in hits:
        sim = hit.get("similarity")
        if sim is None:
            unscored += 1
            kept.append(hit)
        elif float(sim) >= floor:
            kept.append(hit)
        else:
            dropped += 1
    return kept, dropped, unscored
