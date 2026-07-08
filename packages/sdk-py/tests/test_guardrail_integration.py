"""Integration test: GuardrailKind loaded via full Kernel pipeline."""
from __future__ import annotations

import pytest
from pathlib import Path

from dna.kernel import Kernel


BASE_DIR = Path(__file__).parent.parent.parent.parent / "scopes" / "open-swe" / ".dna"


@pytest.fixture
def mi():
    return Kernel.quick("open-swe", base_dir=str(BASE_DIR))


class TestGuardrailIntegration:
    def test_all_guardrails_loaded(self, mi):
        guardrails = mi.all("Guardrail")
        names = sorted(g.name for g in guardrails)
        assert names == ["code-quality", "pii-protection", "review-ethics", "safety"]

    def test_safety_guardrail(self, mi):
        g = mi.one("Guardrail", "safety")
        assert g.name == "safety"
        assert g.spec.severity == "error"
        assert g.spec.scope == "both"
        assert len(g.spec.rules) == 5
        assert any("system prompts" in r for r in g.spec.rules)

    def test_code_quality_guardrail(self, mi):
        g = mi.one("Guardrail", "code-quality")
        assert g.name == "code-quality"
        assert g.spec.severity == "warn"
        assert g.spec.scope == "output"
        assert len(g.spec.rules) == 8
        assert any("tests" in r.lower() for r in g.spec.rules)

    def test_pii_protection_guardrail(self, mi):
        g = mi.one("Guardrail", "pii-protection")
        assert g.name == "pii-protection"
        assert g.spec.severity == "error"
        assert g.spec.scope == "output"
        assert len(g.spec.rules) == 6
        assert any("PII" in r for r in g.spec.rules)

    def test_review_ethics_guardrail(self, mi):
        g = mi.one("Guardrail", "review-ethics")
        assert g.name == "review-ethics"
        assert g.spec.severity == "warn"
        assert g.spec.scope == "output"
        assert len(g.spec.rules) == 7

    def test_swe_agent_references_guardrails(self, mi):
        agent = mi.one("Agent", "swe-agent")
        assert "safety" in agent.spec.guardrails
        assert "code-quality" in agent.spec.guardrails
        assert "pii-protection" in agent.spec.guardrails

    def test_reviewer_agent_references_guardrails(self, mi):
        agent = mi.one("Agent", "reviewer-agent")
        assert "safety" in agent.spec.guardrails
        assert "review-ethics" in agent.spec.guardrails

    def test_different_severities(self, mi):
        """Verify the fixture demonstrates both severity levels."""
        guardrails = mi.all("Guardrail")
        severities = {g.name: g.spec.severity for g in guardrails}
        assert severities["safety"] == "error"
        assert severities["code-quality"] == "warn"
        assert severities["pii-protection"] == "error"
        assert severities["review-ethics"] == "warn"

    def test_different_scopes(self, mi):
        """Verify the fixture demonstrates different scopes."""
        guardrails = mi.all("Guardrail")
        scopes = {g.name: g.spec.scope for g in guardrails}
        assert scopes["safety"] == "both"
        assert scopes["code-quality"] == "output"
        assert scopes["pii-protection"] == "output"
        assert scopes["review-ethics"] == "output"
