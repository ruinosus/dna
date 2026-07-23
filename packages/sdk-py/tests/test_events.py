# python/tests/test_events.py
"""Tests for kernel event type derivation."""
from dna.kernel.boot.events import derive_event_type


def test_eval_run_always_completed():
    assert derive_event_type("EvalRun", is_update=False) == "eval_run_completed"
    assert derive_event_type("EvalRun", is_update=True) == "eval_run_completed"


def test_eval_baseline_always_pinned():
    assert derive_event_type("EvalBaseline", is_update=False) == "baseline_pinned"
    assert derive_event_type("EvalBaseline", is_update=True) == "baseline_pinned"


def test_finding_new_is_created():
    assert derive_event_type("Finding", is_update=False) == "finding_created"


def test_finding_update_is_status_changed():
    assert derive_event_type("Finding", is_update=True) == "finding_status_changed"


def test_generic_kind_new():
    assert derive_event_type("Agent", is_update=False) == "document_created"
    assert derive_event_type("Skill", is_update=False) == "document_created"


def test_generic_kind_update():
    assert derive_event_type("Agent", is_update=True) == "document_modified"
    assert derive_event_type("Soul", is_update=True) == "document_modified"


def test_delete_event():
    from dna.kernel.boot.events import DELETE_EVENT_TYPE
    assert DELETE_EVENT_TYPE == "document_deleted"
