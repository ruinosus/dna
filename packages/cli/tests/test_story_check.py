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

    #: overridable per-test — see _run(spec=...)
    spec_factory = None

    def __init__(self, store):
        self._store = store

        class _K:
            def __init__(self, store):
                self._store = store

            async def write_document(self, scope, kind, name, raw):
                self._store[name] = raw

        self.kernel = _K(store)

    def get_doc(self, kind, name, *, tenant=None):
        if self.spec_factory is not None:
            return _Doc(self.spec_factory())
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


def _run(monkeypatch, *args, spec=None):
    store: dict = {}

    @contextmanager
    def _fake(scope=None, *, tenant=None, timeout=30.0):
        s = _FakeSession(store)
        if spec is not None:
            s.spec_factory = lambda: dict(spec)
        yield s

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


# --- i-014: numeric selectors must be EXACT index matches -------------------
#
# Pilot phase-2 regression: `story check --ac 1 --ac 2` marked 3 ACs. A digit
# selector that didn't equal the index fell through to the substring branch,
# so "1" matched any AC whose TEXT contained the character "1" ("v1", "10
# retries", ...). Digit selectors are index-only; substring is for prose.

_GREEDY_SPEC = {
    "status": "in-progress",
    "acceptance_criteria": [
        "Ship the API endpoint",       # 1
        "Add 10 retries to client",    # 2 — text contains "1"
        "Document API v1 contract",    # 3 — text contains "1"
    ],
    "definition_of_done": [
        "CI green on 3.12",            # 1 — text contains "1" and "2"
        "Changelog updated",           # 2
        "PR merged",                   # 3
    ],
}


def test_ac_numeric_selector_is_index_only(monkeypatch):
    r, store = _run(monkeypatch, "--ac", "1", "--evidence", "PR #1",
                    spec=_GREEDY_SPEC)
    assert r.exit_code == 0, r.output
    ac = store["s-x"]["spec"]["acceptance_criteria"]
    done = [i + 1 for i, it in enumerate(ac) if it.get("done")]
    assert done == [1], f"--ac 1 must mark ONLY index 1, marked {done}"


def test_ac_two_numeric_selectors_mark_exactly_two(monkeypatch):
    """The literal pilot repro: --ac 1 --ac 2 marked 3 of 3 ACs."""
    r, store = _run(monkeypatch, "--ac", "1", "--ac", "2",
                    "--evidence", "PR #1", spec=_GREEDY_SPEC)
    assert r.exit_code == 0, r.output
    ac = store["s-x"]["spec"]["acceptance_criteria"]
    done = [i + 1 for i, it in enumerate(ac) if it.get("done")]
    assert done == [1, 2], f"--ac 1 --ac 2 must mark [1, 2], marked {done}"


def test_dod_numeric_selector_is_index_only(monkeypatch):
    """--dod shares _mark_checklist_items — same defect, same fix."""
    r, store = _run(monkeypatch, "--dod", "2", "--evidence", "PR #1",
                    spec=_GREEDY_SPEC)
    assert r.exit_code == 0, r.output
    dod = store["s-x"]["spec"]["definition_of_done"]
    done = [i + 1 for i, it in enumerate(dod) if it.get("done")]
    assert done == [2], f"--dod 2 must mark ONLY index 2, marked {done}"


def test_out_of_range_numeric_selector_matches_nothing(monkeypatch):
    """A digit selector beyond the list must NOT degrade to substring."""
    r, _ = _run(monkeypatch, "--ac", "10", "--evidence", "PR #1",
                spec=_GREEDY_SPEC)
    assert r.exit_code != 0  # "no AC/DoD items matched"


def test_substring_selector_still_works(monkeypatch):
    r, store = _run(monkeypatch, "--ac", "retries", "--evidence", "PR #1",
                    spec=_GREEDY_SPEC)
    assert r.exit_code == 0, r.output
    ac = store["s-x"]["spec"]["acceptance_criteria"]
    done = [i + 1 for i, it in enumerate(ac) if it.get("done")]
    assert done == [2]


def test_backfill_preserves_evidence():
    """_backfill_checklist must keep evidence from a prior `story check`."""
    out = sdlc_cmd._backfill_checklist(
        [{"text": "x", "done": True, "evidence": "PR #7", "done_by": "claude-code"}],
        done_at="2026-05-31T00:00:00+00:00", done_by="story-done-auto",
    )
    assert out is not None and out[0]["evidence"] == "PR #7"
    assert out[0]["done_by"] == "claude-code"  # original preserved, not overwritten
