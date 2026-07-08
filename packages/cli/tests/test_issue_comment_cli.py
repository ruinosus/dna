"""`dna sdlc issue comment` — append findings/decisions to an Issue timeline.

Issues (bugs/tasks) had report→triage→fix→resolve status transitions but no way
to record the running investigation trail (root-cause notes, decisions) — those
were lost or crammed into the final `resolve` text. This mirrors `story comment`
/ `spike comment`: append to the timeline without changing status, auto-promoting
decision-shaped bodies.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from dna_cli import sdlc_cmd
from dna_cli.sdlc_cmd import sdlc
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


class _FakeDocView:
    def __init__(self, raw: dict):
        self._raw = raw
        self.name = raw.get("metadata", {}).get("name") or raw.get("name")
        self.kind = raw.get("kind")
        self.spec = raw.get("spec") or {}


class _FakeKernel:
    def __init__(self, store: dict):
        self._store = store

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

    def get_doc(self, kind, name, *, tenant=None):
        raw = self._store.get((self.scope, kind, name))
        return _FakeDocView(raw) if raw is not None else None

    def run(self, coro):
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


@pytest.fixture
def store(monkeypatch):
    backing: dict = {}

    @contextmanager
    def _fake(scope=None, *, tenant=None, timeout=30.0):
        yield _FakeSession(backing, scope or "dna-development")

    monkeypatch.setattr(sdlc_cmd, "dna_session", _fake)
    return backing


def _seed_issue(store, name="i-001-x", **spec):
    base = {"status": "open", "issue_type": "bug", "description": "D"}
    base.update(spec)
    store[("dna-development", "Issue", name)] = {
        "kind": "Issue", "metadata": {"name": name}, "spec": base,
    }


def _spec(store, name="i-001-x"):
    return store[("dna-development", "Issue", name)]["spec"]


def test_issue_comment_appends_timeline(runner, store):
    _seed_issue(store)
    r = runner.invoke(sdlc, ["issue", "comment", "i-001-x", "--body", "root cause: cache stale"])
    assert r.exit_code == 0, r.output
    tl = _spec(store).get("timeline") or []
    assert any(e.get("type") in ("comment", "decision")
               and "cache stale" in (e.get("summary") or "") for e in tl)


def test_issue_comment_missing_errors(runner, store):
    r = runner.invoke(sdlc, ["issue", "comment", "i-ghost", "--body", "x"])
    assert r.exit_code != 0


def test_issue_comment_preserves_status(runner, store):
    _seed_issue(store, status="triaged")
    runner.invoke(sdlc, ["issue", "comment", "i-001-x", "--body", "note"])
    assert _spec(store)["status"] == "triaged"  # comment never flips status
