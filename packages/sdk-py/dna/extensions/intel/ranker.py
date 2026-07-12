"""Ranker — the actionability score + the anti-noise SUPPRESSION core.

Pure application logic (no I/O). :func:`score` assigns a candidate an
actionability score in ``0..1`` WITH a human-readable rationale (so the score is
inspectable, not a black box). :func:`rank_and_suppress` scores every candidate,
sorts by score, and partitions at the source ``threshold``: candidates at/above
the threshold are KEPT (delivered), candidates below are SUPPRESSED (returned
separately + logged, never delivered). Suppression is what keeps the insight
stream signal, not noise.

The heuristic is deliberately simple but real — a concrete action, a strong
evidence rating, and a PIR match each add weight. A later story can swap in a
learned/LLM ranker behind the SAME :func:`score` signature.
"""
from __future__ import annotations

import logging
from typing import Any, NamedTuple

logger = logging.getLogger("dna.intel.ranker")

Candidate = dict[str, Any]

# ── scoring weights (inspectable constants) ────────────────────────────────

_BASE = 0.30
_HAS_ACTION = 0.30
_EVIDENCE_WEIGHT = {
    "evidence-based": 0.25,
    "opinion-practice": 0.12,
    "anecdotal": 0.0,
}
_PIR_MATCH = 0.15


class Score(NamedTuple):
    """An actionability score plus the rationale that explains it. ``float(s)``
    yields the numeric value, so ``Score`` is drop-in wherever a bare float is
    expected while staying inspectable."""

    value: float
    rationale: str

    def __float__(self) -> float:  # pragma: no cover — trivial
        return self.value


def score(candidate: Candidate, source: dict[str, Any]) -> Score:
    """Actionability score in ``0..1`` for ``candidate`` given its ``source``
    spec, with a rationale enumerating each contribution.

    Weights: base presence, a concrete ``action``, the ``evidence_rating``, and
    a PIR match against ``source['pirs']``. Clamped to ``[0, 1]``."""
    parts: list[str] = []
    total = _BASE
    parts.append(f"base {_BASE:.2f}")

    action = (candidate.get("action") or "").strip()
    if action:
        total += _HAS_ACTION
        parts.append(f"+{_HAS_ACTION:.2f} concrete action")
    else:
        parts.append("+0.00 no action")

    rating = candidate.get("evidence_rating") or "anecdotal"
    ev = _EVIDENCE_WEIGHT.get(rating, 0.0)
    total += ev
    parts.append(f"+{ev:.2f} evidence={rating}")

    source_pirs = {p.lower() for p in (source.get("pirs") or [])}
    cand_pirs = {p.lower() for p in (candidate.get("pirs") or [])}
    matched = source_pirs & cand_pirs
    if matched:
        total += _PIR_MATCH
        parts.append(f"+{_PIR_MATCH:.2f} PIR match ({', '.join(sorted(matched))})")
    else:
        parts.append("+0.00 no PIR match")

    value = max(0.0, min(1.0, total))
    rationale = " · ".join(parts) + f" = {value:.2f}"
    return Score(value=round(value, 4), rationale=rationale)


def rank_and_suppress(
    candidates: list[Candidate],
    threshold: float,
    source: dict[str, Any] | None = None,
) -> tuple[list[Candidate], list[Candidate]]:
    """Score + partition ``candidates`` at ``threshold``.

    Each candidate is annotated in place with ``score`` (float) and
    ``score_rationale`` (str). Returns ``(kept, suppressed)`` — both sorted by
    score descending. ``kept`` = ``score >= threshold`` (delivered);
    ``suppressed`` = below (NOT delivered; logged for auditability).
    """
    src = source or {}
    scored: list[Candidate] = []
    for cand in candidates:
        s = score(cand, src)
        annotated = dict(cand)
        annotated["score"] = s.value
        annotated["score_rationale"] = s.rationale
        scored.append(annotated)

    scored.sort(key=lambda c: c.get("score", 0.0), reverse=True)
    kept = [c for c in scored if c["score"] >= threshold]
    suppressed = [c for c in scored if c["score"] < threshold]

    for c in suppressed:
        logger.info(
            "intel: suppressed insight %r (score=%.2f < threshold=%.2f) — %s",
            c.get("title"), c.get("score", 0.0), threshold, c.get("score_rationale"),
        )
    return kept, suppressed
