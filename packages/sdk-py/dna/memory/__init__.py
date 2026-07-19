"""``dna.memory`` — memory verbs over existing Kinds + the deterministic
scoring core.

Memory in DNA is the Kinds the SDK already has (Engram, Research,
Evidence) recalled by the same ``RecordSearchProvider`` that powers search,
with four declarative verbs and the affective/bi-temporal fields already in the
Engram schema. This package holds:

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
from dna.memory.semantic import (
    ENGRAM_TEXT_FIELDS,
    cosine_similarity,
    ecphory_rank,
    engram_text,
    fuse_semantic_recall,
    semantic_scores_from_vectors,
)
from dna.memory.personal import (
    PERSONAL_SCOPE,
    PERSONAL_TENANT_PREFIX,
    PERSONAL_TENANT_SCHEME,
    WORKSPACE_SCOPE,
    MemoryScope,
    PersonalIdentityRequired,
    PersonalOverrideRejected,
    assert_no_personal_override,
    is_personal_tenant,
    personal_tenant,
    resolve_memory_tenant,
    tenant_scheme,
)
from dna.memory.verbs import (
    MEMORY_KINDS,
    backfill_index,
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
    "backfill_index",
    # personal / private per-user memory (ADR-personal-memory)
    "PERSONAL_TENANT_SCHEME",
    "PERSONAL_TENANT_PREFIX",
    "MemoryScope",
    "WORKSPACE_SCOPE",
    "PERSONAL_SCOPE",
    "PersonalIdentityRequired",
    "PersonalOverrideRejected",
    "personal_tenant",
    "is_personal_tenant",
    "tenant_scheme",
    "resolve_memory_tenant",
    "assert_no_personal_override",
    # ecphory
    "EngramRef",
    "EcphoryScore",
    "EcphoryRunResult",
    "score_engram",
    "apply_semon_adjustments",
    "expand_homophony",
    "run_ecphory",
    # semantic recall (s-memory-semantic-recall)
    "ENGRAM_TEXT_FIELDS",
    "engram_text",
    "cosine_similarity",
    "semantic_scores_from_vectors",
    "ecphory_rank",
    "fuse_semantic_recall",
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
