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
        # O stack de middleware é quem decide o que PARA para aprovação. Sem
        # capturá-lo, um teste de portão humano só consegue afirmar que a tool
        # existe — que é justamente a metade que nunca esteve quebrada.
        captured["middleware"] = list(kwargs.get("middleware") or [])
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


async def _tool_names_after_the_chain(middleware, already_registered=()) -> set[str]:
    """`already_registered` are the tools `create_agent(tools=…)` put on the
    agent — in a real run the model request ALREADY carries them when the
    middleware chain sees it. Starting the double empty would measure only the
    MCP-injected half and quietly prove nothing about the host's tools."""
    mcp_mw, allowlist_mw = middleware

    async def terminal(request):
        return [t.name for t in (request.tools or [])]

    names = await mcp_mw.awrap_model_call(
        _FakeSubModelRequest(tools=list(already_registered)),
        lambda req: allowlist_mw.awrap_model_call(req, terminal),
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


# ── the sub-run gets the HOST's tools and middleware ───────────────────────
# The half the tests above cannot see: in the fixture `update_document_draft`
# is an MCP tool, so the target's own federation serves it. In a real host it
# is a LOCAL tool the host registers through `hooks.extensions["tools"]` —
# and until this change the sub-run got NONE of those, nor any host
# middleware. An agent whose whole job runs on a host tool therefore reached
# the model without it and narrated the work instead of doing it; and every
# host policy expressed as middleware (auth-graceful, attachment extraction,
# post-tool projections) silently did not apply on the delegated path.


class _FakeHostTool:
    def __init__(self, name):
        self.name = name


class _FakeHostMiddleware:
    """Stands in for a host middleware. Only identity is asserted — what it
    does is the host's business, that it RUNS is the SDK's."""


def _capture_run_local_build(monkeypatch):
    """Like `_capture_run_local_middleware`, but keeps `tools=` too — the host
    tools never appear in the middleware chain, they are registered
    statically."""
    captured = {}

    def fake_create_agent(model, tools=None, middleware=None, **kwargs):
        captured["tools"] = list(tools or [])
        captured["middleware"] = list(middleware or [])
        return _FakeSubAgentGraph()

    monkeypatch.setattr("langchain.agents.create_agent", fake_create_agent)
    return captured


def _run_local_with(tmp_path, monkeypatch, *, tools=None, middleware=None, target="conv"):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    _stub_federation_tools(monkeypatch)
    captured = _capture_run_local_build(monkeypatch)
    mi = _mi(tmp_path)
    hooks = RuntimeHooks(
        mcp_auth=lambda: {},
        compose=_compose,
        extensions={"tools": tools or [], "middleware": middleware or []},
    )
    run_local = _make_run_local(mi, hooks)
    asyncio.run(run_local(target, "converta isto"))
    return captured, hooks


def test_a_host_tool_reaches_the_sub_run(tmp_path, monkeypatch):
    """The defect this change exists to fix: a delegate whose job runs on a
    host tool used to reach the model without it. No error — the model simply
    could not do the work, and said it had."""
    tool = _FakeHostTool("update_document_draft_local")
    captured, _ = _run_local_with(tmp_path, monkeypatch, tools=[tool])
    assert tool in captured["tools"], "the sub-agent was built without the host's tools"


def test_host_middleware_reaches_the_sub_run(tmp_path, monkeypatch):
    """A sub-run outside host policy is not isolation — it is a hole in policy
    that only opens on the delegated path."""
    mw = _FakeHostMiddleware()
    captured, _ = _run_local_with(tmp_path, monkeypatch, middleware=[mw])
    assert mw in captured["middleware"], "host middleware did not apply to the sub-run"


def test_host_middleware_runs_AFTER_the_dna_disciplines(tmp_path, monkeypatch):
    """Same order the LangChain adapter builds for the mounted agent: the DNA
    middlewares first, host extras last. Order is load-bearing there (the MCP
    schema injection must precede the allowlist filter), and a sub-run that
    ordered them differently would be a second, divergent pipeline."""
    mw = _FakeHostMiddleware()
    captured, _ = _run_local_with(tmp_path, monkeypatch, middleware=[mw])
    assert captured["middleware"][-1] is mw
    assert len(captured["middleware"]) > 1, "the DNA disciplines vanished"


def test_a_host_tool_is_NOT_filtered_out_by_the_targets_mcp_allowlist(
    tmp_path, monkeypatch
):
    """`conv` restricts its MCP allowlist to two of the federation's four. A
    host tool is not an MCP tool and must survive that filter — otherwise
    registering it would be pointless, which is exactly what happens without
    `extra_allowed`. This is the same treatment the adapter already gives the
    mounted agent's host tools."""
    tool = _FakeHostTool("host_only_tool")
    captured, _ = _run_local_with(tmp_path, monkeypatch, tools=[tool])
    names = asyncio.run(
        _tool_names_after_the_chain(captured["middleware"][:2], already_registered=[tool])
    )
    assert "host_only_tool" in names
    # and the target's OWN restriction is untouched by the addition
    assert "list_my_kinds" not in names


def test_the_sub_run_can_NOT_delegate_onward(tmp_path, monkeypatch):
    """Load-bearing, and invisible in the code: `_make_run_local` captures
    `hooks` BEFORE `build_runtime` appends `delegate_to` to a REPLACED hooks
    object, so the sub-agent never sees the tool. A delegation cycle would
    recurse until the stack died — and now that host tools DO cross into the
    sub-run, nothing but this capture order stops `delegate_to` from crossing
    with them."""
    from dataclasses import replace as _replace

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    _stub_federation_tools(monkeypatch)
    captured = _capture_run_local_build(monkeypatch)
    mi = _mi(tmp_path)
    hooks = RuntimeHooks(mcp_auth=lambda: {}, compose=_compose, extensions={"tools": []})
    run_local = _make_run_local(mi, hooks)

    # Exactly what build_runtime does after building run_local.
    delegate_to = _FakeHostTool("delegate_to")
    _replace(hooks, extensions={"tools": [delegate_to]})

    asyncio.run(run_local("conv", "x"))
    assert delegate_to not in captured["tools"]
    assert "delegate_to" not in [getattr(t, "name", None) for t in captured["tools"]]


# ── registrar uma tool local ≠ exigir aprovação dela ────────────────────────


def _hitl_gated(captured) -> set[str]:
    """Os nomes que o `HumanInTheLoopMiddleware` vai interromper."""
    for m in captured["middleware"]:
        gate = getattr(m, "interrupt_on", None)
        if gate is not None:
            return set(gate)
    raise AssertionError("nenhum HumanInTheLoopMiddleware no stack")


def test_uma_tool_local_de_LEITURA_nao_pede_aprovacao(tmp_path, monkeypatch):
    """⚠️ MEDIDO no dna-cloud em 02/08/2026, e o sintoma era na cara do usuário.

    `extra_confirm` era "todo nome de tool local", e alimentava DUAS coisas: a
    allowlist e o portão humano. Enquanto as locais eram só escritas (os drafts
    de memória e documento) as duas listas coincidiam — e a coincidência virou
    regra sem ninguém decidir isso.

    Aí chegou `analyze_spreadsheet`, que só LÊ a planilha que o usuário acabou de
    anexar. O turno parava, e quem perguntou "quantas linhas tem?" recebia um
    cartão de aprovação.
    """
    class _Leitura:
        name = "le_planilha"
        extras = {"requires_confirmation": False}

    _app, captured, _hooks = _build(
        "solo-copilot", tmp_path, monkeypatch, extra_tools=[_Leitura()]
    )
    assert "le_planilha" in _tool_names(captured["tools"]), "sumiu do agente"
    assert "le_planilha" not in _hitl_gated(captured), "leitura pedindo aprovação"


def test_uma_tool_local_SEM_declaracao_continua_gated(tmp_path, monkeypatch):
    """O default é FECHADO, e de propósito.

    Default aberto desgataria uma escrita futura em silêncio — o erro caro do
    outro lado, e o único dos dois que ninguém percebe até ter acontecido.
    """
    class _Sem:
        name = "escreve_algo"

    _app, captured, _hooks = _build(
        "solo-copilot", tmp_path, monkeypatch, extra_tools=[_Sem()]
    )
    assert "escreve_algo" in _hitl_gated(captured)


def test_a_tool_de_leitura_continua_VISIVEL_para_a_allowlist(tmp_path, monkeypatch):
    """A separação das duas listas não pode custar a primeira pergunta.

    A allowlist filtra o que ela não conhece: uma tool local ausente dali é
    descartada antes de o modelo poder chamá-la. Desgatear tinha de mudar SÓ o
    portão humano.
    """
    class _Leitura:
        name = "le_planilha"
        extras = {"requires_confirmation": False}

    _app, captured, _hooks = _build(
        "solo-copilot", tmp_path, monkeypatch, extra_tools=[_Leitura()]
    )
    for m in captured["middleware"]:
        allowed = getattr(m, "allowed", None) or getattr(m, "_allowed", None)
        if allowed and "le_planilha" in allowed:
            return
    raise AssertionError("a allowlist não enxerga a tool de leitura")
