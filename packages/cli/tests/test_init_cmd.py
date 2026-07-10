"""Tests for ``dna init`` — agent-ready onboarding (s-dna-init-agent-ready).

Covers the four materialization steps (board, skill, AGENTS.md, hooks),
idempotence (never clobber without --force), and the market-fidelity
contract: the generated AGENTS.md parses back through the SDK's
``agentsmd`` reader, and the materialized skill round-trips through the
``agentskills`` reader byte-faithful to the embedded onboarding asset.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from dna_cli import _git_symbiosis as gs
from dna_cli.init_cmd import (
    SKILL_NAME,
    TOOL_SKILL_DIRS,
    _derive_scope,
    _onboarding_root,
    init,
)


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A clean git project dir, CWD'd into (init's default --dir '.')."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    # init must pin the source to <dir>/.dna regardless of ambient env.
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.delenv("DNA_BASE_DIR", raising=False)
    return tmp_path


def _hookspath(repo: Path) -> str | None:
    proc = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=repo, capture_output=True, text=True,
    )
    return proc.stdout.strip() or None


# --- the happy path -----------------------------------------------------------


def test_init_creates_full_onboarding_tree(runner, project):
    r = runner.invoke(init, ["--scope", "acme-dev"])
    assert r.exit_code == 0, r.output

    # 1. Board: Genome written through the kernel + seeded SDLC containers.
    board = project / ".dna" / "acme-dev"
    genome_file = board / "manifest.yaml"
    assert genome_file.exists()
    genome = yaml.safe_load(genome_file.read_text())
    assert genome["kind"] == "Genome"
    assert genome["apiVersion"] == "github.com/ruinosus/dna/v1"
    assert genome["metadata"]["name"] == "acme-dev"
    for container in ("stories", "features", "issues"):
        assert (board / container / ".gitkeep").exists()

    # 2. Skill bundle projected for the DEFAULT tools (claude + copilot),
    #    and NOT for unselected ones.
    for tool in ("claude", "copilot"):
        skill_md = project / TOOL_SKILL_DIRS[tool] / SKILL_NAME / "SKILL.md"
        assert skill_md.exists(), tool
        assert f"name: {SKILL_NAME}" in skill_md.read_text()
    assert not (project / TOOL_SKILL_DIRS["cursor"]).exists()
    assert not (project / TOOL_SKILL_DIRS["opencode"]).exists()

    # 3. AGENTS.md at the project root (the canonical instruction surface).
    assert (project / "AGENTS.md").exists()

    # 4. Hooks wired exactly like `dna sdlc hooks install`.
    assert _hookspath(project) == gs.HOOKS_DIR
    hook = project / gs.HOOKS_DIR / gs.HOOK_NAME
    assert hook.exists()
    assert hook.read_bytes() == gs.hook_source_path().read_bytes()

    assert "5 created" in r.output  # board + 2 skill projections + AGENTS.md + hooks
    assert "Next steps" in r.output


def test_init_tools_all_projects_every_tool_dir(runner, project):
    r = runner.invoke(init, ["--tools", "all"])
    assert r.exit_code == 0, r.output
    contents = set()
    for tool, rel in TOOL_SKILL_DIRS.items():
        skill_md = project / rel / SKILL_NAME / "SKILL.md"
        assert skill_md.exists(), tool
        contents.add(skill_md.read_bytes())
    # One Kind, N projections — byte-identical everywhere.
    assert len(contents) == 1


def test_init_tools_explicit_subset_and_unknown_tool(runner, project):
    r = runner.invoke(init, ["--tools", "cursor"])
    assert r.exit_code == 0, r.output
    assert (project / TOOL_SKILL_DIRS["cursor"] / SKILL_NAME / "SKILL.md").exists()
    assert not (project / ".claude").exists()
    assert not (project / ".github" / "skills").exists()

    r = CliRunner().invoke(init, ["--tools", "clippy"])
    assert r.exit_code != 0
    assert "unknown tool" in (r.output or "") + str(r.exception or "")


def test_init_default_scope_derived_from_dirname(runner, project):
    r = runner.invoke(init, [])
    assert r.exit_code == 0, r.output
    expected = _derive_scope(project)
    assert expected.endswith("-dev")
    assert (project / ".dna" / expected / "manifest.yaml").exists()


def test_init_dir_option_targets_another_directory(runner, tmp_path, monkeypatch):
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.delenv("DNA_BASE_DIR", raising=False)
    target = tmp_path / "elsewhere"
    target.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    monkeypatch.chdir(tmp_path)  # NOT the target
    r = runner_ = CliRunner().invoke(init, ["--dir", str(target), "--scope", "elsewhere-dev"])
    assert r.exit_code == 0, r.output
    assert (target / ".dna" / "elsewhere-dev" / "manifest.yaml").exists()
    assert (target / "AGENTS.md").exists()
    assert _hookspath(target) == gs.HOOKS_DIR
    # Nothing leaked into the CWD.
    assert not (tmp_path / ".dna").exists()
    assert not (tmp_path / "AGENTS.md").exists()


def test_init_rejects_missing_dir_and_bad_scope(runner, project):
    r = runner.invoke(init, ["--dir", "does/not/exist"])
    assert r.exit_code != 0
    r = runner.invoke(init, ["--scope", "Not A Slug"])
    assert r.exit_code != 0


# --- idempotence ---------------------------------------------------------------


def test_init_rerun_is_idempotent_and_reports_skips(runner, project):
    assert runner.invoke(init, ["--scope", "acme-dev"]).exit_code == 0

    # Customize materialized artifacts, then re-run.
    agents = project / "AGENTS.md"
    agents.write_text("# my customized conventions\n")
    skill_md = project / TOOL_SKILL_DIRS["claude"] / SKILL_NAME / "SKILL.md"
    skill_md.write_text("---\nname: dna-sdlc-cli\n---\n\ncustomized\n")

    r = runner.invoke(init, ["--scope", "acme-dev"])
    assert r.exit_code == 0, r.output
    assert "0 created" in r.output
    assert "5 skipped" in r.output
    # Customizations survived.
    assert agents.read_text() == "# my customized conventions\n"
    assert "customized" in skill_md.read_text()


def test_init_force_overwrites_files_but_never_the_board(runner, project):
    assert runner.invoke(init, ["--scope", "acme-dev"]).exit_code == 0
    agents = project / "AGENTS.md"
    agents.write_text("# custom\n")
    genome_file = project / ".dna" / "acme-dev" / "manifest.yaml"
    board_before = genome_file.read_text()
    # Simulate a real, living board — --force must not touch it.
    (project / ".dna" / "acme-dev" / "stories" / "s-x.yaml").write_text("kind: Story\n")

    r = CliRunner().invoke(init, ["--scope", "acme-dev", "--force"])
    assert r.exit_code == 0, r.output
    # AGENTS.md restored from the embedded asset...
    assert "dna sdlc" in agents.read_text()
    # ...but the board (Genome + content) untouched.
    assert genome_file.read_text() == board_before
    assert (project / ".dna" / "acme-dev" / "stories" / "s-x.yaml").exists()


# --- market fidelity: generated artifacts parse back through the SDK ------------


def test_generated_agents_md_parses_via_agentsmd_reader(runner, project):
    from dna.extensions.agentsmd import AgentDefinitionReader
    from dna.kernel.bundle_handle import FilesystemBundleHandle

    assert runner.invoke(init, []).exit_code == 0
    reader = AgentDefinitionReader()
    handle = FilesystemBundleHandle(project)
    assert reader.detect(handle)
    raw = reader.read(handle)
    assert raw["apiVersion"] == "agents.md/v1"
    assert raw["kind"] == "AgentDefinition"
    assert "dna sdlc" in raw["spec"]["content"]
    # Byte-fidelity: reading the generated file yields the same content the
    # embedded onboarding asset carries (reader→writer→reader fixpoint).
    src = AgentDefinitionReader().read(FilesystemBundleHandle(_onboarding_root()))
    assert raw["spec"]["content"] == src["spec"]["content"]


def test_materialized_skill_roundtrips_via_agentskills_reader(runner, project):
    from dna.extensions.agentskills import SkillReader
    from dna.kernel.bundle_handle import FilesystemBundleHandle

    assert runner.invoke(init, []).exit_code == 0
    reader = SkillReader()
    dest = project / ".claude" / "skills" / SKILL_NAME
    assert reader.detect(FilesystemBundleHandle(dest))
    materialized = reader.read(FilesystemBundleHandle(dest))
    embedded = reader.read(
        FilesystemBundleHandle(_onboarding_root() / "skills" / SKILL_NAME)
    )
    # The reader→writer round-trip is lossless: parsing the materialized
    # bundle yields the embedded asset exactly (metadata AND instruction).
    assert materialized == embedded
    assert materialized["metadata"]["name"] == SKILL_NAME
    # And the files themselves are byte-identical (byte-faithful writer).
    assert (dest / "SKILL.md").read_bytes() == (
        _onboarding_root() / "skills" / SKILL_NAME / "SKILL.md"
    ).read_bytes()


def test_embedded_onboarding_assets_carry_no_repo_internals():
    """The onboarding Genome is for CONSUMER projects — no dna-repo paths."""
    root = _onboarding_root()
    for rel in (f"skills/{SKILL_NAME}/SKILL.md", "AGENTS.md"):
        text = (root / rel).read_text()
        for forbidden in ("dna-development", "packages/sdk-py", "packages/cli",
                          ".venv", "this repo"):
            assert forbidden not in text, f"{rel} leaks repo-internal ref {forbidden!r}"


# --- graceful degradation --------------------------------------------------------


def test_init_without_git_skips_hooks_with_note(runner, tmp_path, monkeypatch):
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.delenv("DNA_BASE_DIR", raising=False)
    monkeypatch.chdir(tmp_path)  # plain dir, no .git
    r = runner.invoke(init, ["--scope", "plain-dev"])
    assert r.exit_code == 0, r.output
    assert (tmp_path / ".dna" / "plain-dev" / "manifest.yaml").exists()
    assert (tmp_path / "AGENTS.md").exists()
    assert "not a git repository" in r.output
    assert "4 created" in r.output  # board + 2 skill projections + AGENTS.md


def test_init_respects_foreign_hookspath(runner, project):
    subprocess.run(
        ["git", "config", "core.hooksPath", ".husky"], cwd=project, check=True,
    )
    r = runner.invoke(init, ["--scope", "acme-dev"])
    assert r.exit_code == 0, r.output
    assert _hookspath(project) == ".husky"  # untouched
    assert "already set to '.husky'" in r.output


def test_init_json_output(runner, project):
    r = runner.invoke(init, ["--scope", "acme-dev", "--json"])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["scope"] == "acme-dev"
    steps = {s["step"]: s["outcome"] for s in payload["steps"]}
    assert steps == {
        "board": "created",
        "skill[claude]": "created", "skill[copilot]": "created",
        "agents-md": "created", "hooks": "created",
    }
