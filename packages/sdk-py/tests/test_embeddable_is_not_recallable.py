"""Item 14 — ``embeddable`` and ``recallable`` are two questions, not one.

``MEMORY_KINDS`` (3) and ``kernel.embeddable_kinds()`` (7) intersected in exactly
ONE Kind. That is not a coincidence to be tidied away by unifying them: ``embed:``
declares WHICH FIELDS of a Kind carry an embeddable payload, and
``memory.recallable`` declares that a Kind participates in the memory verbs —
retention decay, affect weighting, reconsolidation on recall. An ADR should be
findable by semantic search WITHOUT being decay-ranked as a memory. Overloading
``embed:`` to mean both would have made every embeddable Kind a memory the moment
somebody declared a field on it.
"""
from __future__ import annotations

from dna.kernel import Kernel
from dna.memory.semantic import ENGRAM_TEXT_FIELDS
from dna.memory.verbs import MEMORY_KINDS, TRAIT_RECALLABLE, recallable_kinds


def test_the_two_sets_are_genuinely_different():
    k = Kernel.auto()
    recallable = set(recallable_kinds(k))
    embeddable = set(k.embeddable_kinds())
    assert recallable, "no Kind declares memory.recallable"
    assert embeddable, "no Kind declares embed:"
    assert recallable != embeddable, (
        "if these ever became equal, one of the two declarations stopped "
        "carrying its own meaning"
    )
    # There ARE embeddable Kinds that are deliberately not memories.
    assert embeddable - recallable, (
        "every embeddable Kind became a memory — that is the overload this "
        "trait exists to prevent"
    )


def test_recallable_is_the_trait_not_a_list():
    k = Kernel.auto()
    assert set(recallable_kinds(k)) == set(k.kinds_with_trait(TRAIT_RECALLABLE))


def test_recallable_falls_back_to_the_static_list_without_a_registry():
    """A narrow duck-typed kernel (a test double) keeps the pre-trait behavior
    exactly — the fallback is not a guess, it is the old constant."""
    assert recallable_kinds(object()) == MEMORY_KINDS


def test_the_static_fallback_still_matches_the_declarations():
    """The constant survives for kernel-less callers, so it must not drift from
    what the Kinds declare."""
    k = Kernel.auto()
    assert set(MEMORY_KINDS) == set(recallable_kinds(k))


def test_engram_cue_and_index_agree():
    """The cue side embeds ENGRAM_TEXT_FIELDS; the index side embeds ``embed:``.

    They were (area, title, summary, body) and (summary, body): recall built its
    query vector from four planes and compared it against a document vector that
    had never seen two of them. Every cosine was computed between two different
    notions of what the memory says."""
    k = Kernel.auto()
    port = k.kind_port_for("Engram")
    assert port is not None
    assert tuple(port.embed_fields) == ENGRAM_TEXT_FIELDS, (
        "engram.kind.yaml `embed:` and dna.memory.semantic.ENGRAM_TEXT_FIELDS "
        "must name the same fields in the same order — the index and the cue "
        "have to mean the same thing"
    )
