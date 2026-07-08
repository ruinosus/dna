"""TDD for the FOCUS feed completeness guards (i-113 produces, i-114 narração).

Both guards are WARN-only (they mirror ``story_done_guard``, NOT the test-gate):
they return a list of warning strings; an empty list means "all good". They are
pure (no I/O) so they're trivially testable in isolation.

- ``narration_guard`` warns when no comment/decision event was posted since the
  last status_change — the FOCUS feed goes mute ('start → silence → done').
- ``produces_guard`` warns when a work item closes with no linked output at all
  (empty produces[] + empty back-refs) — the FOCUS outputs panel stays empty.
"""
from __future__ import annotations

from dna_cli.sdlc_cmd import (
    _has_narration_since_last_status_change,
    _has_linked_outputs,
    narration_guard,
    produces_guard,
)


# ── _has_narration_since_last_status_change ──────────────────────────────────

def test_narration_empty_timeline_is_absent() -> None:
    assert _has_narration_since_last_status_change([]) is False
    assert _has_narration_since_last_status_change(None) is False


def test_narration_status_change_then_comment_is_present() -> None:
    timeline = [
        {"type": "status_change", "from": "todo", "to": "in-progress"},
        {"type": "comment", "summary": "começando X"},
    ]
    assert _has_narration_since_last_status_change(timeline) is True


def test_narration_status_change_then_decision_is_present() -> None:
    timeline = [
        {"type": "status_change", "from": "todo", "to": "in-progress"},
        {"type": "decision", "summary": "optei por Y porque Z"},
    ]
    assert _has_narration_since_last_status_change(timeline) is True


def test_narration_status_change_with_nothing_after_is_absent() -> None:
    timeline = [
        {"type": "comment", "summary": "groom note"},
        {"type": "status_change", "from": "todo", "to": "in-progress"},
    ]
    assert _has_narration_since_last_status_change(timeline) is False


def test_narration_comment_before_last_status_change_is_absent() -> None:
    # A comment exists, but it predates the LAST status_change → mute since.
    timeline = [
        {"type": "status_change", "from": "todo", "to": "in-progress"},
        {"type": "comment", "summary": "did the work"},
        {"type": "status_change", "from": "in-progress", "to": "review"},
    ]
    assert _has_narration_since_last_status_change(timeline) is False


def test_narration_no_status_change_at_all_is_absent() -> None:
    timeline = [{"type": "comment", "summary": "just a note"}]
    assert _has_narration_since_last_status_change(timeline) is False


# ── _has_linked_outputs ──────────────────────────────────────────────────────

def test_outputs_nonempty_produces_is_true() -> None:
    assert _has_linked_outputs({"produces": [{"kind": "Plan", "name": "plan-x"}]}) is True


def test_outputs_only_html_artifacts_is_true() -> None:
    assert _has_linked_outputs({"html_artifacts": ["ha-foo"]}) is True


def test_outputs_only_spec_refs_is_true() -> None:
    assert _has_linked_outputs({"spec_refs": ["spec-foo"]}) is True


def test_outputs_empty_everything_is_false() -> None:
    assert _has_linked_outputs({}) is False
    assert _has_linked_outputs({"produces": [], "spec_refs": [], "html_artifacts": []}) is False


def test_outputs_non_dict_is_false() -> None:
    assert _has_linked_outputs(None) is False


# ── narration_guard ──────────────────────────────────────────────────────────

def test_narration_guard_warns_when_mute() -> None:
    spec = {"timeline": [{"type": "status_change", "from": "todo", "to": "in-progress"}]}
    warns = narration_guard(spec)
    assert len(warns) == 1
    assert "narração" in warns[0].lower() or "narracao" in warns[0].lower()


def test_narration_guard_clean_when_narrated() -> None:
    spec = {"timeline": [
        {"type": "status_change", "from": "todo", "to": "in-progress"},
        {"type": "comment", "summary": "narrei"},
    ]}
    assert narration_guard(spec) == []


# ── produces_guard ───────────────────────────────────────────────────────────

def test_produces_guard_warns_when_empty() -> None:
    warns = produces_guard({})
    assert len(warns) == 1
    assert "output" in warns[0].lower()


def test_produces_guard_clean_when_linked() -> None:
    assert produces_guard({"produces": [{"kind": "Spec", "name": "spec-x"}]}) == []
    assert produces_guard({"html_artifacts": ["ha-x"]}) == []
