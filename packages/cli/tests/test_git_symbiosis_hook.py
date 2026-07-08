"""Tests for the prepare-commit-msg hook (git↔SDLC symbiosis).

The hook is a standalone python3 script (zero deps) versioned at
``scripts/git-hooks/prepare-commit-msg``; we load it by path and drive
``main()`` directly against throwaway git repos. Also asserts the
no-drift invariants: hook constants == dna_cli._git_symbiosis constants,
and repo copy == packaged copy (dna_cli/data/git-hooks/).
"""
from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from dna_cli import _git_symbiosis as gs
from dna_cli._active_story import read_active_story, write_active_story

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK_PATH = REPO_ROOT / "scripts" / "git-hooks" / "prepare-commit-msg"


def _load_hook():
    loader = SourceFileLoader("dna_prepare_commit_msg", str(HOOK_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def hook():
    return _load_hook()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Throwaway git repo, process cwd inside it (the hook resolves the
    repo root via `git rev-parse --show-toplevel` from cwd)."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    # active-story path resolution in _active_story walks up to .git;
    # make sure no ambient env override leaks in.
    monkeypatch.delenv("DNA_ACTIVE_STORY_PATH", raising=False)
    monkeypatch.delenv(gs.COAUTHOR_ENV, raising=False)
    return tmp_path


def _set_active(repo: Path, scope="dna-development", name="s-x") -> None:
    (repo / ".dna").mkdir(exist_ok=True)
    (repo / ".dna" / "active-story.txt").write_text(f"{scope}:{name}\n")


def _msg(repo: Path, text: str) -> Path:
    p = repo / "COMMIT_EDITMSG"
    p.write_text(text, encoding="utf-8")
    return p


# ── stamping ─────────────────────────────────────────────────────────


def test_stamps_work_item_and_coauthor(hook, repo):
    _set_active(repo, name="s-x")
    msg = _msg(repo, "feat: do the thing\n")
    assert hook.main(["hook", str(msg)]) == 0
    out = msg.read_text()
    assert "Work-Item: Story/s-x" in out
    assert f"Co-Authored-By: {gs.DEFAULT_SDLC_COAUTHOR}" in out
    # trailers form a proper block (blank line before them)
    body, _, trailer_block = out.rstrip("\n").rpartition("\n\n")
    assert "feat: do the thing" in body
    assert "Work-Item: Story/s-x" in trailer_block


def test_idempotent_never_duplicates(hook, repo):
    _set_active(repo, name="s-x")
    msg = _msg(repo, "feat: thing\n")
    assert hook.main(["hook", str(msg)]) == 0
    assert hook.main(["hook", str(msg)]) == 0  # e.g. re-run on amend flows
    out = msg.read_text()
    assert out.count("Work-Item: Story/s-x") == 1
    assert out.count(gs.DEFAULT_SDLC_COAUTHOR) == 1


def test_keeps_existing_different_coauthor(hook, repo):
    _set_active(repo, name="s-x")
    msg = _msg(repo, "feat: thing\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n")
    hook.main(["hook", str(msg)])
    out = msg.read_text()
    assert "Co-Authored-By: Claude <noreply@anthropic.com>" in out
    assert f"Co-Authored-By: {gs.DEFAULT_SDLC_COAUTHOR}" in out


def test_coauthor_env_override(hook, repo, monkeypatch):
    monkeypatch.setenv(gs.COAUTHOR_ENV, "acme-sdlc[bot] <acme@example.com>")
    _set_active(repo, name="s-x")
    msg = _msg(repo, "feat: thing\n")
    hook.main(["hook", str(msg)])
    out = msg.read_text()
    assert "Co-Authored-By: acme-sdlc[bot] <acme@example.com>" in out
    assert gs.DEFAULT_SDLC_COAUTHOR not in out


# ── no-stamp cases (absence is signal) ───────────────────────────────


def test_no_active_story_no_stamp(hook, repo):
    msg = _msg(repo, "feat: thing\n")
    assert hook.main(["hook", str(msg)]) == 0
    assert msg.read_text() == "feat: thing\n"


@pytest.mark.parametrize("source", ["merge", "squash", "commit"])
def test_skips_merge_squash_amend_sources(hook, repo, source):
    _set_active(repo, name="s-x")
    msg = _msg(repo, "Merge branch 'x'\n")
    assert hook.main(["hook", str(msg), source]) == 0
    assert "Work-Item" not in msg.read_text()


def test_empty_message_not_stamped(hook, repo):
    _set_active(repo, name="s-x")
    msg = _msg(repo, "\n# Please enter the commit message.\n#\n")
    assert hook.main(["hook", str(msg)]) == 0
    assert "Work-Item" not in msg.read_text()


def test_malformed_pointer_no_stamp(hook, repo):
    (repo / ".dna").mkdir()
    (repo / ".dna" / "active-story.txt").write_text("no-colon-here\n")
    msg = _msg(repo, "feat: thing\n")
    assert hook.main(["hook", str(msg)]) == 0
    assert "Work-Item" not in msg.read_text()


def test_message_and_template_sources_do_stamp(hook, repo):
    _set_active(repo, name="s-y")
    for source in ("message", "template"):
        msg = _msg(repo, "feat: thing\n")
        assert hook.main(["hook", str(msg), source]) == 0
        assert "Work-Item: Story/s-y" in msg.read_text()


# ── end-to-end: a REAL git commit gets stamped ───────────────────────


def test_real_commit_is_stamped_end_to_end(hook, repo):
    subprocess.run(["git", "config", "core.hooksPath", gs.HOOKS_DIR], check=True)
    hooks_dir = repo / gs.HOOKS_DIR
    hooks_dir.mkdir(parents=True)
    target = hooks_dir / gs.HOOK_NAME
    target.write_bytes(HOOK_PATH.read_bytes())
    target.chmod(target.stat().st_mode | stat.S_IXUSR)
    subprocess.run(["git", "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "config", "user.name", "T"], check=True)
    _set_active(repo, name="s-e2e")
    (repo / "f.txt").write_text("hi")
    subprocess.run(["git", "add", "f.txt"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feat: e2e"], check=True)
    body = subprocess.run(
        ["git", "log", "-1", "--format=%B"], capture_output=True, text=True, check=True,
    ).stdout
    assert "Work-Item: Story/s-e2e" in body
    assert f"Co-Authored-By: {gs.DEFAULT_SDLC_COAUTHOR}" in body
    # and the way back: commits_for_work_item finds it via --grep
    rows = gs.commits_for_work_item("Story", "s-e2e", cwd=repo)
    assert rows and rows[0]["subject"] == "feat: e2e"


# ── no-drift invariants ──────────────────────────────────────────────


def test_hook_constants_match_cli_module(hook):
    assert hook.WORK_ITEM_TRAILER == gs.WORK_ITEM_TRAILER
    assert hook.COAUTHOR_TRAILER == gs.COAUTHOR_TRAILER
    assert hook.DEFAULT_SDLC_COAUTHOR == gs.DEFAULT_SDLC_COAUTHOR
    assert hook.COAUTHOR_ENV == gs.COAUTHOR_ENV


def test_repo_hook_is_byte_identical_to_packaged_copy():
    assert HOOK_PATH.exists(), f"missing {HOOK_PATH}"
    assert HOOK_PATH.read_bytes() == gs.hook_source_path().read_bytes(), (
        "scripts/git-hooks/prepare-commit-msg drifted from "
        "packages/cli/dna_cli/data/git-hooks/prepare-commit-msg — sync them"
    )


def test_repo_hook_is_executable():
    assert os.access(HOOK_PATH, os.X_OK), "hook must carry the executable bit"


# ── active-story pointer format (what the hook consumes) ─────────────


def test_active_story_pointer_roundtrip(tmp_path, monkeypatch, hook):
    monkeypatch.setenv("DNA_ACTIVE_STORY_PATH", str(tmp_path / "active-story.txt"))
    write_active_story("dna-development", "s-sdlc-git-symbiosis")
    raw = (tmp_path / "active-story.txt").read_text()
    assert raw == "dna-development:s-sdlc-git-symbiosis\n"  # <scope>:<name>, single line
    assert read_active_story() == ("dna-development", "s-sdlc-git-symbiosis")
    # the hook's own parser agrees with the CLI's
    (tmp_path / ".dna").mkdir()
    (tmp_path / ".dna" / "active-story.txt").write_text(raw)
    assert hook.read_active_story(str(tmp_path)) == (
        "dna-development", "s-sdlc-git-symbiosis",
    )
