"""SDLC discoverability & correctness fixes.

Two CLI behaviours that were wrong/missing:

1. `epic show` counted 0/0 stories because it read the stale forward
   `Feature.spec.stories[]` list. The real link is `Story.spec.feature`
   (maintained one-way at `story create --feature`). `feature show` already
   reverse-looks-up; `epic show` must too.

2. There was no verb to move a Feature `discovery → in-development` without
   clobbering its fields (`feature create` is a full overwrite). `feature
   start` does a read-modify-write that preserves every other field and
   stamps the timeline.

Approach mirrors test_sdlc_workitem_cli.py: patch `dna_session` with an
in-memory fake. Here the fake also implements `query_list` (needed by the
reverse-lookup) and re-reads written docs.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from click.testing import CliRunner

from dna_cli import sdlc_cmd
from dna_cli.sdlc_cmd import sdlc


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

    def query_list(self, kind, *, tenant=None):
        return [
            _FakeDocView(raw)
            for (sc, kd, _nm), raw in self._store.items()
            if sc == self.scope and kd == kind
        ]

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


def _seed(store, kind, name, spec, scope="dna-development"):
    store[(scope, kind, name)] = {
        "kind": kind,
        "metadata": {"name": name},
        "spec": spec,
    }


# ─── Fix 1: epic show reverse-lookup ───────────────────────────────


def test_epic_show_counts_stories_via_reverse_lookup(runner, store):
    """Stories link to a Feature via Story.spec.feature; epic show must count
    them even when Feature.spec.stories[] is empty/stale."""
    _seed(store, "Epic", "e-x", {"status": "planning", "features": ["f-x"]})
    # Feature has NO forward stories[] list — the stale-but-common case.
    _seed(store, "Feature", "f-x", {"status": "in-development"})
    _seed(store, "Story", "s-a", {"status": "done", "feature": "f-x"})
    _seed(store, "Story", "s-b", {"status": "todo", "feature": "f-x"})

    result = runner.invoke(sdlc, ["epic", "show", "e-x"])
    assert result.exit_code == 0, result.output
    # 1 of 2 done — NOT 0/0.
    assert "1/2" in result.output
    assert "0/0" not in result.output


def test_epic_show_burndown_totals(runner, store):
    """Burndown line aggregates across features by reverse-lookup."""
    _seed(store, "Epic", "e-y", {"status": "planning", "features": ["f-1", "f-2"]})
    _seed(store, "Feature", "f-1", {"status": "done"})
    _seed(store, "Feature", "f-2", {"status": "in-development"})
    _seed(store, "Story", "s-1", {"status": "done", "feature": "f-1"})
    _seed(store, "Story", "s-2", {"status": "done", "feature": "f-2"})
    _seed(store, "Story", "s-3", {"status": "todo", "feature": "f-2"})

    result = runner.invoke(sdlc, ["epic", "show", "e-y"])
    assert result.exit_code == 0, result.output
    assert "2/3" in result.output  # 2 done of 3 total


# ─── Fix 2: feature start (status transition, field-preserving) ────


def test_feature_start_moves_to_in_development(runner, store):
    """`feature start` flips discovery → in-development."""
    _seed(store, "Feature", "f-z", {
        "status": "discovery",
        "description": "important desc",
        "epic": "e-z",
        "priority": "high",
        "timeline": [{"type": "status_change", "to": "discovery"}],
    })
    result = runner.invoke(sdlc, ["feature", "start", "f-z"])
    assert result.exit_code == 0, result.output
    raw = store[("dna-development", "Feature", "f-z")]
    assert raw["spec"]["status"] == "in-development"


def test_feature_start_preserves_fields(runner, store):
    """The transition must NOT clobber desc/epic/priority (unlike create)."""
    _seed(store, "Feature", "f-keep", {
        "status": "discovery",
        "description": "do not lose me",
        "epic": "e-keep",
        "priority": "highest",
        "business_value": 800,
    })
    result = runner.invoke(sdlc, ["feature", "start", "f-keep"])
    assert result.exit_code == 0, result.output
    spec = store[("dna-development", "Feature", "f-keep")]["spec"]
    assert spec["description"] == "do not lose me"
    assert spec["epic"] == "e-keep"
    assert spec["priority"] == "highest"
    assert spec["business_value"] == 800


def test_feature_start_stamps_timeline(runner, store):
    """A status_change event lands on the timeline."""
    _seed(store, "Feature", "f-tl", {"status": "discovery", "timeline": []})
    result = runner.invoke(sdlc, ["feature", "start", "f-tl"])
    assert result.exit_code == 0, result.output
    tl = store[("dna-development", "Feature", "f-tl")]["spec"].get("timeline", [])
    assert any(
        e.get("type") == "status_change" and e.get("to") == "in-development"
        for e in tl
    ), tl


def test_feature_start_missing_feature_errors(runner, store):
    """Unknown feature → non-zero exit, clear message."""
    result = runner.invoke(sdlc, ["feature", "start", "f-ghost"])
    assert result.exit_code != 0
    assert "f-ghost" in result.output or "not found" in result.output.lower()
