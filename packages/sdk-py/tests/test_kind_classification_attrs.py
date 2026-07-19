"""s-kernel-kindport-classification-attrs — the kernel's Kind-classification
sets are now DERIVED from per-KindPort attributes (is_schema_affecting /
is_overlayable / scope_inheritable) instead of hardcoded name frozensets.

The crisp gate: the derived sets must EQUAL the original hardcoded frozensets,
exactly — behavior-identical. Plus the attribute defaults + a couple of
representative Kinds.
"""
from __future__ import annotations

from dna.kernel import Kernel
from dna.kernel.kind_base import KindBase


# The original hardcoded frozensets (pre-refactor), locked here as the oracle.
# "Tool" left this set on s-tool-kind-descriptor (f-dna-tools-as-data): the
# Tool Kind migrated from a composition-plane class to a RECORD-plane
# descriptor. A record Kind carries no composition signal by construction
# (DeclarativeKindPort has no is_schema_affecting), which is correct — a Tool
# is not a prompt target and never composes into an agent prompt, so writing
# a Tool doc must NOT invalidate the composition schema cache. Agents still
# reference tools by name via dep_filters.tools (a filter resolved at
# composition, not a schema contribution).
ORIG_SCHEMA_INVALIDATING = frozenset({
    "Genome", "KindDefinition", "LayerPolicy",
    "Agent", "Skill", "Soul", "Guardrail",
    "SafetyPolicy", "Hook", "Recognizer",
})
ORIG_NON_OVERLAYABLE = frozenset({"Genome", "KindDefinition", "LayerPolicy"})
ORIG_NON_INHERITABLE = frozenset({
    "Story", "Issue", "Feature", "Milestone", "Roadmap",
    "Narrative", "VibeSession", "Engram", "Plan",
    "Genome", "KindDefinition", "LayerPolicy",
})


def _kernel() -> Kernel:
    return Kernel.auto()


def test_schema_invalidating_derived_equals_original():
    assert set(_kernel()._SCHEMA_INVALIDATING_KINDS) == set(ORIG_SCHEMA_INVALIDATING)


def test_non_overlayable_derived_equals_original():
    assert set(_kernel()._NON_OVERLAYABLE_KINDS) == set(ORIG_NON_OVERLAYABLE)


def test_non_inheritable_derived_equals_original():
    # Includes the two legacy names with no registered Kind (Milestone,
    # VibeSession) via _LEGACY_NON_INHERITABLE.
    assert set(_kernel()._NON_INHERITABLE_KINDS) == set(ORIG_NON_INHERITABLE)


def test_inheritable_denylist_membership_unchanged():
    inh = _kernel()._INHERITABLE_KINDS
    # everything inherits by default EXCEPT the non-inheritable denylist
    assert "Agent" in inh
    assert "Skill" in inh
    assert "Story" not in inh
    assert "Genome" not in inh
    assert "Milestone" not in inh  # legacy denylist name


def test_removed_kinds_stays_constant():
    # OracleVerdict/Oracle are removed (no registered Kind) — still a constant.
    rk = _kernel()._REMOVED_KINDS
    assert "OracleVerdict" in rk and "Oracle" in rk


def test_kindbase_attribute_defaults():
    class Bare(KindBase):
        pass
    b = Bare()
    assert b.is_schema_affecting is False
    assert b.is_overlayable is True
    assert b.scope_inheritable is True


def test_representative_kind_attributes():
    kinds = {getattr(kp, "kind", None): kp for kp in _kernel()._kinds.values()}
    # structural: schema-affecting + non-overlayable + non-inheritable
    pkg = kinds["Genome"]
    assert pkg.is_schema_affecting and not pkg.is_overlayable and not pkg.scope_inheritable
    # schema-only Kind
    ua = kinds["Agent"]
    assert ua.is_schema_affecting and ua.is_overlayable and ua.scope_inheritable
    # ledger Kind: non-inheritable only
    story = kinds["Story"]
    assert not story.is_schema_affecting and story.is_overlayable and not story.scope_inheritable
