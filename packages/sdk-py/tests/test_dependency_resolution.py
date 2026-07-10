"""Integration tests for dependency resolution with multiple kinds.

Proves the full flow: manifest declares deps → resolver fetches → cache stores →
kernel composes all kinds together. Uses LocalResolver (which is what GitHubResolver
delegates to after cloning) to simulate external repos.

This is the proof that ANY kind from ANY source (GitHub, HTTP, local) works
end-to-end through the dependency pipeline.
"""
from __future__ import annotations

import pytest
from pathlib import Path

import yaml

from dna.kernel import Kernel
from dna.kernel.protocols import ResolvedItem
from dna.adapters.filesystem import FilesystemSource, FilesystemCache
from dna.adapters.resolvers.local import LocalResolver
from dna.adapters.resolvers.github import GitHubResolver


# ---------------------------------------------------------------------------
# Helpers — build a fake "remote repo" with multiple kinds
# ---------------------------------------------------------------------------


def _create_remote_repo(tmp_path: Path) -> Path:
    """Simulate a GitHub repo / HTTP registry with multiple kinds.

    Structure:
        remote-repo/
        ├── skills/
        │   ├── tdd/SKILL.md
        │   └── debugging/SKILL.md
        ├── souls/
        │   └── expert/SOUL.md
        └── guardrails/
            └── safety/GUARDRAIL.md
    """
    repo = tmp_path / "remote-repo"

    # Skills
    for name, content in [("tdd", "# TDD Skill\nWrite tests first."), ("debugging", "# Debug Skill\nFind root cause.")]:
        d = repo / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(content)

    # Soul
    soul_dir = repo / "souls" / "expert"
    soul_dir.mkdir(parents=True)
    (soul_dir / "SOUL.md").write_text("# Expert Soul\nDeep technical knowledge.")

    # Guardrail
    gr_dir = repo / "guardrails" / "safety"
    gr_dir.mkdir(parents=True)
    (gr_dir / "GUARDRAIL.md").write_text("---\nseverity: block\nrules:\n  - No PII exposure\n  - No harmful content\n---\n# Safety Guardrail\nEnsure safe outputs.")

    return repo


def _create_project(tmp_path: Path, remote_path: Path) -> Path:
    """Create a project that depends on the remote repo."""
    project = tmp_path / "project" / ".dna" / "my-app"
    project.mkdir(parents=True)

    manifest = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": "my-app", "description": "Test project"},
        "spec": {
            "default_agent": "main-agent",
            "dependencies": [
                {
                    "source": f"local:{remote_path}",
                    "items": [
                        {"kind": "Skill", "names": ["tdd", "debugging"]},
                        {"kind": "Soul", "names": ["expert"]},
                        {"kind": "Guardrail", "names": ["safety"]},
                    ],
                },
            ],
        },
    }
    (project / "manifest.yaml").write_text(yaml.dump(manifest, default_flow_style=False))

    # Local agent
    agents_dir = project / "agents"
    agents_dir.mkdir()
    agent = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "main-agent"},
        "spec": {
            "instruction": "You are the main agent.",
            "soul": "expert",
            "skills": ["tdd", "debugging"],
            "guardrails": ["safety"],
        },
    }
    (agents_dir / "main-agent.yaml").write_text(yaml.dump(agent, default_flow_style=False))

    return tmp_path / "project" / ".dna"


def _build_kernel(base_dir: Path) -> Kernel:
    """Wire a full kernel with filesystem source + cache + local resolver."""
    k = Kernel.auto()
    k.source(FilesystemSource(str(base_dir)))
    k.cache(FilesystemCache(str(base_dir)))
    k.resolver("local", LocalResolver(base_dir=str(base_dir)))
    return k


# ---------------------------------------------------------------------------
# Tests — dependency resolution with multiple kinds
# ---------------------------------------------------------------------------


class TestMultiKindDependencyResolution:
    """Proves: manifest declares deps with 3 different kinds → all resolve and compose."""

    @pytest.fixture
    def env(self, tmp_path):
        remote = _create_remote_repo(tmp_path)
        base_dir = _create_project(tmp_path, remote)
        kernel = _build_kernel(base_dir)
        mi = kernel.instance("my-app")
        return mi

    def test_skills_resolved(self, env):
        skills = [d for d in env.documents if d.kind == "Skill"]
        names = [s.name for s in skills]
        assert "tdd" in names
        assert "debugging" in names

    def test_soul_resolved(self, env):
        souls = [d for d in env.documents if d.kind == "Soul"]
        names = [s.name for s in souls]
        assert "expert" in names

    def test_guardrail_resolved(self, env):
        guardrails = [d for d in env.documents if d.kind == "Guardrail"]
        names = [g.name for g in guardrails]
        assert "safety" in names

    def test_all_kinds_present(self, env):
        kinds = env.list_kinds()
        assert "Skill" in kinds
        assert "Soul" in kinds
        assert "Guardrail" in kinds
        assert "Agent" in kinds
        assert "Genome" in kinds

    def test_build_prompt_composes_all_kinds(self, env):
        prompt = env.build_prompt(agent="main-agent")
        assert "main agent" in prompt.lower()
        # Soul should be composed into the prompt
        assert len(prompt) > 50

    def test_agent_sees_deps_via_dep_filters(self, env):
        ctx = env._build_context(env._find_agent("main-agent"), None)
        # Agent declared soul: expert → should have soulspec-soul in context
        assert len(ctx.get("soulspec-soul", [])) == 1
        assert ctx["soulspec-soul"][0]["name"] == "expert"
        # Agent declared skills: [tdd, debugging] → should have agentskills-skill
        skill_names = [s["name"] for s in ctx.get("agentskills-skill", [])]
        assert "tdd" in skill_names
        assert "debugging" in skill_names

    def test_guardrail_in_context(self, env):
        ctx = env._build_context(env._find_agent("main-agent"), None)
        guardrails = ctx.get("guardrails-guardrail", [])
        names = [g["name"] for g in guardrails]
        assert "safety" in names


class TestCachePreventsReResolution:
    """Proves: second instance() call reads from cache, not from source."""

    def test_cached_on_second_call(self, tmp_path):
        remote = _create_remote_repo(tmp_path)
        base_dir = _create_project(tmp_path, remote)
        kernel = _build_kernel(base_dir)

        # First call — populates cache
        mi1 = kernel.instance("my-app")
        assert len([d for d in mi1.documents if d.kind == "Skill"]) == 2

        # Delete the remote to prove cache is used
        import shutil
        shutil.rmtree(remote)

        # Second call — should still work from cache
        mi2 = kernel.instance("my-app")
        assert len([d for d in mi2.documents if d.kind == "Skill"]) == 2
        assert len([d for d in mi2.documents if d.kind == "Soul"]) == 1
        assert len([d for d in mi2.documents if d.kind == "Guardrail"]) == 1


class TestLockfileIncludesAllResolvedKinds:
    """Proves: lockfile captures ALL kinds from ALL sources."""

    def test_lock_has_all_kinds(self, tmp_path):
        remote = _create_remote_repo(tmp_path)
        base_dir = _create_project(tmp_path, remote)
        kernel = _build_kernel(base_dir)
        mi = kernel.instance("my-app")

        lock = mi.generate_lock()
        lock_kinds = {e.kind for e in lock.documents}

        assert "Genome" in lock_kinds
        assert "Agent" in lock_kinds
        assert "Skill" in lock_kinds
        assert "Soul" in lock_kinds
        assert "Guardrail" in lock_kinds

    def test_lock_has_correct_count(self, tmp_path):
        remote = _create_remote_repo(tmp_path)
        base_dir = _create_project(tmp_path, remote)
        kernel = _build_kernel(base_dir)
        mi = kernel.instance("my-app")

        lock = mi.generate_lock()
        # 1 Module + 1 Agent + 2 Skills + 1 Soul + 1 Guardrail = 6
        assert len(lock.documents) == 6


class TestGitHubResolverUnit:
    """Unit tests for GitHubResolver parsing (no actual git clone)."""

    def test_cache_key_deterministic(self):
        r = GitHubResolver()
        assert r.cache_key("github:org/repo") == r.cache_key("github:org/repo")

    def test_cache_key_includes_ref(self):
        r = GitHubResolver()
        k1 = r.cache_key("github:org/repo@v1")
        k2 = r.cache_key("github:org/repo@v2")
        assert k1 != k2

    def test_cache_key_safe_chars(self):
        r = GitHubResolver()
        key = r.cache_key("github:my-org/my-repo@feature/branch")
        assert key.startswith("github-")
        assert ":" not in key


class TestLegacyDepShorthandRejected:
    """i-009 — the pre-v3 dep shorthand ('skills: [...]' as a top-level dep
    key) is a DEAD format: the Genome contract is ``items: [{kind, names}]``
    (no doc, schema or resolver ever documented the shorthand). Silently
    ignoring it made resolution fall through to ``_resolve_all`` with the
    wrong granularity — pointed at a flat tree it returned the bundle
    SUBDIRECTORIES (references/, scripts/) instead of the bundles.
    The shorthand is now rejected loudly with a rewrite recipe.
    """

    @pytest.mark.asyncio
    async def test_local_resolver_rejects_skills_shorthand(self, tmp_path):
        from dna.kernel.protocols import ResolveError
        remote = _create_remote_repo(tmp_path)
        resolver = LocalResolver()
        dep = {"source": f"local:{remote}", "skills": ["tdd", "debugging"]}
        with pytest.raises(ResolveError) as excinfo:
            await resolver.resolve(f"local:{remote}", dep)
        msg = str(excinfo.value)
        assert "skills" in msg            # names the offending key
        assert "items" in msg             # points at the v3 contract

    @pytest.mark.asyncio
    async def test_github_resolver_rejects_shorthand_before_walking(self, tmp_path, monkeypatch):
        """The github path (the market-demo case) must reject too — it used
        to skip the check entirely and land in _resolve_all."""
        from dna.adapters.resolvers.github import FetchedTree
        from dna.kernel.protocols import ResolveError
        remote = _create_remote_repo(tmp_path)
        r = GitHubResolver()
        monkeypatch.setattr(
            GitHubResolver, "fetch_tree",
            lambda self, uri, timeout=60: FetchedTree(
                root=remote / "skills", owner="anthropics", repo="skills",
                subdir="skills", ref="main", commit=None,
            ),
        )
        dep = {
            "source": "github:anthropics/skills/skills@main",
            "skills": ["tdd", "debugging"],
        }
        with pytest.raises(ResolveError) as excinfo:
            await r.resolve("github:anthropics/skills/skills@main", dep)
        assert "items" in str(excinfo.value)

    def test_kernel_surfaces_shorthand_as_resolve_error(self, tmp_path):
        """Through kernel.instance() the rejection lands in mi.resolve_errors
        (a loud report, not a crash)."""
        remote = _create_remote_repo(tmp_path)
        project = tmp_path / "project" / ".dna" / "legacy-app"
        project.mkdir(parents=True)
        manifest = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Genome",
            "metadata": {"name": "legacy-app"},
            "spec": {
                "dependencies": [
                    {"source": f"local:{remote}", "skills": ["tdd"]},
                ],
            },
        }
        (project / "Genome.yaml").write_text(
            yaml.dump(manifest, default_flow_style=False)
        )
        kernel = _build_kernel(tmp_path / "project" / ".dna")
        mi = kernel.instance("legacy-app")
        assert any("items" in e for e in mi.resolve_errors)
        # And the wrong-granularity fallback did NOT happen: no Skill docs
        # imported from the dep.
        assert not [d for d in mi.documents if d.kind == "Skill"]

    @pytest.mark.asyncio
    async def test_items_format_still_resolves(self, tmp_path):
        """Control: the v3 items format keeps working untouched."""
        remote = _create_remote_repo(tmp_path)
        resolver = LocalResolver()
        dep = {
            "source": f"local:{remote}",
            "items": [{"kind": "Skill", "names": ["tdd"]}],
        }
        resolved = await resolver.resolve(f"local:{remote}", dep)
        assert [r.name for r in resolved] == ["tdd"]
