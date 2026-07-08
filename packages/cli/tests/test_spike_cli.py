"""`dna sdlc spike comment` + `spike link` (s-spike-traceability).

Spikes lacked a running decision/findings trail (only status transitions) and
had no CLI to attach their outputs — so a spike's Research/HtmlArtifact/ADR sat
in limbo (FOCUS showed OUTPUTS=0 despite the artifacts existing). These two
commands close that:
- `spike comment` mirrors `story comment` (append to timeline, auto-promote
  decisions).
- `spike link` populates the schema's already-declared ref arrays
  (follow_up_adr, research_refs, html_artifacts, references, follow_up_story,
  feature, related_spikes) via read-modify-write — no hand-edited YAML.
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
            _FakeDocView(raw) for (sc, kd, _n), raw in self._store.items()
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


def _seed_spike(store, name="sp-x", **spec):
    base = {"status": "in-progress", "question_to_answer": "Q?", "title": "T"}
    base.update(spec)
    store[("dna-development", "Spike", name)] = {
        "kind": "Spike", "metadata": {"name": name}, "spec": base,
    }


def _spec(store, name="sp-x"):
    return store[("dna-development", "Spike", name)]["spec"]


# ─── spike comment ─────────────────────────────────────────────────


def test_spike_comment_appends_timeline(runner, store):
    _seed_spike(store, timeline=[])
    r = runner.invoke(sdlc, ["spike", "comment", "sp-x", "--body", "achei que X bate Y"])
    assert r.exit_code == 0, r.output
    tl = _spec(store)["timeline"]
    assert any(e.get("type") in ("comment", "decision") and "X bate Y" in (e.get("summary") or "") for e in tl)


def test_spike_comment_missing_errors(runner, store):
    r = runner.invoke(sdlc, ["spike", "comment", "sp-ghost", "--body", "x"])
    assert r.exit_code != 0
    assert "sp-ghost" in r.output or "not found" in r.output.lower()


def test_spike_comment_preserves_status(runner, store):
    _seed_spike(store, status="in-progress", timeline=[])
    runner.invoke(sdlc, ["spike", "comment", "sp-x", "--body", "nota"])
    assert _spec(store)["status"] == "in-progress"  # comment never flips status


# ─── spike link ────────────────────────────────────────────────────


def test_link_adr_sets_follow_up_adr(runner, store):
    _seed_spike(store)
    r = runner.invoke(sdlc, ["spike", "link", "sp-x", "--adr", "adr-mem"])
    assert r.exit_code == 0, r.output
    assert _spec(store)["follow_up_adr"] == "adr-mem"


def test_link_spec_sets_follow_up_spec(runner, store):
    _seed_spike(store)
    r = runner.invoke(sdlc, ["spike", "link", "sp-x", "--spec", "spec-mem"])
    assert r.exit_code == 0, r.output
    assert _spec(store)["follow_up_spec"] == "spec-mem"


def test_link_research_appends_array(runner, store):
    _seed_spike(store)
    runner.invoke(sdlc, ["spike", "link", "sp-x", "--research", "rsh-a"])
    runner.invoke(sdlc, ["spike", "link", "sp-x", "--research", "rsh-b"])
    assert _spec(store)["research_refs"] == ["rsh-a", "rsh-b"]


def test_link_research_dedups(runner, store):
    _seed_spike(store)
    runner.invoke(sdlc, ["spike", "link", "sp-x", "--research", "rsh-a"])
    runner.invoke(sdlc, ["spike", "link", "sp-x", "--research", "rsh-a"])
    assert _spec(store)["research_refs"] == ["rsh-a"]


def test_link_artifact_and_reference(runner, store):
    _seed_spike(store)
    r = runner.invoke(sdlc, ["spike", "link", "sp-x", "--artifact", "ha-1", "--reference", "ref-1"])
    assert r.exit_code == 0, r.output
    assert _spec(store)["html_artifacts"] == ["ha-1"]
    assert _spec(store)["references"] == ["ref-1"]


def test_link_multiple_in_one_call(runner, store):
    _seed_spike(store)
    r = runner.invoke(sdlc, [
        "spike", "link", "sp-x",
        "--adr", "adr-m", "--research", "rsh-m", "--artifact", "ha-m",
        "--follow-up-story", "s-build", "--feature", "f-mem",
    ])
    assert r.exit_code == 0, r.output
    s = _spec(store)
    assert s["follow_up_adr"] == "adr-m"
    assert s["research_refs"] == ["rsh-m"]
    assert s["html_artifacts"] == ["ha-m"]
    assert s["follow_up_story"] == "s-build"
    assert s["feature"] == "f-mem"


def test_link_preserves_existing_fields(runner, store):
    _seed_spike(store, findings="already found", research_refs=["rsh-old"])
    runner.invoke(sdlc, ["spike", "link", "sp-x", "--artifact", "ha-new"])
    s = _spec(store)
    assert s["findings"] == "already found"
    assert s["research_refs"] == ["rsh-old"]  # untouched
    assert s["html_artifacts"] == ["ha-new"]


def test_link_missing_spike_errors(runner, store):
    r = runner.invoke(sdlc, ["spike", "link", "sp-ghost", "--adr", "adr-x"])
    assert r.exit_code != 0


def test_link_no_args_is_noop_error(runner, store):
    """Calling link with nothing to link should tell the user, not silently pass."""
    _seed_spike(store)
    r = runner.invoke(sdlc, ["spike", "link", "sp-x"])
    assert r.exit_code != 0
