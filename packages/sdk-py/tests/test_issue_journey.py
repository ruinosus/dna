"""TDD for the Issue lifecycle arc (s-focus-stakeholder-view follow-up).

Issues don't fit the Story arc (specify/plan). They have their own market-aligned
lifecycle: report → triage → fix → resolve. Derived from the issue's own signals
(description/repro = its spec; severity+type = triaged; status/commit = fix;
resolution/closed = resolve).
"""
from __future__ import annotations

from dna.extensions.sdlc.journey_derive import (
    ISSUE_PHASES,
    derive_issue_journey,
)


def _p(j, name):
    return next(p for p in j.phases if p.phase == name)


def test_issue_phases_canonical_order() -> None:
    j = derive_issue_journey("i-foo", {"status": "open"})
    assert [p.phase for p in j.phases] == list(ISSUE_PHASES)
    assert ISSUE_PHASES == ("report", "triage", "fix", "resolve")


def test_open_issue_only_report() -> None:
    j = derive_issue_journey("i-foo", {"status": "open", "created_at": "2026-06-01T10:00:00Z"})
    assert _p(j, "report").present is True
    assert _p(j, "triage").present is False
    assert _p(j, "fix").present is False
    assert _p(j, "triage").skipped is False  # nothing later present
    assert j.active_phase == "report"


def test_triage_from_severity_and_type() -> None:
    j = derive_issue_journey("i-foo", {"status": "open", "severity": "high", "type": "bug"})
    tr = _p(j, "triage")
    assert tr.present is True


def test_triage_from_repro_even_if_open() -> None:
    j = derive_issue_journey("i-foo", {"status": "open", "reproduction_steps": ["passo 1", "passo 2"]})
    assert _p(j, "triage").present is True


def test_fix_from_in_progress() -> None:
    j = derive_issue_journey("i-foo", {"status": "in-progress"})
    assert _p(j, "fix").present is True


def test_resolve_from_resolution_and_active_none() -> None:
    j = derive_issue_journey("i-foo", {"status": "resolved", "closed_at": "2026-06-01T12:00:00Z", "resolution": "fixed in #50"})
    r = _p(j, "resolve")
    assert r.present is True
    assert "fixed in #50" in r.evidence
    assert j.active_phase is None


def test_wontfix_resolves() -> None:
    j = derive_issue_journey("i-foo", {"status": "wont-fix"})
    assert _p(j, "resolve").present is True


def test_ref_is_issue_prefixed() -> None:
    assert derive_issue_journey("i-foo", {"status": "open"}).ref == "Issue/i-foo"


def test_dispatcher_routes_by_kind() -> None:
    from dna.extensions.sdlc.journey_derive import derive_journey
    issue = derive_journey("Issue", "i-x", {"status": "open"})
    assert [p.phase for p in issue.phases] == list(ISSUE_PHASES)
    story = derive_journey("Story", "s-x", {"status": "todo"})
    assert story.phases[0].phase == "discover"
    # Spike now has its OWN arc (s-spike-traceability) — was wrongly routed to
    # the story arc before, which made FOCUS show "especificação PULADA" etc.
    spike = derive_journey("Spike", "sp-x", {"status": "in-progress"})
    assert spike.phases[0].phase == "propose"
