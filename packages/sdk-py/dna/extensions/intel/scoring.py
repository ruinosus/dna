"""scoring.py — o tuning do motor de intel como DADO (`CognitivePolicy.intel`).

Os pesos do ranker, o limiar do dedup e as forças do feedback eram constantes
"inspecionáveis" — inspecionáveis, mas não decidíveis: um tenant que discorde
do `0.85` da barra de ação não tinha onde declarar (varredura de valores,
03/08/2026; cauda do #36).

A seção mora na CognitivePolicy — o doc ÚNICO de política do workspace — e
não em cada `IntelSource`: os pesos são do MOTOR, e espalhá-los por fonte
fragmentaria o tuning (o `threshold` por fonte continua no IntelSource, que é
onde ele sempre morou).

O resolver segue a casa: puro, fail-soft, clamp em tudo — política é dado de
tenant, e um peso absurdo declara-se, não executa.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["IntelScoring", "resolve_intel_scoring"]


def _num(v: object, fb: float, lo: float, hi: float) -> float:
    if isinstance(v, (int, float)) and lo <= float(v) <= hi:
        return float(v)
    return fb


@dataclass(frozen=True)
class IntelScoring:
    """`CognitivePolicy.intel` — defaults espelham as constantes que substituem."""

    #: Score a partir do qual um insight "exige ação" nas telas (o antigo
    #: ACTION_BAR do portal — julgamento de produto, agora declarável).
    action_bar: float = 0.85
    #: Pesos do ranker (base + ação concreta + evidência + PIR).
    ranker_base: float = 0.30
    ranker_has_action: float = 0.30
    ranker_pir_match: float = 0.15
    evidence_weights: dict[str, float] = field(
        default_factory=lambda: {
            "evidence-based": 0.25,
            "opinion-practice": 0.12,
            "anecdotal": 0.0,
        }
    )
    #: Acima disto dois insights são "o mesmo" (dedup por cosseno).
    dedup_cosine_threshold: float = 0.97
    #: Feedback: acima disto um candidato é "o mesmo padrão" de uma disposição
    #: passada; e o quanto um dismiss/action passado pesa no score novo.
    feedback_sim_threshold: float = 0.80
    feedback_dismiss_penalty: float = 0.50
    feedback_action_bonus: float = 0.10


def resolve_intel_scoring(spec: dict | None) -> IntelScoring:
    """`CognitivePolicy.intel` → IntelScoring. Lixo/ausente = default campo a
    campo (paridade sem doc: byte-igual ao comportamento de antes)."""
    d = ((spec or {}).get("intel") or {}) if isinstance(spec, dict) else {}
    if not isinstance(d, dict):
        d = {}
    base = IntelScoring()
    ranker = d.get("ranker") if isinstance(d.get("ranker"), dict) else {}
    dedup = d.get("dedup") if isinstance(d.get("dedup"), dict) else {}
    fb = d.get("feedback") if isinstance(d.get("feedback"), dict) else {}

    pesos = dict(base.evidence_weights)
    declarados = ranker.get("evidence_weights")
    if isinstance(declarados, dict):
        for chave, fallback in base.evidence_weights.items():
            pesos[chave] = _num(declarados.get(chave), fallback, 0.0, 1.0)

    return IntelScoring(
        action_bar=_num(d.get("action_bar"), base.action_bar, 0.0, 1.0),
        ranker_base=_num(ranker.get("base"), base.ranker_base, 0.0, 1.0),
        ranker_has_action=_num(ranker.get("has_action"), base.ranker_has_action, 0.0, 1.0),
        ranker_pir_match=_num(ranker.get("pir_match"), base.ranker_pir_match, 0.0, 1.0),
        evidence_weights=pesos,
        dedup_cosine_threshold=_num(
            dedup.get("cosine_threshold"), base.dedup_cosine_threshold, 0.5, 1.0
        ),
        feedback_sim_threshold=_num(
            fb.get("sim_threshold"), base.feedback_sim_threshold, 0.0, 1.0
        ),
        feedback_dismiss_penalty=_num(
            fb.get("dismiss_penalty"), base.feedback_dismiss_penalty, 0.0, 1.0
        ),
        feedback_action_bonus=_num(
            fb.get("action_bonus"), base.feedback_action_bonus, 0.0, 1.0
        ),
    )
