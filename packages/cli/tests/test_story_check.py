"""Tests for `dna sdlc story check` — granular AC/DoD closure with evidence.

`story done` blanket-backfills the checklist (done_by=story-done-auto, no
evidence). `story check` marks SPECIFIC items done WITH evidence (PR #, commit,
prose), selectable by 1-based index or text substring. Evidence must survive a
later `story done` backfill (regression: _backfill_checklist preserves it).
"""
from contextlib import contextmanager

from click.testing import CliRunner

from dna_cli import sdlc_cmd


class _Doc:
    def __init__(self, spec):
        self.spec = spec


class _FakeSession:
    scope = "dna-development"

    def __init__(self, store):
        self._store = store

        class _K:
            def __init__(self, store):
                self._store = store

            async def write_document(self, scope, kind, name, raw):
                self._store[name] = raw

        self.kernel = _K(store)

    def get_doc(self, kind, name, *, tenant=None):
        spec = {
            "status": "review",
            "acceptance_criteria": ["AC one about brief", "AC two about tests"],
            "definition_of_done": ["DoD merged", "DoD docs updated"],
        }
        return _Doc(spec)

    def run(self, coro):
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _run(monkeypatch, *args):
    store: dict = {}

    @contextmanager
    def _fake(scope=None, *, tenant=None, timeout=30.0):
        yield _FakeSession(store)

    monkeypatch.setattr(sdlc_cmd, "dna_session", _fake)
    r = CliRunner().invoke(sdlc_cmd.sdlc, ["story", "check", "s-x", *args])
    return r, store


def test_check_by_index_marks_item_with_evidence(monkeypatch):
    r, store = _run(monkeypatch, "--ac", "1", "--evidence", "PR #42")
    assert r.exit_code == 0, r.output
    ac = store["s-x"]["spec"]["acceptance_criteria"]
    assert ac[0]["done"] is True and ac[0]["evidence"] == "PR #42"
    assert ac[0]["done_by"]  # stamped
    assert "done" not in ac[1] or ac[1].get("done") is not True  # item 2 untouched


def test_check_by_substring(monkeypatch):
    r, store = _run(monkeypatch, "--dod", "docs", "--evidence", "commit abc")
    assert r.exit_code == 0, r.output
    dod = store["s-x"]["spec"]["definition_of_done"]
    matched = [d for d in dod if d.get("done")]
    assert len(matched) == 1 and matched[0]["text"] == "DoD docs updated"


def test_check_all(monkeypatch):
    r, store = _run(monkeypatch, "--all", "--evidence", "PR #99")
    assert r.exit_code == 0, r.output
    spec = store["s-x"]["spec"]
    assert all(i["done"] and i["evidence"] == "PR #99" for i in spec["acceptance_criteria"])
    assert all(i["done"] and i["evidence"] == "PR #99" for i in spec["definition_of_done"])


def test_check_requires_selector(monkeypatch):
    r, _ = _run(monkeypatch, "--evidence", "PR #1")
    assert r.exit_code != 0  # no --ac/--dod/--all


def test_backfill_preserves_evidence():
    """_backfill_checklist must keep evidence from a prior `story check`."""
    out = sdlc_cmd._backfill_checklist(
        [{"text": "x", "done": True, "evidence": "PR #7", "done_by": "claude-code"}],
        done_at="2026-05-31T00:00:00+00:00", done_by="story-done-auto",
    )
    assert out is not None and out[0]["evidence"] == "PR #7"
    assert out[0]["done_by"] == "claude-code"  # original preserved, not overwritten
