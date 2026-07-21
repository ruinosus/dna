"""`dna sdlc kaizen` — post a `kaizen` event onto a work item's timeline.

Phase B (f-sdlc-realtime-observability): a flagged kaizen observation should
show up live in the FOCUS feed. The CLI appends a `kaizen` timeline event on the
active work item (optionally linking the Issue/Story that captured the
improvement) without changing status.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from dna_cli._ctx import SESSION_PROVIDER_KEY
from dna_cli.sdlc_cmd import (
    _build_kaizen_doc_spec,
    _build_kaizen_event,
    _kaizen_slug,
    sdlc,
)
from click.testing import CliRunner


# ---------------------------------------------------------------------------
# Pure helper: _build_kaizen_event
# ---------------------------------------------------------------------------

def test_build_kaizen_event_with_issue():
    ev = _build_kaizen_event(body="hardcoded token cap", issue="i-1",
                             actor="claude-code", now="2026-06-09T12:00:00+00:00")
    assert ev == {
        "type": "kaizen",
        "summary": "hardcoded token cap",
        "issue": "i-1",
        "actor": "claude-code",
        "at": "2026-06-09T12:00:00+00:00",
        "source": "cli",
    }


def test_build_kaizen_event_without_issue():
    ev = _build_kaizen_event(body="x", issue=None, actor="a",
                             now="2026-06-09T12:00:00+00:00")
    assert "issue" not in ev
    assert ev == {
        "type": "kaizen",
        "summary": "x",
        "actor": "a",
        "at": "2026-06-09T12:00:00+00:00",
        "source": "cli",
    }
    # empty-string issue is also dropped
    ev2 = _build_kaizen_event(body="x", issue="", actor="a",
                              now="2026-06-09T12:00:00+00:00")
    assert "issue" not in ev2


def test_build_kaizen_event_with_doc_ref():
    """s-kaizen-kind: the event refs its first-class Kaizen doc twin."""
    ev = _build_kaizen_event(body="x", issue=None, actor="a",
                             now="2026-06-09T12:00:00+00:00",
                             kaizen_doc="kz-001-x")
    assert ev["kaizen_doc"] == "kz-001-x"
    # falsy ref is dropped (back-compat with pre-doc events)
    ev2 = _build_kaizen_event(body="x", issue=None, actor="a",
                              now="2026-06-09T12:00:00+00:00",
                              kaizen_doc=None)
    assert "kaizen_doc" not in ev2


# ---------------------------------------------------------------------------
# Pure helpers: _build_kaizen_doc_spec + _kaizen_slug (s-kaizen-kind)
# ---------------------------------------------------------------------------

def test_build_kaizen_doc_spec_routed_when_issue():
    spec = _build_kaizen_doc_spec(
        body="hardcoded token cap", work_item="Story/s-x", issue="i-1",
        actor="claude-code", now="2026-06-09T12:00:00+00:00",
    )
    assert spec == {
        "body": "hardcoded token cap",
        "work_item": "Story/s-x",
        "issue": "i-1",
        "status": "routed",
        "actor": "claude-code",
        "created_at": "2026-06-09T12:00:00+00:00",
    }


def test_build_kaizen_doc_spec_observed_without_issue():
    spec = _build_kaizen_doc_spec(
        body="x", work_item="Issue/i-9", issue=None,
        actor="a", now="2026-06-09T12:00:00+00:00",
    )
    assert spec["status"] == "observed"
    assert "issue" not in spec


def test_kaizen_slug():
    assert _kaizen_slug("Step is MANUAL, automate it!") == "step-is-manual-automate-it"
    assert len(_kaizen_slug("a" * 100)) <= 28
    assert _kaizen_slug("!!!") == "obs"  # degenerate body still names the doc


# ---------------------------------------------------------------------------
# kinds-api feed types include "kaizen"
# ---------------------------------------------------------------------------

def test_kaizen_in_focus_feed_types():
    pytest.importorskip("dna_kinds_api")
    from dna_kinds_api.routes.focus import _FEED_TYPES
    assert "kaizen" in _FEED_TYPES


# ---------------------------------------------------------------------------
# CliRunner: dna sdlc kaizen <wi> --body --issue
# ---------------------------------------------------------------------------

@pytest.fixture
def runner(session_obj):
    """CliRunner whose invokes carry the injected session by default."""
    r = CliRunner()
    _orig = r.invoke

    def _invoke(*args, **kwargs):
        kwargs.setdefault("obj", session_obj)
        return _orig(*args, **kwargs)

    r.invoke = _invoke  # type: ignore[method-assign]
    return r


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

    def query_list(self, kind, *, filter=None, tenant=None):
        return [
            _FakeDocView(raw)
            for (sc, kn, _), raw in self._store.items()
            if sc == self.scope and kn == kind
        ]

    def run(self, coro):
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


@pytest.fixture
def store():
    """The in-memory backing dict the fake session reads/writes."""
    return {}


@pytest.fixture
def session_obj(store):
    """The ctx.obj to inject (f-cli-session-injection): a session factory."""

    @contextmanager
    def _fake(scope=None, *, tenant=None, timeout=30.0):
        yield _FakeSession(store, scope or "dna-development")

    return {SESSION_PROVIDER_KEY: _fake}


def _seed_story(store, name="s-x", **spec):
    base = {"status": "in-progress", "description": "D"}
    base.update(spec)
    store[("dna-development", "Story", name)] = {
        "kind": "Story", "metadata": {"name": name}, "spec": base,
    }


def _spec(store, kind="Story", name="s-x"):
    return store[("dna-development", kind, name)]["spec"]


def test_kaizen_appends_event_with_issue(runner, store):
    _seed_story(store)
    r = runner.invoke(sdlc, ["kaizen", "s-x", "--body", "step is manual", "--issue", "i-1"])
    assert r.exit_code == 0, r.output
    tl = _spec(store).get("timeline") or []
    ev = next(e for e in tl if e.get("type") == "kaizen")
    assert ev["summary"] == "step is manual"
    assert ev["issue"] == "i-1"
    assert ev["source"] == "cli"


def test_kaizen_without_issue(runner, store):
    _seed_story(store)
    r = runner.invoke(sdlc, ["kaizen", "s-x", "--body", "smells"])
    assert r.exit_code == 0, r.output
    tl = _spec(store).get("timeline") or []
    ev = next(e for e in tl if e.get("type") == "kaizen")
    assert "issue" not in ev


def test_kaizen_accepts_kind_slash_ref(runner, store):
    _seed_story(store)
    r = runner.invoke(sdlc, ["kaizen", "Story/s-x", "--body", "qualified ref"])
    assert r.exit_code == 0, r.output
    assert any(e.get("type") == "kaizen" for e in _spec(store).get("timeline") or [])


def test_kaizen_preserves_status(runner, store):
    _seed_story(store, status="review")
    runner.invoke(sdlc, ["kaizen", "s-x", "--body", "note"])
    assert _spec(store)["status"] == "review"  # kaizen never flips status


def test_kaizen_missing_errors(runner, store):
    r = runner.invoke(sdlc, ["kaizen", "s-ghost", "--body", "x"])
    assert r.exit_code != 0
    # no orphan Kaizen doc for a nonexistent work item
    assert not [k for k in store if k[1] == "Kaizen"]


# ---------------------------------------------------------------------------
# s-kaizen-kind: dual-write — event AND first-class Kaizen doc
# ---------------------------------------------------------------------------

def _kaizen_docs(store):
    return {k: v for k, v in store.items() if k[1] == "Kaizen"}


def test_kaizen_creates_doc_and_event_ref(runner, store):
    _seed_story(store)
    r = runner.invoke(sdlc, ["kaizen", "s-x", "--body", "Step is manual", "--issue", "i-1"])
    assert r.exit_code == 0, r.output
    docs = _kaizen_docs(store)
    assert len(docs) == 1
    (scope, _, name), raw = next(iter(docs.items()))
    assert scope == "dna-development"
    assert name == "kz-001-step-is-manual"
    assert raw["spec"]["body"] == "Step is manual"
    assert raw["spec"]["work_item"] == "Story/s-x"
    assert raw["spec"]["issue"] == "i-1"
    assert raw["spec"]["status"] == "routed"  # --issue → already routed
    assert raw["spec"]["actor"] == "claude-code"
    assert raw["spec"]["created_at"]
    # the timeline event refs the doc
    ev = next(e for e in _spec(store).get("timeline") or [] if e.get("type") == "kaizen")
    assert ev["kaizen_doc"] == name
    # doc slug surfaced in the output (backticked — ⌘K-pasteable)
    assert f"`{name}`" in r.output


def test_kaizen_doc_observed_without_issue(runner, store):
    _seed_story(store)
    r = runner.invoke(sdlc, ["kaizen", "s-x", "--body", "smells"])
    assert r.exit_code == 0, r.output
    (_, _, name), raw = next(iter(_kaizen_docs(store).items()))
    assert raw["spec"]["status"] == "observed"
    assert "issue" not in raw["spec"]
    assert name == "kz-001-smells"


def test_kaizen_doc_number_auto_increments(runner, store):
    _seed_story(store)
    # pre-existing Kaizen doc → next is kz-008
    store[("dna-development", "Kaizen", "kz-007-old")] = {
        "kind": "Kaizen", "metadata": {"name": "kz-007-old"},
        "spec": {"body": "old", "status": "observed"},
    }
    r = runner.invoke(sdlc, ["kaizen", "s-x", "--body", "new one"])
    assert r.exit_code == 0, r.output
    assert ("dna-development", "Kaizen", "kz-008-new-one") in store


# ---------------------------------------------------------------------------
# --label (repeatable) lands on the Kaizen doc spec
# ---------------------------------------------------------------------------

def test_build_kaizen_doc_spec_with_labels():
    spec = _build_kaizen_doc_spec(
        body="hardcoded limit", work_item="Story/s-x", issue=None,
        actor="claude-code", now="2026-06-10T10:00:00+00:00",
        labels=["debt", "hardcoded"],
    )
    assert spec["labels"] == ["debt", "hardcoded"]


def test_build_kaizen_doc_spec_no_labels_key_when_empty():
    spec = _build_kaizen_doc_spec(
        body="x", work_item="Story/s-x", issue=None,
        actor="a", now="2026-06-10T10:00:00+00:00",
        labels=None,
    )
    assert "labels" not in spec


def test_kaizen_cli_label_repeatable(runner, store):
    """--label TEXT (repeatable) lands on the Kaizen doc as spec.labels."""
    _seed_story(store)
    r = runner.invoke(
        sdlc,
        ["kaizen", "s-x", "--body", "token cap hardcoded",
         "--label", "debt", "--label", "hardcoded"],
    )
    assert r.exit_code == 0, r.output
    (_, _, name), raw = next(iter(_kaizen_docs(store).items()))
    assert raw["spec"]["labels"] == ["debt", "hardcoded"]
