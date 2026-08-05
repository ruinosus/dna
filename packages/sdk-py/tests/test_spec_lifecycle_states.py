"""The Spec arc after `executed` + `shelved` — the two terminal states it lacked.

Both states were added because a real board could not say two true things:

1. A spec that was accepted and then SHIPPED stayed `accepted` forever, so
   every reader that counts by status counted a finished design as pending
   work. The consumer that hit it worked around the hole by DERIVING execution
   from citations (spec ↔ closed work items) — a screen-level patch for a
   model-level gap, and it read seven specs wrong.
2. A spec whose direction was decided as "not now, but the design holds" had
   only `deprecate`, which means OBSOLETE. Recording "postponed" as "no longer
   applicable" is not a rounding error; it throws away a design that is still
   correct.

So this file asserts three things, and the third is the one that matters most
here: (a) the new states exist and are reachable, (b) the arc refuses the moves
that would make a terminal state lie, and (c) NOTHING a pre-existing document
could say stopped being valid.
"""
from __future__ import annotations

import pytest

from dna.extensions.sdlc import (
    ARTIFACT_STATUSES,
    InvalidSpecTransition,
    SPEC_OPEN_STATUSES,
    SPEC_STATUSES,
    SPEC_TERMINAL_STATUSES,
    SPEC_TRANSITIONS,
    SpecKind,
    spec_board_bucket,
    validate_spec_transition,
)


# ── the vocabulary ───────────────────────────────────────────────────────────

def test_spec_arc_is_the_artifact_arc_plus_two():
    """SPEC_STATUSES is ARTIFACT_STATUSES widened, not replaced — the old five
    keep their positions AND their meanings."""
    assert SPEC_STATUSES[: len(ARTIFACT_STATUSES)] == ARTIFACT_STATUSES
    assert set(SPEC_STATUSES) - set(ARTIFACT_STATUSES) == {"executed", "shelved"}


def test_artifact_statuses_did_not_widen():
    """Plan and ADR declare their OWN enums; widening Spec must not widen them.

    A shared tuple that quietly grew would put `executed` in `plan create
    --status`'s choices while plan.kind.yaml still rejects it — a CLI that
    offers a value the write refuses."""
    assert set(ARTIFACT_STATUSES) == {
        "draft", "proposed", "accepted", "deprecated", "superseded"
    }


def test_open_and_terminal_partition_the_arc():
    """Every status is on exactly one side. A status in neither is a document
    no board knows what to do with."""
    assert SPEC_OPEN_STATUSES | SPEC_TERMINAL_STATUSES == set(SPEC_STATUSES)
    assert not (SPEC_OPEN_STATUSES & SPEC_TERMINAL_STATUSES)


def test_accepted_is_still_pending_work():
    """The defect was NOT that `accepted` counted as pending — it does owe work.
    It was that a shipped spec had nowhere else to go."""
    assert "accepted" in SPEC_OPEN_STATUSES
    assert spec_board_bucket("accepted") == "open"


# ── the transitions ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("current", ["draft", "proposed", "accepted", "shelved"])
def test_executed_is_reachable_from_every_live_state(current):
    """A design can ship without a formal `accept`, and a shelved design can be
    picked up and built. Refusing either would only teach people to lie about
    the status."""
    validate_spec_transition(current, "executed")  # no raise


@pytest.mark.parametrize("current", ["deprecated", "superseded"])
def test_executed_is_refused_from_a_dead_spec(current):
    """`deprecated` = the design no longer applies; `superseded` = the
    REPLACEMENT is what got built. Marking either executed hides which document
    the code actually follows."""
    with pytest.raises(InvalidSpecTransition) as exc:
        validate_spec_transition(current, "executed")
    # The refusal NAMES the current status and what would work — a denial that
    # says neither just buys another guess.
    assert current in str(exc.value)
    assert "accepted" in str(exc.value)


@pytest.mark.parametrize("current", ["draft", "proposed", "accepted"])
def test_shelve_is_reachable_from_every_undone_state(current):
    validate_spec_transition(current, "shelved")  # no raise


@pytest.mark.parametrize("current", ["executed", "deprecated", "superseded"])
def test_shelve_is_refused_from_a_finished_spec(current):
    """Shelving is a decision about work NOT YET DONE. You cannot postpone what
    already shipped, and you cannot postpone what is already dead."""
    with pytest.raises(InvalidSpecTransition):
        validate_spec_transition(current, "shelved")


def test_shelved_is_reversible_by_the_pre_existing_verbs():
    """`shelved` is terminal on the BOARD, not in the graph: the direction can
    change back, and when it does the old verbs un-shelve it. They are
    unconstrained, so this is a statement about the arc, not a loophole."""
    for target in ("proposed", "accepted"):
        assert target not in SPEC_TRANSITIONS
        validate_spec_transition("shelved", target)  # no raise


@pytest.mark.parametrize("target", ["proposed", "accepted", "deprecated", "superseded"])
@pytest.mark.parametrize("current", list(SPEC_STATUSES))
def test_pre_existing_targets_stay_unguarded(current, target):
    """The four transitions that existed before are still total.

    A rule applied retroactively would refuse moves that were legal when the
    documents were written — the one thing an additive change may not do. An
    executed spec being superseded later is exactly such a move, and it is
    legitimate."""
    validate_spec_transition(current, target)  # no raise


def test_a_status_less_legacy_doc_is_never_illegal():
    """`status` is required by the schema, but a document harvested from disk
    before this repo owned the arc may not carry one. It is not retroactively
    in violation."""
    validate_spec_transition(None, "executed")
    validate_spec_transition(None, "shelved")


# ── the projection ───────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "status,bucket",
    [
        ("draft", "open"),
        ("proposed", "open"),
        ("accepted", "open"),
        ("executed", "done"),
        ("shelved", "parked"),
        ("deprecated", "parked"),
        ("superseded", "parked"),
    ],
)
def test_board_bucket_is_the_one_status_to_column_mapping(status, bucket):
    """The mapping a board projection owes a Spec, so no consumer has to derive
    it from citations again. `executed` is the only achievement; the other three
    terminal states are closures and must not be counted as work done — nor left
    in "to do"."""
    assert spec_board_bucket(status) == bucket


def test_no_terminal_status_reads_as_pending():
    assert all(spec_board_bucket(s) != "open" for s in SPEC_TERMINAL_STATUSES)


def test_an_unknown_status_reads_as_open():
    """Fail toward VISIBLE. A state nobody declared is the one state a board
    must not quietly retire — an invented status silently bucketed as done is
    how work disappears."""
    assert spec_board_bucket("whatever") == "open"
    assert spec_board_bucket(None) == "open"


# ── the schema carries the evidence ──────────────────────────────────────────

def test_schema_declares_the_evidence_fields():
    """The states are only as good as their proof: a terminal status nobody can
    audit is a claim, not a record. The CLI requires the text; the schema is
    where it lands and where a reader finds it."""
    props = SpecKind().schema()["properties"]
    for field in (
        "executed_at", "execution_summary",
        "shelved_at", "shelve_reason",
        "deprecated_at", "deprecation_reason",
    ):
        assert field in props, f"{field} missing from Spec schema"
        assert props[field]["type"] == "string"


def test_evidence_fields_are_optional():
    """Required-ness belongs to the VERB, not the schema: a Spec still in
    `draft` has no execution to prove, and making the field required would fail
    every document that never reaches a terminal state."""
    assert set(SpecKind().schema()["required"]) == {"title", "date", "status"}


def test_a_legacy_spec_doc_still_validates():
    """Retro-compat, end to end: the exact shape a Spec had before this change
    is still a legal Spec."""
    legacy = {
        "title": "Phase 16 — Scope segregation",
        "date": "2026-05-08",
        "status": "accepted",
        "phase": "done",
        "pattern": "rfc",
    }
    schema = SpecKind().schema()
    assert all(k in schema["properties"] for k in legacy)
    assert legacy["status"] in schema["properties"]["status"]["enum"]
    # And it projects the way it always did: accepted-not-executed is open work.
    assert spec_board_bucket(legacy["status"]) == "open"
