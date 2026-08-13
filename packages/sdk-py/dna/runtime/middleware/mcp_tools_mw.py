"""Lazy MCP tool discovery as a create_agent middleware.

Root cause this fixes: eager `load_mcp_tools(...)` at build time 401s — there is
no user bearer at boot and the prod copilot carries no service credential, so the
copilot crashloops. The old hand-rolled copilot discovered per-request under the
user bearer; this restores that shape.

Mechanism (verified against langchain 1.3.14 `langchain/agents/factory.py`):
`create_agent` supports DYNAMIC tools. The "unknown client-side tool" validation
at factory.py ~1304 is SKIPPED whenever any middleware defines `wrap_tool_call`
(`if not has_wrap_tool_call:`), and the `DYNAMIC_TOOL_ERROR_TEMPLATE` instances
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

The WHY channel (s-hitl-por-que-mcp-writes): for the HITL-gated tools named in
`rationale_tools`, the MODEL-FACING copy of the schema gains an optional
`rationale: string` argument — the model's stated reason, which
`dna_hitl_middleware`'s description factory surfaces verbatim on the approval
card. The argument exists ONLY between model and middleware: it is injected
into a `model_copy` of the tool (the cached execution tool keeps the MCP
server's schema intact) and STRIPPED from the args before the real execution
in `wrap_tool_call` — the MCP server never sees an argument it does not
declare. A gated tool whose REAL schema already declares `rationale` is left
untouched (never shadowed) and never stripped.
"""
from __future__ import annotations

import asyncio
import logging

from langchain.agents.middleware import AgentMiddleware

from dna.runtime.mcp_tools import load_mcp_tools

_log = logging.getLogger("dna.runtime.mcp_tools_mw")

#: ⭐ O nome do argumento SINTÉTICO do canal do porquê. Público porque ele tem
#: um SEGUNDO leitor, e esse leitor é de FORA deste repositório: quem compara
#: `arguments` com `edited_args` para medir o quanto o agente errou precisa
#: descontá-lo. Ele entra no que o modelo propôs e é removido antes da execução
#: (`_strip_rationale`), então uma comparação que o contasse veria uma "correção
#: do humano" onde houve máquina dos dois lados.
#:
#: ⚠️ **É por isso que ele é PÚBLICO, e não `_RATIONALE_ARG`.** Um consumidor
#: que precise descontar um nome tem de poder lê-lo daqui; enumerá-lo do lado
#: dele seria uma segunda cópia do mesmo vocabulário, e cópia de vocabulário
#: diverge — a lição que `dna_hitl_middleware` já custou uma vez.
RATIONALE_ARG = "rationale"
_RATIONALE_ARG = RATIONALE_ARG
_RATIONALE_SCHEMA = {
    "type": "string",
    "description": (
        "Why this action is needed, in one or two sentences, written in the "
        "user's language. Shown verbatim to the human who approves or rejects "
        "this call — state the reason, not a restatement of the arguments."
    ),
}


class DnaMcpToolsMiddleware(AgentMiddleware):
    """Discover the DNA MCP tools LAZILY (first authenticated model call) and
    both inject their schemas into the model request and execute their calls.

    `rationale_tools` names the HITL-gated tools whose model-facing schema
    gains the optional `rationale` argument (stripped again before execution
    — see module docstring). Empty by default: without it, injected schemas
    and executed args are byte-identical to before."""

    def __init__(self, mcp_url: str, mcp_auth, rationale_tools=frozenset()) -> None:
        super().__init__()
        self._mcp_url = mcp_url
        self._mcp_auth = mcp_auth
        self._rationale_tools = frozenset(rationale_tools or ())
        self._tools: dict | None = None
        # Model-facing tool list: gated tools swapped for their
        # rationale-augmented copies; everything else the same objects.
        self._model_tools: list | None = None
        # The gated tools whose schema WE augmented — exactly the set whose
        # `rationale` arg must be stripped before execution. A gated tool that
        # already declared its own `rationale` is in neither.
        self._augmented: frozenset[str] = frozenset()
        self._lock = asyncio.Lock()

    def _with_rationale_arg(self, tool):
        """A `model_copy` of `tool` whose JSON-schema dict gains the optional
        `rationale` property — or `(tool, False)` (and no strip later) when
        the schema is not a dict or already declares `rationale`."""
        schema = getattr(tool, "args_schema", None)
        if not isinstance(schema, dict):
            return tool, False
        props = schema.get("properties")
        props = dict(props) if isinstance(props, dict) else {}
        if _RATIONALE_ARG in props:
            return tool, False  # the real tool owns this name — never shadow it
        props[_RATIONALE_ARG] = dict(_RATIONALE_SCHEMA)
        # `required` untouched: the rationale is optional by design (the HITL
        # description factory degrades to the default machinery without it).
        return (
            tool.model_copy(update={"args_schema": {**schema, "properties": props}}),
            True,
        )

    async def _ensure_discovered(self) -> dict:
        # Fast path: already cached (schemas are identity-independent).
        if self._tools is not None:
            return self._tools
        async with self._lock:
            if self._tools is None:
                discovered = await load_mcp_tools(self._mcp_url, self._mcp_auth)
                model_tools = []
                augmented = set()
                for t in discovered:
                    if t.name in self._rationale_tools:
                        model_tool, did = self._with_rationale_arg(t)
                        model_tools.append(model_tool)
                        if did:
                            augmented.add(t.name)
                    else:
                        model_tools.append(t)
                # Execution keeps the ORIGINAL tools — the MCP server's schema
                # stays intact; only the model sees the augmented copies.
                self._tools = {t.name: t for t in discovered}
                self._model_tools = model_tools
                self._augmented = frozenset(augmented)
                _log.debug("discovered %d MCP tool(s) lazily", len(self._tools))
        return self._tools

    def _strip_rationale(self, tool_call):
        """The tool_call to EXECUTE: for a tool whose schema we augmented, a
        copy without the injected `rationale` arg (the server does not declare
        it); anything else rides through verbatim. Never mutates the original
        — the ToolCall dict lives in checkpointed message history."""
        args = tool_call.get("args")
        if (
            tool_call["name"] in self._augmented
            and isinstance(args, dict)
            and _RATIONALE_ARG in args
        ):
            return {
                **tool_call,
                "args": {k: v for k, v in args.items() if k != _RATIONALE_ARG},
            }
        return tool_call

    # --- async hooks (the path that actually runs in production) ---------

    async def awrap_model_call(self, request, handler):
        await self._ensure_discovered()
        # Injected MCP tools FIRST, then any local tools already on the request.
        return await handler(
            request.override(tools=[*(self._model_tools or []), *(request.tools or [])])
        )

    async def awrap_tool_call(self, request, handler):
        name = request.tool_call["name"]
        if self._tools and name in self._tools:
            # A BaseTool invoked with a full ToolCall dict returns a ToolMessage
            # (verified against langchain_core.tools). Bypass the static ToolNode.
            return await self._tools[name].ainvoke(self._strip_rationale(request.tool_call))
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
                request.override(
                    tools=[*(self._model_tools or []), *(request.tools or [])]
                )
            )
        _log.debug("sync wrap_model_call before async warmup — MCP tools not injected")
        return handler(request)

    def wrap_tool_call(self, request, handler):
        name = request.tool_call["name"]
        if self._tools and name in self._tools:
            return self._tools[name].invoke(self._strip_rationale(request.tool_call))
        return handler(request)
