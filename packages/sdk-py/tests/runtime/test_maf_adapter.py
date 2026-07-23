"""MafRuntime (target "maf") — the Microsoft Agent Framework / Foundry adapter.

No live network / no credential: `FoundryChatClient` and `DefaultAzureCredential`
are stubbed, and the MCP tool's connect/load are stubbed to RAISE so the lazy
invariant is proven (build must never dial). The real `MCPStreamableHTTPTool` is
kept (its construction genuinely doesn't dial) so the allowlist/HITL projections
are asserted against the actual mounted tool objects.
"""
import asyncio
import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI

from dna.emit import build_copilot_context
from dna.kernel import Kernel
from dna.runtime.adapters import maf_rt
from dna.runtime.adapters.maf_rt import MafRuntime
from dna.runtime.port import AGUIApp, RuntimeHooks

# Committed fixture (this repo), same one the LangChain adapter test uses.
FIXTURE_SRC = Path(__file__).parent / "fixtures" / "dna" / "dna-cloud-dev"


def _copy_fixture(tmp_path: Path) -> Path:
    dest = tmp_path / ".dna" / "dna-cloud-dev"
    dest.mkdir(parents=True)
    for subdir in ("copilots", "agents", "federations", "tools"):
        shutil.copytree(FIXTURE_SRC / subdir, dest / subdir)
    return tmp_path / ".dna"


def _build_ctx(tmp_path):
    base_dir = _copy_fixture(tmp_path)
    mi = Kernel.quick("dna-cloud-dev", base_dir=str(base_dir))
    return build_copilot_context(mi, "memory-copilot")


async def _compose(_headers):
    return "PROMPT"


# ── fakes: no Foundry client, no Azure credential, no MCP dial ──────────────


class _FakeAgent:
    """A duck agent that satisfies `SupportsAgentRun` (so MAF's AG-UI endpoint
    accepts it) and records the `as_agent` kwargs for assertion."""

    description = "fake"

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.name = kwargs.get("name", "agent")
        self.id = self.name

    async def run(self, *a, **k):  # pragma: no cover - never invoked
        ...

    def get_session(self, *a, **k):  # pragma: no cover
        ...

    def create_session(self, *a, **k):  # pragma: no cover
        ...


class _FakeFoundryClient:
    instances: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        _FakeFoundryClient.instances.append(self)

    def as_agent(self, **kwargs):
        return _FakeAgent(**kwargs)


def _stub_backend(monkeypatch):
    """Stub the Foundry client + Azure credential, and make the MCP tool's
    network entrypoints RAISE if touched at build (the lazy assertion)."""
    _FakeFoundryClient.instances = []
    monkeypatch.setattr(
        "agent_framework.foundry.FoundryChatClient", _FakeFoundryClient
    )
    monkeypatch.setattr(
        "azure.identity.DefaultAzureCredential", lambda *a, **k: object()
    )

    from agent_framework import MCPStreamableHTTPTool

    def _boom(self, *a, **k):
        raise AssertionError("MCP network dial at build time (not lazy!)")

    monkeypatch.setattr(MCPStreamableHTTPTool, "connect", _boom, raising=False)
    monkeypatch.setattr(MCPStreamableHTTPTool, "load_tools", _boom, raising=False)


def _mounted_tools(app):
    return app.agent.kwargs["tools"]


# ── tests ───────────────────────────────────────────────────────────────────


def test_build_returns_aguiapp_with_graph_none(tmp_path, monkeypatch):
    _stub_backend(monkeypatch)
    ctx = _build_ctx(tmp_path)
    hooks = RuntimeHooks(mcp_auth=lambda: {"Authorization": "Bearer x"}, compose=_compose)

    app = asyncio.run(MafRuntime().build(ctx, hooks))

    assert isinstance(app, AGUIApp)
    # MAF has no LangGraph state — rehydration handle is None (a follow-on).
    assert app.graph is None


def test_attach_registers_the_agui_route(tmp_path, monkeypatch):
    _stub_backend(monkeypatch)
    ctx = _build_ctx(tmp_path)
    hooks = RuntimeHooks(mcp_auth=lambda: {}, compose=_compose)
    app = asyncio.run(MafRuntime().build(ctx, hooks))

    fastapi_app = FastAPI()
    app.attach(fastapi_app, path="/agui")

    paths = {route.path for route in fastapi_app.routes}
    assert "/agui" in paths


def test_instructions_from_ctx(tmp_path, monkeypatch):
    _stub_backend(monkeypatch)
    ctx = _build_ctx(tmp_path)
    hooks = RuntimeHooks(mcp_auth=lambda: {}, compose=_compose)
    app = asyncio.run(MafRuntime().build(ctx, hooks))

    # The DNA-composed base prompt is carried byte-equal as the agent's
    # static instructions (mirrors the emitter's INSTRUCTIONS).
    assert app.agent.kwargs["instructions"] == ctx.instructions
    assert app.agent.kwargs["name"] == ctx.name
    # ctx.model wins — bound on the Foundry client (declarative-first, no env).
    assert _FakeFoundryClient.instances[-1].kwargs.get("model") == ctx.model


def test_allowlist_only_declared_tools_mounted(tmp_path, monkeypatch):
    _stub_backend(monkeypatch)
    ctx = _build_ctx(tmp_path)
    hooks = RuntimeHooks(mcp_auth=lambda: {}, compose=_compose)
    app = asyncio.run(MafRuntime().build(ctx, hooks))

    tools = _mounted_tools(app)
    assert len(tools) == len(ctx.mcp_servers) == 1
    declared = sorted(ctx.mcp_servers[0].allowed_tools)
    # Only the server's declared allowlist is mounted (i-038).
    assert sorted(tools[0].allowed_tools) == declared


def test_hitl_approval_mode_gates_confirm_tools(tmp_path, monkeypatch):
    _stub_backend(monkeypatch)
    ctx = _build_ctx(tmp_path)
    hooks = RuntimeHooks(mcp_auth=lambda: {}, compose=_compose)
    app = asyncio.run(MafRuntime().build(ctx, hooks))

    approval = _mounted_tools(app)[0].approval_mode
    assert isinstance(approval, dict), "gated tools ⇒ MCPSpecificApproval dict"
    allowed = set(ctx.mcp_servers[0].allowed_tools)
    expected_gated = sorted(ctx.tools_requiring_confirmation & allowed)
    expected_reads = sorted(allowed - ctx.tools_requiring_confirmation)
    assert sorted(approval["always_require_approval"]) == expected_gated
    assert sorted(approval["never_require_approval"]) == expected_reads
    # The fixture DOES declare confirm tools — guard the test's own premise.
    assert expected_gated


def test_lazy_no_mcp_dial_at_build(tmp_path, monkeypatch):
    # _stub_backend makes MCPStreamableHTTPTool.connect/load_tools RAISE; a
    # clean build proves construction never dials (lazy-MCP invariant).
    _stub_backend(monkeypatch)
    ctx = _build_ctx(tmp_path)
    hooks = RuntimeHooks(mcp_auth=lambda: {"Authorization": "Bearer x"}, compose=_compose)

    app = asyncio.run(MafRuntime().build(ctx, hooks))  # must not raise

    # And the per-request bearer bridge is wired as a header_provider (invoked
    # by MAF per outbound MCP request, never at build).
    provider = _mounted_tools(app)[0]._header_provider
    assert callable(provider)
    assert provider({}) == {"Authorization": "Bearer x"}


def test_maf_module_imports_without_extra():
    # The module imports agent_framework only inside build/attach — importing it
    # (and thus registering "maf") must not require the [maf] extra.
    assert maf_rt.MafRuntime.target == "maf"
