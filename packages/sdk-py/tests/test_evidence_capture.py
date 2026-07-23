"""Tests for evidence auto-capture via post_save hook."""
from dna.kernel.write.evidence import extract_suite
from dna.extensions.evidence.builder import compute_content_hash


def test_compute_content_hash_canonical():
    assert compute_content_hash({"b": 2, "a": 1}) == compute_content_hash({"a": 1, "b": 2})


def test_extract_suite_from_eval_run():
    assert extract_suite("EvalRun", {"suite": "smoke"}, None) == "smoke"


def test_extract_suite_from_finding_source():
    assert extract_suite("Finding", {"source": "screening-reads"}, None) == "screening-reads"


def test_extract_suite_explicit_overrides():
    assert extract_suite("EvalRun", {"suite": "old"}, "explicit") == "explicit"


def test_extract_suite_non_eval_kind():
    assert extract_suite("Agent", {"suite": "irrelevant"}, None) is None
