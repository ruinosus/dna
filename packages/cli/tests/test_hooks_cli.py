"""Tests for `dna sdlc hooks install|uninstall|status` (git↔SDLC symbiosis)."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

# Importing hooks_cmd registers the group on `sdlc` (same as dna_cli/__init__).
from dna_cli import hooks_cmd  # noqa: F401
from dna_cli import _git_symbiosis as gs
from dna_cli.sdlc_cmd import sdlc


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DNA_ACTIVE_STORY_PATH", raising=False)
    monkeypatch.delenv(gs.COAUTHOR_ENV, raising=False)
    return tmp_path


def _hookspath(repo: Path) -> str | None:
    proc = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=repo, capture_output=True, text=True,
    )
    return proc.stdout.strip() or None


def test_install_sets_hookspath_and_materializes_hook(runner, repo):
    r = runner.invoke(sdlc, ["hooks", "install"])
    assert r.exit_code == 0, r.output
    assert _hookspath(repo) == gs.HOOKS_DIR
    hook = repo / gs.HOOKS_DIR / gs.HOOK_NAME
    assert hook.exists() and os.access(hook, os.X_OK)
    assert hook.read_bytes() == gs.hook_source_path().read_bytes()
    assert "INSTALLED" in r.output
    # documented consequence: scripts/git-hooks becomes THE hooks dir
    assert "ONLY hooks dir" in r.output


def test_install_is_idempotent(runner, repo):
    assert runner.invoke(sdlc, ["hooks", "install"]).exit_code == 0
    r = runner.invoke(sdlc, ["hooks", "install"])
    assert r.exit_code == 0, r.output
    assert _hookspath(repo) == gs.HOOKS_DIR


def test_install_refuses_foreign_hookspath(runner, repo):
    subprocess.run(["git", "config", "core.hooksPath", ".husky"], cwd=repo, check=True)
    r = runner.invoke(sdlc, ["hooks", "install"])
    assert r.exit_code != 0
    assert ".husky" in r.output
    assert _hookspath(repo) == ".husky"  # untouched


def test_uninstall_removes_only_ours(runner, repo):
    runner.invoke(sdlc, ["hooks", "install"])
    r = runner.invoke(sdlc, ["hooks", "uninstall"])
    assert r.exit_code == 0, r.output
    assert _hookspath(repo) is None
    # nothing set → friendly no-op
    r2 = runner.invoke(sdlc, ["hooks", "uninstall"])
    assert r2.exit_code == 0
    assert "nothing to uninstall" in r2.output


def test_uninstall_refuses_foreign_hookspath(runner, repo):
    subprocess.run(["git", "config", "core.hooksPath", ".husky"], cwd=repo, check=True)
    r = runner.invoke(sdlc, ["hooks", "uninstall"])
    assert r.exit_code != 0
    assert _hookspath(repo) == ".husky"


def test_status_reports_wiring_and_active_story(runner, repo):
    r = runner.invoke(sdlc, ["hooks", "status"])
    assert r.exit_code == 0, r.output
    assert "(not set)" in r.output and "hooks install" in r.output
    assert "active story:    (none" in r.output

    runner.invoke(sdlc, ["hooks", "install"])
    (repo / ".dna").mkdir(exist_ok=True)
    (repo / ".dna" / "active-story.txt").write_text("dna-development:s-x\n")
    r2 = runner.invoke(sdlc, ["hooks", "status"])
    assert r2.exit_code == 0, r2.output
    assert gs.HOOKS_DIR in r2.output
    assert "dna-development:s-x" in r2.output
    assert gs.DEFAULT_SDLC_COAUTHOR in r2.output


def test_commands_fail_outside_git_repo(runner, tmp_path, monkeypatch):
    # a dir that is guaranteed not to be inside any git repo
    outside = tmp_path / "no-repo"
    outside.mkdir()
    monkeypatch.chdir(outside)
    monkeypatch.setattr(gs, "repo_root", lambda **kw: None)
    for cmd in (["hooks", "install"], ["hooks", "uninstall"], ["hooks", "status"]):
        r = runner.invoke(sdlc, cmd)
        assert r.exit_code != 0
        assert "not inside a git repository" in r.output
