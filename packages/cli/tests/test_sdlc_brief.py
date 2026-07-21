"""Tests for `dna sdlc brief` — the cross-session session-start aggregator.

Read-only command: aggregates in-progress work + open spikes + recent
AgentSessions + recent Engram + open high/critical Issues into one
screen. We fake `dna_session` so `query_list(kind)` returns canned docs
and assert each section renders.
"""
from contextlib import contextmanager

from click.testing import CliRunner

from dna_cli._ctx import SESSION_PROVIDER_KEY
from dna_cli import sdlc_cmd


class _Doc:
    def __init__(self, name: str, spec: dict):
        self.name = name
        self.spec = spec


_FIXTURE = {
    "Story": [
        _Doc("s-active", {"status": "in-progress", "title": "active story"}),
        _Doc("s-done", {"status": "done", "title": "finished"}),
    ],
    "Feature": [_Doc("f-active", {"status": "in-development", "title": "feat"})],
    "Epic": [_Doc("e-active", {"status": "in-progress", "title": "epic"})],
    "Spike": [
        _Doc("s-spike-open", {"status": "proposed", "question_to_answer": "Q?"}),
        _Doc("s-spike-done", {"status": "answered", "question_to_answer": "done"}),
    ],
    "AgentSession": [
        _Doc("vs-new", {"started_at": "2026-05-31T10:00:00Z"}),
        _Doc("vs-old", {"started_at": "2026-05-01T10:00:00Z"}),
    ],
    "Engram": [
        _Doc("rem-new", {"summary": "newest lesson", "affect": "triumph", "created_at": "2026-05-31T10:00:00Z"}),
        _Doc("rem-old", {"summary": "older lesson", "affect": "regret", "created_at": "2026-05-01T10:00:00Z"}),
    ],
    "Issue": [
        _Doc("i-hi", {"status": "open", "severity": "high", "description": "hot bug"}),
        _Doc("i-low", {"status": "open", "severity": "low", "description": "minor"}),
    ],
}


class _FakeSession:
    scope = "dna-development"

    def query_list(self, kind, **kw):
        return list(_FIXTURE.get(kind, []))


@contextmanager
def _fake_session(scope=None, *, tenant=None, timeout=30.0):
    yield _FakeSession()


def _run(monkeypatch, *args, gh_prs="default"):
    # i-127: never hit the real gh CLI from tests. Default fixture: one
    # fresh PR + one stale (>24h) PR.
    if gh_prs == "default":
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        gh_prs = [
            {"number": 310, "title": "fresh pr", "headRefName": "fix/x",
             "createdAt": now.isoformat()},
            {"number": 278, "title": "orphan spec pr", "headRefName": "spec/scopes",
             "createdAt": (now - timedelta(hours=30)).isoformat()},
        ]
    monkeypatch.setattr(sdlc_cmd, "_gh_open_prs", lambda: gh_prs)
    return CliRunner().invoke(
        sdlc_cmd.sdlc, ["brief", *args],
        obj={SESSION_PROVIDER_KEY: _fake_session},
    )


def test_brief_runs_and_renders_all_sections(monkeypatch):
    r = _run(monkeypatch)
    assert r.exit_code == 0, r.output
    for header in ("Session brief", "In progress", "Open spikes",
                   "Recent sessions", "Recent lessons", "high/critical issues"):
        assert header in r.output, f"missing section: {header}"


def test_brief_filters_by_status_and_severity(monkeypatch):
    r = _run(monkeypatch)
    out = r.output
    # in-progress shown, done hidden
    assert "s-active" in out and "s-done" not in out
    # open spike shown, answered hidden
    assert "s-spike-open" in out and "s-spike-done" not in out
    # high-sev issue shown, low hidden
    assert "i-hi" in out and "i-low" not in out


def test_brief_sorts_recent_first(monkeypatch):
    r = _run(monkeypatch)
    out = r.output
    # newest session + lesson come before older ones
    assert out.index("vs-new") < out.index("vs-old")
    assert out.index("rem-new") < out.index("rem-old")


def test_brief_json_mode(monkeypatch):
    r = _run(monkeypatch, "--json")
    assert r.exit_code == 0, r.output
    import json
    data = json.loads(r.output)
    assert set(data) == {"in_progress", "spikes", "sessions", "lessons",
                         "issues", "open_prs"}
    assert {d["name"] for d in data["in_progress"]} == {"s-active", "f-active", "e-active"}


# ---------------------------------------------------------------------------
# Open GitHub PRs section (i-127)
# ---------------------------------------------------------------------------

def test_brief_lists_open_prs_and_flags_stale(monkeypatch):
    r = _run(monkeypatch)
    out = r.output
    assert "Open PRs (2)" in out
    assert "#310" in out and "fresh pr" in out
    assert "#278" in out and "orphan spec pr" in out
    # >24h PR gets the stale flag; the fresh one doesn't
    stale_line = next(l for l in out.splitlines() if "#278" in l)
    fresh_line = next(l for l in out.splitlines() if "#310" in l)
    assert ">24h" in stale_line
    assert ">24h" not in fresh_line


def test_brief_gh_unavailable_fail_soft(monkeypatch):
    r = _run(monkeypatch, gh_prs=None)
    assert r.exit_code == 0, r.output
    assert "(gh indisponível)" in r.output


def test_brief_no_open_prs(monkeypatch):
    r = _run(monkeypatch, gh_prs=[])
    assert r.exit_code == 0, r.output
    assert "Open PRs (0)" in r.output


def test_brief_json_open_prs_shape(monkeypatch):
    r = _run(monkeypatch, "--json")
    import json
    data = json.loads(r.output)
    by_num = {p["number"]: p for p in data["open_prs"]}
    assert by_num[278]["stale_24h"] is True
    assert by_num[310]["stale_24h"] is False
    assert by_num[310]["branch"] == "fix/x"
