"""Lazy MCP tool discovery as a create_agent middleware.

Root cause this fixes: eager `load_mcp_tools(...)` at build time 401s — there is
no user bearer at boot and the prod copilot carries no service credential, so the
copilot crashloops. The old hand-rolled copilot discovered per-request under the
user bearer; this restores that shape.

Mechanism (verified against langchain 1.3.14 `langchain/agents/factory.py`):
`create_agent` supports DYNAMIC tools. The "unknown client-side tool" validation
at factory.py ~1304 is SKIPPED whenever any middleware defines `wrap_tool_call`
(`if not has_wrap_tool_call:`), and the `DYNAMIC_TOOL_ERROR_TEMPLATE` documents
"Option 2: Implement `wrap_tool_call` to execute tools that are added
dynamically". So this middleware:
  (a) injects tool SCHEMAS into `request.tools` in `wrap_model_call` — the model
      sees and may call them; and
  (b) EXECUTES them in `wrap_tool_call`, bypassing the static ToolNode (which
      only holds the host's local tools).

Discovery is lazy: it happens on the FIRST model call, when the per-request
bearer is present (the httpx.Auth threaded into `load_mcp_tools` reads the request
contextvar). Tool SCHEMAS are identity-independent, so caching the discovered set
process-wide across users is correct — the per-request bearer only matters for
EXECUTION, which the tool objects' own httpx.Auth re-reads on every `ainvoke`.
"""
from __future__ import annotations

import asyncio
import logging

from langchain.agents.middleware import AgentMiddleware

from dna.runtime.mcp_tools import load_mcp_tools

_log = logging.getLogger("dna.runtime.mcp_tools_mw")


class DnaMcpToolsMiddleware(AgentMiddleware):
    """Discover the DNA MCP tools LAZILY (first authenticated model call) and
    both inject their schemas into the model request and execute their calls."""

    def __init__(self, mcp_url: str, mcp_auth) -> None:
        super().__init__()
        self._mcp_url = mcp_url
        self._mcp_auth = mcp_auth
        self._tools: dict | None = None
        self._lock = asyncio.Lock()

    async def _ensure_discovered(self) -> dict:
        # Fast path: already cached (schemas are identity-independent).
        if self._tools is not None:
            return self._tools
        async with self._lock:
            if self._tools is None:
                discovered = await load_mcp_tools(self._mcp_url, self._mcp_auth)
                self._tools = {t.name: t for t in discovered}
                _log.debug("discovered %d MCP tool(s) lazily", len(self._tools))
        return self._tools

    # --- async hooks (the path that actually runs in production) ---------

    async def awrap_model_call(self, request, handler):
        tools = await self._ensure_discovered()
        # Injected MCP tools FIRST, then any local tools already on the request.
        return await handler(
            request.override(tools=[*tools.values(), *(request.tools or [])])
        )

    async def awrap_tool_call(self, request, handler):
        name = request.tool_call["name"]
        if self._tools and name in self._tools:
            # A BaseTool invoked with a full ToolCall dict returns a ToolMessage
            # (verified against langchain_core.tools). Bypass the static ToolNode.
            return await self._tools[name].ainvoke(request.tool_call)
        # Local / unknown tool → the real ToolNode via the downstream handler.
        return await handler(request)

    # --- sync hooks (production is async; these are best-effort fallbacks) --

    def wrap_model_call(self, request, handler):
        # Cannot drive async discovery from a sync hook. If a prior async warmup
        # populated the cache, mirror the async injection; otherwise pass the
        # request through unchanged (model sees local tools only). Never block
        # or raise — a sync call before any async warmup is a benign degrade.
        if self._tools is not None:
            return handler(
                request.override(tools=[*self._tools.values(), *(request.tools or [])])
            )
        _log.debug("sync wrap_model_call before async warmup — MCP tools not injected")
        return handler(request)

    def wrap_tool_call(self, request, handler):
        name = request.tool_call["name"]
        if self._tools and name in self._tools:
            return self._tools[name].invoke(request.tool_call)
        return handler(request)
