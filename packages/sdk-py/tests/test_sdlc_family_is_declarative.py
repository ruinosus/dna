"""Item 13 — a new work item participates by DECLARING, with no list edited.

Thirteen Kind-name lists, thirteen memberships, one intent. The proof they had
diverged is in the tree: the v1.3 Milestone→Epic rename updated one list and
missed another, and Epic silently inherited across scopes for a release.

The claim this file makes is testable and it is the point of the whole exercise:
register a brand-new Kind that declares ``sdlc.work-item``, and it appears in the
digest, the gallery, the board probe, the transitions, the comments and the date
contract — with nothing in this repository edited.
"""
from __future__ import annotations

import pytest

from dna.application import sdlc as S
from dna.application import sdlc_family as F
from dna.kernel import Kernel
from dna.kernel.meta import DeclarativeKindPort
from dna.kernel.models import TypedKindDefinition

# ── the fallbacks are pinned to the live declarations ───────────────────────


def test_fallback_families_equal_what_the_kinds_declare():
    """The kernel-less fallbacks exist for pure consumers. If they were allowed
    to drift they would just be the fourteenth list."""
    k = Kernel.auto()
    for trait, names in F.FALLBACK_FAMILIES.items():
        assert tuple(sorted(k.kinds_with_trait(trait))) == names, trait


def test_dated_spec_fields_equals_the_derived_table():
    k = Kernel.auto()
    assert S.DATED_SPEC_FIELDS == F.dated_spec_fields(k)


def test_status_enums_fallback_agrees_with_each_kinds_own_schema():
    k = Kernel.auto()
    for kind, enum in S._STATUS_ENUMS.items():
        assert F.status_enum_for(k, kind) == enum, kind


def test_governed_kinds_fallback_equals_the_trait():
    from dna.extensions.guardrails.write_guards import (
        TRAIT_GOVERNED,
        _GOVERNED_KINDS_FALLBACK,
    )

    k = Kernel.auto()
    assert set(k.kinds_with_trait(TRAIT_GOVERNED)) == set(_GOVERNED_KINDS_FALLBACK)


# ── the six Kinds that had no named write tool (item 7) ─────────────────────


def test_every_work_item_kind_is_transitionable():
    """Item 7: six of the ten Kinds the digest reads had no named create /
    transition tool, and `set_status` refused them. That resolved BY DECLARATION
    — a work item is writable because it carries the trait and declares its own
    status enum, not because somebody added it to a tuple."""
    k = Kernel.auto()
    work_items = set(F.work_item_kinds(k))
    transitionable = set(F.transitionable_kinds(k))
    assert work_items == transitionable, (
        f"work items with no declared status arc: "
        f"{sorted(work_items - transitionable)}"
    )
    # The four that used to be the whole writable set, and the four that were not.
    assert {"Story", "Issue", "Feature", "Epic"} <= transitionable
    assert {"Spike", "Bug", "Task", "Initiative"} <= transitionable


def test_a_previously_unwritable_kind_now_transitions():
    k = Kernel.auto()
    S.validate_transition(
        "Spike", "answered", valid=F.status_enum_for(k, "Spike"))
    with pytest.raises(S.InvalidTransition, match="not a valid Spike status"):
        S.validate_transition(
            "Spike", "done", valid=F.status_enum_for(k, "Spike"))


# ── THE proof: one declaration, six participations, no list edited ──────────


_NEW_KIND_DESCRIPTOR = {
    "apiVersion": "github.com/ruinosus/dna/core/v1",
    "kind": "KindDefinition",
    "metadata": {"name": "chore"},
    "spec": {
        "target_api_version": "example.com/board/v1",
        "target_kind": "Chore",
        "alias": "board-chore",
        "origin": "example.com/board",
        "plane": "record",
        "tenant_scope": "global",
        "traits": ["sdlc.work-item", "sdlc.dated"],
        "storage": {"type": "yaml", "dir": "chores"},
        "schema": {
            "type": "object",
            "required": ["status"],
            "properties": {
                "title": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["open", "doing", "done"],
                },
                "created_at": {"type": "string"},
                "updated_at": {"type": "string"},
                "timeline": {"type": "array", "items": {"type": "object"}},
            },
        },
    },
}


@pytest.fixture
def kernel_with_new_work_item():
    k = Kernel.auto()
    port = DeclarativeKindPort.from_typed(
        TypedKindDefinition.from_raw(_NEW_KIND_DESCRIPTOR))
    k.kind(port)
    return k


def test_a_new_kind_joins_every_family_by_declaring_one_trait(
    kernel_with_new_work_item,
):
    k = kernel_with_new_work_item
    assert "Chore" in F.work_item_kinds(k)      # ...the work-item family
    assert "Chore" in F.digest_kinds(k)         # ...the digest walk
    assert "Chore" in F.producer_kinds(k)       # ...the gallery / produces
    assert "Chore" in F.board_probe_order(k)    # ...the board-card probe
    assert "Chore" in F.transitionable_kinds(k)  # ...set_status
    assert F.dated_spec_fields(k)["Chore"] == ("created_at", "updated_at")
    assert F.status_enum_for(k, "Chore") == ("open", "doing", "done")


def test_the_new_kind_transitions_and_comments_over_the_shared_core(
    kernel_with_new_work_item,
):
    """Not just "the lists include it" — the write verbs actually work on it."""

    class _K:
        def __init__(self, real):
            self._real = real
            self.docs = {
                ("sc", "Chore", "c-1"): {
                    "apiVersion": "example.com/board/v1", "kind": "Chore",
                    "metadata": {"name": "c-1"},
                    "spec": {"title": "T", "status": "open"},
                },
            }

        def __getattr__(self, item):
            return getattr(self._real, item)

        async def get_document(self, scope, kind, name):
            return self.docs.get((scope, kind, name))

        async def write_document(self, scope, kind, name, raw, **kw):
            self.docs[(scope, kind, name)] = raw

    k = _K(kernel_with_new_work_item)
    import asyncio

    out = asyncio.run(S.set_status(k, "sc", "Chore", "c-1", "doing"))
    assert out["to"] == "doing"
    note = asyncio.run(S.add_comment(k, "sc", "Chore", "c-1", "narrating"))
    assert note["event_type"] == "comment"
    with pytest.raises(S.InvalidTransition, match="not a valid Chore status"):
        asyncio.run(S.set_status(k, "sc", "Chore", "c-1", "review"))


def test_a_kind_without_the_trait_joins_nothing(kernel_with_new_work_item):
    """The trait is what does the work — not the plane, the namespace or the
    presence of a status enum."""
    k = Kernel.auto()
    assert "Chore" not in F.work_item_kinds(k)
    assert "ADR" not in F.work_item_kinds(k)      # declares sdlc.decision only
    assert "ADR" in F.digest_kinds(k)
    assert "ADR" not in F.transitionable_kinds(k)
