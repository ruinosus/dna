"""DnaMcpToolsMiddleware — lazy MCP discovery, schema injection, dynamic exec.

pytest-asyncio is NOT installed, so async hooks are driven via asyncio.run.
"""
import asyncio
import shutil
from pathlib import Path

from langchain_core.messages import ToolMessage

from dna.runtime.builder import build_copilot
from dna.runtime.middleware.mcp_tools_mw import DnaMcpToolsMiddleware

FIXTURE_SRC = Path(__file__).parent / "fixtures" / "dna" / "dna-cloud-dev"


def _copy_fixture(tmp_path: Path) -> Path:
    dest = tmp_path / ".dna" / "dna-cloud-dev"
    dest.mkdir(parents=True)
    for subdir in ("copilots", "agents", "federations", "tools"):
        shutil.copytree(FIXTURE_SRC / subdir, dest / subdir)
    return tmp_path / ".dna"


class _FakeTool:
    def __init__(self, name):
        self.name = name
        self.ainvoke_calls = []

    async def ainvoke(self, tool_call):
        self.ainvoke_calls.append(tool_call)
        return ToolMessage(content=f"ran-{self.name}", tool_call_id=tool_call["id"])


class _FakeModelRequest:
    def __init__(self, tools=None):
        self.tools = list(tools) if tools is not None else []

    def override(self, **overrides):
        r = _FakeModelRequest(tools=overrides.get("tools", self.tools))
        return r


class _FakeToolCallRequest:
    def __init__(self, tool_call):
        self.tool_call = tool_call


def test_build_does_zero_boot_discovery(tmp_path, monkeypatch):
    """build_copilot must complete WITHOUT calling load_mcp_tools (no boot
    credential, no boot network)."""
    base_dir = _copy_fixture(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")

    calls = {"n": 0}

    async def spy_load_mcp_tools(mcp_url, auth):
        calls["n"] += 1
        return []

    monkeypatch.setattr(
        "dna.runtime.middleware.mcp_tools_mw.load_mcp_tools", spy_load_mcp_tools
    )

    async def compose(_):
        return "PROMPT"

    graph = asyncio.run(
        build_copilot(
            "memory-copilot",
            base_dir=str(base_dir),
            scope="dna-cloud-dev",
            mcp_url="http://127.0.0.1:9/mcp",
            mcp_auth=lambda: {},
            compose=compose,
            extra_tools=[],
            extra_middleware=[],
        )
    )

    assert graph is not None
    assert hasattr(graph, "ainvoke")
    assert calls["n"] == 0  # ZERO discovery at build


def test_awrap_model_call_discovers_once_and_injects(monkeypatch):
    calls = {"n": 0}
    recall = _FakeTool("recall")

    async def spy_load_mcp_tools(mcp_url, auth):
        calls["n"] += 1
        return [recall]

    monkeypatch.setattr(
        "dna.runtime.middleware.mcp_tools_mw.load_mcp_tools", spy_load_mcp_tools
    )

    mw = DnaMcpToolsMiddleware("http://mcp", lambda: {})
    local = _FakeTool("local_tool")

    seen = {}

    async def handler(request):
        seen["request"] = request
        return "RESULT"

    async def drive():
        req = _FakeModelRequest(tools=[local])
        out = await mw.awrap_model_call(req, handler)
        assert out == "RESULT"
        # Injected MCP tools FIRST, then local tools.
        names = [t.name for t in seen["request"].tools]
        assert names == ["recall", "local_tool"]
        # Second pass reuses the cache — spy not called again.
        await mw.awrap_model_call(_FakeModelRequest(tools=[local]), handler)

    asyncio.run(drive())
    assert calls["n"] == 1  # discovered exactly once


def test_awrap_tool_call_executes_cached_mcp_tool_else_delegates(monkeypatch):
    recall = _FakeTool("recall")

    async def spy_load_mcp_tools(mcp_url, auth):
        return [recall]

    monkeypatch.setattr(
        "dna.runtime.middleware.mcp_tools_mw.load_mcp_tools", spy_load_mcp_tools
    )

    mw = DnaMcpToolsMiddleware("http://mcp", lambda: {})

    handler_calls = {"n": 0}

    async def handler(request):
        handler_calls["n"] += 1
        return ToolMessage(content="from-handler", tool_call_id=request.tool_call["id"])

    async def drive():
        # Populate the cache (as the first model call would).
        await mw._ensure_discovered()

        # (1) MCP tool → executed by the middleware, NOT the handler.
        mcp_call = _FakeToolCallRequest(
            {"name": "recall", "args": {}, "id": "c1", "type": "tool_call"}
        )
        res = await mw.awrap_tool_call(mcp_call, handler)
        assert isinstance(res, ToolMessage)
        assert res.content == "ran-recall"
        assert len(recall.ainvoke_calls) == 1
        assert handler_calls["n"] == 0

        # (2) Local / unknown tool → delegates to the handler (real ToolNode).
        local_call = _FakeToolCallRequest(
            {"name": "local_tool", "args": {}, "id": "c2", "type": "tool_call"}
        )
        res2 = await mw.awrap_tool_call(local_call, handler)
        assert res2.content == "from-handler"
        assert handler_calls["n"] == 1
        assert len(recall.ainvoke_calls) == 1  # unchanged

    asyncio.run(drive())


def test_sync_wrap_model_call_passes_through_before_warmup():
    """Sync hook before any async warmup: pass through unchanged, never raise."""
    mw = DnaMcpToolsMiddleware("http://mcp", lambda: {})
    local = _FakeTool("local_tool")
    seen = {}

    def handler(request):
        seen["request"] = request
        return "R"

    out = mw.wrap_model_call(_FakeModelRequest(tools=[local]), handler)
    assert out == "R"
    # No MCP tools injected — only the local tool remains.
    assert [t.name for t in seen["request"].tools] == ["local_tool"]
