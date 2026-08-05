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

    # The fixture's memory-copilot declares `persistence.{checkpoint,memory}`
    # on Postgres (ref `primary-pg`) — since this caller passes no
    # `hooks.checkpointer`, the adapter now resolves it declaratively
    # (Task 4). Stub the resolver so this test never dials real Postgres —
    # `resolve_persistence`'s own DSN/env-var behavior is covered by
    # test_declarative_config.py.
    async def fake_resolve_persistence(_persistence):
        return None, None

    monkeypatch.setattr(
        "dna.runtime.persistence.resolve_persistence", fake_resolve_persistence
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


# --- the WHY channel (s-hitl-por-que-mcp-writes): rationale inject + strip ---


def _structured_mcp_tool(name, properties, required=()):
    """A REAL StructuredTool shaped exactly as langchain_mcp_adapters builds
    MCP tools: `args_schema` is the server's JSON-schema DICT (tools.py:
    `StructuredTool(..., args_schema=tool.inputSchema)`) — so the augmentation
    path is exercised against the true pydantic `model_copy` boundary."""
    from langchain_core.tools import StructuredTool

    async def _run(**kwargs):  # never executed in these tests
        return "ok"

    return StructuredTool(
        name=name,
        description=f"{name} (test double of an MCP tool)",
        args_schema={
            "type": "object",
            "properties": dict(properties),
            "required": list(required),
        },
        coroutine=_run,
    )


class _RecordingSchemaTool:
    """Execution recorder with an MCP-shaped dict schema and pydantic-like
    `model_copy` — lets the strip tests capture EXACTLY the args that would
    reach the MCP server."""

    def __init__(self, name, properties):
        self.name = name
        self.args_schema = {"type": "object", "properties": dict(properties)}
        self.ainvoke_calls = []
        self.invoke_calls = []

    def model_copy(self, update=None):
        import copy

        clone = copy.copy(self)
        for key, value in (update or {}).items():
            setattr(clone, key, value)
        return clone

    async def ainvoke(self, tool_call):
        self.ainvoke_calls.append(tool_call)
        return ToolMessage(content=f"ran-{self.name}", tool_call_id=tool_call["id"])

    def invoke(self, tool_call):
        self.invoke_calls.append(tool_call)
        return ToolMessage(content=f"ran-{self.name}", tool_call_id=tool_call["id"])


def test_gated_tool_model_schema_gains_optional_rationale_and_exec_schema_stays_intact(
    monkeypatch,
):
    remember = _structured_mcp_tool("remember", {"summary": {"type": "string"}}, ["summary"])
    recall = _structured_mcp_tool("recall", {"query": {"type": "string"}})

    async def spy_load_mcp_tools(mcp_url, auth):
        return [remember, recall]

    monkeypatch.setattr(
        "dna.runtime.middleware.mcp_tools_mw.load_mcp_tools", spy_load_mcp_tools
    )
    mw = DnaMcpToolsMiddleware("http://mcp", lambda: {}, rationale_tools={"remember"})

    seen = {}

    async def handler(request):
        seen["request"] = request
        return "R"

    asyncio.run(mw.awrap_model_call(_FakeModelRequest(), handler))
    injected = {t.name: t for t in seen["request"].tools}

    # The MODEL sees remember with an optional `rationale` string arg…
    model_schema = injected["remember"].args_schema
    assert model_schema["properties"]["rationale"]["type"] == "string"
    assert "rationale" not in model_schema["required"]  # optional by design
    assert "summary" in model_schema["properties"]  # real args untouched

    # …while the EXECUTED tool keeps the MCP server's schema byte-intact.
    exec_schema = mw._tools["remember"].args_schema
    assert "rationale" not in exec_schema["properties"]
    assert injected["remember"] is not mw._tools["remember"]  # a copy, not a mutation

    # A non-gated tool is the SAME object, schema untouched.
    assert injected["recall"] is recall
    assert "rationale" not in recall.args_schema["properties"]


def test_rationale_is_stripped_before_execution_and_history_not_mutated(monkeypatch):
    """The mutation-killer the story's DoD names: remove the strip and this
    test dies — the recorder sees the injected arg the MCP server does not
    declare."""
    remember = _RecordingSchemaTool("remember", {"summary": {"type": "string"}})
    recall = _RecordingSchemaTool("recall", {"query": {"type": "string"}})

    async def spy_load_mcp_tools(mcp_url, auth):
        return [remember, recall]

    monkeypatch.setattr(
        "dna.runtime.middleware.mcp_tools_mw.load_mcp_tools", spy_load_mcp_tools
    )
    mw = DnaMcpToolsMiddleware("http://mcp", lambda: {}, rationale_tools={"remember"})

    original_call = {
        "name": "remember",
        "args": {"summary": "x", "rationale": "porque o usuário pediu"},
        "id": "c1",
        "type": "tool_call",
    }

    async def drive():
        await mw._ensure_discovered()
        await mw.awrap_tool_call(_FakeToolCallRequest(original_call), _fail_handler)
        # Non-gated tool: args ride VERBATIM (its args are the server's business).
        await mw.awrap_tool_call(
            _FakeToolCallRequest(
                {"name": "recall", "args": {"query": "q", "rationale": "hallucinated"},
                 "id": "c2", "type": "tool_call"}
            ),
            _fail_handler,
        )

    asyncio.run(drive())

    (executed,) = remember.ainvoke_calls
    assert executed["args"] == {"summary": "x"}  # rationale STRIPPED
    assert executed["id"] == "c1"
    # The checkpointed ToolCall (message history) was never mutated.
    assert original_call["args"] == {"summary": "x", "rationale": "porque o usuário pediu"}

    (recall_executed,) = recall.ainvoke_calls
    assert recall_executed["args"] == {"query": "q", "rationale": "hallucinated"}


def test_sync_wrap_tool_call_strips_the_same_way(monkeypatch):
    remember = _RecordingSchemaTool("remember", {"summary": {"type": "string"}})

    async def spy_load_mcp_tools(mcp_url, auth):
        return [remember]

    monkeypatch.setattr(
        "dna.runtime.middleware.mcp_tools_mw.load_mcp_tools", spy_load_mcp_tools
    )
    mw = DnaMcpToolsMiddleware("http://mcp", lambda: {}, rationale_tools={"remember"})
    asyncio.run(mw._ensure_discovered())

    call = {"name": "remember", "args": {"summary": "x", "rationale": "y"},
            "id": "c1", "type": "tool_call"}
    mw.wrap_tool_call(_FakeToolCallRequest(call), _fail_sync_handler)

    (executed,) = remember.invoke_calls
    assert executed["args"] == {"summary": "x"}
    assert call["args"] == {"summary": "x", "rationale": "y"}  # original intact


def test_gated_tool_that_already_declares_rationale_is_never_shadowed_nor_stripped(
    monkeypatch,
):
    """A REAL `rationale` arg belongs to the server: the schema is not
    overwritten and the value is executed through, not swallowed."""
    audit = _RecordingSchemaTool(
        "audit_write",
        {"target": {"type": "string"}, "rationale": {"type": "string"}},
    )

    async def spy_load_mcp_tools(mcp_url, auth):
        return [audit]

    monkeypatch.setattr(
        "dna.runtime.middleware.mcp_tools_mw.load_mcp_tools", spy_load_mcp_tools
    )
    mw = DnaMcpToolsMiddleware("http://mcp", lambda: {}, rationale_tools={"audit_write"})

    seen = {}

    async def handler(request):
        seen["request"] = request
        return "R"

    async def drive():
        await mw.awrap_model_call(_FakeModelRequest(), handler)
        await mw.awrap_tool_call(
            _FakeToolCallRequest(
                {"name": "audit_write",
                 "args": {"target": "t", "rationale": "the server's own arg"},
                 "id": "c1", "type": "tool_call"}
            ),
            _fail_handler,
        )

    asyncio.run(drive())

    (injected,) = seen["request"].tools
    assert injected is audit  # untouched — the tool owns the name
    (executed,) = audit.ainvoke_calls
    assert executed["args"] == {"target": "t", "rationale": "the server's own arg"}


def test_without_rationale_tools_injection_and_execution_are_unchanged(monkeypatch):
    """Backward compat: the default (no rationale_tools) neither augments a
    schema nor touches args — the pre-story wire, byte for byte."""
    remember = _structured_mcp_tool("remember", {"summary": {"type": "string"}})

    async def spy_load_mcp_tools(mcp_url, auth):
        return [remember]

    monkeypatch.setattr(
        "dna.runtime.middleware.mcp_tools_mw.load_mcp_tools", spy_load_mcp_tools
    )
    mw = DnaMcpToolsMiddleware("http://mcp", lambda: {})

    seen = {}

    async def handler(request):
        seen["request"] = request
        return "R"

    asyncio.run(mw.awrap_model_call(_FakeModelRequest(), handler))
    (injected,) = seen["request"].tools
    assert injected is remember  # same object — no copy, no augmentation
    assert "rationale" not in injected.args_schema["properties"]


async def _fail_handler(request):  # a gated MCP call must never reach the ToolNode
    raise AssertionError("handler must not be called for a cached MCP tool")


def _fail_sync_handler(request):
    raise AssertionError("handler must not be called for a cached MCP tool")
