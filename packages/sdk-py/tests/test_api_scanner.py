"""Tests for APIScanner — skipped if no OPENAI_API_KEY."""

import pytest

@pytest.mark.requires_llm
class TestAPIScanner:
    def test_detects_hate_speech(self):
        from dna.safety.scanners.api_scanner import APIScanner

        scanner = APIScanner(
            [
                {
                    "type": "content_safety",
                    "categories": ["hate"],
                    "tier": "api",
                    "threshold": 0.3,
                }
            ]
        )
        if not scanner.available():
            pytest.skip("API scanner not available")
        violations = scanner.scan(
            "I hate all people from that country, they should be eliminated"
        )
        assert len(violations) > 0

    def test_clean_text_passes(self):
        from dna.safety.scanners.api_scanner import APIScanner

        scanner = APIScanner(
            [
                {
                    "type": "content_safety",
                    "categories": ["hate"],
                    "tier": "api",
                }
            ]
        )
        if not scanner.available():
            pytest.skip("API scanner not available")
        violations = scanner.scan("The weather is nice today")
        assert len(violations) == 0
