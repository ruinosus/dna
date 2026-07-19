"""Feedback loop — dispositions tune the ranker (pure application logic).

s-intel-feedback-loop. The flywheel: the reader marks each delivered insight as
useful (``actioned``) or noise (``dismissed``); that disposition is recorded as
an engram in the memory co-pillar (a ``Engram``) and, on the NEXT pass,
tunes the ranker so semantically-similar candidates are suppressed (``dismissed``
raises the effective threshold for that pattern/source) or reinforced
(``actioned``). Relevance improves on its own; the KPI is the noise rate falling
over time.

This module is PURE: the score adjustment and the precision metric are functions
of numbers the engine computes (per-candidate cosine to the dismissed/actioned
engrams via ``kernel.embed`` + :func:`dna.memory.semantic.cosine_similarity`).
The kernel-bound half (recall the engrams, embed, write the feedback memory)
lives in the engine + ``set_insight_state``. Keeping it pure makes the decision
inspectable and the TypeScript twin (i-027) a straight mirror.
"""
from __future__ import annotations

from typing import Any

# The tag every intel-feedback engram carries, so the ranker can find just the
# feedback memories (not every Engram in the scope). Inspectable const.
FEEDBACK_TAG = "intel-feedback"
DISPOSITION_DISMISSED = "dismissed"
DISPOSITION_ACTIONED = "actioned"

# The dispositions that produce a feedback engram (the ranker-tuning ones).
FEEDBACK_DISPOSITIONS: tuple[str, ...] = (DISPOSITION_DISMISSED, DISPOSITION_ACTIONED)

# Above this cue↔engram cosine a candidate is judged "the same pattern" as a
# past disposition. Deliberately LOWER than the dedup threshold: dedup drops
# near-identical repeats; feedback reaches the merely-similar. Inspectable.
FEEDBACK_SIM_THRESHOLD = 0.80

# A dismissed-similar candidate loses this much score — enough to push a
# clear-the-bar candidate under a typical 0.6 threshold (i.e. RAISE the effective
# threshold for that pattern). An actioned-similar candidate gains a smaller
# reinforcement bump. Inspectable constants.
DISMISS_PENALTY = 0.50
ACTION_BONUS = 0.10


def feedback_area(source_ref: str | None) -> str:
    """The Engram ``area`` under which a source's feedback engrams live —
    ``Intel/<source>`` — so the ranker recalls only THIS source's feedback."""
    return f"Intel/{source_ref or '_'}"


def adjust_score(
    base_score: float,
    sim_dismissed: float,
    sim_actioned: float,
    *,
    threshold: float = FEEDBACK_SIM_THRESHOLD,
    dismiss_penalty: float = DISMISS_PENALTY,
    action_bonus: float = ACTION_BONUS,
) -> tuple[float, list[str]]:
    """Adjust a candidate's actionability score by past dispositions.

    ``sim_dismissed`` / ``sim_actioned`` are the candidate's max cosine to the
    source's dismissed / actioned engrams. When either clears ``threshold`` the
    score is penalized / reinforced. Returns ``(adjusted, notes)`` where notes
    explain each contribution (appended to the ranker rationale — the number
    stays inspectable). Clamped to ``[0, 1]``. Pure."""
    adjusted = base_score
    notes: list[str] = []
    if sim_dismissed >= threshold:
        adjusted -= dismiss_penalty
        notes.append(
            f"-{dismiss_penalty:.2f} similar to a dismissed insight "
            f"(cos {sim_dismissed:.2f})"
        )
    if sim_actioned >= threshold:
        adjusted += action_bonus
        notes.append(
            f"+{action_bonus:.2f} similar to an actioned insight "
            f"(cos {sim_actioned:.2f})"
        )
    adjusted = max(0.0, min(1.0, adjusted))
    return round(adjusted, 4), notes


def precision(actioned: int, dismissed: int) -> float | None:
    """Precision of the feed = ``actioned / (actioned + dismissed)``. ``None``
    when no disposition has been given yet (undefined, not zero). Pure."""
    denom = actioned + dismissed
    return round(actioned / denom, 4) if denom else None


def noise_rate(actioned: int, dismissed: int) -> float | None:
    """The product KPI = ``dismissed / (actioned + dismissed)`` — the fraction of
    delivered insights the reader called noise. ``None`` until a disposition
    exists. Pure (``1 - precision``)."""
    denom = actioned + dismissed
    return round(dismissed / denom, 4) if denom else None


def summarize_states(counts: dict[str, int]) -> dict[str, Any]:
    """Build the inspectable metrics dict from per-state insight counts.

    ``counts`` maps state → count (new/actioned/dismissed/snoozed). Returns
    ``{counts, actioned, dismissed, precision, noise_rate}``. Pure."""
    actioned = int(counts.get(DISPOSITION_ACTIONED, 0))
    dismissed = int(counts.get(DISPOSITION_DISMISSED, 0))
    return {
        "counts": dict(counts),
        "actioned": actioned,
        "dismissed": dismissed,
        "precision": precision(actioned, dismissed),
        "noise_rate": noise_rate(actioned, dismissed),
    }


__all__ = [
    "FEEDBACK_TAG",
    "DISPOSITION_DISMISSED",
    "DISPOSITION_ACTIONED",
    "FEEDBACK_DISPOSITIONS",
    "FEEDBACK_SIM_THRESHOLD",
    "DISMISS_PENALTY",
    "ACTION_BONUS",
    "feedback_area",
    "adjust_score",
    "precision",
    "noise_rate",
    "summarize_states",
]
