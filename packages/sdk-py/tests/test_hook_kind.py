"""Tests for the Hook Kind — declarative hooks in manifest."""
import pytest
from dna import Kernel


class TestHookKind:
    def test_hook_kind_registered(self):
        k = Kernel.auto()
        found = any(kp.kind == "Hook" for kp in k._kinds.values())
        assert found

    def test_hook_kind_metadata(self):
        k = Kernel.auto()
        for kp in k._kinds.values():
            if kp.kind == "Hook":
                assert kp.alias == "helix-hook"
                assert kp.is_root is False
                assert kp.is_prompt_target is False
                break

    def test_hook_inject_fields(self, tmp_path):
        # Create manifest structure
        dna = tmp_path / ".dna" / "test"
        dna.mkdir(parents=True)
        (dna / "manifest.yaml").write_text(
            "apiVersion: github.com/ruinosus/dna/v1\n"
            "kind: Genome\n"
            "metadata:\n"
            "  name: test\n"
            "spec:\n"
            "  default_agent: agent-1\n"
        )

        agents = dna / "agents"
        agents.mkdir()
        (agents / "agent-1.yaml").write_text(
            "apiVersion: github.com/ruinosus/dna/v1\n"
            "kind: Agent\n"
            "metadata:\n"
            "  name: agent-1\n"
            "spec:\n"
            "  instruction: 'Hello {{environment}}'\n"
        )

        hooks = dna / "hooks" / "inject-env"
        hooks.mkdir(parents=True)
        (hooks / "HOOK.md").write_text(
            "---\n"
            "name: inject-env\n"
            "target: pre_build_prompt\n"
            "type: middleware\n"
            "action: inject_fields\n"
            "---\n\n"
            "environment: production\n"
            "team: backend\n"
        )

        mi = Kernel.quick("test", base_dir=str(tmp_path / ".dna"))
        hook_docs = mi.all("Hook")
        assert len(hook_docs) == 1
        assert hook_docs[0].name == "inject-env"

        mi.apply_hooks()
        prompt = mi.prompt.build()
        assert "production" in prompt

    def test_hook_doc_spec_fields(self, tmp_path):
        """Verify the Hook spec has the expected parsed fields."""
        dna = tmp_path / ".dna" / "test"
        dna.mkdir(parents=True)
        (dna / "manifest.yaml").write_text(
            "apiVersion: github.com/ruinosus/dna/v1\n"
            "kind: Genome\n"
            "metadata:\n"
            "  name: test\n"
            "spec:\n"
            "  default_agent: agent-1\n"
        )

        agents = dna / "agents"
        agents.mkdir()
        (agents / "agent-1.yaml").write_text(
            "apiVersion: github.com/ruinosus/dna/v1\n"
            "kind: Agent\n"
            "metadata:\n"
            "  name: agent-1\n"
            "spec:\n"
            "  instruction: 'test'\n"
        )

        hooks = dna / "hooks" / "my-hook"
        hooks.mkdir(parents=True)
        (hooks / "HOOK.md").write_text(
            "---\n"
            "name: my-hook\n"
            "target: post_build_prompt\n"
            "type: event\n"
            "action: log\n"
            "---\n\n"
            "Some body text\n"
        )

        mi = Kernel.quick("test", base_dir=str(tmp_path / ".dna"))
        hook_docs = mi.all("Hook")
        assert len(hook_docs) == 1
        doc = hook_docs[0]
        assert doc.spec.get("target") == "post_build_prompt"
        assert doc.spec.get("type") == "event"
        assert doc.spec.get("action") == "log"

    def test_hook_multiple_inject(self, tmp_path):
        """Multiple hook documents are all loaded."""
        dna = tmp_path / ".dna" / "test"
        dna.mkdir(parents=True)
        (dna / "manifest.yaml").write_text(
            "apiVersion: github.com/ruinosus/dna/v1\n"
            "kind: Genome\n"
            "metadata:\n"
            "  name: test\n"
            "spec:\n"
            "  default_agent: agent-1\n"
        )

        agents = dna / "agents"
        agents.mkdir()
        (agents / "agent-1.yaml").write_text(
            "apiVersion: github.com/ruinosus/dna/v1\n"
            "kind: Agent\n"
            "metadata:\n"
            "  name: agent-1\n"
            "spec:\n"
            "  instruction: '{{env}} {{region}}'\n"
        )

        for hook_name, body in [("hook-a", "env: staging\n"), ("hook-b", "region: us-east\n")]:
            d = dna / "hooks" / hook_name
            d.mkdir(parents=True)
            (d / "HOOK.md").write_text(
                f"---\nname: {hook_name}\ntarget: pre_build_prompt\ntype: middleware\naction: inject_fields\n---\n\n{body}"
            )

        mi = Kernel.quick("test", base_dir=str(tmp_path / ".dna"))
        hook_docs = mi.all("Hook")
        assert len(hook_docs) == 2

        mi.apply_hooks()
        prompt = mi.prompt.build()
        assert "staging" in prompt
        assert "us-east" in prompt
