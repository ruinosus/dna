"""GitHubResolver.fetch_tree — the imperative fetch behind `dna install`.

Offline: the URI grammar (shared with resolve() via parse_github_uri) and the
clone/rev-parse orchestration are exercised with a monkeypatched
``subprocess.run`` — no network. The real-clone path is covered by the
network-gated suite in ``test_github_real.py`` and by the CLI's
``test_install_github_real.py``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dna.adapters.resolvers.github import (
    FetchedTree,
    GitHubResolver,
    parse_github_uri,
)
from dna.kernel.protocols import ResolveError


# ─── grammar ──────────────────────────────────────────────────────────


def test_parse_full_uri():
    assert parse_github_uri("github:anthropics/skills/skills/pdf@main") == (
        "anthropics", "skills", "skills/pdf", "main",
    )


def test_parse_repo_only():
    assert parse_github_uri("github:obra/superpowers") == (
        "obra", "superpowers", None, None,
    )


def test_parse_subdir_no_ref():
    assert parse_github_uri("github:a/b/deep/sub/dir") == ("a", "b", "deep/sub/dir", None)


def test_parse_ref_no_subdir():
    assert parse_github_uri("github:a/b@v1.2.3") == ("a", "b", None, "v1.2.3")


def test_parse_invalid_raises_resolve_error():
    with pytest.raises(ResolveError, match="Invalid github URI"):
        parse_github_uri("github:not-a-repo")


# ─── fetch_tree orchestration (faked clone) ───────────────────────────


class _FakeRun:
    """Stand-in for subprocess.run: 'clones' by creating a small tree and
    answers rev-parse with a fixed sha."""

    def __init__(self, fail_clone: bool = False):
        self.fail_clone = fail_clone
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        import subprocess
        if cmd[:2] == ["git", "clone"]:
            if self.fail_clone:
                raise subprocess.CalledProcessError(128, cmd)
            dest = Path(cmd[-1])
            (dest / "skills" / "pdf").mkdir(parents=True)
            (dest / "skills" / "pdf" / "SKILL.md").write_text("---\nname: pdf\n---\nbody\n")
            return subprocess.CompletedProcess(cmd, 0)
        if cmd[1] == "-C" and "rev-parse" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="cafebabe" * 5 + "\n")
        raise AssertionError(f"unexpected command: {cmd}")


def test_fetch_tree_returns_subdir_and_commit(monkeypatch):
    fake = _FakeRun()
    monkeypatch.setattr("dna.adapters.resolvers.github.subprocess.run", fake)
    ft = GitHubResolver().fetch_tree("github:acme/widgets/skills@main")
    assert isinstance(ft, FetchedTree)
    assert ft.root.name == "skills" and ft.root.is_dir()
    assert (ft.owner, ft.repo, ft.subdir, ft.ref) == ("acme", "widgets", "skills", "main")
    assert ft.commit == "cafebabe" * 5
    # the ref rides the clone as --branch (same behavior resolve() had)
    clone = fake.calls[0]
    assert "--branch" in clone and "main" in clone


def test_fetch_tree_missing_subdir_raises_resolve_error(monkeypatch):
    monkeypatch.setattr("dna.adapters.resolvers.github.subprocess.run", _FakeRun())
    with pytest.raises(ResolveError, match="does not exist"):
        GitHubResolver().fetch_tree("github:acme/widgets/no-such-dir")


def test_fetch_tree_clone_failure_raises_resolve_error(monkeypatch):
    monkeypatch.setattr(
        "dna.adapters.resolvers.github.subprocess.run", _FakeRun(fail_clone=True),
    )
    with pytest.raises(ResolveError, match="Git clone failed"):
        GitHubResolver().fetch_tree("github:acme/widgets")
