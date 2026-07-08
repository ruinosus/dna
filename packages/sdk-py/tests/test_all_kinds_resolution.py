"""Integration tests — resolve ALL kind types through the dependency pipeline.

Uses the real market-demo fixture (which has Skills, Souls, AGENTS.md) and
synthetic Guardrails to prove every kind resolves correctly through:
  manifest → resolver → cache → kernel → MI → build_prompt

This is the definitive test that the SDK handles all kinds end-to-end.
"""
from __future__ import annotations

import pytest
from pathlib import Path

import yaml

from dna.kernel import Kernel
from dna.adapters.filesystem import FilesystemSource, FilesystemCache
from dna.adapters.resolvers.local import LocalResolver


MARKET_DEMO = Path(__file__).parent.parent.parent.parent / "scopes" / "market-integration" / ".dna" / "market-demo"


def _build_project(tmp_path: Path, deps: list[dict], agent_spec: dict) -> "ManifestInstance":
    """Create a project with given dependencies and return MI."""
    project = tmp_path / ".dna" / "proj"
    project.mkdir(parents=True)

    manifest = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": "proj"},
        "spec": {"default_agent": "main", "dependencies": deps},
    }
    (project / "manifest.yaml").write_text(yaml.dump(manifest, default_flow_style=False))

    agent = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "main"},
        "spec": agent_spec,
    }
    (project / "agents").mkdir()
    (project / "agents" / "main.yaml").write_text(yaml.dump(agent, default_flow_style=False))

    base = tmp_path / ".dna"
    k = Kernel.auto()
    k.source(FilesystemSource(str(base)))
    k.cache(FilesystemCache(str(base)))
    k.resolver("local", LocalResolver(base_dir=str(base)))
    return k.instance("proj")


# ---------------------------------------------------------------------------
# Kind: Skill — from market-demo
# ---------------------------------------------------------------------------


class TestSkillResolution:
    def test_resolves_specific_skills(self, tmp_path):
        mi = _build_project(tmp_path, [
            {"source": f"local:{MARKET_DEMO}", "items": [
                {"kind": "Skill", "names": ["brainstorming", "claude-api"]},
            ]},
        ], {"instruction": "Agent.", "skills": ["brainstorming", "claude-api"]})

        skills = mi.all("Skill")
        names = [s.name for s in skills]
        assert "brainstorming" in names
        assert "claude-api" in names

    def test_skill_instruction_not_empty(self, tmp_path):
        mi = _build_project(tmp_path, [
            {"source": f"local:{MARKET_DEMO}", "items": [
                {"kind": "Skill", "names": ["brainstorming"]},
            ]},
        ], {"instruction": "Agent.", "skills": ["brainstorming"]})

        skill = mi.one("Skill", "brainstorming")
        assert len(skill.spec.get("instruction", "")) > 100

    def test_skill_with_scripts_has_scripts(self, tmp_path):
        mi = _build_project(tmp_path, [
            {"source": f"local:{MARKET_DEMO}", "items": [
                {"kind": "Skill", "names": ["brainstorming"]},
            ]},
        ], {"instruction": "Agent.", "skills": ["brainstorming"]})

        skill = mi.one("Skill", "brainstorming")
        scripts = skill.spec.get("scripts", {})
        assert len(scripts) > 0, f"Expected scripts. Spec keys: {list(skill.spec.keys())}"


# ---------------------------------------------------------------------------
# Kind: Soul — from market-demo (brad: SOUL.md + soul.json + companions)
# ---------------------------------------------------------------------------


class TestSoulResolution:
    def test_resolves_soul(self, tmp_path):
        mi = _build_project(tmp_path, [
            {"source": f"local:{MARKET_DEMO}", "items": [
                {"kind": "Soul", "names": ["brad"]},
            ]},
        ], {"instruction": "Agent.", "soul": "brad"})

        souls = mi.all("Soul")
        names = [s.name for s in souls]
        assert "brad" in names

    def test_soul_has_content(self, tmp_path):
        mi = _build_project(tmp_path, [
            {"source": f"local:{MARKET_DEMO}", "items": [
                {"kind": "Soul", "names": ["brad"]},
            ]},
        ], {"instruction": "Agent.", "soul": "brad"})

        soul = mi.one("Soul", "brad")
        soul_content = soul.spec.get("soul_content", "")
        assert len(soul_content) > 50, f"Soul content too short: {len(soul_content)}"

    def test_soul_has_companion_files(self, tmp_path):
        """Brad soul has STYLE.md and AGENTS.md companion files.

        After the soulspec.org canonical refactor (commit 9f37617),
        IDENTITY.md and HEARTBEAT.md were dropped — they are not part
        of the canonical spec. Only SOUL.md + STYLE.md + soul.json
        + optional AGENTS.md are read by the Soul reader.
        """
        mi = _build_project(tmp_path, [
            {"source": f"local:{MARKET_DEMO}", "items": [
                {"kind": "Soul", "names": ["brad"]},
            ]},
        ], {"instruction": "Agent.", "soul": "brad"})

        soul = mi.one("Soul", "brad")
        spec = soul.spec
        assert len(spec.get("style_content", "")) > 0, "Missing STYLE.md content"
        assert len(spec.get("agents_content", "")) > 0, "Missing AGENTS.md content"

    def test_soul_has_json(self, tmp_path):
        """Brad soul has soul.json with structured data."""
        mi = _build_project(tmp_path, [
            {"source": f"local:{MARKET_DEMO}", "items": [
                {"kind": "Soul", "names": ["brad"]},
            ]},
        ], {"instruction": "Agent.", "soul": "brad"})

        soul = mi.one("Soul", "brad")
        soul_json = soul.spec.get("soul_json")
        assert soul_json is not None, "Missing soul.json content"
        assert isinstance(soul_json, dict), f"soul_json should be dict, got {type(soul_json)}"

    def test_soul_flattens_in_prompt(self, tmp_path):
        """Soul with flatten_in_context=True should inject content into build_prompt."""
        mi = _build_project(tmp_path, [
            {"source": f"local:{MARKET_DEMO}", "items": [
                {"kind": "Soul", "names": ["brad"]},
            ]},
        ], {"instruction": "You are the main agent.", "soul": "brad"})

        prompt = mi.build_prompt(agent="main")
        # Soul content should be flattened into the prompt
        assert len(prompt) > 100, f"Prompt too short ({len(prompt)}), soul not flattened?"


# ---------------------------------------------------------------------------
# Kind: Guardrail — synthetic (no real GitHub repo has them yet)
# ---------------------------------------------------------------------------


class TestGuardrailResolution:
    def _create_guardrail_repo(self, tmp_path: Path) -> Path:
        repo = tmp_path / "guardrail-repo"
        gr_dir = repo / "guardrails" / "pii-shield"
        gr_dir.mkdir(parents=True)
        # NOTE: GuardrailReader parses rules from the BODY (markdown list),
        # not from YAML frontmatter. This is the correct format:
        (gr_dir / "GUARDRAIL.md").write_text(
            "---\nseverity: block\nscope: output\n---\n"
            "# PII Shield\n\n"
            "- Never expose PII\n"
            "- Mask email addresses\n"
            "- Mask phone numbers\n"
        )
        return repo

    def test_resolves_guardrail(self, tmp_path):
        repo = self._create_guardrail_repo(tmp_path)
        mi = _build_project(tmp_path, [
            {"source": f"local:{repo}", "items": [
                {"kind": "Guardrail", "names": ["pii-shield"]},
            ]},
        ], {"instruction": "Agent.", "guardrails": ["pii-shield"]})

        guardrails = mi.all("Guardrail")
        names = [g.name for g in guardrails]
        assert "pii-shield" in names

    def test_guardrail_has_rules(self, tmp_path):
        repo = self._create_guardrail_repo(tmp_path)
        mi = _build_project(tmp_path, [
            {"source": f"local:{repo}", "items": [
                {"kind": "Guardrail", "names": ["pii-shield"]},
            ]},
        ], {"instruction": "Agent.", "guardrails": ["pii-shield"]})

        gr = mi.one("Guardrail", "pii-shield")
        rules = gr.spec.get("rules", [])
        assert len(rules) == 3
        assert "Never expose PII" in rules

    def test_guardrail_severity(self, tmp_path):
        repo = self._create_guardrail_repo(tmp_path)
        mi = _build_project(tmp_path, [
            {"source": f"local:{repo}", "items": [
                {"kind": "Guardrail", "names": ["pii-shield"]},
            ]},
        ], {"instruction": "Agent.", "guardrails": ["pii-shield"]})

        gr = mi.one("Guardrail", "pii-shield")
        assert gr.spec.get("severity") == "block"


# ---------------------------------------------------------------------------
# ALL kinds together — Skill + Soul + Guardrail in one manifest
# ---------------------------------------------------------------------------


class TestAllKindsTogether:
    def _create_mixed_repo(self, tmp_path: Path) -> Path:
        repo = tmp_path / "mixed-repo"

        # Skill
        sk = repo / "skills" / "my-skill"
        sk.mkdir(parents=True)
        (sk / "SKILL.md").write_text("---\nname: my-skill\n---\n# My Skill\nDo things well.")

        # Soul
        so = repo / "souls" / "wise"
        so.mkdir(parents=True)
        (so / "SOUL.md").write_text("# Wise Soul\nPatient, thoughtful, wise.")

        # Guardrail
        gr = repo / "guardrails" / "safe"
        gr.mkdir(parents=True)
        (gr / "GUARDRAIL.md").write_text("---\nseverity: warn\n---\n# Safe\n\n- Be safe\n")

        return repo

    def test_all_three_kinds_resolve(self, tmp_path):
        repo = self._create_mixed_repo(tmp_path)
        mi = _build_project(tmp_path, [
            {"source": f"local:{repo}", "items": [
                {"kind": "Skill", "names": ["my-skill"]},
                {"kind": "Soul", "names": ["wise"]},
                {"kind": "Guardrail", "names": ["safe"]},
            ]},
        ], {
            "instruction": "You are the orchestrator.",
            "soul": "wise",
            "skills": ["my-skill"],
            "guardrails": ["safe"],
        })

        assert mi.one("Skill", "my-skill") is not None
        assert mi.one("Soul", "wise") is not None
        assert mi.one("Guardrail", "safe") is not None

    def test_all_kinds_in_context(self, tmp_path):
        repo = self._create_mixed_repo(tmp_path)
        mi = _build_project(tmp_path, [
            {"source": f"local:{repo}", "items": [
                {"kind": "Skill", "names": ["my-skill"]},
                {"kind": "Soul", "names": ["wise"]},
                {"kind": "Guardrail", "names": ["safe"]},
            ]},
        ], {
            "instruction": "Orchestrator.",
            "soul": "wise",
            "skills": ["my-skill"],
            "guardrails": ["safe"],
        })

        ctx = mi._build_context(mi._find_agent("main"), None)
        assert len(ctx.get("agentskills-skill", [])) == 1
        assert len(ctx.get("soulspec-soul", [])) == 1
        assert len(ctx.get("guardrails-guardrail", [])) == 1

    def test_build_prompt_with_all_kinds(self, tmp_path):
        repo = self._create_mixed_repo(tmp_path)
        mi = _build_project(tmp_path, [
            {"source": f"local:{repo}", "items": [
                {"kind": "Skill", "names": ["my-skill"]},
                {"kind": "Soul", "names": ["wise"]},
                {"kind": "Guardrail", "names": ["safe"]},
            ]},
        ], {
            "instruction": "You are the orchestrator agent.",
            "soul": "wise",
            "skills": ["my-skill"],
            "guardrails": ["safe"],
        })

        prompt = mi.build_prompt(agent="main")
        assert "orchestrator" in prompt.lower()
        assert len(prompt) > 50

    def test_lockfile_captures_all_kinds(self, tmp_path):
        repo = self._create_mixed_repo(tmp_path)
        mi = _build_project(tmp_path, [
            {"source": f"local:{repo}", "items": [
                {"kind": "Skill", "names": ["my-skill"]},
                {"kind": "Soul", "names": ["wise"]},
                {"kind": "Guardrail", "names": ["safe"]},
            ]},
        ], {
            "instruction": "Agent.",
            "soul": "wise",
            "skills": ["my-skill"],
            "guardrails": ["safe"],
        })

        lock = mi.generate_lock()
        lock_kinds = {e.kind for e in lock.documents}
        assert "Skill" in lock_kinds
        assert "Soul" in lock_kinds
        assert "Guardrail" in lock_kinds
        assert "Genome" in lock_kinds
        assert "Agent" in lock_kinds

    def test_cache_roundtrip_all_kinds(self, tmp_path):
        """Resolve → cache → delete source → resolve again from cache."""
        import shutil
        repo = self._create_mixed_repo(tmp_path)
        mi1 = _build_project(tmp_path, [
            {"source": f"local:{repo}", "items": [
                {"kind": "Skill", "names": ["my-skill"]},
                {"kind": "Soul", "names": ["wise"]},
                {"kind": "Guardrail", "names": ["safe"]},
            ]},
        ], {
            "instruction": "Agent.",
            "soul": "wise",
            "skills": ["my-skill"],
            "guardrails": ["safe"],
        })

        # Confirm first load works
        assert mi1.one("Skill", "my-skill") is not None
        assert mi1.one("Soul", "wise") is not None
        assert mi1.one("Guardrail", "safe") is not None

        # Delete source
        shutil.rmtree(repo)

        # Build again — should work from cache
        base = tmp_path / ".dna"
        k = Kernel.auto()
        k.source(FilesystemSource(str(base)))
        k.cache(FilesystemCache(str(base)))
        k.resolver("local", LocalResolver(base_dir=str(base)))
        mi2 = k.instance("proj")

        assert mi2.one("Skill", "my-skill") is not None
        assert mi2.one("Soul", "wise") is not None
        assert mi2.one("Guardrail", "safe") is not None
