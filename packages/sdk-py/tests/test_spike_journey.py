"""TDD for the Spike investigation arc (s-spike-traceability).

Spikes don't fit the Story arc (specify/plan/build) — that's why FOCUS showed a
Spike with "especificação/planejamento PULADA" and "construção" active, which is
nonsense for an investigation. A Spike has its own arc:
propose → investigate → findings → handoff, derived from its own signals
(created = proposed; in-progress/logged_hours/comments/linked-artifacts =
investigating; findings field or answered = findings; follow_up_story/adr =
handoff).
"""
from __future__ import annotations

from dna.extensions.sdlc.journey_derive import (
    SPIKE_PHASES,
    derive_journey,
    derive_spike_journey,
)


def _p(j, name):
    return next(p for p in j.phases if p.phase == name)


def test_spike_phases_canonical_order() -> None:
    j = derive_spike_journey("sp-foo", {"status": "proposed"})
    assert [p.phase for p in j.phases] == list(SPIKE_PHASES)
    assert SPIKE_PHASES == ("propose", "investigate", "findings", "handoff")


def test_proposed_spike_only_propose() -> None:
    j = derive_spike_journey("sp-foo", {"status": "proposed", "created_at": "2026-06-01T10:00:00Z"})
    assert _p(j, "propose").present is True
    assert _p(j, "investigate").present is False
    assert _p(j, "findings").present is False
    assert _p(j, "handoff").present is False
    assert j.active_phase == "propose"


def test_investigate_from_in_progress() -> None:
    j = derive_spike_journey("sp-foo", {"status": "in-progress"})
    assert _p(j, "investigate").present is True
    assert j.active_phase == "investigate"


def test_investigate_from_logged_hours() -> None:
    j = derive_spike_journey("sp-foo", {"status": "proposed", "logged_hours": 3})
    assert _p(j, "investigate").present is True


def test_investigate_from_linked_artifacts() -> None:
    """Linked Research/HtmlArtifact = work happened, even if status lags."""
    j = derive_spike_journey("sp-foo", {
        "status": "proposed",
        "research_refs": ["rsh-x"],
        "html_artifacts": ["ha-y"],
    })
    assert _p(j, "investigate").present is True


def test_findings_from_field() -> None:
    j = derive_spike_journey("sp-foo", {"status": "in-progress", "findings": "X beats Y"})
    assert _p(j, "findings").present is True
    assert "X beats Y" in _p(j, "findings").evidence


def test_findings_from_answered_status() -> None:
    j = derive_spike_journey("sp-foo", {"status": "answered"})
    assert _p(j, "findings").present is True


def test_handoff_from_follow_up_adr() -> None:
    j = derive_spike_journey("sp-foo", {"status": "answered", "follow_up_adr": "adr-mem"})
    h = _p(j, "handoff")
    assert h.present is True
    assert "adr-mem" in h.evidence


def test_handoff_from_follow_up_story() -> None:
    j = derive_spike_journey("sp-foo", {"status": "in-progress", "follow_up_story": "s-build"})
    assert _p(j, "handoff").present is True


def test_handoff_from_follow_up_spec() -> None:
    j = derive_spike_journey("sp-foo", {"status": "in-progress", "follow_up_spec": "spec-mem"})
    h = _p(j, "handoff")
    assert h.present is True
    assert "spec-mem" in h.evidence


def test_answered_spike_active_none() -> None:
    j = derive_spike_journey("sp-foo", {
        "status": "answered", "findings": "done", "follow_up_adr": "adr-x",
        "completed_at": "2026-06-01T12:00:00Z",
    })
    assert j.active_phase is None


def test_abandoned_spike_active_none() -> None:
    j = derive_spike_journey("sp-foo", {"status": "abandoned"})
    assert j.active_phase is None


def test_dispatcher_routes_spike_to_spike_arc() -> None:
    """derive_journey('Spike', ...) must use the spike arc, NOT the story arc."""
    j = derive_journey("Spike", "sp-foo", {"status": "in-progress"})
    assert [p.phase for p in j.phases] == list(SPIKE_PHASES)


def test_skipped_marks_gap_before_present() -> None:
    """findings present but no investigate signal → investigate is skipped.
    (status proposed avoids the 'answered ⇒ investigated' inference.)"""
    j = derive_spike_journey("sp-foo", {"status": "proposed", "findings": "x"})
    assert _p(j, "findings").present is True
    assert _p(j, "investigate").present is False
    assert _p(j, "investigate").skipped is True
