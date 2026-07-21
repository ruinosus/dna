"""Tests for the way BACK from git to the SDLC (s-sdlc-git-symbiosis):

- `dna sdlc story show` grows a Commits section fed by
  `git log --grep "Work-Item: Story/<name>"` (fail-soft);
- `dna sdlc story commits` merges trailer-stamped commits with
  timeline commit_refs, deduped by sha.

The git side is monkeypatched at the seam (`_gitsym.commits_for_work_item`)
so tests are deterministic; the real git path is covered end-to-end in
test_git_symbiosis_hook.py.
"""
from __future__ import annotations

import json
from contextlib import contextmanager

from click.testing import CliRunner

from dna_cli._ctx import SESSION_PROVIDER_KEY
from dna_cli import sdlc_cmd


class _Doc:
    def __init__(self, name, spec):
        self.name = name
        self.spec = spec


_SPEC = {
    "title": "Symbiosis test story",
    "status": "in-progress",
    "timeline": [
        {"at": "2026-07-08T10:00:00Z", "type": "status_change", "to": "in-progress"},
        {
            "at": "2026-07-08T11:00:00Z", "type": "decision",
            "summary": "design corrected",
            "commit_ref": "e0dcf12f5c758a02203e97b4e33bc9f9b5d32b8c",
        },
    ],
}

_TRAILER_COMMITS = [
    {
        "sha": "abc1234", "full_sha": "abc1234" + "0" * 33,
        "date": "2026-07-08", "subject": "feat(cli): stamp trailers",
    },
    {
        # same commit that the timeline also references — must dedup
        "sha": "e0dcf12", "full_sha": "e0dcf12f5c758a02203e97b4e33bc9f9b5d32b8c",
        "date": "2026-07-08", "subject": "chore(sdlc): file story",
    },
]


def _session_obj(found=True):
    class _FakeSession:
        scope = "dna-development"

        def get_doc(self, kind, name, *, tenant=None):
            return _Doc(name, dict(_SPEC)) if found else None

    @contextmanager
    def _fake(scope=None, *, tenant=None, timeout=30.0):
        yield _FakeSession()

    return {SESSION_PROVIDER_KEY: _fake}


def _patch_commits(monkeypatch, value):
    monkeypatch.setattr(
        sdlc_cmd._gitsym, "commits_for_work_item", lambda kind, name, **kw: value,
    )


# ── story show — Commits section ─────────────────────────────────────


def test_show_renders_commits_section(monkeypatch):
    obj = _session_obj()
    _patch_commits(monkeypatch, _TRAILER_COMMITS)
    r = CliRunner().invoke(sdlc_cmd.sdlc, ["story", "show", "s-symb"], obj=obj)
    assert r.exit_code == 0, r.output
    assert "Commits (2, via Work-Item trailer)" in r.output
    assert "abc1234" in r.output and "feat(cli): stamp trailers" in r.output


def test_show_omits_section_when_no_commits(monkeypatch):
    obj = _session_obj()
    _patch_commits(monkeypatch, [])
    r = CliRunner().invoke(sdlc_cmd.sdlc, ["story", "show", "s-symb"], obj=obj)
    assert r.exit_code == 0, r.output
    assert "Commits (" not in r.output


def test_show_fail_soft_when_git_unavailable(monkeypatch):
    obj = _session_obj()
    _patch_commits(monkeypatch, None)  # not a git repo / git missing
    r = CliRunner().invoke(sdlc_cmd.sdlc, ["story", "show", "s-symb"], obj=obj)
    assert r.exit_code == 0, r.output
    assert "Commits (" not in r.output


# ── story commits — merged trailer + timeline view ───────────────────


def test_commits_merges_and_dedups(monkeypatch):
    obj = _session_obj()
    _patch_commits(monkeypatch, _TRAILER_COMMITS)
    r = CliRunner().invoke(sdlc_cmd.sdlc, ["story", "commits", "s-symb", "--json"], obj=obj)
    assert r.exit_code == 0, r.output
    rows = json.loads(r.output)
    shas = [row["full_sha"] for row in rows]
    assert len(shas) == len(set(shas)) == 2  # deduped: e0dcf12 appears once
    by_sha = {row["sha"]: row for row in rows}
    assert by_sha["abc1234"]["source"] == "trailer"
    assert by_sha["e0dcf12"]["source"] == "trailer"  # trailer wins over timeline


def test_commits_timeline_only_when_git_unavailable(monkeypatch):
    obj = _session_obj()
    _patch_commits(monkeypatch, None)
    r = CliRunner().invoke(sdlc_cmd.sdlc, ["story", "commits", "s-symb", "--json"], obj=obj)
    assert r.exit_code == 0, r.output
    rows = json.loads(r.output)
    assert len(rows) == 1
    assert rows[0]["source"] == "timeline:decision"
    assert rows[0]["full_sha"].startswith("e0dcf12")


def test_commits_empty_message(monkeypatch):
    obj = {SESSION_PROVIDER_KEY: _empty_session()}
    _patch_commits(monkeypatch, [])
    r = CliRunner().invoke(sdlc_cmd.sdlc, ["story", "commits", "s-symb"], obj=obj)
    assert r.exit_code == 0, r.output
    assert "no commits found" in r.output
    assert "Work-Item: Story/s-symb" in r.output  # teaches the convention


def _empty_session():
    class _FakeSession:
        scope = "dna-development"

        def get_doc(self, kind, name, *, tenant=None):
            return _Doc(name, {"title": "t", "status": "todo", "timeline": []})

    @contextmanager
    def _fake(scope=None, *, tenant=None, timeout=30.0):
        yield _FakeSession()

    return _fake
