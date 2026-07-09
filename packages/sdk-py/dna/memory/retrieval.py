"""BM25 memory ranking — the pure lexical scoring core.

Ported (deterministic core only) from the upstream ``cognitive.retrieval``.
Left behind: the ``AAP_SCORING_FORMULA`` env switch (genagents variant), the
``ManifestInstance``-bound helpers, and the SynthesisRun/ArchiveProposal side
sections (those are service surfaces).

Scoring formula (Semon amendment):

    final = base_bm25 × recency_decay × affect_weight × surface_damping × confidence

- ``base_bm25``     hand-rolled BM25 (k1=1.5, b=0.75) over ``area`` + ``summary``.
- ``recency_decay`` exp(-Δdays_since_last_surfaced / 30); 1.0 when never surfaced.
- ``affect_weight`` evocative palette (surprise > ominous > regret > triumph > wistful).
- ``surface_damp``  1/(1 + surface_count × 0.1) — attentional fatigue.
- ``confidence``    ``confidence_score`` numeric multiplier.

Pure: takes ``list[Memory]`` (name + spec), returns ranked scores. Bi-temporal
filtering + cue side-effects are applied by the verb layer.

s-memory-verbs (2026-07-09).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from dna.memory.decay import confidence_score_numeric

_AFFECT_WEIGHTS: dict[str, float] = {
    "triumph": 1.2,
    "regret": 1.3,
    "surprise": 1.5,
    "wistful": 1.0,
    "ominous": 1.4,
}

_BM25_K1 = 1.5
_BM25_B = 0.75
_RECENCY_HALFLIFE_DAYS = 30.0
_SURFACE_DAMP_K = 0.1

_PARTIAL_PREFIX_FLOOR = 0.05
_PARTIAL_MIN_PREFIX_LEN = 3

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass
class Memory:
    """Slim {name, spec} view of a memory record used by the ranker."""
    name: str
    spec: dict[str, Any]


@dataclass
class RankedMemory:
    name: str
    score: float
    factors: dict[str, float] = field(default_factory=dict)


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _doc_text(spec: dict[str, Any]) -> str:
    return f"{spec.get('area') or ''} {spec.get('summary') or ''}"


def bm25_score(
    query_tokens: list[str], doc_tokens: list[str], *,
    doc_lengths: list[int], idf: dict[str, float],
) -> float:
    """Single-doc BM25 against the query. 0.0 when nothing matches."""
    if not doc_tokens:
        return 0.0
    avg_dl = sum(doc_lengths) / len(doc_lengths) if doc_lengths else 0.0
    if avg_dl == 0.0:
        return 0.0
    dl = len(doc_tokens)
    tf = Counter(doc_tokens)
    score = 0.0
    for term in query_tokens:
        if term not in idf:
            continue
        f = tf.get(term, 0)
        if f == 0:
            continue
        num = f * (_BM25_K1 + 1)
        den = f + _BM25_K1 * (1 - _BM25_B + _BM25_B * dl / avg_dl)
        score += idf[term] * (num / den)
    return score


def build_idf(corpus_tokens: list[list[str]]) -> dict[str, float]:
    """IDF for every corpus term: ln((N - df + 0.5)/(df + 0.5) + 1)."""
    n = len(corpus_tokens)
    df: Counter[str] = Counter()
    for tokens in corpus_tokens:
        for term in set(tokens):
            df[term] += 1
    return {
        term: math.log((n - count + 0.5) / (count + 0.5) + 1)
        for term, count in df.items()
    }


def recency_factor(last_surfaced: str | None, now: datetime) -> float:
    """exp(-Δdays/30). 1.0 when never surfaced."""
    if not last_surfaced:
        return 1.0
    try:
        dt = datetime.fromisoformat(last_surfaced.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return 1.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delta_days = (now - dt).total_seconds() / 86400
    if delta_days <= 0:
        return 1.0
    return math.exp(-delta_days / _RECENCY_HALFLIFE_DAYS)


def affect_factor(affect: str | None) -> float:
    return _AFFECT_WEIGHTS.get(affect or "", 1.0)


def surface_damp(count: int | None) -> float:
    return 1.0 / (1.0 + (count or 0) * _SURFACE_DAMP_K)


def _has_prefix_overlap(query_tokens: list[str], doc_tokens: list[str]) -> bool:
    """True iff any (q, d) token pair shares a ≥3-char prefix — partial ecforia."""
    q = [t for t in query_tokens if len(t) >= _PARTIAL_MIN_PREFIX_LEN]
    d = [t for t in doc_tokens if len(t) >= _PARTIAL_MIN_PREFIX_LEN]
    for qt in q:
        for dt in d:
            if qt == dt:
                continue
            n = min(len(qt), len(dt))
            i = 0
            while i < n and qt[i] == dt[i]:
                i += 1
            if i >= _PARTIAL_MIN_PREFIX_LEN:
                return True
    return False


def rank_memories(
    memories: list[Memory],
    query: str,
    *,
    now: datetime | None = None,
    limit: int = 5,
    partial: bool = False,
) -> list[RankedMemory]:
    """Rank memories by ``bm25 × recency × affect × surface_damp × confidence``.

    Pure — no side effects, no bi-temporal filtering (the verb applies that
    upstream). When ``partial`` is True, docs sharing a ≥3-char prefix with a
    query token also surface at a small floor (Marr/Semon pattern completion);
    strict-mode results are a subset of partial-mode results.
    """
    now = now or datetime.now(timezone.utc)
    query_tokens = tokenize(query)
    corpus_tokens = [tokenize(_doc_text(m.spec)) for m in memories]
    ranked: list[RankedMemory] = []
    if query_tokens and memories:
        doc_lengths = [len(t) for t in corpus_tokens]
        idf = build_idf(corpus_tokens)
        for mem, tokens in zip(memories, corpus_tokens):
            base = bm25_score(query_tokens, tokens, doc_lengths=doc_lengths, idf=idf)
            partial_match = False
            if base <= 0.0:
                if not partial or not _has_prefix_overlap(query_tokens, tokens):
                    continue
                base = _PARTIAL_PREFIX_FLOOR
                partial_match = True
            spec = mem.spec or {}
            rec = recency_factor(spec.get("last_surfaced"), now)
            aff = affect_factor(spec.get("affect"))
            damp = surface_damp(spec.get("surface_count"))
            conf = confidence_score_numeric(spec)
            final = base * rec * aff * damp * conf
            ranked.append(RankedMemory(
                name=mem.name,
                score=final,
                factors={
                    "base": base,
                    "recency": rec,
                    "affect": aff,
                    "surface_damp": damp,
                    "confidence_score": conf,
                    "partial_match": partial_match,
                },
            ))
    ranked.sort(key=lambda r: (-r.score, r.name))
    return ranked[:limit]


__all__ = [
    "Memory",
    "RankedMemory",
    "tokenize",
    "bm25_score",
    "build_idf",
    "recency_factor",
    "affect_factor",
    "surface_damp",
    "rank_memories",
]
