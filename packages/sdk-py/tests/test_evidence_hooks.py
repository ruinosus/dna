"""Tests for evidence auto-capture hook integration."""
from dna.extensions.evidence import should_capture


def test_should_capture_matches_policy():
    policy_spec = {"events": ["eval_run_completed", "finding_created"], "auto_capture": True}
    assert should_capture(policy_spec, "eval_run_completed") is True
    assert should_capture(policy_spec, "document_created") is False
    assert should_capture({"events": [], "auto_capture": True}, "eval_run_completed") is False


def test_should_capture_disabled():
    policy_spec = {"events": ["eval_run_completed"], "auto_capture": False}
    assert should_capture(policy_spec, "eval_run_completed") is False


def test_should_capture_default_auto_capture():
    """auto_capture defaults to True when omitted."""
    policy_spec = {"events": ["eval_run_completed"]}
    assert should_capture(policy_spec, "eval_run_completed") is True
