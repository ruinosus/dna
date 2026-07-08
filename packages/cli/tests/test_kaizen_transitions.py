"""`dna sdlc kaizen route|resolve` — Kaizen arc transitions (i-125).

The Kaizen Kind declares observed → routed → resolved but the CLI only
wrote on create; later transitions would require hand-editing YAML
(against the repo rule). These subcommands route through
kernel.write_document like their siblings. The historical bare form
`dna sdlc kaizen <wi> --body` must keep working (default subcommand).
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from click.testing import CliRunner

from dna_cli import sdlc_cmd
from dna_cli.sdlc_cmd import kaizen_transition_guard, sdlc


# ---------------------------------------------------------------------------
# kaizen_transition_guard — pure
# ---------------------------------------------------------------------------

def test_route_from_observed_ok() -> None:
    assert kaizen_transition_guard("observed", "route") is None


def test_route_default_status_is_observed() -> None:
    assert kaizen_transition_guard(None, "route") is None


def test_route_from_routed_blocked() -> None:
    assert "já está" in kaizen_transition_guard("routed", "route")


def test_route_from_resolved_blocked() -> None:
    assert "inválida" in kaizen_transition_guard("resolved", "route")


def test_resolve_from_observed_and_routed_ok() -> None:
    assert kaizen_transition_guard("observed", "resolve") is None
    assert kaizen_transition_guard("routed", "resolve") is None


def test_resolve_from_resolved_blocked() -> None:
    assert "já está" in kaizen_transition_guard("resolved", "resolve")


# ---------------------------------------------------------------------------
# CliRunner — fake session (mirrors test_kaizen_event.py)
# ---------------------------------------------------------------------------

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


def _seed_kaizen(store, name="kz-001-test", **spec):
    base = {"body": "obs", "status": "observed", "work_item": "Story/s-x"}
    base.update(spec)
    store[("dna-development", "Kaizen", name)] = {
        "kind": "Kaizen", "metadata": {"name": name}, "spec": base,
    }


def _spec(store, name="kz-001-test"):
    return store[("dna-development", "Kaizen", name)]["spec"]


def test_route_sets_status_and_issue(runner, store):
    _seed_kaizen(store)
    r = runner.invoke(sdlc, ["kaizen", "route", "kz-001-test", "--issue", "i-042"])
    assert r.exit_code == 0, r.output
    assert _spec(store)["status"] == "routed"
    assert _spec(store)["issue"] == "i-042"
    assert _spec(store)["updated_at"]


def test_resolve_from_routed(runner, store):
    _seed_kaizen(store, status="routed", issue="i-042")
    r = runner.invoke(sdlc, ["kaizen", "resolve", "kz-001-test"])
    assert r.exit_code == 0, r.output
    assert _spec(store)["status"] == "resolved"


def test_resolve_direct_from_observed(runner, store):
    _seed_kaizen(store)
    r = runner.invoke(sdlc, ["kaizen", "resolve", "kz-001-test"])
    assert r.exit_code == 0, r.output
    assert _spec(store)["status"] == "resolved"


def test_route_blocked_after_resolve(runner, store):
    _seed_kaizen(store, status="resolved")
    r = runner.invoke(sdlc, ["kaizen", "route", "kz-001-test", "--issue", "i-1"])
    assert r.exit_code != 0
    assert _spec(store)["status"] == "resolved"  # unchanged


def test_route_missing_doc_errors(runner, store):
    r = runner.invoke(sdlc, ["kaizen", "route", "kz-ghost", "--issue", "i-1"])
    assert r.exit_code != 0


def test_bare_form_still_flags_observation(runner, store):
    """Backwards compat: `dna sdlc kaizen <wi> --body` (no subcommand)."""
    store[("dna-development", "Story", "s-x")] = {
        "kind": "Story", "metadata": {"name": "s-x"},
        "spec": {"status": "in-progress", "description": "D"},
    }
    r = runner.invoke(sdlc, ["kaizen", "s-x", "--body", "manual step"])
    assert r.exit_code == 0, r.output
    tl = store[("dna-development", "Story", "s-x")]["spec"].get("timeline") or []
    assert any(e.get("type") == "kaizen" for e in tl)
    kz = [k for k in store if k[1] == "Kaizen"]
    assert len(kz) == 1


def test_explicit_flag_subcommand(runner, store):
    store[("dna-development", "Story", "s-x")] = {
        "kind": "Story", "metadata": {"name": "s-x"},
        "spec": {"status": "in-progress", "description": "D"},
    }
    r = runner.invoke(sdlc, ["kaizen", "flag", "s-x", "--body", "manual step"])
    assert r.exit_code == 0, r.output
