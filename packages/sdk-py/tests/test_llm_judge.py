"""Tests for LLMJudgeScanner — skipped if no OPENAI_API_KEY."""

import pytest

@pytest.mark.requires_llm
class TestLLMJudge:
    def test_detects_off_topic(self):
        from dna.safety.scanners.llm_judge import LLMJudgeScanner

        scanner = LLMJudgeScanner(
            [
                {
                    "type": "topic_restriction",
                    "allowed": ["technology", "programming"],
                    "denied": ["medical_advice", "legal_advice"],
                    "tier": "llm_judge",
                }
            ]
        )
        if not scanner.available():
            pytest.skip("LLM judge not available")
        violations = scanner.scan(
            "What medication should I take for my headache? I need a prescription."
        )
        assert len(violations) > 0
        assert violations[0].rule_type == "topic_restriction"

    def test_on_topic_passes(self):
        from dna.safety.scanners.llm_judge import LLMJudgeScanner

        scanner = LLMJudgeScanner(
            [
                {
                    "type": "topic_restriction",
                    "allowed": ["technology", "programming"],
                    "tier": "llm_judge",
                }
            ]
        )
        if not scanner.available():
            pytest.skip("LLM judge not available")
        violations = scanner.scan(
            "How do I implement a binary search in Python?"
        )
        assert len(violations) == 0
