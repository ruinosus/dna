"""Tests for v1.5 board-grade fields on Story/Feature/Epic/Issue.

Fields added: priority, labels, reporter, watchers, created_at,
updated_at + (Story/Feature) sprint_ref, time_tracking,
definition_of_done, business_value, mockups, release_target.
Epic drops sprint_ref/time_tracking/mockups/release_target.
Issue keeps only the universal common fields (severity is its
native classification).
"""
from __future__ import annotations

import jsonschema
import pytest

from dna.extensions.sdlc import (
    StoryKind, FeatureKind, EpicKind, IssueKind,
    PRIORITIES, STORY_STATUSES, FEATURE_STATUSES, EPIC_STATUSES,
    ISSUE_STATUSES, ISSUE_TYPES, ISSUE_SEVERITIES,
)


# ─── Enum constant ─────────────────────────────────────────────────────


def test_priorities_jira_aligned():
    """Five Jira-aligned priorities."""
    assert PRIORITIES == ("highest", "high", "medium", "low", "lowest")


# ─── Story rich fields ─────────────────────────────────────────────────


@pytest.fixture
def story_schema() -> dict:
    return StoryKind().schema()


def test_story_has_all_v15_fields(story_schema):
    """All 11 board-grade fields land on Story."""
    expected = {
        "priority", "labels", "reporter", "watchers",
        "created_at", "updated_at", "sprint_ref",
        "time_tracking", "definition_of_done",
        "business_value", "mockups", "release_target",
    }
    assert expected.issubset(set(story_schema["properties"].keys()))


def test_story_priority_enum(story_schema):
    assert story_schema["properties"]["priority"]["enum"] == list(PRIORITIES)


def test_story_business_value_bounds(story_schema):
    bv = story_schema["properties"]["business_value"]
    assert bv["minimum"] == 0 and bv["maximum"] == 1000


def test_story_time_tracking_shape(story_schema):
    tt = story_schema["properties"]["time_tracking"]
    assert tt["type"] == "object"
    assert tt["additionalProperties"] is False
    assert set(tt["properties"].keys()) == {
        "logged_h", "remaining_h", "original_estimate_h",
    }
    for p in tt["properties"].values():
        assert p["type"] == "number"
        assert p["minimum"] == 0


def test_story_back_compat_minimal_yaml(story_schema):
    """Pre-v1.5 minimal Story (description+status only) still validates."""
    raw = {"description": "x", "status": "todo"}
    jsonschema.validate(raw, story_schema)


def test_story_full_v15_payload(story_schema):
    raw = {
        "description": "x",
        "status": "todo",
        "priority": "high",
        "labels": ["backend", "perf"],
        "reporter": "alice",
        "watchers": ["bob", "carol"],
        "created_at": "2026-05-09T10:00:00+00:00",
        "updated_at": "2026-05-09T11:00:00+00:00",
        "sprint_ref": "2026-Q2-S2",
        "time_tracking": {
            "logged_h": 4,
            "remaining_h": 12,
            "original_estimate_h": 16,
        },
        "definition_of_done": ["tests pass", "PR merged"],
        "business_value": 750,
        "mockups": ["https://figma.com/foo"],
        "release_target": "platform/dna-sdk-v3@0.2.0",
    }
    jsonschema.validate(raw, story_schema)


def test_story_invalid_priority_rejected(story_schema):
    raw = {"description": "x", "status": "todo", "priority": "URGENT"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(raw, story_schema)


def test_story_business_value_over_1000_rejected(story_schema):
    raw = {"description": "x", "status": "todo", "business_value": 1001}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(raw, story_schema)


def test_story_time_tracking_negative_rejected(story_schema):
    raw = {
        "description": "x", "status": "todo",
        "time_tracking": {"logged_h": -1},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(raw, story_schema)


def test_story_summary_includes_v15_fields():
    raw_doc = type("D", (), {"spec": {
        "status": "in-progress", "feature": "f-x", "owner": "alice",
        "priority": "high", "labels": ["a", "b"], "sprint_ref": "S2",
        "business_value": 500,
    }})()
    summary = StoryKind().summary(raw_doc)
    assert summary["priority"] == "high"
    assert summary["labels"] == ["a", "b"]
    assert summary["sprint_ref"] == "S2"
    assert summary["business_value"] == 500


def test_story_summary_defaults_when_missing():
    raw_doc = type("D", (), {"spec": {"status": "todo"}})()
    summary = StoryKind().summary(raw_doc)
    assert summary["priority"] == "medium"
    assert summary["labels"] == []
    assert summary["sprint_ref"] == ""
    assert summary["business_value"] is None


# ─── Feature rich fields ───────────────────────────────────────────────


def test_feature_has_v15_fields():
    schema = FeatureKind().schema()
    expected = {
        "priority", "labels", "reporter", "watchers",
        "created_at", "updated_at", "sprint_ref",
        "time_tracking", "definition_of_done",
        "business_value", "mockups", "release_target",
    }
    assert expected.issubset(set(schema["properties"].keys()))


def test_feature_back_compat():
    schema = FeatureKind().schema()
    raw = {"description": "x", "status": "discovery"}
    jsonschema.validate(raw, schema)


# ─── Epic rich fields (subset — no sprint/time_tracking/mockups) ───────


def test_epic_has_subset_of_fields():
    schema = EpicKind().schema()
    has = set(schema["properties"].keys())
    # Common fields present.
    must_have = {
        "priority", "labels", "reporter", "watchers",
        "created_at", "updated_at",
        "definition_of_done", "business_value",
    }
    assert must_have.issubset(has)
    # Epic-excluded fields ABSENT.
    must_lack = {"sprint_ref", "time_tracking", "mockups", "release_target"}
    assert must_lack.isdisjoint(has)


def test_epic_back_compat():
    schema = EpicKind().schema()
    raw = {"status": "planning"}
    jsonschema.validate(raw, schema)


# ─── Issue rich fields (universal common only) ─────────────────────────


def test_issue_has_universal_common_fields():
    schema = IssueKind().schema()
    has = set(schema["properties"].keys())
    must_have = {
        "priority", "labels", "reporter", "watchers",
        "created_at", "updated_at",
    }
    assert must_have.issubset(has)
    # Issue must NOT have Story/Feature-specific fields.
    must_lack = {
        "sprint_ref", "time_tracking", "definition_of_done",
        "business_value", "mockups", "release_target",
    }
    assert must_lack.isdisjoint(has)


def test_issue_back_compat():
    schema = IssueKind().schema()
    raw = {
        "description": "bug", "type": "bug",
        "severity": "high", "status": "open",
    }
    jsonschema.validate(raw, schema)


# ─── Sanity: existing enums untouched ──────────────────────────────────


# ─── v1.6 Activity Timeline ────────────────────────────────────────────


def test_timeline_field_present_on_story_feature_epic_issue():
    """Timeline opt-in field on all 4 board Kinds."""
    for KP in (StoryKind, FeatureKind, EpicKind, IssueKind):
        schema = KP().schema()
        assert "timeline" in schema["properties"], f"{KP.__name__} missing timeline"
        tl = schema["properties"]["timeline"]
        assert tl["type"] == "array"
        assert tl["items"]["type"] == "object"


def test_timeline_entry_required_fields():
    """Each timeline entry requires at + actor + type."""
    schema = StoryKind().schema()
    entry_schema = schema["properties"]["timeline"]["items"]
    assert set(entry_schema["required"]) == {"at", "actor", "type"}


def test_timeline_entry_validates_status_change():
    schema = StoryKind().schema()
    raw = {
        "description": "x", "status": "in-progress",
        "timeline": [{
            "at": "2026-05-09T20:00:00+00:00",
            "actor": "claude-code",
            "type": "status_change",
            "source": "cli",
            "from": "todo",
            "to": "in-progress",
        }],
    }
    jsonschema.validate(raw, schema)


def test_timeline_entry_validates_decision():
    schema = StoryKind().schema()
    raw = {
        "description": "x", "status": "todo",
        "timeline": [{
            "at": "2026-05-09T18:35:00+00:00",
            "actor": "claude-code",
            "type": "decision",
            "source": "agent-session-extracted",
            "summary": "descartei KindForm-with-overrides em favor de bespoke",
            "session_ref": "vs-2026-05-09-...",
        }],
    }
    jsonschema.validate(raw, schema)


def test_timeline_unknown_type_rejected_by_enum():
    """Phase 1 enums are documentation-style but jsonschema enforces them."""
    schema = StoryKind().schema()
    raw = {
        "description": "x", "status": "todo",
        "timeline": [{
            "at": "2026-05-09T20:00:00+00:00",
            "actor": "x",
            "type": "deploy",  # not in enum
        }],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(raw, schema)


def test_timeline_additionalproperties_per_entry():
    """Custom keys per entry must round-trip (e.g. confidence on a decision)."""
    schema = StoryKind().schema()
    raw = {
        "description": "x", "status": "todo",
        "timeline": [{
            "at": "2026-05-09T20:00:00+00:00",
            "actor": "x",
            "type": "decision",
            "summary": "y",
            "confidence": 0.85,
            "tools_used": ["StoryForm.tsx", "Edit"],
        }],
    }
    jsonschema.validate(raw, schema)


def test_timeline_back_compat_missing_field_ok():
    """Pre-v1.6 docs without timeline still parse."""
    schema = StoryKind().schema()
    raw = {"description": "x", "status": "todo"}
    jsonschema.validate(raw, schema)


def test_no_status_enums_changed():
    # `needs-triage` (pré-groom) + `deferred` (PM olhou, talvez depois) added
    # by f-rec-triage-as-status (commit 27fc4cc1). Guard updated to match.
    assert STORY_STATUSES == ("needs-triage", "todo", "in-progress", "review", "done", "blocked", "deferred", "cancelled")
    assert FEATURE_STATUSES == ("discovery", "in-development", "done", "cancelled", "blocked")
    assert EPIC_STATUSES == ("planning", "in-progress", "done", "cancelled", "deprecated")
    assert ISSUE_STATUSES == ("open", "triaged", "in-progress", "resolved", "wont-fix", "duplicate")
    assert ISSUE_TYPES == ("bug", "enhancement", "question", "task")
    assert ISSUE_SEVERITIES == ("low", "medium", "high", "critical")
