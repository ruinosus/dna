"""Deterministic ecphory — Semon's Law of Ecphory as a pure function.

Ported (deterministic core only) from the upstream ``cognitive.ecphory``.
Semon's theory IS deterministic math: partial-match between a cue context and
an engram's ``encoding_context``, weighted overlap, saturation/novelty/recency
adjustments, homophony propagation. The upstream module wrapped this in an LLM
narrator + kernel-writing side effects + an async event loop; ALL of that is
left behind — this module is the scoring FUNCTION. The verb layer
(``dna.memory.verbs``) owns persistence (cues_history/confidence bump) via the
kernel.

s-memory-verbs (2026-07-09). Numeric weights come from ``RecallPolicy``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from dna.memory.policy import DEFAULT_RECALL_POLICY, RecallPolicy


@dataclass
class EngramRef:
    """Slim view of an engram used by the scoring loop."""
    name: str
    spec: dict[str, Any]


@dataclass
class EcphoryScore:
    """Per-engram score with explanation."""
    engram: EngramRef
    score: float
    matched_dims: list[str] = field(default_factory=list)
    reason_tags: list[str] = field(default_factory=list)

    def to_dict(self, *, kind: str) -> dict[str, Any]:
        """Project to a serializable direct/homophonic item."""
        s = self.engram.spec
        out: dict[str, Any] = {
            "name": self.engram.name,
            "score": round(self.score, 3),
            "summary": (s.get("summary") or "")[:240],
            "affect": s.get("affect"),
            "confidence_score": s.get("confidence_score"),
            "matched_dims": list(self.matched_dims),
            "reason_tags": list(self.reason_tags),
            "kind": kind,
        }
        if kind == "homophonic" and self.reason_tags:
            via = next((t for t in self.reason_tags if t.startswith("via=")), None)
            basis = next((t for t in self.reason_tags if t.startswith("basis=")), None)
            out["reason"] = f"homophonic · {via or ''} · {basis or ''}".strip(" ·")
        else:
            out["reason"] = "direct · " + ", ".join(self.matched_dims[:3])
        return out


def _within_window(at_iso: str | None, *, now: datetime, hours: float) -> bool:
    if not at_iso:
        return False
    try:
        ts = datetime.fromisoformat(at_iso.replace("Z", "+00:00"))
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts) <= timedelta(hours=hours)


def _tokenize(s: str) -> set[str]:
    return {t for t in re.split(r"[\s/_\-]+", s.lower()) if t}


def score_engram(
    engram: EngramRef, cue_ctx: dict[str, Any],
    semantic_scores: dict[str, float] | None = None,
    policy: RecallPolicy | None = None,
) -> EcphoryScore:
    """Partial-match score between an engram's encoding_context and a cue.

    Weighted overlap (weights sum ~1.0): primary semantic (area OR summary OR
    embedding-cosine, MAX not sum) 0.55, co_topics jaccard 0.20, source_refs
    0.15, affect mood 0.05, time_of_day 0.05.
    """
    pol = policy or DEFAULT_RECALL_POLICY
    spec = engram.spec
    ec = spec.get("encoding_context") or {}
    matched: list[str] = []
    score = 0.0
    tags: list[str] = []

    ec_area = (ec.get("area") or spec.get("area") or "").strip()
    cue_area = (cue_ctx.get("area_inferred") or cue_ctx.get("query") or "").strip()
    cue_q = cue_area.lower()

    # Path 1: area token overlap.
    area_score = 0.0
    area_label = ""
    if ec_area and cue_area:
        ec_tokens = _tokenize(ec_area)
        cue_tokens = _tokenize(cue_area)
        if ec_tokens and cue_tokens:
            common = ec_tokens & cue_tokens
            if common == ec_tokens or common == cue_tokens:
                area_score = pol.content_weight
                area_label = "area"
            elif common:
                jaccard = len(common) / len(ec_tokens | cue_tokens)
                area_score = pol.content_weight * jaccard
                area_label = f"area~{jaccard:.2f}"

    # Path 2: query phrase in summary/title/body.
    summary_score = 0.0
    summary_label = ""
    if cue_q and len(cue_q) >= 3:
        haystack = " ".join(
            str(spec.get(f) or "") for f in ("summary", "title", "body")
        ).lower()
        if haystack and cue_q in haystack:
            summary_score = pol.content_weight
            summary_label = "summary"
        elif haystack:
            q_tokens = _tokenize(cue_q)
            content_tokens = _tokenize(haystack)
            if q_tokens and q_tokens.issubset(content_tokens):
                summary_score = pol.summary_partial_weight
                summary_label = "summary-tokens"

    # Path 3: embedding cosine (only when caller feeds semantic_scores).
    semantic_score = 0.0
    semantic_label = ""
    if semantic_scores:
        cos = float(semantic_scores.get(engram.name, 0.0) or 0.0)
        if cos > 0.0:
            semantic_score = pol.cosine_weight * cos
            semantic_label = f"semantic~{cos:.2f}"

    primary = max(area_score, summary_score, semantic_score)
    if primary > 0:
        score += primary
        if primary == area_score and area_label:
            matched.append(area_label)
        elif primary == summary_score and summary_label:
            matched.append(summary_label)
        elif semantic_label:
            matched.append(semantic_label)

    # co_topics jaccard.
    ec_topics = set(ec.get("co_topics") or [])
    cue_topics = set(cue_ctx.get("co_topics") or [])
    if ec_topics and cue_topics:
        overlap = ec_topics & cue_topics
        union = ec_topics | cue_topics
        if union:
            score += pol.co_topics_weight * (len(overlap) / len(union))
            if overlap:
                matched.append(f"co_topics({len(overlap)})")

    # source_refs distinctiveness.
    ec_refs = set(ec.get("source_refs") or spec.get("source_refs") or [])
    cue_refs = set(cue_ctx.get("source_refs") or [])
    if ec_refs and cue_refs and (ec_refs & cue_refs):
        score += pol.source_refs_weight
        matched.append("source_refs")

    # affect mood (marginal boost).
    ec_affect = ec.get("affect") or spec.get("affect")
    cue_affect = cue_ctx.get("affect_mood")
    if ec_affect and cue_affect and ec_affect != "neutral" and cue_affect != "neutral":
        if ec_affect == cue_affect:
            score += pol.affect_weight
            matched.append("affect")

    # time_of_day (perceptual, marginal).
    if ec.get("time_of_day") and cue_ctx.get("time_of_day") \
            and ec.get("time_of_day") == cue_ctx.get("time_of_day"):
        score += pol.time_weight
        matched.append("time")

    return EcphoryScore(engram=engram, score=score, matched_dims=matched, reason_tags=tags)


def apply_semon_adjustments(
    s: EcphoryScore, *, now: datetime, policy: RecallPolicy | None = None,
) -> EcphoryScore:
    """Saturation / novelty / recency / high-fidelity modifiers."""
    pol = policy or DEFAULT_RECALL_POLICY
    spec = s.engram.spec
    cues = spec.get("cues_history") or []
    recent_24h = sum(
        1 for c in cues
        if isinstance(c, dict) and _within_window(c.get("at"), now=now, hours=24)
    )
    if recent_24h >= pol.saturation_threshold:
        s.score *= pol.saturation_decay
        s.reason_tags.append("saturation_decay")
    if not cues:
        s.score += pol.novelty_boost
        s.reason_tags.append("novelty_boost")
    if _within_window(spec.get("created_at"), now=now, hours=24):
        s.score += pol.recency_boost
        s.reason_tags.append("recency_boost")
    strength = spec.get("confidence_score")
    if isinstance(strength, (int, float)) and strength > 1.1:
        s.score += 0.05
        s.reason_tags.append("high_fidelity")
    return s


def expand_homophony(
    directs: list[EcphoryScore], engram_by_name: dict[str, EngramRef],
) -> list[EcphoryScore]:
    """For each direct hit, surface homophonic neighbors via ``homophonic_links``.
    Score = direct.score × 0.7 × link.resonance_score. Dedup by name (max)."""
    homo: dict[str, EcphoryScore] = {}
    for d in directs:
        for link in (d.engram.spec.get("homophonic_links") or []):
            if not isinstance(link, dict):
                continue
            target_name = (link.get("target_name") or link.get("engram_name") or "").strip()
            if not target_name or target_name == d.engram.name:
                continue
            target = engram_by_name.get(target_name)
            if target is None:
                continue
            resonance = float(link.get("resonance_score") or 0.5)
            new_score = d.score * 0.7 * resonance
            tags = [f"via={d.engram.name}", f"basis={link.get('basis') or 'co-area'}"]
            existing = homo.get(target_name)
            if existing is None or new_score > existing.score:
                homo[target_name] = EcphoryScore(
                    engram=target, score=new_score,
                    matched_dims=["homophonic"], reason_tags=tags,
                )
    return sorted(homo.values(), key=lambda s: s.score, reverse=True)


def _infer_area(cue: dict[str, Any]) -> str:
    explicit = cue.get("area") or cue.get("area_inferred")
    if explicit:
        return str(explicit)
    query = (cue.get("query") or "").strip().lower()
    if query:
        return query
    topics = (cue.get("context") or {}).get("recent_turn_topics") or []
    return str(topics[0]) if topics else ""


@dataclass
class EcphoryRunResult:
    cue_used: dict[str, Any]
    direct: list[dict[str, Any]]
    homophonic: list[dict[str, Any]]
    partial: bool


def run_ecphory(
    *,
    cue: dict[str, Any],
    engrams: list[EngramRef],
    limit_direct: int = 5,
    limit_homophonic: int = 4,
    semantic_scores: dict[str, float] | None = None,
    direct_threshold: float | None = None,
    policy: RecallPolicy | None = None,
    now: datetime | None = None,
) -> EcphoryRunResult:
    """End-to-end deterministic ecphory (PURE — no side effects, no kernel).

    Steps: build cue_ctx → score every engram → Semon adjustments → filter
    directs (≥ threshold) top-K → expand homophony. Side effects (cues_history
    bump) are the verb layer's job.
    """
    pol = policy or DEFAULT_RECALL_POLICY
    threshold = direct_threshold if direct_threshold is not None else pol.direct_threshold
    now = now or datetime.now(timezone.utc)
    cue_ctx = {
        "query": cue.get("query") or "",
        "area_inferred": _infer_area(cue),
        "affect_mood": (cue.get("context") or {}).get("jarvis_affect_now")
                       or cue.get("affect_mood"),
        "co_topics": (cue.get("context") or {}).get("recent_turn_topics")
                     or cue.get("co_topics") or [],
        "time_of_day": (cue.get("context") or {}).get("time_of_day"),
        "source_refs": cue.get("source_refs") or [],
    }
    engram_by_name = {e.name: e for e in engrams}
    scored: list[EcphoryScore] = []
    for e in engrams:
        s = score_engram(e, cue_ctx, semantic_scores=semantic_scores, policy=pol)
        s = apply_semon_adjustments(s, now=now, policy=pol)
        scored.append(s)
    directs = sorted(
        [s for s in scored if s.score >= threshold],
        key=lambda s: s.score, reverse=True,
    )[:limit_direct]
    homophonic = expand_homophony(directs, engram_by_name)[:limit_homophonic]
    return EcphoryRunResult(
        cue_used=cue_ctx,
        direct=[d.to_dict(kind="direct") for d in directs],
        homophonic=[h.to_dict(kind="homophonic") for h in homophonic],
        partial=len(directs) == 0,
    )


__all__ = [
    "EngramRef",
    "EcphoryScore",
    "EcphoryRunResult",
    "score_engram",
    "apply_semon_adjustments",
    "expand_homophony",
    "run_ecphory",
]
