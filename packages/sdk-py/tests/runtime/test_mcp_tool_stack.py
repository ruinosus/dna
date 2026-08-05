"""`mcp_tool_stack` — the reusable (middleware, allowed_tools) seam factored
out of `LangChainRuntime.build` so a delegation target's isolated sub-run
(`dna.runtime.builder`'s `run_local`, A.1) resolves its OWN tools through the
exact same discover-then-allowlist mechanism the mounted agent uses, instead
of a second, drifting reimplementation.

Reuses the `_FakeModelRequest`/`_FakeTool` doubles `test_mcp_tools_mw.py`
already established for driving `DnaMcpToolsMiddleware.awrap_model_call`.
"""
from __future__ import annotations

import asyncio

from dna.runtime.adapters.langchain_rt import mcp_tool_stack
from dna.runtime.middleware.allowlist import DnaAllowlistMiddleware
from dna.runtime.middleware.mcp_tools_mw import DnaMcpToolsMiddleware


class _FakeTool:
    def __init__(self, name):
        self.name = name


class _FakeModelRequest:
    def __init__(self, tools=None):
        self.tools = list(tools) if tools is not None else []

    def override(self, **overrides):
        return _FakeModelRequest(tools=overrides.get("tools", self.tools))


class _EmitMcpServerLike:
    """A minimal stand-in for `dna.emit.EmitMcpServer` — only the attribute
    `mcp_tool_stack`/`DnaMcpToolsMiddleware` actually read."""

    def __init__(self, url: str, allowed_tools: list[str]):
        self.url = url
        self.allowed_tools = list(allowed_tools)


def test_no_mcp_servers_yields_no_middleware_and_an_empty_allowlist():
    middleware, allowed = mcp_tool_stack([], mcp_auth=lambda: {})
    assert middleware == []
    assert allowed == frozenset()


def test_the_middleware_pair_is_mcp_discovery_then_allowlist_in_that_order():
    servers = [_EmitMcpServerLike("https://mcp.example/mcp", ["list_kinds"])]
    middleware, allowed = mcp_tool_stack(servers, mcp_auth=lambda: {})
    assert allowed == frozenset({"list_kinds"})
    assert len(middleware) == 2
    assert isinstance(middleware[0], DnaMcpToolsMiddleware)
    assert isinstance(middleware[1], DnaAllowlistMiddleware)


def test_mcp_auth_is_reused_verbatim_not_wrapped_or_cloned():
    """Property: no new credential is fabricated for the sub-run — the exact
    same per-request hook object is threaded through to DnaMcpToolsMiddleware."""
    sentinel_auth = lambda: {}  # noqa: E731 — identity, not behavior, is what's asserted
    servers = [_EmitMcpServerLike("https://mcp.example/mcp", [])]
    middleware, _allowed = mcp_tool_stack(servers, mcp_auth=sentinel_auth)
    assert middleware[0]._mcp_auth is sentinel_auth


def test_discovery_then_allowlist_end_to_end_filters_to_the_declared_subset(monkeypatch):
    """The property that matters for A.1: a target's OWN allowed_tools is
    what a sub-run's tool surface is fail-closed to — driven exactly as
    `create_agent`'s model-call pipeline would drive it."""

    async def fake_load_mcp_tools(mcp_url, auth):
        return [_FakeTool("list_kinds"), _FakeTool("author_kind"), _FakeTool("secret_tool")]

    monkeypatch.setattr(
        "dna.runtime.middleware.mcp_tools_mw.load_mcp_tools", fake_load_mcp_tools
    )

    servers = [
        _EmitMcpServerLike("https://mcp.example/mcp", ["list_kinds", "author_kind"])
    ]
    middleware, allowed = mcp_tool_stack(servers, mcp_auth=lambda: {})
    assert allowed == frozenset({"list_kinds", "author_kind"})

    async def terminal(request):
        return [t.name for t in (request.tools or [])]

    async def drive():
        mcp_mw, allowlist_mw = middleware
        return await mcp_mw.awrap_model_call(
            _FakeModelRequest(),
            lambda req: allowlist_mw.awrap_model_call(req, terminal),
        )

    names = asyncio.run(drive())
    assert set(names) == {"list_kinds", "author_kind"}
    assert "secret_tool" not in names


def test_extra_allowed_widens_the_filter_without_touching_mcp_servers_allowlist():
    """Used by `LangChainRuntime.build` to fold in HITL-confirm tool names
    from the host's own `extra_tools` — a concern the delegation sub-run does
    NOT have (it passes no `extra_allowed`), kept here so the parameter's
    contract stays pinned."""
    servers = [_EmitMcpServerLike("https://mcp.example/mcp", ["list_kinds"])]
    _middleware, allowed = mcp_tool_stack(
        servers, mcp_auth=lambda: {}, extra_allowed=frozenset({"host_tool"})
    )
    assert allowed == frozenset({"list_kinds", "host_tool"})


def test_rationale_tools_is_threaded_to_the_discovery_middleware_and_defaults_empty():
    """`LangChainRuntime.build` passes the HITL-gated MCP tool names so their
    model-facing schemas gain the optional `rationale` arg; the delegation
    sub-run (`run_local`) passes none — its isolated run has no human in the
    loop, so the default MUST stay empty (wire unchanged)."""
    servers = [_EmitMcpServerLike("https://mcp.example/mcp", ["remember"])]

    middleware, _allowed = mcp_tool_stack(
        servers, mcp_auth=lambda: {}, rationale_tools=frozenset({"remember"})
    )
    assert middleware[0]._rationale_tools == frozenset({"remember"})

    default_middleware, _ = mcp_tool_stack(servers, mcp_auth=lambda: {})
    assert default_middleware[0]._rationale_tools == frozenset()
