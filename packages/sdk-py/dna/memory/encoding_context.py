"""Deterministic encoding_context stamping — the engraphy conditions snapshot.

Ported verbatim (behavior) from the upstream ``cognitive.engraphic_context``.
The "encoding-specificity" contract (Semon 1904): the conditions prevailing at
engraphy must be partially reinstated at ecphory. This module stamps those
conditions — cheap, no LLM. ``remember`` calls
``stamp_encoding_context_if_absent`` before persisting; ``score_engram`` scores
ecphory candidates by partial-match against this dict.

s-memory-verbs (2026-07-09).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def time_of_day(dt: datetime) -> str:
    """Map an hour to {morning, afternoon, evening, night}."""
    hour = dt.hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 22:
        return "evening"
    return "night"


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def derive_encoding_context(
    spec: dict[str, Any],
    *,
    ambient: dict[str, Any] | None = None,
    derived_marker: str = "verb-autostamp",
) -> dict[str, Any]:
    """Build a deterministic encoding_context from the spec. Mirrors area/affect/
    source_refs, derives time_of_day from ``created_at`` (falls back to now),
    uses ``tags`` (+ optional ambient topics) as the co_topics proxy. Fresh dict."""
    ambient = ambient or {}
    created = _parse_iso(spec.get("created_at"))
    dt = created or datetime.now(timezone.utc)
    tod = ambient.get("time_of_day") or time_of_day(dt)

    spec_tags = [str(t) for t in (spec.get("tags") or []) if isinstance(t, (str, int))]
    ambient_topics = [
        str(t) for t in (ambient.get("recent_turn_topics") or [])
        if isinstance(t, (str, int))
    ]
    seen: dict[str, None] = {}
    for t in [*spec_tags, *ambient_topics]:
        if t and t not in seen:
            seen[t] = None
        if len(seen) >= 5:
            break
    co_topics = list(seen.keys())

    return {
        "area": spec.get("area") or "",
        "affect": ambient.get("affect") or spec.get("affect") or "neutral",
        "time_of_day": tod,
        "co_topics": co_topics,
        "source_refs": list(spec.get("source_refs") or []),
        "_derived": derived_marker,
    }


def stamp_encoding_context_if_absent(
    spec: dict[str, Any],
    *,
    ambient: dict[str, Any] | None = None,
    derived_marker: str = "verb-autostamp",
) -> dict[str, Any]:
    """Mutate ``spec`` in place: add encoding_context if missing/empty.
    Idempotent — NEVER overwrites a caller-provided one. Returns ``spec``."""
    existing = spec.get("encoding_context")
    if isinstance(existing, dict) and existing:
        return spec
    spec["encoding_context"] = derive_encoding_context(
        spec, ambient=ambient, derived_marker=derived_marker,
    )
    return spec


__all__ = [
    "time_of_day",
    "derive_encoding_context",
    "stamp_encoding_context_if_absent",
]
