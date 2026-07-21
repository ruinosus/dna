"""Tests for the SDLC work-item + artifact CLI groups.

Covers the 6 Kinds wired to the CLI for parity (schemas + Studio screens
existed, CLI didn't): Spike, Bug, Task, ADR, Spec, Plan — plus the new
`issue start` transition and `doc apply` multi-document support.

Approach: REAL creates against an in-memory store. The fake session is
INJECTED through the click context (``obj={SESSION_PROVIDER_KEY: fake}``,
f-cli-session-injection) — no reaching inside command modules. The fake's
``kernel.write_document`` records into a dict and its ``get_doc`` reads it
back. The write path (spec assembly, timeline stamping, _build_raw) runs
for real — only the HTTP boundary is faked. Each `create` is asserted to
exit 0 + emit its success message, and each Kind's required-option
enforcement is asserted to fire (missing required → exit != 0).
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from click.testing import CliRunner

from dna_cli._ctx import SESSION_PROVIDER_KEY
from dna_cli.sdlc_cmd import sdlc


@pytest.fixture
def runner(session_obj):
    """CliRunner whose invokes carry the injected session by default.

    An explicit ``obj=`` at a call site wins (setdefault) — used by tests
    that build their own fake.
    """
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
        self.name = raw.get("metadata", {}).get("name")
        self.kind = raw.get("kind")
        self.spec = raw.get("spec") or {}


class _FakeKernel:
    """Records write_document calls into the shared store."""

    def __init__(self, store: dict):
        self._store = store
        # doc_cmd._stamp_created_at_if_in_schema walks kernel._kinds; empty
        # dict makes it a no-op (returns early), which is fine for the test.
        self._kinds: dict = {}

    def with_tenant(self, tenant):
        return self

    async def write_document(self, scope, kind, name, raw, **_):
        self._store[(scope, kind, name)] = raw
        return "v1"


class _FakeSession:
    """Drop-in for ClientSession backed by an in-memory dict store."""

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

        # Use a throwaway loop and tear it down cleanly so we don't pollute
        # the process-global current-loop (other test files' fakes call
        # asyncio.get_event_loop() and break on a leaked/half-open loop).
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
    """The ctx.obj to inject: a session factory over the backing store."""

    @contextmanager
    def _fake(scope=None, *, tenant=None, timeout=30.0):
        yield _FakeSession(store, scope or "dna-development")

    return {SESSION_PROVIDER_KEY: _fake}


# ---------------------------------------------------------------------------
# Real create — one per Kind. Asserts exit 0 + success message + persisted doc.
# ---------------------------------------------------------------------------

CREATE_CASES = [
    (
        "spike",
        ["spike", "create", "sp-cache-strategy", "--question", "Redis or in-proc?"],
        "CREATED Spike/sp-cache-strategy",
        ("dna-development", "Spike", "sp-cache-strategy"),
    ),
    (
        "bug",
        ["bug", "create", "b-login-500", "--desc", "Login returns 500", "--severity", "high"],
        "CREATED Bug/b-login-500",
        ("dna-development", "Bug", "b-login-500"),
    ),
    (
        "task",
        ["task", "create", "t-add-index", "--desc", "Add DB index"],
        "CREATED Task/t-add-index",
        ("dna-development", "Task", "t-add-index"),
    ),
    (
        "adr",
        [
            "adr", "create", "adr-use-postgres",
            "--title", "Use Postgres", "--context", "Need durable store",
            "--decision", "We will use Postgres",
        ],
        "CREATED ADR/adr-use-postgres",
        ("dna-development", "ADR", "adr-use-postgres"),
    ),
    (
        "spec",
        ["spec", "create", "spec-auth-v1", "--title", "Auth v1"],
        "CREATED Spec/spec-auth-v1",
        ("dna-development", "Spec", "spec-auth-v1"),
    ),
    (
        "plan",
        ["plan", "create", "plan-auth-v1", "--title", "Auth v1 plan"],
        "CREATED Plan/plan-auth-v1",
        ("dna-development", "Plan", "plan-auth-v1"),
    ),
]


@pytest.mark.parametrize("label,args,expect_msg,key", CREATE_CASES, ids=[c[0] for c in CREATE_CASES])
def test_create_writes_doc(runner, store, label, args, expect_msg, key):
    result = runner.invoke(sdlc, args)
    assert result.exit_code == 0, f"{label}: exit {result.exit_code}\n{result.output}"
    assert expect_msg in result.output, f"{label}: missing message\n{result.output}"
    # Real write landed in the store with the expected (kind, name).
    assert key in store, f"{label}: doc not persisted; store keys: {list(store)}"
    raw = store[key]
    spec = raw["spec"]
    # create stamps created_at/updated_at + a first timeline event.
    assert spec.get("created_at")
    assert spec.get("updated_at")
    assert spec.get("timeline"), f"{label}: no timeline stamped"
    assert spec["timeline"][0]["to"] == spec["status"]


# ---------------------------------------------------------------------------
# Required-option enforcement — each create has at least one required opt.
# ---------------------------------------------------------------------------

MISSING_REQUIRED_CASES = [
    ("spike", ["spike", "create", "x"]),            # missing --question
    ("bug", ["bug", "create", "x"]),                # missing --desc
    ("task", ["task", "create", "x"]),              # missing --desc
    ("adr", ["adr", "create", "x", "--title", "T"]),  # missing --context/--decision
    ("spec", ["spec", "create", "x"]),              # missing --title
    ("plan", ["plan", "create", "x"]),              # missing --title
]


@pytest.mark.parametrize("label,args", MISSING_REQUIRED_CASES, ids=[c[0] for c in MISSING_REQUIRED_CASES])
def test_create_required_option_enforced(runner, label, args):
    result = runner.invoke(sdlc, args)
    assert result.exit_code != 0, f"{label}: expected non-zero, got 0\n{result.output}"


# ---------------------------------------------------------------------------
# --help works for every group's create (registration smoke).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("group", ["spike", "bug", "task", "adr", "spec", "plan", "epic"])
def test_create_help(runner, group):
    result = runner.invoke(sdlc, [group, "create", "--help"])
    assert result.exit_code == 0, f"{group}: help failed\n{result.output}"
    assert "Usage:" in result.output


# ---------------------------------------------------------------------------
# epic create (s-dx-epic-create) — closes the last CRUD gap in the SDLC CLI.
# ---------------------------------------------------------------------------

def test_epic_create_writes_doc_with_timeline(runner, store):
    result = runner.invoke(
        sdlc,
        [
            "epic", "create", "e-demo",
            "--title", "Demo epic", "--desc", "A demo epic",
            "--status", "in-progress", "--priority", "high",
            "--labels", "dx,sdk",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "CREATED Epic/e-demo (status: in-progress)" in result.output
    raw = store[("dna-development", "Epic", "e-demo")]
    assert raw["kind"] == "Epic"
    spec = raw["spec"]
    assert spec["title"] == "Demo epic"
    assert spec["status"] == "in-progress"
    assert spec["priority"] == "high"
    assert spec["labels"] == ["dx", "sdk"]
    assert spec["reporter"] == "claude-code"  # default
    assert spec.get("created_at") and spec.get("updated_at")
    # First timeline event = the create itself (parity with feature/story).
    assert spec["timeline"][0]["type"] == "status_change"
    assert spec["timeline"][0]["to"] == "in-progress"


def test_epic_create_default_status_is_planning(runner, store):
    result = runner.invoke(
        sdlc, ["epic", "create", "e-p", "--title", "T", "--desc", "D"],
    )
    assert result.exit_code == 0, result.output
    assert store[("dna-development", "Epic", "e-p")]["spec"]["status"] == "planning"


def test_epic_create_show_finds_it(runner, store):
    runner.invoke(sdlc, ["epic", "create", "e-found", "--title", "T", "--desc", "D"])
    result = runner.invoke(sdlc, ["epic", "show", "e-found"])
    assert result.exit_code == 0, result.output
    assert "Epic: e-found" in result.output


@pytest.mark.parametrize("args", [
    ["epic", "create", "e-x"],                    # missing --title + --desc
    ["epic", "create", "e-x", "--title", "T"],    # missing --desc
])
def test_epic_create_required_options_enforced(runner, args):
    result = runner.invoke(sdlc, args)
    assert result.exit_code != 0, result.output


# ---------------------------------------------------------------------------
# Transitions read-modify-write through the store.
# ---------------------------------------------------------------------------

def test_spike_answer_transition(runner, store):
    runner.invoke(sdlc, ["spike", "create", "sp-x", "--question", "Q?"])
    result = runner.invoke(
        sdlc, ["spike", "answer", "sp-x", "--findings", "Use Redis", "--recommendation", "Ship it"],
    )
    assert result.exit_code == 0, result.output
    assert "UPDATED Spike/sp-x → answered" in result.output
    spec = store[("dna-development", "Spike", "sp-x")]["spec"]
    assert spec["status"] == "answered"
    assert spec["findings"] == "Use Redis"
    assert spec["completed_at"]


def test_bug_resolve_transition(runner, store):
    runner.invoke(sdlc, ["bug", "create", "b-x", "--desc", "broken"])
    result = runner.invoke(sdlc, ["bug", "resolve", "b-x", "--resolution", "patched"])
    assert result.exit_code == 0, result.output
    assert "UPDATED Bug/b-x → resolved" in result.output
    spec = store[("dna-development", "Bug", "b-x")]["spec"]
    assert spec["status"] == "resolved"
    assert spec["closed_at"]


def test_task_block_transition(runner, store):
    runner.invoke(sdlc, ["task", "create", "t-x", "--desc", "work"])
    result = runner.invoke(sdlc, ["task", "block", "t-x", "--reason", "waiting on infra"])
    assert result.exit_code == 0, result.output
    spec = store[("dna-development", "Task", "t-x")]["spec"]
    assert spec["status"] == "blocked"
    assert spec["blocked_reason"] == "waiting on infra"


def test_adr_supersede_transition(runner, store):
    runner.invoke(
        sdlc,
        ["adr", "create", "adr-x", "--title", "T", "--context", "C", "--decision", "D"],
    )
    result = runner.invoke(sdlc, ["adr", "supersede", "adr-x", "--by", "adr-y"])
    assert result.exit_code == 0, result.output
    spec = store[("dna-development", "ADR", "adr-x")]["spec"]
    assert spec["status"] == "superseded"
    assert spec["superseded_by"] == "adr-y"


def test_plan_accept_transition(runner, store):
    runner.invoke(sdlc, ["plan", "create", "p-x", "--title", "P"])
    result = runner.invoke(sdlc, ["plan", "accept", "p-x"])
    assert result.exit_code == 0, result.output
    spec = store[("dna-development", "Plan", "p-x")]["spec"]
    assert spec["status"] == "accepted"
    assert spec["accepted_at"]


def test_transition_missing_doc_fails(runner, store):
    result = runner.invoke(sdlc, ["spike", "start", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# Issue start (Tier 3).
# ---------------------------------------------------------------------------

def test_issue_start_transition(runner, store):
    """issue start mutates Issue → in-progress via the same store pattern."""
    backing = store
    # Seed an Issue directly.
    backing[("dna-development", "Issue", "i-001-x")] = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
        "kind": "Issue",
        "metadata": {"name": "i-001-x"},
        "spec": {"status": "open", "type": "bug", "severity": "low"},
    }
    result = runner.invoke(sdlc, ["issue", "start", "i-001-x"])
    assert result.exit_code == 0, result.output
    assert "STARTED i-001-x" in result.output
    spec = backing[("dna-development", "Issue", "i-001-x")]["spec"]
    assert spec["status"] == "in-progress"


# ---------------------------------------------------------------------------
# `dna doc apply` multi-document YAML (Tier 3).
# ---------------------------------------------------------------------------

def _doc_fake_session(store: dict, scope: str):
    """Mirror of _FakeSession but matching doc_cmd's dna_session surface."""
    return _FakeSession(store, scope)


def test_doc_apply_multi_document(runner, monkeypatch, tmp_path):
    from dna_cli import doc_cmd
    from dna_cli.doc_cmd import doc

    backing: dict = {}

    @contextmanager
    def _fake_dna_session(scope=None):
        yield _FakeSession(backing, scope or "dna-development")

    monkeypatch.setattr(doc_cmd, "dna_session", _fake_dna_session)

    f = tmp_path / "multi.yaml"
    f.write_text(
        "apiVersion: github.com/ruinosus/dna/sdlc/v1\n"
        "kind: Spike\n"
        "metadata:\n  name: sp-a\n"
        "spec:\n  title: A\n  question_to_answer: Q?\n  status: proposed\n"
        "---\n"
        "apiVersion: github.com/ruinosus/dna/sdlc/v1\n"
        "kind: Task\n"
        "metadata:\n  name: t-a\n"
        "spec:\n  title: T\n  status: todo\n",
        encoding="utf-8",
    )
    result = runner.invoke(doc, ["apply", str(f), "--scope", "dna-development"])
    assert result.exit_code == 0, result.output
    assert ("dna-development", "Spike", "sp-a") in backing
    assert ("dna-development", "Task", "t-a") in backing
    # Both reported as CREATED.
    assert result.output.count("CREATED") == 2


def test_doc_apply_single_document_unchanged_behavior(runner, monkeypatch, tmp_path):
    from dna_cli import doc_cmd
    from dna_cli.doc_cmd import doc

    backing: dict = {}

    @contextmanager
    def _fake_dna_session(scope=None):
        yield _FakeSession(backing, scope or "dna-development")

    monkeypatch.setattr(doc_cmd, "dna_session", _fake_dna_session)

    f = tmp_path / "single.yaml"
    f.write_text(
        "apiVersion: github.com/ruinosus/dna/sdlc/v1\n"
        "kind: Task\n"
        "metadata:\n  name: t-solo\n"
        "spec:\n  title: T\n  status: todo\n",
        encoding="utf-8",
    )
    result = runner.invoke(doc, ["apply", str(f), "--scope", "dna-development"])
    assert result.exit_code == 0, result.output
    assert ("dna-development", "Task", "t-solo") in backing


def test_doc_apply_multi_document_missing_name_fails(runner, monkeypatch, tmp_path):
    from dna_cli import doc_cmd
    from dna_cli.doc_cmd import doc

    backing: dict = {}

    @contextmanager
    def _fake_dna_session(scope=None):
        yield _FakeSession(backing, scope or "dna-development")

    monkeypatch.setattr(doc_cmd, "dna_session", _fake_dna_session)

    f = tmp_path / "bad.yaml"
    f.write_text(
        "apiVersion: github.com/ruinosus/dna/sdlc/v1\n"
        "kind: Task\n"
        "metadata:\n  name: t-ok\n"
        "spec:\n  title: T\n  status: todo\n"
        "---\n"
        "apiVersion: github.com/ruinosus/dna/sdlc/v1\n"
        "kind: Task\n"
        "metadata: {}\n"
        "spec:\n  title: T2\n  status: todo\n",
        encoding="utf-8",
    )
    result = runner.invoke(doc, ["apply", str(f), "--scope", "dna-development"])
    assert result.exit_code != 0
    # Error names the offending document index.
    assert "document #1" in result.output
