"""Ebbinghaus forgetting curve + bi-temporal validity — pure math.

Ported (deterministic core only) from the upstream ``embeddings.decay``.
Left behind: the ranking-formula env switch, the ACT-R activation variant
(unused by the verbs), and the kernel-reading policy resolver.

Model: R(t) = e^(-t/S) where ``t`` = days since last recall, ``S`` =
stability (days). Stability comes from the memory's ``confidence_score``
tier (faint/firm/burning) or a numeric legacy value.

s-memory-verbs (2026-07-09).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from dna.memory.policy import DEFAULT_DECAY_POLICY, DecayPolicy


def _parse_iso(ts: Any) -> datetime | None:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def confidence_score_numeric(spec: dict[str, Any] | None, default: float = 1.0) -> float:
    """Canonical ``confidence_score`` → float. Accepts numeric (1.0-10.0) OR a
    string tier (faint=1.0, firm=3.0, burning=5.0). Returns ``default`` when
    missing/malformed."""
    if not isinstance(spec, dict):
        return default
    raw = spec.get("confidence_score")
    if raw is None:
        return default
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        return {"faint": 1.0, "firm": 3.0, "burning": 5.0}.get(raw.lower(), default)
    return default


def stability_from_spec(spec: dict[str, Any] | None, policy: DecayPolicy | None = None) -> float:
    """Resolve stability (days) from a memory spec.

    Priority: explicit ``engram_stability_days`` → string tier → legacy
    numeric ``confidence_score`` (interpolated 1=faint, 5=firm, 10=burning)
    → default.
    """
    pol = policy or DEFAULT_DECAY_POLICY
    tiers = pol.tiers()
    if not isinstance(spec, dict) or not spec:
        return pol.default_stability_days
    explicit = spec.get("engram_stability_days")
    if isinstance(explicit, (int, float)) and explicit > 0:
        return float(explicit)
    strength = spec.get("confidence_score")
    if isinstance(strength, str):
        return tiers.get(strength.lower(), pol.default_stability_days)
    if isinstance(strength, (int, float)):
        s = float(strength)
        if s <= 1.0:
            return tiers["faint"]
        if s <= 5.0:
            ratio = (s - 1.0) / 4.0
            return tiers["faint"] + ratio * (tiers["firm"] - tiers["faint"])
        if s <= 10.0:
            ratio = (s - 5.0) / 5.0
            return tiers["firm"] + ratio * (tiers["burning"] - tiers["firm"])
        return tiers["burning"]
    return pol.default_stability_days


def days_since(ts: Any, *, now: datetime | None = None) -> float | None:
    """Days elapsed since ``ts`` (ISO-8601). None on unparseable input."""
    dt = _parse_iso(ts)
    if dt is None:
        return None
    n = now or datetime.now(timezone.utc)
    if n.tzinfo is None:
        n = n.replace(tzinfo=timezone.utc)
    return max((n - dt).total_seconds() / 86400.0, 0.0)


def ebbinghaus_retention(stability_days: float, days_since_recall: float | None) -> float:
    """R(t) = e^(-t/S). 1.0 when never recalled (``days_since_recall`` None/≤0)."""
    if days_since_recall is None or days_since_recall <= 0:
        return 1.0
    s = max(0.1, float(stability_days))
    return math.exp(-float(days_since_recall) / s)


def recall_bump(
    current_stability: float, days_since_recall: float | None,
    policy: DecayPolicy | None = None,
) -> float:
    """Spacing-effect bump: S_new = S_old × (1 + 0.5 × R(t)); capped."""
    pol = policy or DEFAULT_DECAY_POLICY
    s = max(0.1, float(current_stability))
    r = ebbinghaus_retention(s, days_since_recall)
    return min(s * (1.0 + 0.5 * r), pol.max_stability_days)


def decay_adjusted_score(
    base_score: float,
    spec: dict[str, Any] | None,
    *,
    floor: float = 0.05,
    now: datetime | None = None,
    policy: DecayPolicy | None = None,
) -> tuple[float, float]:
    """Multiply a ranking score by current retention. Returns
    ``(adjusted, retention)``. ``floor`` keeps ancient engrams discoverable."""
    s = stability_from_spec(spec, policy)
    last = (spec or {}).get("last_surfaced") or (spec or {}).get("last_recall_at")
    days = days_since(last, now=now)
    retention = ebbinghaus_retention(s, days)
    return base_score * max(floor, retention), retention


def currently_valid(valid_to: Any, *, now: datetime | None = None) -> bool:
    """Bi-temporal filter (Zep valid_from/valid_to). True when the memory is
    still current — i.e. ``valid_to`` is unset OR in the future. A memory
    invalidated in the past (superseded/forgotten) is excluded from default
    recall. Unparseable ``valid_to`` is treated as still-valid (fail-open —
    never hides a memory on a bad timestamp)."""
    if not valid_to:
        return True
    dt = _parse_iso(valid_to)
    if dt is None:
        return True
    n = now or datetime.now(timezone.utc)
    if n.tzinfo is None:
        n = n.replace(tzinfo=timezone.utc)
    return dt > n


__all__ = [
    "confidence_score_numeric",
    "stability_from_spec",
    "days_since",
    "ebbinghaus_retention",
    "recall_bump",
    "decay_adjusted_score",
    "currently_valid",
]
