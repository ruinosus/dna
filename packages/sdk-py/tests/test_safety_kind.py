"""Tests for SafetyPolicy Kind — registration, parsing, metadata."""
from __future__ import annotations

import pytest
from dna import Kernel
from dna.extensions.safety import SafetyPolicyKind
from dna.kernel.models import TypedSafetyPolicy


class TestSafetyPolicyRegistration:
    def test_safety_policy_kind_registered(self):
        k = Kernel.auto()
        found = any(kp.kind == "SafetyPolicy" for kp in k._kinds.values())
        assert found

    def test_safety_policy_kind_metadata(self):
        k = Kernel.auto()
        for kp in k._kinds.values():
            if kp.kind == "SafetyPolicy":
                assert kp.alias == "helix-safety-policy"
                assert kp.is_root is False
                assert kp.is_prompt_target is False
                assert kp.flatten_in_context is False
                break

    def test_registers_kind_only(self):
        """SafetyPolicyExtension registers only a kind; reader/writer are auto-generated."""
        k = Kernel()
        from dna.extensions.safety import SafetyPolicyExtension
        k.load(SafetyPolicyExtension())
        assert ("github.com/ruinosus/dna/v1", "SafetyPolicy") in k._kinds


class TestSafetyPolicyParsing:
    def test_parse_returns_typed(self):
        kp = SafetyPolicyKind()
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "SafetyPolicy",
            "metadata": {"name": "pii-brasil"},
            "spec": {
                "scope": "both",
                "action": "mask",
                "severity": "error",
                "rules": [{"type": "pii", "entities": ["cpf", "email"]}],
            },
        }
        typed = kp.parse(raw)
        assert isinstance(typed, TypedSafetyPolicy)
        assert typed.metadata.name == "pii-brasil"
        assert typed.spec.scope == "both"
        assert typed.spec.action == "mask"
        assert len(typed.spec.rules) == 1
        assert typed.spec.rules[0]["type"] == "pii"

    def test_parse_defaults(self):
        kp = SafetyPolicyKind()
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "SafetyPolicy",
            "metadata": {"name": "empty"},
            "spec": {},
        }
        typed = kp.parse(raw)
        assert typed.spec.scope == "both"
        assert typed.spec.action == "mask"
        assert typed.spec.severity == "error"
        assert typed.spec.rules == []

    def test_parse_body_as_yaml_string(self):
        """When rules come as a text body (from SAFETYPOLICY.md), they should be parsed as YAML."""
        kp = SafetyPolicyKind()
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "SafetyPolicy",
            "metadata": {"name": "from-md"},
            "spec": {
                "scope": "input",
                "action": "mask",
                "severity": "error",
                "rules": "- type: pii\n  entities:\n    - cpf\n    - email\n",
            },
        }
        typed = kp.parse(raw)
        assert isinstance(typed.spec.rules, list)
        assert len(typed.spec.rules) == 1
        assert typed.spec.rules[0]["type"] == "pii"
        assert "cpf" in typed.spec.rules[0]["entities"]


class TestSafetyPolicyKindMethods:
    def test_dep_filters_returns_recognizers(self):
        kp = SafetyPolicyKind()
        deps = kp.dep_filters()
        assert deps is not None
        assert deps["recognizers"] == "presidio-recognizer"

    def test_describe_returns_none(self):
        kp = SafetyPolicyKind()
        assert kp.describe(None) is None

    def test_prompt_template_returns_none(self):
        kp = SafetyPolicyKind()
        assert kp.prompt_template() is None

    def test_summary_returns_expected(self):
        from dataclasses import dataclass

        @dataclass
        class FakeDoc:
            kind: str = "SafetyPolicy"
            name: str = "pii"
            spec: dict = None  # type: ignore
            def __post_init__(self):
                if self.spec is None:
                    self.spec = {
                        "scope": "input",
                        "action": "block",
                        "severity": "error",
                        "rules": [{"type": "pii"}, {"type": "prompt_injection"}],
                    }

        kp = SafetyPolicyKind()
        result = kp.summary(FakeDoc())
        assert result is not None
        assert result["scope"] == "input"
        assert result["action"] == "block"
        assert result["severity"] == "error"
        assert result["rules"] == 2


class TestSafetyPolicyBundleRoundtrip:
    def test_reads_safetypolicy_md(self, tmp_path):
        """SafetyPolicy loads from SAFETYPOLICY.md bundle on disk."""
        dna = tmp_path / ".dna" / "test"
        dna.mkdir(parents=True)
        (dna / "manifest.yaml").write_text(
            "apiVersion: github.com/ruinosus/dna/v1\n"
            "kind: Genome\n"
            "metadata:\n"
            "  name: test\n"
            "spec:\n"
            "  default_agent: a1\n"
        )

        agents = dna / "agents"
        agents.mkdir()
        (agents / "a1.yaml").write_text(
            "apiVersion: github.com/ruinosus/dna/v1\n"
            "kind: Agent\n"
            "metadata:\n"
            "  name: a1\n"
            "spec:\n"
            "  instruction: 'test'\n"
        )

        safety = dna / "safety" / "pii-brasil"
        safety.mkdir(parents=True)
        (safety / "SAFETYPOLICY.md").write_text(
            "---\n"
            "name: pii-brasil\n"
            "description: Mascara PII brasileiro\n"
            "scope: both\n"
            "action: mask\n"
            "severity: error\n"
            "---\n\n"
            "- type: pii\n"
            "  entities:\n"
            "    - cpf\n"
            "    - email\n"
        )

        mi = Kernel.quick("test", base_dir=str(tmp_path / ".dna"))
        policy_docs = mi.all("SafetyPolicy")
        assert len(policy_docs) == 1
        doc = policy_docs[0]
        assert doc.name == "pii-brasil"
        assert doc.spec.get("scope") == "both"
        assert doc.spec.get("action") == "mask"
        rules = doc.spec.get("rules", [])
        assert isinstance(rules, list)
        assert len(rules) == 1
        assert rules[0]["type"] == "pii"
        assert "cpf" in rules[0]["entities"]
