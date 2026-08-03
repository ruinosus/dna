"""Recall/decay tuning knobs — pure, declarative defaults.

Ported (deterministic core only) from the upstream cognitive layer's
``recall_policy`` / ``decay_policy``. The KERNEL-reading resolvers
(``resolve_recall_policy`` / ``resolve_decay_policy``, which read a
``CognitivePolicy`` doc) are DELIBERATELY left behind — those are a
service concern (scope-overlay resolution over the source). Here the
dataclass field defaults ARE the calibrated values; the pure scoring
functions take an optional policy and fall back to these.

s-memory-verbs (2026-07-09). Parity-critical numeric constants — the TS
twin (``src/memory/policy.ts``) mirrors every default.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecallPolicy:
    """Ecphory scoring weights + gate thresholds (Tulving/Nairne/Semon).

    Defaults are the upstream 2026-06-15-calibrated values. ``structural``
    weights are theory-derived (model/language agnostic); the ``semantic``
    ones (``cosine_weight``, ``direct_threshold``) are coupled to the
    embedding space and would be re-tuned per model — but the deterministic
    ecphory core here never sees a live embedding, so they are inert unless a
    caller feeds ``semantic_scores``.
    """

    # semantic (embedding-space coupled)
    direct_threshold: float = 0.30
    cosine_weight: float = 0.61

    # structural (theory-derived, stable)
    content_weight: float = 0.55
    summary_partial_weight: float = 0.28
    co_topics_weight: float = 0.20
    source_refs_weight: float = 0.15
    affect_weight: float = 0.05
    time_weight: float = 0.05
    novelty_boost: float = 0.05
    recency_boost: float = 0.10
    saturation_decay: float = 0.6
    saturation_threshold: int = 3

    # retrieval shape
    limit_direct: int = 8
    limit_homophonic: int = 6


@dataclass(frozen=True)
class DecayPolicy:
    """Ebbinghaus retention knobs (per confidence tier + fallback stability)."""

    tier_faint: float = 5.0
    tier_firm: float = 15.0
    tier_burning: float = 45.0
    default_stability_days: float = 15.0
    max_stability_days: float = 60.0
    relevance_decay_seed: float = 0.95

    def tiers(self) -> dict[str, float]:
        return {
            "faint": self.tier_faint,
            "firm": self.tier_firm,
            "burning": self.tier_burning,
        }


DEFAULT_RECALL_POLICY = RecallPolicy()
DEFAULT_DECAY_POLICY = DecayPolicy()


__all__ = [
    "RecallPolicy",
    "DecayPolicy",
    "DEFAULT_RECALL_POLICY",
    "DEFAULT_DECAY_POLICY",
]


# ── E2 do épico das nove seções (spec 2026-08-03): os resolvers que a
# docstring acima dizia "deliberadamente deixados para trás" — a metade PURA.
# Quem tem o kernel busca o SPEC (com cache); aqui só se extrai, com os
# defaults do dataclass como fallback campo a campo.


def resolve_decay_policy(spec: dict | None) -> DecayPolicy:
    """`CognitivePolicy.decay` → DecayPolicy. Campo ausente/lixo = default."""
    d = ((spec or {}).get("decay") or {}) if isinstance(spec, dict) else {}
    tiers = d.get("stability_tiers") or {}

    def _num(v, fb):
        return float(v) if isinstance(v, (int, float)) and v > 0 else fb

    base = DecayPolicy()
    return DecayPolicy(
        tier_faint=_num(tiers.get("faint"), base.tier_faint),
        tier_firm=_num(tiers.get("firm"), base.tier_firm),
        tier_burning=_num(tiers.get("burning"), base.tier_burning),
        default_stability_days=_num(
            d.get("default_stability_days"), base.default_stability_days
        ),
        max_stability_days=_num(d.get("max_stability_days"), base.max_stability_days),
    )


def resolve_affect_palette(spec: dict | None) -> list | None:
    """`CognitivePolicy.affect.palette` — o vocabulário emocional PRÓPRIO do
    workspace (o Kind Engram abriu o campo de propósito em 03/08; esta é a
    ponta que faltava para a paleta ALCANÇAR o scoring)."""
    a = ((spec or {}).get("affect") or {}) if isinstance(spec, dict) else {}
    palette = a.get("palette")
    return palette if isinstance(palette, list) and palette else None

