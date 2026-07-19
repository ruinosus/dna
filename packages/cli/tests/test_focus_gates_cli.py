"""CliRunner tests for the FOCUS feed completeness guards wired into the SDLC
transition commands (i-113 produces, i-114 narração).

Both guards are WARN-only: they emit ``⚠ …`` to stderr but NEVER change the
exit code. ``--note`` posts an inline comment that silences the narração warn;
``--no-narrate`` / ``--allow-no-produces`` silence each warn directly.

Backed by the same in-memory fake session as ``test_sdlc_workitem_cli.py`` (the
``store`` fixture) — the write path runs for real, only the HTTP boundary is
faked. We seed a Story whose timeline is JUST a status_change (mute feed) so the
guards fire, then assert their presence/absence under each flag.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from click.testing import CliRunner

from dna_cli import sdlc_cmd
from dna_cli.sdlc_cmd import sdlc


# ── fake session (mirrors test_sdlc_workitem_cli.py) ─────────────────────────

class _FakeDocView:
    def __init__(self, raw: dict):
        self._raw = raw
        self.name = raw.get("metadata", {}).get("name")
        self.kind = raw.get("kind")
        self.spec = raw.get("spec") or {}


class _FakeKernel:
    def __init__(self, store: dict):
        self._store = store
        self._kinds: dict = {}

    def with_tenant(self, tenant):
        return self

    async def write_document(self, scope, kind, name, raw, **_):
        self._store[(scope, kind, name)] = raw
        return "v1"


class _FakeSession:
    def __init__(self, store: dict, scope: str):
        self._store = store
        self.scope = scope
        self.kernel = _FakeKernel(store)
        self.holder = type("_H", (), {"reload": lambda self: None})()

    def get_doc(self, kind, name, *, tenant=None):
        raw = self._store.get((self.scope, kind, name))
        return _FakeDocView(raw) if raw is not None else None

    def query_list(self, kind):  # used by feature ship child-check
        out = []
        for (sc, k, _n), raw in self._store.items():
            if sc == self.scope and k == kind:
                out.append(_FakeDocView(raw))
        return out

    def run(self, coro):
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def store(monkeypatch):
    backing: dict = {}

    @contextmanager
    def _fake(scope=None, *, tenant=None, timeout=30.0):
        yield _FakeSession(backing, scope or "dna-development")

    monkeypatch.setattr(sdlc_cmd, "dna_session", _fake)
    return backing


def _seed_story(store: dict, name: str, *, status: str = "todo", **spec_extra) -> None:
    """Seed a Story whose timeline is ONLY a status_change (a mute feed)."""
    spec = {
        "status": status,
        "timeline": [{"type": "status_change", "from": None, "to": status,
                      "at": "2026-06-09T00:00:00+00:00"}],
        **spec_extra,
    }
    store[("dna-development", "Story", name)] = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Story",
        "metadata": {"name": name}, "spec": spec,
    }


# ── GUARD A: narração on start ───────────────────────────────────────────────

def test_start_warns_when_mute(runner, store):
    _seed_story(store, "s-mute")
    r = runner.invoke(sdlc, [
        "story", "start", "s-mute", "--plan", "fazer X", "--scope", "dna-development",
    ])
    assert r.exit_code == 0, r.output
    assert "narração" in r.output


def test_start_no_narrate_silences(runner, store):
    _seed_story(store, "s-silent")
    r = runner.invoke(sdlc, [
        "story", "start", "s-silent", "--plan", "fazer X",
        "--no-narrate", "--scope", "dna-development",
    ])
    assert r.exit_code == 0, r.output
    assert "narração" not in r.output


def test_start_note_persists_comment_and_silences_warn(runner, store):
    _seed_story(store, "s-noted")
    r = runner.invoke(sdlc, [
        "story", "start", "s-noted", "--plan", "fazer X",
        "--note", "começando pelo parser", "--scope", "dna-development",
    ])
    assert r.exit_code == 0, r.output
    # The note silenced the narração warn …
    assert "narração" not in r.output
    # … and it was persisted as a comment event on the timeline.
    spec = store[("dna-development", "Story", "s-noted")]["spec"]
    summaries = [e.get("summary") for e in spec["timeline"] if e.get("type") in ("comment", "decision")]
    assert "começando pelo parser" in summaries


# ── GUARD A: narração on review ──────────────────────────────────────────────

@pytest.fixture
def open_pr(monkeypatch):
    """i-133: `story review` now checks for an open PR on the current
    branch (real gh subprocess). Fake one so these tests exercise ONLY
    the narração guard."""
    monkeypatch.setattr(sdlc_cmd, "_gh_open_prs_for_branch", lambda b: [{"number": 1}])


def test_review_warns_when_mute(runner, store, open_pr):
    _seed_story(store, "s-rev", status="in-progress")
    r = runner.invoke(sdlc, ["story", "review", "s-rev", "--scope", "dna-development"])
    assert r.exit_code == 0, r.output
    assert "narração" in r.output


def test_review_note_silences_and_persists(runner, store, open_pr):
    _seed_story(store, "s-rev2", status="in-progress")
    r = runner.invoke(sdlc, [
        "story", "review", "s-rev2", "--note", "PR aberto #999", "--scope", "dna-development",
    ])
    assert r.exit_code == 0, r.output
    assert "narração" not in r.output
    spec = store[("dna-development", "Story", "s-rev2")]["spec"]
    assert any(e.get("summary") == "PR aberto #999" for e in spec["timeline"])


# ── GUARD A + B together on done ─────────────────────────────────────────────

def test_done_emits_both_warns(runner, store, monkeypatch):
    # Isolate from the realtime Engram hook (fail-soft anyway).
    _seed_story(store, "s-done", status="review")
    r = runner.invoke(sdlc, [
        "story", "done", "s-done", "--no-commit", "--allow-no-tests",
        "--scope", "dna-development",
    ])
    assert r.exit_code == 0, r.output
    assert "narração" in r.output       # GUARD A
    assert "output" in r.output.lower() # GUARD B (produces)


def test_done_escapes_silence_both(runner, store):
    _seed_story(store, "s-done2", status="review")
    r = runner.invoke(sdlc, [
        "story", "done", "s-done2", "--no-commit", "--allow-no-tests",
        "--no-narrate", "--allow-no-produces", "--scope", "dna-development",
    ])
    assert r.exit_code == 0, r.output
    assert "narração" not in r.output
    assert "painel de outputs" not in r.output


def test_done_produces_silenced_by_linked_output(runner, store):
    _seed_story(store, "s-done3", status="review",
                produces=[{"kind": "Spec", "name": "spec-x"}])
    r = runner.invoke(sdlc, [
        "story", "done", "s-done3", "--no-commit", "--allow-no-tests",
        "--no-narrate", "--scope", "dna-development",
    ])
    assert r.exit_code == 0, r.output
    assert "painel de outputs" not in r.output  # produces guard satisfied


# ── option surface ───────────────────────────────────────────────────────────

def test_transition_commands_expose_new_options():
    start = {o.name for o in sdlc_cmd.cmd_story_start.params}
    assert {"note", "no_narrate"} <= start
    review = {o.name for o in sdlc_cmd.cmd_story_review.params}
    assert {"note", "no_narrate"} <= review
    done = {o.name for o in sdlc_cmd.cmd_story_done.params}
    assert {"note", "no_narrate", "allow_no_produces"} <= done
    ship = {o.name for o in sdlc_cmd.cmd_feature_ship.params}
    assert "allow_no_produces" in ship
    resolve = {o.name for o in sdlc_cmd.cmd_issue_resolve.params}
    assert "allow_no_produces" in resolve
