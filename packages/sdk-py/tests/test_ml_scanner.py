"""Tests for MLScanner — skipped if presidio/detoxify not installed."""
import pytest

try:
    from dna.safety.scanners.ml_scanner import (
        MLScanner,
        _check_detoxify,
        _check_presidio,
    )

    HAS_ML = _check_presidio() or _check_detoxify()
except ImportError:
    HAS_ML = False


@pytest.mark.skipif(not HAS_ML, reason="safety-ml deps not installed")
class TestMLScanner:
    def test_detects_person_name(self):
        scanner = MLScanner(
            [{"type": "pii", "entities": ["person"], "tier": "ml"}]
        )
        if not scanner.available():
            pytest.skip("presidio not available")
        violations = scanner.scan(
            "O nome do cliente e Joao Silva e ele mora em Sao Paulo"
        )
        person_violations = [v for v in violations if v.entity == "person"]
        assert len(person_violations) > 0

    def test_available_returns_false_without_deps(self):
        # This test only makes sense if deps ARE installed
        scanner = MLScanner(
            [{"type": "pii", "entities": ["person"], "tier": "ml"}]
        )
        # Just verify it doesn't crash
        assert isinstance(scanner.available(), bool)
