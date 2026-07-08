"""TDD for the derived journey (s-journey-derived).

The journey of a Story is a PURE FUNCTION of its own state (timeline + status +
created/closed) plus its linked artifacts (Spec via spec_refs, Plan via a
story ref, LessonLearned via source_refs). Computed on read — no WorkflowEvent
writes needed. These tests pin the 6-phase derivation rules (discover/specify/
plan/build/verify/reflect) + skipped detection.
"""
from __future__ import annotations

from dna.extensions.sdlc.journey_derive import (
    JOURNEY_PHASES,
    derive_story_journey,
)


def _phase(journey, name):
    return next(p for p in journey.phases if p.phase == name)


def test_phases_always_six_in_canonical_order() -> None:
    j = derive_story_journey("s-foo", {"status": "todo"})
    assert [p.phase for p in j.phases] == list(JOURNEY_PHASES)
    assert "verify" in JOURNEY_PHASES
    # verify sits between build and reflect.
    phases = list(JOURNEY_PHASES)
    assert phases.index("build") < phases.index("verify") < phases.index("reflect")


def test_bare_story_only_discover_present_nothing_skipped() -> None:
    # Just created, todo, no AC/spec/plan/commit/lesson.
    j = derive_story_journey("s-foo", {"status": "todo", "created_at": "2026-05-31T10:00:00Z"})
    assert _phase(j, "discover").present is True
    assert _phase(j, "specify").present is False
    assert _phase(j, "build").present is False
    # No later phase present → earlier absent phases are NOT skipped.
    assert _phase(j, "specify").skipped is False
    assert j.active_phase == "discover"


def test_specify_present_from_ac_and_dod() -> None:
    j = derive_story_journey(
        "s-foo",
        {"status": "todo", "acceptance_criteria": [{"text": "x"}], "definition_of_done": [{"text": "y"}]},
    )
    sp = _phase(j, "specify")
    assert sp.present is True
    assert "AC" in sp.evidence


def test_specify_present_from_linked_spec_ref() -> None:
    j = derive_story_journey(
        "s-foo",
        {"status": "todo", "spec_refs": ["spec-auth-v1"]},
        specs=[{"name": "spec-auth-v1", "spec": {"created_at": "2026-05-20T09:00:00Z"}}],
    )
    sp = _phase(j, "specify")
    assert sp.present is True
    assert sp.source_ref == "Spec/spec-auth-v1"
    assert sp.at == "2026-05-20T09:00:00Z"


def test_plan_present_from_linked_plan() -> None:
    j = derive_story_journey(
        "s-foo",
        {"status": "in-progress"},
        plans=[{"name": "plan-foo", "spec": {"story_ref": "s-foo", "created_at": "2026-05-21T09:00:00Z"}}],
    )
    pl = _phase(j, "plan")
    assert pl.present is True
    assert pl.source_ref == "Plan/plan-foo"


def test_build_present_from_timeline_in_progress() -> None:
    j = derive_story_journey(
        "s-foo",
        {
            "status": "in-progress",
            "timeline": [
                {"type": "status_change", "to": "in-progress", "at": "2026-05-22T08:00:00Z", "actor": "claude-code"},
            ],
        },
    )
    b = _phase(j, "build")
    assert b.present is True
    assert b.at == "2026-05-22T08:00:00Z"


def test_build_present_from_commit_ref() -> None:
    j = derive_story_journey("s-foo", {"status": "review", "commit_ref": "abc1234567"})
    b = _phase(j, "build")
    assert b.present is True
    assert "abc1234" in b.evidence


def test_reflect_present_when_done_and_active_is_none() -> None:
    j = derive_story_journey("s-foo", {"status": "done", "closed_at": "2026-05-30T18:00:00Z"})
    r = _phase(j, "reflect")
    assert r.present is True
    assert r.at == "2026-05-30T18:00:00Z"
    # A completed journey has no active phase.
    assert j.active_phase is None


def test_reflect_present_from_linked_lesson_even_if_not_done() -> None:
    j = derive_story_journey(
        "s-foo",
        {"status": "in-progress"},
        lessons=[{"name": "rem-foo", "spec": {"source_refs": ["Story/s-foo"], "created_at": "2026-05-25T12:00:00Z"}}],
    )
    r = _phase(j, "reflect")
    assert r.present is True
    assert r.source_ref == "LessonLearned/rem-foo"


def test_skipped_phases_on_todo_to_done_jump() -> None:
    # Story jumped straight to done: no AC/spec, no plan. discover + build (done
    # implies built) + reflect present; specify + plan absent BUT skipped
    # (because a later phase — reflect — is present).
    j = derive_story_journey("s-foo", {"status": "done", "closed_at": "2026-05-30T18:00:00Z"})
    assert _phase(j, "discover").present is True
    assert _phase(j, "reflect").present is True
    assert _phase(j, "specify").present is False
    assert _phase(j, "specify").skipped is True
    assert _phase(j, "plan").present is False
    assert _phase(j, "plan").skipped is True


def test_ref_is_story_kind_prefixed() -> None:
    j = derive_story_journey("s-foo", {"status": "todo"})
    assert j.ref == "Story/s-foo"


def test_plan_skip_reason_surfaced_when_consciously_skipped() -> None:
    # `story start --no-plan --skip-reason "..."` stamps plan_skip_reason.
    # plan stays absent but the journey shows WHY (honest, not a silent hole).
    j = derive_story_journey(
        "s-foo",
        {"status": "in-progress", "plan_skip_reason": "hotfix de 1 linha, sem design"},
    )
    plan = _phase(j, "plan")
    assert plan.present is False
    assert "hotfix de 1 linha" in plan.evidence


def test_linked_plan_wins_over_skip_reason() -> None:
    # If a Plan is actually linked, it lights up regardless of a stale reason.
    j = derive_story_journey(
        "s-foo",
        {"status": "in-progress", "plan_skip_reason": "ignored"},
        plans=[{"name": "plan-s-foo", "spec": {"story_ref": "s-foo"}}],
    )
    plan = _phase(j, "plan")
    assert plan.present is True
    assert plan.source_ref == "Plan/plan-s-foo"


def test_produces_research_lights_specify() -> None:
    j = derive_story_journey(
        "s-foo",
        {"status": "todo", "produces": [{"kind": "Research", "name": "rsh-x"}]},
    )
    sp = _phase(j, "specify")
    assert sp.present is True
    assert sp.source_ref == "Research/rsh-x"


def test_produces_html_role_plan_lights_plan() -> None:
    j = derive_story_journey(
        "s-foo",
        {"status": "in-progress", "produces": [{"kind": "HtmlArtifact", "name": "ha-y", "role": "plan"}]},
    )
    pl = _phase(j, "plan")
    assert pl.present is True
    assert pl.source_ref == "HtmlArtifact/ha-y"


def test_produces_html_default_role_lights_specify_not_plan() -> None:
    j = derive_story_journey(
        "s-foo",
        {"status": "todo", "produces": [{"kind": "HtmlArtifact", "name": "ha-z"}]},
    )
    assert _phase(j, "specify").present is True
    assert _phase(j, "plan").present is False


def test_produces_explicit_plan_without_plans_param() -> None:
    j = derive_story_journey(
        "s-foo",
        {"status": "in-progress", "produces": [{"kind": "Plan", "name": "plan-explicit"}]},
    )
    pl = _phase(j, "plan")
    assert pl.present is True
    assert pl.source_ref == "Plan/plan-explicit"


# ── verify phase (TestRun-driven) ───────────────────────────────────────────

def test_verify_absent_without_test_run() -> None:
    j = derive_story_journey("s-foo", {"status": "in-progress"})
    assert _phase(j, "verify").present is False
    assert _phase(j, "verify").source_ref is None


def test_verify_present_via_produces_with_outcome() -> None:
    spec = {
        "status": "in-progress",
        "produces": [{"kind": "TestRun", "name": "tr-1", "at": "2026-06-07T12:00:00Z"}],
    }
    runs = [{"name": "tr-1", "spec": {"outcome": "pass", "guide_ref": "tg-x"}}]
    j = derive_story_journey("s-foo", spec, test_runs=runs)
    v = _phase(j, "verify")
    assert v.present is True
    assert v.source_ref == "TestRun/tr-1"
    assert "→ pass" in v.evidence


def test_verify_present_via_verifies_backref_even_without_produces() -> None:
    # The run isn't in produces[], but its own `verifies` points at this Story.
    runs = [{"name": "tr-2", "spec": {"outcome": "fail", "verifies": ["Story/s-foo"]}}]
    j = derive_story_journey("s-foo", {"status": "review"}, test_runs=runs)
    v = _phase(j, "verify")
    assert v.present is True
    assert v.source_ref == "TestRun/tr-2"
    assert "→ fail" in v.evidence


def test_verify_marks_build_done_but_verify_skipped_when_reflect_present() -> None:
    # Story done (reflect present) with NO test run → verify is an honest skip.
    spec = {"status": "done", "closed_at": "2026-06-07T15:00:00Z"}
    j = derive_story_journey("s-foo", spec)
    assert _phase(j, "reflect").present is True
    assert _phase(j, "verify").present is False
    assert _phase(j, "verify").skipped is True  # sits before a present phase
