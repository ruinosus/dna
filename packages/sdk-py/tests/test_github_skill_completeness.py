"""Completeness tests — prove that ALL files in real GitHub skills are read.

Tests that the SkillReader captures every file in the bundle:
- SKILL.md → spec.instruction
- scripts/*.py → spec.scripts
- reference/*.md → spec.extras["reference"]
- root files (LICENSE.txt, forms.md) → spec.root_files
- arbitrary subdirs (python/, typescript/) → spec.extras

Uses real skills from github:anthropics/skills with varying complexity.
Requires internet access.
"""
from __future__ import annotations

import subprocess
import pytest
from pathlib import Path

import yaml

from dna.kernel import Kernel
from dna.adapters.filesystem import FilesystemSource, FilesystemCache
from dna.adapters.resolvers.local import LocalResolver
from dna.adapters.resolvers.github import GitHubResolver


def _has_internet() -> bool:
    try:
        subprocess.run(
            ["git", "ls-remote", "https://github.com/anthropics/skills.git", "HEAD"],
            capture_output=True, timeout=10,
        )
        return True
    except Exception:
        return False


network = pytest.mark.requires_network


def _build(tmp_path: Path, skill_names: list[str]):
    """Build a project that resolves specific skills from anthropics/skills."""
    project = tmp_path / ".dna" / "test"
    project.mkdir(parents=True)

    manifest = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": "test"},
        "spec": {
            "default_agent": "a",
            "dependencies": [
                {
                    "source": "github:anthropics/skills",
                    "items": [{"kind": "Skill", "names": skill_names}],
                },
            ],
        },
    }
    (project / "manifest.yaml").write_text(yaml.dump(manifest, default_flow_style=False))

    agent = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "a"},
        "spec": {"instruction": "Agent.", "skills": skill_names},
    }
    (project / "agents").mkdir()
    (project / "agents" / "a.yaml").write_text(yaml.dump(agent, default_flow_style=False))

    base = tmp_path / ".dna"
    k = Kernel.auto()
    k.source(FilesystemSource(str(base)))
    k.cache(FilesystemCache(str(base)))
    k.resolver("local", LocalResolver(base_dir=str(base)))
    k.resolver("github", GitHubResolver())
    return k.instance("test")


# ---------------------------------------------------------------------------
# claude-api: SKILL.md + 27 files in subdirs (python/, typescript/, shared/)
# ---------------------------------------------------------------------------


@network
class TestClaudeApiSkill:
    """claude-api has the most complex structure: subdirs per language."""

    def test_instruction_from_skill_md(self, tmp_path):
        mi = _build(tmp_path, ["claude-api"])
        skill = next((d for d in mi.documents if d.kind == "Skill" and d.name == "claude-api"), None)
        assert skill is not None
        instruction = skill.spec.get("instruction", "")
        assert len(instruction) > 200

    def test_has_extras_subdirs(self, tmp_path):
        mi = _build(tmp_path, ["claude-api"])
        skill = next((d for d in mi.documents if d.kind == "Skill" and d.name == "claude-api"), None)
        extras = skill.spec.get("extras", {})
        # Should have python/, typescript/, shared/, etc.
        assert len(extras) > 0, f"Expected extras subdirs, got none. Spec keys: {list(skill.spec.keys())}"

    def test_python_subdir_files_present(self, tmp_path):
        mi = _build(tmp_path, ["claude-api"])
        skill = next((d for d in mi.documents if d.kind == "Skill" and d.name == "claude-api"), None)
        extras = skill.spec.get("extras", {})
        # python/ subdir should contain claude-api and agent-sdk docs
        python_files = extras.get("python", {})
        assert len(python_files) > 0, f"Expected python/ files. Extras keys: {list(extras.keys())}"

    def test_shared_subdir_files_present(self, tmp_path):
        mi = _build(tmp_path, ["claude-api"])
        skill = next((d for d in mi.documents if d.kind == "Skill" and d.name == "claude-api"), None)
        extras = skill.spec.get("extras", {})
        shared_files = extras.get("shared", {})
        assert len(shared_files) > 0, f"Expected shared/ files. Extras keys: {list(extras.keys())}"

    def test_root_files_include_license(self, tmp_path):
        mi = _build(tmp_path, ["claude-api"])
        skill = next((d for d in mi.documents if d.kind == "Skill" and d.name == "claude-api"), None)
        root_files = skill.spec.get("root_files", {})
        assert "LICENSE.txt" in root_files


# ---------------------------------------------------------------------------
# pdf: SKILL.md + scripts/*.py + root .md files
# ---------------------------------------------------------------------------


@network
class TestPdfSkill:
    """pdf has scripts/ (Python) and root .md reference files."""

    def test_scripts_present(self, tmp_path):
        mi = _build(tmp_path, ["pdf"])
        skill = next((d for d in mi.documents if d.kind == "Skill" and d.name == "pdf"), None)
        scripts = skill.spec.get("scripts", {})
        # scripts may be dict (direct read) or list (after cache roundtrip)
        count = len(scripts)
        assert count >= 5, f"Expected 5+ scripts, got {count}"

    def test_root_md_files_captured(self, tmp_path):
        mi = _build(tmp_path, ["pdf"])
        skill = next((d for d in mi.documents if d.kind == "Skill" and d.name == "pdf"), None)
        root_files = skill.spec.get("root_files", {})
        # forms.md and reference.md are root-level files (not in scripts/ or reference/)
        root_keys = list(root_files.keys()) if isinstance(root_files, dict) else root_files
        assert "forms.md" in root_keys, f"Expected forms.md in root_files. Got: {root_keys}"
        assert "reference.md" in root_keys


# ---------------------------------------------------------------------------
# mcp-builder: SKILL.md + reference/*.md + scripts/*.py
# ---------------------------------------------------------------------------


@network
class TestMcpBuilderSkill:
    """mcp-builder has both reference/ and scripts/ subdirectories."""

    def test_reference_dir_captured(self, tmp_path):
        mi = _build(tmp_path, ["mcp-builder"])
        skill = next((d for d in mi.documents if d.kind == "Skill" and d.name == "mcp-builder"), None)
        # reference/ is a _KNOWN_DIR in SkillReader → goes to spec.references
        references = skill.spec.get("references", {})
        ref_count = len(references)
        # If references is empty but extras has reference/, it went to wrong place
        extras = skill.spec.get("extras", {})
        assert ref_count > 0 or "reference" in (extras if isinstance(extras, dict) else {}), \
            f"Expected references or extras['reference']. refs={ref_count}, extras keys={list(extras.keys()) if isinstance(extras, dict) else extras}"

    def test_scripts_dir_captured(self, tmp_path):
        mi = _build(tmp_path, ["mcp-builder"])
        skill = next((d for d in mi.documents if d.kind == "Skill" and d.name == "mcp-builder"), None)
        scripts = skill.spec.get("scripts", {})
        assert len(scripts) > 0


# ---------------------------------------------------------------------------
# webapp-testing: SKILL.md + scripts/ + examples/ (non-standard subdir)
# ---------------------------------------------------------------------------


@network
class TestWebappTestingSkill:
    """webapp-testing has scripts/ (known) + examples/ (extra subdir)."""

    def test_scripts_captured(self, tmp_path):
        mi = _build(tmp_path, ["webapp-testing"])
        skill = next((d for d in mi.documents if d.kind == "Skill" and d.name == "webapp-testing"), None)
        scripts = skill.spec.get("scripts", {})
        assert len(scripts) > 0

    def test_examples_in_extras(self, tmp_path):
        mi = _build(tmp_path, ["webapp-testing"])
        skill = next((d for d in mi.documents if d.kind == "Skill" and d.name == "webapp-testing"), None)
        extras = skill.spec.get("extras", {})
        # examples/ is not a known dir → should be in extras
        assert "examples" in extras, f"Expected examples/ in extras. Got: {list(extras.keys())}"
        example_files = extras["examples"]
        assert len(example_files) >= 2


# ---------------------------------------------------------------------------
# Cross-skill: resolve ALL 5 complex skills at once
# ---------------------------------------------------------------------------


@network
class TestAllComplexSkills:
    """Resolve 5 skills with different structures in one manifest."""

    def test_all_five_resolved(self, tmp_path):
        mi = _build(tmp_path, ["frontend-design", "claude-api", "pdf", "mcp-builder", "webapp-testing"])
        skills = [d for d in mi.documents if d.kind == "Skill"]
        names = sorted(s.name for s in skills)
        assert names == ["claude-api", "frontend-design", "mcp-builder", "pdf", "webapp-testing"]

    def test_each_has_instruction(self, tmp_path):
        mi = _build(tmp_path, ["frontend-design", "claude-api", "pdf", "mcp-builder", "webapp-testing"])
        for skill in [d for d in mi.documents if d.kind == "Skill"]:
            instruction = skill.spec.get("instruction", "")
            assert len(instruction) > 50, f"Skill {skill.name} has short instruction: {len(instruction)} chars"
