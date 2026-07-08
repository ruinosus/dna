"""Tests for SafetyPolicy input enforcement via apply_hooks()."""
from __future__ import annotations

import pytest
from dna import Kernel


class TestSafetyInputEnforcement:
    def test_masks_cpf_in_prompt(self, tmp_path):
        """SafetyPolicy with scope=input masks CPF values in prompt context."""
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
            "  instruction: 'CPF: {{user_cpf}}'\n"
        )

        safety = dna / "safety" / "pii"
        safety.mkdir(parents=True)
        (safety / "SAFETYPOLICY.md").write_text(
            "---\n"
            "name: pii\n"
            "scope: input\n"
            "action: mask\n"
            "severity: error\n"
            "---\n\n"
            "- type: pii\n"
            "  entities:\n"
            "    - cpf\n"
            "    - email\n"
        )

        mi = Kernel.quick("test", base_dir=str(tmp_path / ".dna"))
        mi.apply_hooks()
        prompt = mi.prompt.build(context={"user_cpf": "529.982.247-25"})
        assert "529.982.247-25" not in prompt
        assert "***.***.***-**" in prompt

    def test_masks_email_in_prompt(self, tmp_path):
        """SafetyPolicy with scope=both masks email values in prompt context."""
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
            "  instruction: 'Contact: {{email}}'\n"
        )

        safety = dna / "safety" / "pii"
        safety.mkdir(parents=True)
        (safety / "SAFETYPOLICY.md").write_text(
            "---\n"
            "name: pii\n"
            "scope: both\n"
            "action: mask\n"
            "severity: error\n"
            "---\n\n"
            "- type: pii\n"
            "  entities:\n"
            "    - email\n"
        )

        mi = Kernel.quick("test", base_dir=str(tmp_path / ".dna"))
        mi.apply_hooks()
        prompt = mi.prompt.build(context={"email": "joao@example.com"})
        assert "joao@example.com" not in prompt
        assert "***@example.com" in prompt

    def test_output_only_policy_does_not_affect_input(self, tmp_path):
        """SafetyPolicy with scope=output should not create pre_build_prompt hooks."""
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
            "  instruction: 'CPF: {{user_cpf}}'\n"
        )

        safety = dna / "safety" / "output-only"
        safety.mkdir(parents=True)
        (safety / "SAFETYPOLICY.md").write_text(
            "---\n"
            "name: output-only\n"
            "scope: output\n"
            "action: mask\n"
            "severity: error\n"
            "---\n\n"
            "- type: pii\n"
            "  entities:\n"
            "    - cpf\n"
        )

        mi = Kernel.quick("test", base_dir=str(tmp_path / ".dna"))
        mi.apply_hooks()
        prompt = mi.prompt.build(context={"user_cpf": "529.982.247-25"})
        # Output-only policy should NOT mask input
        assert "529.982.247-25" in prompt

    def test_multiple_policies_applied(self, tmp_path):
        """Multiple SafetyPolicy documents are all applied."""
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
            "  instruction: 'CPF: {{cpf}} Email: {{email}}'\n"
        )

        # Policy 1: CPF
        p1 = dna / "safety" / "pii-cpf"
        p1.mkdir(parents=True)
        (p1 / "SAFETYPOLICY.md").write_text(
            "---\n"
            "name: pii-cpf\n"
            "scope: input\n"
            "action: mask\n"
            "severity: error\n"
            "---\n\n"
            "- type: pii\n"
            "  entities:\n"
            "    - cpf\n"
        )

        # Policy 2: Email
        p2 = dna / "safety" / "pii-email"
        p2.mkdir(parents=True)
        (p2 / "SAFETYPOLICY.md").write_text(
            "---\n"
            "name: pii-email\n"
            "scope: input\n"
            "action: mask\n"
            "severity: error\n"
            "---\n\n"
            "- type: pii\n"
            "  entities:\n"
            "    - email\n"
        )

        mi = Kernel.quick("test", base_dir=str(tmp_path / ".dna"))
        mi.apply_hooks()
        prompt = mi.prompt.build(context={
            "cpf": "529.982.247-25",
            "email": "test@example.com",
        })
        assert "529.982.247-25" not in prompt
        assert "test@example.com" not in prompt
