"""A.1 — who wires `run_local` into `delegate_to` (the fiação no runtime).

`dna.runtime.builder.build_runtime` already reads the mounted agent's def.
This file proves the CENTRAL property the plan (A.1) names: an agent that
declares NO `team_members` never receives `delegate_to` (not even in its
tools list); one that DOES receive it — derived from the declaration itself,
never a hand-kept list of agent names.

Wiring decision (see `dna/runtime/builder.py`'s module docstring for the
full reasoning): the tool is assembled in `build_runtime` (which alone has
`mi`, needed both to read `team_members` and to let `run_local` compose
another named agent) and handed to the LangChain adapter through
`hooks.extensions["tools"]` — the SAME escape hatch the adapter already
merges into `create_agent(tools=...)`. So this test intercepts
`langchain.agents.create_agent` (patched at ITS defining module, since the
adapter imports it lazily at call time) to see exactly what `tools=` it was
built with, without needing a real model/API key beyond a dummy one
`init_chat_model` accepts at construction time.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from dna.runtime.builder import _make_run_local, build_runtime
from dna.runtime.config import build_env_mi
from dna.runtime.port import RuntimeHooks

FIXTURE_SRC = Path(__file__).parent / "runtime" / "fixtures" / "dna" / "delegation-dev"


def _copy_fixture(tmp_path: Path) -> Path:
    dest = tmp_path / ".dna" / "delegation-dev"
    dest.mkdir(parents=True)
    # No `tools/` in this fixture (no agent declares `spec.tools`) — an empty
    # dir wouldn't survive git tracking anyway.
    for subdir in ("copilots", "agents", "federations"):
        shutil.copytree(FIXTURE_SRC / subdir, dest / subdir)
    return tmp_path / ".dna"


async def _compose(_headers):
    return "PROMPT"


def _stub_no_mcp_discovery(monkeypatch):
    async def fake_load_mcp_tools(mcp_url, auth):
        return []

    monkeypatch.setattr(
        "dna.runtime.middleware.mcp_tools_mw.load_mcp_tools", fake_load_mcp_tools
    )


def _stub_no_persistence_resolution(monkeypatch):
    async def fake_resolve_persistence(_persistence):
        return None, None

    monkeypatch.setattr(
        "dna.runtime.persistence.resolve_persistence", fake_resolve_persistence
    )


class _FakeGraph:
    def ainvoke(self, *a, **kw):  # pragma: no cover — never called in this test
        raise AssertionError("the compiled graph is never invoked by this test")

    def invoke(self, *a, **kw):  # pragma: no cover
        raise AssertionError("the compiled graph is never invoked by this test")


def _stub_create_agent(monkeypatch):
    """Capture the `tools=` kwarg `LangChainRuntime.build` calls
    `create_agent(...)` with — patched on `langchain.agents` (its defining
    module), because the adapter does `from langchain.agents import
    create_agent` INSIDE `build()`, so a fresh attribute lookup happens on
    every call and picks up this patch."""
    captured = {}

    def fake_create_agent(model, tools=None, **kwargs):
        captured["tools"] = list(tools or [])
        return _FakeGraph()

    monkeypatch.setattr("langchain.agents.create_agent", fake_create_agent)
    return captured


def _build(copilot: str, tmp_path, monkeypatch, extra_tools=None):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    _stub_no_mcp_discovery(monkeypatch)
    _stub_no_persistence_resolution(monkeypatch)
    captured = _stub_create_agent(monkeypatch)

    base_dir = _copy_fixture(tmp_path)
    extensions = {"tools": extra_tools} if extra_tools is not None else None
    hooks = RuntimeHooks(mcp_auth=lambda: {}, compose=_compose, extensions=extensions)

    app = asyncio.run(
        build_runtime(copilot, base_dir=str(base_dir), scope="delegation-dev", hooks=hooks)
    )
    return app, captured, hooks


def _tool_names(tools) -> set[str]:
    return {getattr(t, "name", None) for t in tools}


# ── the central property ────────────────────────────────────────────────────


def test_an_agent_without_team_members_does_not_receive_delegate_to(tmp_path, monkeypatch):
    _app, captured, _hooks = _build("solo-copilot", tmp_path, monkeypatch)
    assert "delegate_to" not in _tool_names(captured["tools"])


def test_an_agent_with_team_members_receives_delegate_to(tmp_path, monkeypatch):
    _app, captured, _hooks = _build("super-copilot", tmp_path, monkeypatch)
    names = _tool_names(captured["tools"])
    assert "delegate_to" in names


def test_the_delegate_to_tool_lists_the_declared_target_by_name(tmp_path, monkeypatch):
    """Not just presence — the tool actually reflects `super-agent`'s roster
    (`conv`, declared via team_members + the target's own
    delegation_target_for.agents), proving it was built from the real
    declaration and not a stub."""
    _app, captured, _hooks = _build("super-copilot", tmp_path, monkeypatch)
    tool = next(t for t in captured["tools"] if getattr(t, "name", None) == "delegate_to")
    assert "conv" in tool.description


# ── the tool arrives ALONGSIDE the host's own extra tools, not instead of ──


def test_host_supplied_extra_tools_are_preserved_alongside_delegate_to(tmp_path, monkeypatch):
    class _HostTool:
        name = "host_tool"

    host_tool = _HostTool()
    _app, captured, _hooks = _build(
        "super-copilot", tmp_path, monkeypatch, extra_tools=[host_tool]
    )
    names = _tool_names(captured["tools"])
    assert "delegate_to" in names
    assert "host_tool" in names


def test_host_supplied_extra_tools_survive_unchanged_when_no_team_members(tmp_path, monkeypatch):
    class _HostTool:
        name = "host_tool"

    host_tool = _HostTool()
    _app, captured, _hooks = _build(
        "solo-copilot", tmp_path, monkeypatch, extra_tools=[host_tool]
    )
    names = _tool_names(captured["tools"])
    assert names == {"host_tool"}


# ── build_runtime never mutates the CALLER's hooks object in place ─────────


def test_build_runtime_does_not_mutate_the_callers_hooks_extensions_dict(tmp_path, monkeypatch):
    extensions = {"tools": []}
    hooks = RuntimeHooks(mcp_auth=lambda: {}, compose=_compose, extensions=extensions)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    _stub_no_mcp_discovery(monkeypatch)
    _stub_no_persistence_resolution(monkeypatch)
    _stub_create_agent(monkeypatch)

    base_dir = _copy_fixture(tmp_path)
    asyncio.run(
        build_runtime("super-copilot", base_dir=str(base_dir), scope="delegation-dev", hooks=hooks)
    )
    # The caller's own dict/hooks are untouched — build_runtime built a NEW
    # extensions dict (and a NEW RuntimeHooks via dataclasses.replace) rather
    # than appending into the caller's list in place.
    assert extensions == {"tools": []}
    assert hooks.extensions is extensions


# ── the sub-run gets the TARGET's own tools — restated after coordinator ────
# review: `run_local` originally built the sub-agent with `tools=[]`, which
# would make delegation mechanically real but practically useless (a
# delegate that can't read Kinds or write a draft can only talk). These
# tests drive `_make_run_local` directly against the fixture's `conv`
# (RESTRICTED to a subset of the federation's allowed_tools) and `wide-conv`
# (no override — inherits the federation's full list), proving both halves:
# a target's declared tools actually reach its sub-run, AND a target's own
# restriction holds there too — a delegate reaches no more than it would
# reach mounted directly (delegation is not privilege escalation).


class _FakeSubTool:
    def __init__(self, name):
        self.name = name


class _FakeSubModelRequest:
    """Same double `tests/runtime/test_mcp_tools_mw.py` /
    `test_mcp_tool_stack.py` use to drive `DnaMcpToolsMiddleware`/
    `DnaAllowlistMiddleware` without a real LangGraph model call."""

    def __init__(self, tools=None):
        self.tools = list(tools) if tools is not None else []

    def override(self, **overrides):
        return _FakeSubModelRequest(tools=overrides.get("tools", self.tools))


def _stub_federation_tools(monkeypatch):
    """The fixture's `dna-mcp` federation declares
    `[list_kinds, list_my_kinds, author_kind, update_document_draft]` — stand
    in a fake MCP server that actually serves exactly those four, so the
    projected `allowed_tools` is what gets exercised, not a guess."""

    async def fake_load_mcp_tools(mcp_url, auth):
        return [
            _FakeSubTool(n)
            for n in ("list_kinds", "list_my_kinds", "author_kind", "update_document_draft")
        ]

    monkeypatch.setattr(
        "dna.runtime.middleware.mcp_tools_mw.load_mcp_tools", fake_load_mcp_tools
    )


class _FakeSubAgentGraph:
    """`run_local` still awaits `graph.ainvoke(...)` after `create_agent`
    returns — unlike `_FakeGraph` above (deliberately never-invoked, for the
    delegate_to-tool-presence tests), this one completes normally so
    `run_local` returns cleanly; these tests only inspect the `middleware=`
    `create_agent` was BUILT with, not `run_local`'s return value."""

    async def ainvoke(self, *_a, **_kw):
        from types import SimpleNamespace

        return {"messages": [SimpleNamespace(content="ok")]}


def _capture_run_local_middleware(monkeypatch):
    """`run_local` builds its sub-agent via `create_agent(..., middleware=…)`
    — capture that list so the test can drive it exactly as the model-call
    pipeline would, instead of only checking `tools=` (MCP tools are never in
    `tools=`; they're injected lazily by `DnaMcpToolsMiddleware`)."""
    captured = {}

    def fake_create_agent(model, tools=None, middleware=None, **kwargs):
        captured["middleware"] = list(middleware or [])
        return _FakeSubAgentGraph()

    monkeypatch.setattr("langchain.agents.create_agent", fake_create_agent)
    return captured


async def _tool_names_after_the_chain(middleware) -> set[str]:
    mcp_mw, allowlist_mw = middleware

    async def terminal(request):
        return [t.name for t in (request.tools or [])]

    names = await mcp_mw.awrap_model_call(
        _FakeSubModelRequest(), lambda req: allowlist_mw.awrap_model_call(req, terminal)
    )
    return set(names)


def _mi(tmp_path):
    base_dir = _copy_fixture(tmp_path)
    return asyncio.run(build_env_mi(base_dir=str(base_dir), scope="delegation-dev"))


def test_a_target_with_declared_tools_actually_reaches_them_in_the_sub_run(
    tmp_path, monkeypatch
):
    """Positive: `wide-conv` declares mcp_servers with NO allowed_tools
    override — it inherits the federation's full list, and that full list
    (not an empty `tools=[]`) is what its sub-run gets."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    _stub_federation_tools(monkeypatch)
    captured = _capture_run_local_middleware(monkeypatch)

    mi = _mi(tmp_path)
    hooks = RuntimeHooks(mcp_auth=lambda: {}, compose=_compose)
    run_local = _make_run_local(mi, hooks)

    asyncio.run(run_local("wide-conv", "faça qualquer coisa"))
    names = asyncio.run(_tool_names_after_the_chain(captured["middleware"]))
    assert names == {"list_kinds", "list_my_kinds", "author_kind", "update_document_draft"}


def test_a_targets_own_allowed_tools_restriction_holds_in_the_sub_run(tmp_path, monkeypatch):
    """Negative: `conv` restricts allowed_tools to a subset of what the
    federation serves — its sub-run must NOT reach the other two, even
    though the federation (and its sibling `wide-conv`) allow them."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    _stub_federation_tools(monkeypatch)
    captured = _capture_run_local_middleware(monkeypatch)

    mi = _mi(tmp_path)
    hooks = RuntimeHooks(mcp_auth=lambda: {}, compose=_compose)
    run_local = _make_run_local(mi, hooks)

    asyncio.run(run_local("conv", "converta isto"))
    names = asyncio.run(_tool_names_after_the_chain(captured["middleware"]))
    assert names == {"list_kinds", "author_kind"}
    assert "list_my_kinds" not in names
    assert "update_document_draft" not in names


def test_run_local_reuses_the_same_mcp_auth_hook_object_not_a_new_one(tmp_path, monkeypatch):
    """No fabricated/cached credential for the sub-run — the exact per-request
    hook the delegator's own request carries is what the target's
    DnaMcpToolsMiddleware gets, re-read at call time like any other MCP call."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    _stub_federation_tools(monkeypatch)
    captured = _capture_run_local_middleware(monkeypatch)

    mi = _mi(tmp_path)
    sentinel_auth = lambda: {}  # noqa: E731 — identity is what's asserted
    hooks = RuntimeHooks(mcp_auth=sentinel_auth, compose=_compose)
    run_local = _make_run_local(mi, hooks)

    asyncio.run(run_local("conv", "x"))
    mcp_mw = captured["middleware"][0]
    assert mcp_mw._mcp_auth is sentinel_auth
