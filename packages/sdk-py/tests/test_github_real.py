"""Integration test — resolve REAL skills from GitHub repos.

Clones real public repositories and proves the SDK can read their SKILL.md bundles.
These tests require internet access and git.

Sources:
- anthropics/skills: Official Anthropic skills (17 skills with SKILL.md)
- obra/superpowers: Superpowers framework skills (14 skills with SKILL.md)

Marked with pytest.mark.network so they can be skipped in CI without internet.
"""
from __future__ import annotations

import subprocess
import tempfile
import shutil
from pathlib import Path

import pytest
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


def _build_project_with_github_dep(tmp_path: Path, github_uri: str, items: list[dict]) -> Kernel:
    """Create a project that depends on a real GitHub repo."""
    project = tmp_path / ".dna" / "test-project"
    project.mkdir(parents=True)

    manifest = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": "test-project"},
        "spec": {
            "default_agent": "tester",
            "dependencies": [{"source": github_uri, "items": items}],
        },
    }
    (project / "manifest.yaml").write_text(yaml.dump(manifest, default_flow_style=False))

    agent = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "tester"},
        "spec": {"instruction": "You are a test agent."},
    }
    agents_dir = project / "agents"
    agents_dir.mkdir()
    (agents_dir / "tester.yaml").write_text(yaml.dump(agent, default_flow_style=False))

    base = tmp_path / ".dna"
    k = Kernel.auto()
    k.source(FilesystemSource(str(base)))
    k.cache(FilesystemCache(str(base)))
    k.resolver("local", LocalResolver(base_dir=str(base)))
    k.resolver("github", GitHubResolver())
    return k


# ---------------------------------------------------------------------------
# Real GitHub: anthropics/skills
# ---------------------------------------------------------------------------


@network
class TestAnthropicSkills:
    """Resolve real skills from github:anthropics/skills."""

    def test_resolve_frontend_design(self, tmp_path):
        k = _build_project_with_github_dep(tmp_path, "github:anthropics/skills", [
            {"kind": "Skill", "names": ["frontend-design"]},
        ])
        mi = k.instance("test-project")
        skills = [d for d in mi.documents if d.kind == "Skill"]
        names = [s.name for s in skills]
        assert "frontend-design" in names

    def test_skill_has_instruction(self, tmp_path):
        k = _build_project_with_github_dep(tmp_path, "github:anthropics/skills", [
            {"kind": "Skill", "names": ["frontend-design"]},
        ])
        mi = k.instance("test-project")
        skill = next((d for d in mi.documents if d.kind == "Skill" and d.name == "frontend-design"), None)
        assert skill is not None
        instruction = skill.spec.get("instruction", "")
        assert len(instruction) > 100  # Real skill has substantial content

    def test_resolve_multiple_skills(self, tmp_path):
        k = _build_project_with_github_dep(tmp_path, "github:anthropics/skills", [
            {"kind": "Skill", "names": ["frontend-design", "claude-api", "pdf"]},
        ])
        mi = k.instance("test-project")
        skills = [d for d in mi.documents if d.kind == "Skill"]
        names = [s.name for s in skills]
        assert "frontend-design" in names
        assert "claude-api" in names
        assert "pdf" in names

    def test_lockfile_captures_github_skills(self, tmp_path):
        k = _build_project_with_github_dep(tmp_path, "github:anthropics/skills", [
            {"kind": "Skill", "names": ["frontend-design", "claude-api"]},
        ])
        mi = k.instance("test-project")
        lock = mi.generate_lock()
        lock_names = {e.name for e in lock.documents if e.kind == "Skill"}
        assert "frontend-design" in lock_names
        assert "claude-api" in lock_names


# ---------------------------------------------------------------------------
# Real GitHub: obra/superpowers (skills)
# ---------------------------------------------------------------------------


@network
class TestSuperpowersSkills:
    """Resolve real skills from github:obra/superpowers."""

    def test_resolve_tdd_skill(self, tmp_path):
        k = _build_project_with_github_dep(tmp_path, "github:obra/superpowers", [
            {"kind": "Skill", "names": ["test-driven-development"]},
        ])
        mi = k.instance("test-project")
        skill = next((d for d in mi.documents if d.kind == "Skill" and d.name == "test-driven-development"), None)
        assert skill is not None
        assert len(skill.spec.get("instruction", "")) > 100

    def test_resolve_multiple_superpowers(self, tmp_path):
        k = _build_project_with_github_dep(tmp_path, "github:obra/superpowers", [
            {"kind": "Skill", "names": ["brainstorming", "systematic-debugging", "writing-plans"]},
        ])
        mi = k.instance("test-project")
        skills = [d for d in mi.documents if d.kind == "Skill"]
        names = [s.name for s in skills]
        assert "brainstorming" in names
        assert "systematic-debugging" in names
        assert "writing-plans" in names


# ---------------------------------------------------------------------------
# Mixed sources — skills from TWO different GitHub repos
# ---------------------------------------------------------------------------


@network
class TestMixedGitHubSources:
    """Resolve skills from multiple GitHub repos in a single manifest."""

    def test_two_repos_one_manifest(self, tmp_path):
        project = tmp_path / ".dna" / "mixed-project"
        project.mkdir(parents=True)

        manifest = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Genome",
            "metadata": {"name": "mixed-project"},
            "spec": {
                "default_agent": "tester",
                "dependencies": [
                    {
                        "source": "github:anthropics/skills",
                        "items": [{"kind": "Skill", "names": ["frontend-design"]}],
                    },
                    {
                        "source": "github:obra/superpowers",
                        "items": [{"kind": "Skill", "names": ["test-driven-development"]}],
                    },
                ],
            },
        }
        (project / "manifest.yaml").write_text(yaml.dump(manifest, default_flow_style=False))

        agent = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": {"name": "tester"},
            "spec": {
                "instruction": "You are a test agent.",
                "skills": ["frontend-design", "test-driven-development"],
            },
        }
        agents_dir = project / "agents"
        agents_dir.mkdir()
        (agents_dir / "tester.yaml").write_text(yaml.dump(agent, default_flow_style=False))

        base = tmp_path / ".dna"
        k = Kernel.auto()
        k.source(FilesystemSource(str(base)))
        k.cache(FilesystemCache(str(base)))
        k.resolver("local", LocalResolver(base_dir=str(base)))
        k.resolver("github", GitHubResolver())

        mi = k.instance("mixed-project")

        # Skills from both repos present
        skills = [d for d in mi.documents if d.kind == "Skill"]
        names = [s.name for s in skills]
        assert "frontend-design" in names        # from anthropics/skills
        assert "test-driven-development" in names  # from obra/superpowers

    def test_build_prompt_with_mixed_skills(self, tmp_path):
        project = tmp_path / ".dna" / "prompt-project"
        project.mkdir(parents=True)

        manifest = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Genome",
            "metadata": {"name": "prompt-project"},
            "spec": {
                "default_agent": "dev",
                "dependencies": [
                    {
                        "source": "github:anthropics/skills",
                        "items": [{"kind": "Skill", "names": ["frontend-design"]}],
                    },
                    {
                        "source": "github:obra/superpowers",
                        "items": [{"kind": "Skill", "names": ["test-driven-development"]}],
                    },
                ],
            },
        }
        (project / "manifest.yaml").write_text(yaml.dump(manifest, default_flow_style=False))

        agent = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": {"name": "dev"},
            "spec": {
                "instruction": "You are a full-stack developer.",
                "skills": ["frontend-design", "test-driven-development"],
            },
        }
        agents_dir = project / "agents"
        agents_dir.mkdir()
        (agents_dir / "dev.yaml").write_text(yaml.dump(agent, default_flow_style=False))

        base = tmp_path / ".dna"
        k = Kernel.auto()
        k.source(FilesystemSource(str(base)))
        k.cache(FilesystemCache(str(base)))
        k.resolver("local", LocalResolver(base_dir=str(base)))
        k.resolver("github", GitHubResolver())

        mi = k.instance("prompt-project")
        prompt = mi.build_prompt(agent="dev")

        assert "full-stack developer" in prompt.lower()
        # Skills are in context but prompt length depends on agent's template
        # The key proof: skills were resolved and are queryable
        skills = [d for d in mi.documents if d.kind == "Skill"]
        names = [s.name for s in skills]
        assert "frontend-design" in names
        assert "test-driven-development" in names
