"""``dna.memory`` — memory verbs over existing Kinds + the deterministic
scoring core.

Memory in DNA is the Kinds the SDK already has (LessonLearned, Research,
Evidence) recalled by the same ``RecordSearchProvider`` that powers search,
with four declarative verbs and the affective/bi-temporal fields already in the
LessonLearned schema. This package holds:

  * the four verbs (``remember`` / ``recall`` / ``forget`` / ``consolidate``) —
    async, kernel-bound (``dna.memory.verbs``);
  * the DETERMINISTIC pure scoring core ported from the upstream cognitive
    layer — ecphory (Semon's Law of Ecphory), BM25 retrieval, Ebbinghaus decay,
    encoding-context stamping, CoALA classification, recall/decay policy.

Left behind on purpose: LLM scribes, schedulers, deep-sleep, workers, and the
kernel-reading policy resolvers — those are a service, not the SDK.

rsh-memory-similarity-evolution → s-memory-verbs (2026-07-09).
"""
from __future__ import annotations

from dna.memory.decay import (
    confidence_score_numeric,
    currently_valid,
    days_since,
    decay_adjusted_score,
    ebbinghaus_retention,
    recall_bump,
    stability_from_spec,
)
from dna.memory.ecphory import (
    EcphoryRunResult,
    EcphoryScore,
    EngramRef,
    apply_semon_adjustments,
    expand_homophony,
    run_ecphory,
    score_engram,
)
from dna.memory.encoding_context import (
    derive_encoding_context,
    stamp_encoding_context_if_absent,
    time_of_day,
)
from dna.memory.memory_type import classify_memory_type
from dna.memory.policy import (
    DEFAULT_DECAY_POLICY,
    DEFAULT_RECALL_POLICY,
    DecayPolicy,
    RecallPolicy,
)
from dna.memory.retrieval import Memory, RankedMemory, rank_memories
from dna.memory.verbs import (
    MEMORY_KINDS,
    consolidate,
    forget,
    recall,
    remember,
)

__all__ = [
    # verbs
    "MEMORY_KINDS",
    "remember",
    "recall",
    "forget",
    "consolidate",
    # ecphory
    "EngramRef",
    "EcphoryScore",
    "EcphoryRunResult",
    "score_engram",
    "apply_semon_adjustments",
    "expand_homophony",
    "run_ecphory",
    # retrieval
    "Memory",
    "RankedMemory",
    "rank_memories",
    # decay
    "confidence_score_numeric",
    "stability_from_spec",
    "days_since",
    "ebbinghaus_retention",
    "recall_bump",
    "decay_adjusted_score",
    "currently_valid",
    # encoding context
    "time_of_day",
    "derive_encoding_context",
    "stamp_encoding_context_if_absent",
    # memory type
    "classify_memory_type",
    # policy
    "RecallPolicy",
    "DecayPolicy",
    "DEFAULT_RECALL_POLICY",
    "DEFAULT_DECAY_POLICY",
]
