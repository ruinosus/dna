"""Tests for `dna sdlc story pr` + `dna sdlc pr-footer` (s-sdlc-pr-attribution).

The PR half of the git↔SDLC symbiosis: the PR is born FROM the Story —
title `feat(<label>): <title> (<s-x>)`, body = description + AC checklist
+ attribution footer. `--dry-run` is the offline-testable surface (no gh,
no network); the gh invocation itself is asserted via a monkeypatched
subprocess.run. NO test here touches the network.
"""
from __future__ import annotations

import json
import subprocess
from contextlib import contextmanager

import pytest
from click.testing import CliRunner

# Importing pr_cmd registers `story pr` + `pr-footer` on `sdlc` (same as
# dna_cli/__init__).
from dna_cli._ctx import SESSION_PROVIDER_KEY
from dna_cli import pr_cmd
from dna_cli import _git_symbiosis as gs
from dna_cli.pr_cmd import build_gh_args, build_pr_body, build_pr_title
from dna_cli.sdlc_cmd import sdlc


@pytest.fixture
def runner():
    return CliRunner()


class _Doc:
    def __init__(self, name, spec):
        self.name = name
        self.spec = spec


_SPEC = {
    "title": "PR attribution — DNA assina os PRs que nascem das Stories",
    "status": "in-progress",
    "description": "Assim como o Claude Code assina PRs, o DNA assina os seus.",
    "labels": ["cli", "sdlc-tracking"],
    "acceptance_criteria": [
        "story pr cria PR real com footer + Work-Item",
        {"text": "footer configurável via env", "done": True},
    ],
}


def _fake_session(monkeypatch, spec=_SPEC, found=True, record=None):
    # keep _anchor_source_to_repo_root from mutating the process env
    # (monkeypatch restores this after the test)
    monkeypatch.setenv("DNA_SOURCE_URL", "file:///tmp/fake-dna-source")

    class _FakeSession:
        scope = "dna-development"

        def get_doc(self, kind, name, *, tenant=None):
            return _Doc(name, dict(spec)) if found else None

        def run(self, coro):
            coro.close()
            return None

        class kernel:  # noqa: N801 — attribute shape only
            @staticmethod
            def write_document(scope, kind, name, raw):
                if record is not None:
                    record.append(raw)

                async def _noop():
                    return None
                return _noop()

    @contextmanager
    def _fake(scope=None, *, tenant=None, timeout=30.0):
        yield _FakeSession()

    return {SESSION_PROVIDER_KEY: _fake}


# ─── pure builders ────────────────────────────────────────────────────


def test_build_pr_title_shape():
    t = build_pr_title("s-x", _SPEC)
    assert t == ("feat(cli): PR attribution — DNA assina os PRs que nascem "
                 "das Stories (s-x)")


def test_build_pr_title_fallbacks():
    # no labels → sdlc hint; no title → slug as title; whitespace collapsed
    t = build_pr_title("s-y", {"title": "multi\n  line   title"})
    assert t == "feat(sdlc): multi line title (s-y)"


def test_build_pr_body_sections_and_footer():
    body = build_pr_body("s-x", _SPEC)
    # description first
    assert body.startswith("Assim como o Claude Code assina PRs")
    # AC as checklist, done-flag honored
    assert "## Acceptance criteria" in body
    assert "- [ ] story pr cria PR real com footer + Work-Item" in body
    assert "- [x] footer configurável via env" in body
    # footer block at the end, after the --- rule
    assert body.rstrip().endswith(gs.pr_footer("Story", "s-x"))
    assert "\n---\n" in body
    assert "Work-Item: Story/s-x" in body


def test_build_pr_body_without_ac_or_description():
    body = build_pr_body("s-z", {})
    assert "Acceptance criteria" not in body
    # even a bare story gets the attribution footer
    assert body.strip() == gs.pr_footer_block("Story", "s-z")


def test_build_gh_args_passthrough_flags():
    args = build_gh_args("T", "B", base="main", head="feat/x", draft=True)
    assert args[:3] == ["gh", "pr", "create"]
    assert ["--title", "T"] == args[3:5] and ["--body", "B"] == args[5:7]
    assert ["--base", "main"] == args[7:9] and ["--head", "feat/x"] == args[9:11]
    assert args[-1] == "--draft"
    # defaults: no base/head/draft → nothing extra (gh uses current branch)
    assert build_gh_args("T", "B", base=None, head=None, draft=False) == \
        ["gh", "pr", "create", "--title", "T", "--body", "B"]


# ─── footer template + env override ──────────────────────────────────


def test_footer_default_template(monkeypatch):
    monkeypatch.delenv(gs.PR_FOOTER_ENV, raising=False)
    line = gs.pr_footer("Story", "s-x")
    assert "Tracked with [DNA SDLC](https://github.com/ruinosus/dna)" in line
    assert line.endswith("Work-Item: Story/s-x")


def test_footer_env_override_with_placeholder(monkeypatch):
    monkeypatch.setenv(gs.PR_FOOTER_ENV, "Signed by ACME bot — {work_item}")
    assert gs.pr_footer("Story", "s-x") == "Signed by ACME bot — Story/s-x"


def test_footer_env_override_literal(monkeypatch):
    monkeypatch.setenv(gs.PR_FOOTER_ENV, "Fixed banner, no placeholder")
    assert gs.pr_footer("Story", "s-x") == "Fixed banner, no placeholder"


def test_footer_env_override_malformed_never_crashes(monkeypatch):
    monkeypatch.setenv(gs.PR_FOOTER_ENV, "broken {unclosed")
    assert gs.pr_footer("Story", "s-x") == "broken {unclosed"


# ─── dna sdlc pr-footer ───────────────────────────────────────────────


def test_pr_footer_command_emits_block(runner, monkeypatch):
    monkeypatch.delenv(gs.PR_FOOTER_ENV, raising=False)
    r = runner.invoke(sdlc, ["pr-footer", "s-x"])
    assert r.exit_code == 0, r.output
    assert r.output.startswith("---\n")
    assert "Work-Item: Story/s-x" in r.output


def test_pr_footer_command_honors_env(runner, monkeypatch):
    monkeypatch.setenv(gs.PR_FOOTER_ENV, "Custom — {work_item}")
    r = runner.invoke(sdlc, ["pr-footer", "s-y"])
    assert r.exit_code == 0
    assert "---\nCustom — Story/s-y" in r.output


# ─── dna sdlc story pr --dry-run (offline assembly) ───────────────────


def test_story_pr_dry_run_prints_title_body_no_gh(runner, monkeypatch):
    monkeypatch.delenv(gs.PR_FOOTER_ENV, raising=False)
    obj = _fake_session(monkeypatch)

    def _boom(*a, **kw):  # gh must never be invoked on --dry-run
        raise AssertionError("subprocess.run called on --dry-run")

    monkeypatch.setattr(pr_cmd.subprocess, "run", _boom)
    r = runner.invoke(sdlc, ["story", "pr", "s-x", "--dry-run"], obj=obj)
    assert r.exit_code == 0, r.output
    assert "feat(cli): PR attribution" in r.output and "(s-x)" in r.output
    assert "- [ ] story pr cria PR real com footer + Work-Item" in r.output
    assert "Work-Item: Story/s-x" in r.output
    assert "dry-run" in r.output


def test_story_pr_dry_run_footer_env_override(runner, monkeypatch):
    monkeypatch.setenv(gs.PR_FOOTER_ENV, "ACME seal {work_item}")
    obj = _fake_session(monkeypatch)
    r = runner.invoke(sdlc, ["story", "pr", "s-x", "--dry-run"], obj=obj)
    assert r.exit_code == 0, r.output
    assert "ACME seal Story/s-x" in r.output


def test_story_pr_missing_story_fails_loud(runner, monkeypatch):
    obj = _fake_session(monkeypatch, found=False)
    r = runner.invoke(sdlc, ["story", "pr", "s-ghost", "--dry-run"], obj=obj)
    assert r.exit_code != 0
    assert "not found" in r.output


# ─── dna sdlc story pr (gh invocation, mocked) ────────────────────────


def test_story_pr_missing_gh_is_didactic(runner, monkeypatch):
    obj = _fake_session(monkeypatch)
    monkeypatch.setattr(pr_cmd.shutil, "which", lambda _: None)
    r = runner.invoke(sdlc, ["story", "pr", "s-x"], obj=obj)
    assert r.exit_code != 0
    assert "cli.github.com" in r.output
    assert "dna sdlc pr-footer s-x" in r.output


def test_story_pr_invokes_gh_with_built_args(runner, monkeypatch):
    monkeypatch.delenv(gs.PR_FOOTER_ENV, raising=False)
    writes: list = []
    obj = _fake_session(monkeypatch, record=writes)
    monkeypatch.setattr(pr_cmd.shutil, "which", lambda _: "/usr/bin/gh")
    calls: list = []

    def _fake_run(args, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(
            args, 0, stdout="https://github.com/ruinosus/dna/pull/9\n", stderr="")

    monkeypatch.setattr(pr_cmd.subprocess, "run", _fake_run)
    r = runner.invoke(sdlc, ["story", "pr", "s-x",
                             "--base", "main", "--head", "feat/x", "--draft"],
                      obj=obj)
    assert r.exit_code == 0, r.output
    assert len(calls) == 1
    args = calls[0]
    assert args[:3] == ["gh", "pr", "create"]
    assert "--base" in args and "main" in args
    assert "--head" in args and "feat/x" in args
    assert "--draft" in args
    body = args[args.index("--body") + 1]
    assert "Work-Item: Story/s-x" in body
    assert "PR CREATED" in r.output
    assert "https://github.com/ruinosus/dna/pull/9" in r.output
    # the PR URL is stamped back onto the story timeline (pr_opened event)
    raws = [w for w in writes if isinstance(w, dict)]
    assert raws, "expected a timeline write after PR creation"
    events = raws[-1]["spec"]["timeline"]
    assert events[-1]["type"] == "pr_opened"
    assert events[-1]["pr_url"] == "https://github.com/ruinosus/dna/pull/9"


def test_story_pr_gh_failure_fails_loud_with_hints(runner, monkeypatch):
    obj = _fake_session(monkeypatch)
    monkeypatch.setattr(pr_cmd.shutil, "which", lambda _: "/usr/bin/gh")

    def _fake_run(args, **kw):
        return subprocess.CompletedProcess(
            args, 1, stdout="", stderr="pull request create failed: no commits")

    monkeypatch.setattr(pr_cmd.subprocess, "run", _fake_run)
    r = runner.invoke(sdlc, ["story", "pr", "s-x"], obj=obj)
    assert r.exit_code != 0
    assert "no commits" in r.output
    assert "git push -u origin" in r.output  # didactic hint


# ─── groom --title (title is what story pr builds the PR title from) ──


def test_groom_title(runner, monkeypatch):
    writes: list = []

    class _FakeSession:
        scope = "dna-development"

        def get_doc(self, kind, name, *, tenant=None):
            return _Doc(name, {"title": "old", "status": "todo"})

        def run(self, coro):
            coro.close()

        class kernel:  # noqa: N801
            @staticmethod
            def write_document(scope, kind, name, raw):
                async def _noop():
                    return None
                writes.append(raw)
                return _noop()

    @contextmanager
    def _fake(scope=None, *, tenant=None, timeout=30.0):
        yield _FakeSession()

    r = runner.invoke(
        sdlc, ["story", "groom", "s-x", "--title", "new title"],
        obj={SESSION_PROVIDER_KEY: _fake},
    )
    assert r.exit_code == 0, r.output
    assert writes and writes[-1]["spec"]["title"] == "new title"
