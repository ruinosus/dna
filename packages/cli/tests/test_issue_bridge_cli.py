"""Tests for `dna sdlc issue publish|import|sync` + the resolve close hook
(s-github-issues-bridge).

The GitHub Issues side of the symbiosis: DNA bridges to github.com with
provenance (github_number/url/state/synced_at on the Issue Kind schema),
it does not replace the GitHub artifact. Pure builders are tested
offline; every gh invocation is asserted via a monkeypatched
subprocess.run (same pattern as test_story_pr_cli). NO test here touches
the network.
"""
from __future__ import annotations

import json
import subprocess
from contextlib import contextmanager

import pytest
from click.testing import CliRunner

# Importing issue_bridge_cmd registers publish/import/sync on `sdlc issue`
# (same as dna_cli/__init__).
from dna_cli._ctx import SESSION_PROVIDER_KEY
from dna_cli import issue_bridge_cmd as ib
from dna_cli import _github_bridge as gb
from dna_cli import _git_symbiosis as gs
from dna_cli import sdlc_cmd as sc
from dna_cli.sdlc_cmd import sdlc


@pytest.fixture
def runner():
    return CliRunner()


class _Doc:
    def __init__(self, name, spec):
        self.name = name
        self.spec = spec


_SPEC = {
    "title": "scope detect procura manifest legado",
    "description": "O detect olha manifest.yaml e não Genome.yaml.",
    "type": "bug",
    "severity": "high",
    "status": "open",
}

_GH_ISSUE = {
    "number": 42,
    "title": "Broken Link: getting-started 404s",
    "body": "The quickstart link in the README 404s.",
    "state": "OPEN",
    "url": "https://github.com/ruinosus/dna/issues/42",
    "author": {"login": "octocat"},
    "labels": [{"name": "bug"}, {"name": "P1"}],
    "createdAt": "2026-07-01T10:00:00Z",
    "closedAt": None,
}


def _fake_session(monkeypatch, spec=_SPEC, found=True, record=None,
                  existing_issues=()):
    """Session obj to inject: ONE fake covers issue_bridge_cmd AND the
    sdlc_cmd helpers it leans on (`_next_issue_number`) — everything now
    resolves through open_session on the same click context."""
    monkeypatch.setenv("DNA_SOURCE_URL", "file:///tmp/fake-dna-source")

    class _FakeSession:
        scope = "dna-development"

        def get_doc(self, kind, name, *, tenant=None):
            return _Doc(name, dict(spec)) if found else None

        def query_list(self, kind, *, tenant=None):
            return [_Doc(n, dict(s)) for n, s in existing_issues]

        def run(self, coro):
            coro.close()
            return None

        class kernel:  # noqa: N801 — attribute shape only
            @staticmethod
            def write_document(scope, kind, name, raw):
                if record is not None:
                    record.append((name, raw))

                async def _noop():
                    return None
                return _noop()

    @contextmanager
    def _fake(scope=None, *, tenant=None, timeout=30.0):
        yield _FakeSession()

    return {SESSION_PROVIDER_KEY: _fake}


def _gh_present(monkeypatch):
    monkeypatch.setattr(gb.shutil, "which", lambda _: "/usr/bin/gh")


def _gh_absent(monkeypatch):
    monkeypatch.setattr(gb.shutil, "which", lambda _: None)


# ─── pure builders ────────────────────────────────────────────────────


def test_parse_repo_from_remote_shapes():
    assert gb.parse_repo_from_remote("https://github.com/ruinosus/dna.git") == "ruinosus/dna"
    assert gb.parse_repo_from_remote("https://github.com/ruinosus/dna") == "ruinosus/dna"
    assert gb.parse_repo_from_remote("git@github.com:ruinosus/dna.git") == "ruinosus/dna"
    assert gb.parse_repo_from_remote("ssh://git@github.com/ruinosus/dna") == "ruinosus/dna"
    # non-GitHub remotes are not bridgeable
    assert gb.parse_repo_from_remote("https://gitlab.com/x/y.git") is None
    assert gb.parse_repo_from_remote("") is None


def test_parse_issue_ref_forms():
    assert gb.parse_issue_ref("#12") == (12, None)
    assert gb.parse_issue_ref("12") == (12, None)
    assert gb.parse_issue_ref("https://github.com/ruinosus/dna/issues/7") == \
        (7, "ruinosus/dna")
    with pytest.raises(ValueError, match="inválida"):
        gb.parse_issue_ref("not-a-ref")


def test_slug_from_title():
    assert gb.slug_from_title("Broken Link: getting-started 404s") == \
        "broken-link-getting-started-404s"
    assert gb.slug_from_title("A B C D E F G H") == "a-b-c-d-e-f"  # bounded
    assert gb.slug_from_title("!!!") == "imported"  # never empty


def test_build_issue_title_uses_title_plus_slug_suffix():
    t = gb.build_issue_title("i-007-x", _SPEC)
    assert t == "scope detect procura manifest legado (i-007-x)"


def test_build_issue_title_falls_back_to_description_bounded():
    long_desc = "palavra " * 40
    t = gb.build_issue_title("i-009-y", {"description": long_desc})
    assert t.endswith("… (i-009-y)")
    # bounded: 120 chars of squeezed description + ellipsis + suffix
    assert len(t) <= 120 + len("… (i-009-y)")


def test_build_issue_body_sections_and_footer():
    body = gb.build_issue_body(
        "i-007-x", _SPEC, scope="dna-development", repo="ruinosus/dna")
    assert body.startswith("O detect olha manifest.yaml")
    assert "**Type:** bug · **Severity:** high" in body
    assert ".dna/dna-development/issues/i-007-x.yaml" in body
    # 🧬 footer — same template as PRs, Issue work item
    assert body.rstrip().endswith(gs.pr_footer("Issue", "i-007-x"))
    assert "Work-Item: Issue/i-007-x" in body


def test_map_labels_heuristic():
    assert gb.map_labels(["bug", "p1"]) == ("bug", "high")
    assert gb.map_labels(["Feature"]) == ("enhancement", "medium")
    assert gb.map_labels(["question"]) == ("question", "medium")
    assert gb.map_labels(["documentation", "trivial"]) == ("task", "low")
    assert gb.map_labels(["critical"]) == ("task", "critical")
    assert gb.map_labels([]) == ("task", "medium")
    # first match wins in label order
    assert gb.map_labels(["bug", "enhancement"])[0] == "bug"


def test_close_comment_carries_footer_and_resolution():
    c = gb.close_comment("i-007-x", "fixed in #30")
    assert "Resolved in DNA SDLC: fixed in #30" in c
    assert "Work-Item: Issue/i-007-x" in c
    assert "Resolved in DNA SDLC." in gb.close_comment("i-007-x", None)


# ─── publish ──────────────────────────────────────────────────────────


def test_publish_dry_run_prints_and_never_calls_gh(runner, monkeypatch):
    obj = _fake_session(monkeypatch)
    monkeypatch.setattr(ib.gb, "default_repo", lambda: "ruinosus/dna")

    def _boom(*a, **kw):
        raise AssertionError("subprocess.run called on --dry-run")

    monkeypatch.setattr(gb.subprocess, "run", _boom)
    r = runner.invoke(sdlc, ["issue", "publish", "i-007-x", "--dry-run"], obj=obj)
    assert r.exit_code == 0, r.output
    assert "scope detect procura manifest legado (i-007-x)" in r.output
    assert "Work-Item: Issue/i-007-x" in r.output
    assert "dry-run" in r.output


def test_publish_is_idempotent_when_already_published(runner, monkeypatch):
    spec = dict(_SPEC, github_number=9,
                github_url="https://github.com/ruinosus/dna/issues/9")
    obj = _fake_session(monkeypatch, spec=spec)

    def _boom(*a, **kw):
        raise AssertionError("gh must not be called for a published issue")

    monkeypatch.setattr(gb.subprocess, "run", _boom)
    r = runner.invoke(sdlc, ["issue", "publish", "i-007-x"], obj=obj)
    assert r.exit_code == 0, r.output
    assert "já publicada" in r.output
    assert "https://github.com/ruinosus/dna/issues/9" in r.output


def test_publish_invokes_gh_and_stamps_provenance(runner, monkeypatch):
    writes: list = []
    obj = _fake_session(monkeypatch, record=writes)
    monkeypatch.setattr(ib.gb, "default_repo", lambda: "ruinosus/dna")
    _gh_present(monkeypatch)
    calls: list = []

    def _fake_run(args, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(
            args, 0, stdout="https://github.com/ruinosus/dna/issues/33\n", stderr="")

    monkeypatch.setattr(gb.subprocess, "run", _fake_run)
    r = runner.invoke(sdlc, ["issue", "publish", "i-007-x"], obj=obj)
    assert r.exit_code == 0, r.output
    assert len(calls) == 1
    args = calls[0]
    assert args[:3] == ["gh", "issue", "create"]
    assert "--repo" in args and "ruinosus/dna" in args
    body = args[args.index("--body") + 1]
    assert "Work-Item: Issue/i-007-x" in body
    # provenance written back through the kernel
    (name, raw), = writes
    assert name == "i-007-x"
    spec = raw["spec"]
    assert spec["github_number"] == 33
    assert spec["github_url"] == "https://github.com/ruinosus/dna/issues/33"
    assert spec["github_state"] == "open"
    assert spec["github_synced_at"]
    assert spec["timeline"][-1]["type"] == "github_published"
    assert "PUBLISHED Issue/i-007-x → ruinosus/dna#33" in r.output


def test_publish_missing_gh_is_didactic(runner, monkeypatch):
    obj = _fake_session(monkeypatch)
    monkeypatch.setattr(ib.gb, "default_repo", lambda: "ruinosus/dna")
    _gh_absent(monkeypatch)
    r = runner.invoke(sdlc, ["issue", "publish", "i-007-x"], obj=obj)
    assert r.exit_code != 0
    assert "cli.github.com" in r.output
    assert "Traceback" not in r.output


def test_publish_gh_failure_is_didactic(runner, monkeypatch):
    obj = _fake_session(monkeypatch)
    monkeypatch.setattr(ib.gb, "default_repo", lambda: "ruinosus/dna")
    _gh_present(monkeypatch)

    def _fake_run(args, **kw):
        return subprocess.CompletedProcess(
            args, 1, stdout="", stderr="HTTP 401: Bad credentials")

    monkeypatch.setattr(gb.subprocess, "run", _fake_run)
    r = runner.invoke(sdlc, ["issue", "publish", "i-007-x"], obj=obj)
    assert r.exit_code != 0
    assert "Bad credentials" in r.output
    assert "gh auth status" in r.output
    assert "Traceback" not in r.output


def test_publish_without_derivable_repo_asks_for_flag(runner, monkeypatch):
    obj = _fake_session(monkeypatch)
    monkeypatch.setattr(ib.gb, "default_repo", lambda: None)
    r = runner.invoke(sdlc, ["issue", "publish", "i-007-x", "--dry-run"], obj=obj)
    assert r.exit_code != 0
    assert "--repo" in r.output


def test_publish_missing_issue_fails_loud(runner, monkeypatch):
    obj = _fake_session(monkeypatch, found=False)
    r = runner.invoke(sdlc, ["issue", "publish", "i-ghost", "--dry-run"], obj=obj)
    assert r.exit_code != 0
    assert "not found" in r.output


# ─── import ───────────────────────────────────────────────────────────


def _gh_view_ok(monkeypatch, payload=_GH_ISSUE):
    _gh_present(monkeypatch)

    def _fake_run(args, **kw):
        assert args[:3] == ["gh", "issue", "view"]
        return subprocess.CompletedProcess(
            args, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(gb.subprocess, "run", _fake_run)


def test_import_creates_doc_with_provenance_and_heuristics(runner, monkeypatch):
    writes: list = []
    obj = _fake_session(monkeypatch, record=writes,
                  existing_issues=[("i-004-old", {"status": "open"})])
    _gh_view_ok(monkeypatch)
    r = runner.invoke(sdlc, ["issue", "import", "#42", "--repo", "ruinosus/dna"], obj=obj)
    assert r.exit_code == 0, r.output
    (name, raw), = writes
    # board convention: next free number + gh marker + title slug
    assert name == "i-005-gh42-broken-link-getting-started-404s"
    spec = raw["spec"]
    assert spec["github_number"] == 42
    assert spec["github_url"] == "https://github.com/ruinosus/dna/issues/42"
    assert spec["github_state"] == "open"
    assert spec["status"] == "open"
    assert spec["type"] == "bug" and spec["severity"] == "high"  # bug + P1
    assert spec["reporter"] == "octocat"
    assert spec["labels"] == ["bug", "P1"]
    assert spec["timeline"][-1]["type"] == "github_imported"
    assert "IMPORTED ruinosus/dna#42" in r.output


def test_import_url_form_carries_repo(runner, monkeypatch):
    writes: list = []
    obj = _fake_session(monkeypatch, record=writes)
    _gh_view_ok(monkeypatch)
    # no --repo: the URL supplies it (default_repo must not be needed)
    monkeypatch.setattr(ib.gb, "default_repo", lambda: None)
    r = runner.invoke(
        sdlc, ["issue", "import", "https://github.com/ruinosus/dna/issues/42"],
        obj=obj)
    assert r.exit_code == 0, r.output
    assert writes


def test_import_closed_issue_maps_to_resolved(runner, monkeypatch):
    writes: list = []
    obj = _fake_session(monkeypatch, record=writes)
    closed = dict(_GH_ISSUE, state="CLOSED", closedAt="2026-07-05T12:00:00Z")
    _gh_view_ok(monkeypatch, payload=closed)
    r = runner.invoke(sdlc, ["issue", "import", "42", "--repo", "ruinosus/dna"], obj=obj)
    assert r.exit_code == 0, r.output
    spec = writes[0][1]["spec"]
    assert spec["status"] == "resolved"
    assert spec["github_state"] == "closed"
    assert spec["closed_at"] == "2026-07-05T12:00:00Z"


def test_import_is_idempotent_by_github_number(runner, monkeypatch):
    writes: list = []
    obj = _fake_session(
        monkeypatch, record=writes,
        existing_issues=[("i-003-already", {"github_number": 42})])
    _gh_view_ok(monkeypatch)
    r = runner.invoke(sdlc, ["issue", "import", "#42", "--repo", "ruinosus/dna"], obj=obj)
    assert r.exit_code == 0, r.output
    assert "já importada como Issue/i-003-already" in r.output
    assert not writes


def test_import_invalid_ref_is_didactic(runner, monkeypatch):
    obj = _fake_session(monkeypatch)
    r = runner.invoke(sdlc, ["issue", "import", "nope", "--repo", "x/y"], obj=obj)
    assert r.exit_code != 0
    assert "inválida" in r.output
    assert "Traceback" not in r.output


def test_import_missing_gh_is_didactic(runner, monkeypatch):
    obj = _fake_session(monkeypatch)
    _gh_absent(monkeypatch)
    r = runner.invoke(sdlc, ["issue", "import", "#42", "--repo", "ruinosus/dna"], obj=obj)
    assert r.exit_code != 0
    assert "cli.github.com" in r.output
    assert "Traceback" not in r.output


# ─── sync ─────────────────────────────────────────────────────────────


def test_sync_requires_provenance(runner, monkeypatch):
    obj = _fake_session(monkeypatch)  # _SPEC has no github_number
    r = runner.invoke(sdlc, ["issue", "sync", "i-007-x"], obj=obj)
    assert r.exit_code != 0
    assert "github_number" in r.output
    assert "issue publish" in r.output


def test_sync_remote_close_leaves_timeline_note(runner, monkeypatch):
    writes: list = []
    spec = dict(_SPEC, github_number=42, github_state="open")
    obj = _fake_session(monkeypatch, spec=spec, record=writes)
    closed = dict(_GH_ISSUE, state="CLOSED")
    _gh_view_ok(monkeypatch, payload=closed)
    monkeypatch.setattr(ib.gb, "default_repo", lambda: "ruinosus/dna")
    r = runner.invoke(sdlc, ["issue", "sync", "i-007-x"], obj=obj)
    assert r.exit_code == 0, r.output
    new_spec = writes[0][1]["spec"]
    assert new_spec["github_state"] == "closed"
    assert new_spec["github_synced_at"]
    note = new_spec["timeline"][-1]
    assert note["type"] == "comment" and "fechada no remoto" in note["summary"]
    # local status is NOT auto-resolved — that's a human triage decision
    assert new_spec["status"] == "open"
    assert "open → closed" in r.output


def test_sync_no_change_no_note(runner, monkeypatch):
    writes: list = []
    spec = dict(_SPEC, github_number=42, github_state="open")
    obj = _fake_session(monkeypatch, spec=spec, record=writes)
    _gh_view_ok(monkeypatch)  # remote still OPEN
    monkeypatch.setattr(ib.gb, "default_repo", lambda: "ruinosus/dna")
    r = runner.invoke(sdlc, ["issue", "sync", "i-007-x"], obj=obj)
    assert r.exit_code == 0, r.output
    new_spec = writes[0][1]["spec"]
    assert new_spec["github_state"] == "open"
    assert "timeline" not in new_spec or not any(
        e.get("type") == "comment" for e in new_spec.get("timeline", []))


# ─── resolve → close-on-GitHub (fail-soft hook in sdlc_cmd) ───────────


def test_resolve_closes_github_twin_best_effort(runner, monkeypatch):
    writes: list = []
    spec = dict(_SPEC, github_number=42, github_state="open")
    obj = _fake_session(monkeypatch, spec=spec, record=writes)
    monkeypatch.setattr(gb, "default_repo", lambda: "ruinosus/dna")
    _gh_present(monkeypatch)
    calls: list = []

    def _fake_run(args, **kw):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(gb.subprocess, "run", _fake_run)
    r = runner.invoke(sdlc, ["issue", "resolve", "i-007-x",
                             "--resolution", "fixed", "--allow-no-produces"], obj=obj)
    assert r.exit_code == 0, r.output
    close_calls = [c for c in calls if c[:3] == ["gh", "issue", "close"]]
    assert len(close_calls) == 1
    args = close_calls[0]
    assert "42" in args and "--repo" in args
    comment = args[args.index("--comment") + 1]
    assert "Resolved in DNA SDLC: fixed" in comment
    assert "Work-Item: Issue/i-007-x" in comment
    assert "CLOSED GitHub #42" in r.output
    assert "RESOLVED" in r.output
    # second write refreshes provenance
    assert writes[-1][1]["spec"]["github_state"] == "closed"


def test_resolve_without_gh_warns_but_resolves(runner, monkeypatch):
    writes: list = []
    spec = dict(_SPEC, github_number=42)
    obj = _fake_session(monkeypatch, spec=spec, record=writes)
    _gh_absent(monkeypatch)
    r = runner.invoke(sdlc, ["issue", "resolve", "i-007-x", "--allow-no-produces"], obj=obj)
    assert r.exit_code == 0, r.output  # fail-SOFT: local resolve always lands
    assert "NÃO foi fechada no GitHub" in r.output
    assert "RESOLVED" in r.output
    assert writes and writes[0][1]["spec"]["status"] == "resolved"


def test_resolve_without_provenance_never_touches_gh(runner, monkeypatch):
    writes: list = []
    obj = _fake_session(monkeypatch, record=writes)  # no github_number

    def _boom(*a, **kw):
        raise AssertionError("gh must not be called without github_number")

    monkeypatch.setattr(gb.subprocess, "run", _boom)
    r = runner.invoke(sdlc, ["issue", "resolve", "i-007-x", "--allow-no-produces"], obj=obj)
    assert r.exit_code == 0, r.output
    assert "RESOLVED" in r.output
