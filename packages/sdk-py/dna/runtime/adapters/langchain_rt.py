"""LangChainRuntime — the `dna.runtime.port` adapter that assembles a ready
LangGraph copilot from a DNA `EmitContext` + `RuntimeHooks`, over
`langchain.agents.create_agent`. This IS `build_copilot`'s old body, moved
behind the port (C0 Task 2) — parity with the pre-port behavior is the
acceptance bar, not new behavior.

The four DNA disciplines + the host's `hooks.extensions` middleware/tools:
DnaMcpToolsMiddleware (lazy MCP, i-0xx) → DnaAllowlistMiddleware (i-038) →
DnaComposePromptMiddleware (i-040) → dna_hitl_middleware (HITL) → host extras.
Order is load-bearing: DnaMcpToolsMiddleware is OUTERMOST so its schema
injection in `wrap_model_call` runs BEFORE DnaAllowlistMiddleware filters —
the allowlist sees (and vets) the injected MCP tools.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dna.runtime.middleware.allowlist import DnaAllowlistMiddleware
from dna.runtime.middleware.compose_prompt import DnaComposePromptMiddleware
from dna.runtime.middleware.hitl import dna_hitl_middleware
from dna.runtime.middleware.mcp_tools_mw import DnaMcpToolsMiddleware
from dna.runtime.port import RuntimeHooks


def _allowed_tools_set(mcp_servers: Any) -> frozenset[str]:
    """The tool names `mcp_servers` collectively allow. Factored out of
    `_project_config` so `mcp_tool_stack` (a delegation target's isolated
    sub-run, `dna.runtime.builder`) computes the SAME allowlist from ITS OWN
    `mcp_servers` rather than a second, drifting copy of this rule."""
    allowed = {
        t for s in (mcp_servers or []) for t in (getattr(s, "allowed_tools", None) or [])
    }
    # The Tool-doc alias `list` runs as `list_memories` (federation doc note).
    if "list" in allowed:
        allowed.add("list_memories")
    return frozenset(allowed)


def _project_config(ctx: Any) -> tuple[str, str | None, frozenset[str], tuple[str, ...]]:
    """Project the narrow (instructions, model, allowed_tools, confirm_tools)
    tuple `build_copilot` used to get from `copilot_config` — but FROM an
    already-composed `EmitContext`, so the adapter doesn't re-drive the kernel
    a second time now that `build_runtime` composes ctx once up front. Same
    projection rule as `dna.runtime.config.copilot_config` (kept in lockstep;
    that function still serves callers who only want the narrow config)."""
    allowed = _allowed_tools_set(getattr(ctx, "mcp_servers", None) or [])
    confirm_tools = tuple(
        sorted(getattr(ctx, "tools_requiring_confirmation", None) or [])
    )
    return (
        ctx.instructions or "",
        ctx.model,
        allowed,
        confirm_tools,
    )


def mcp_tool_stack(
    mcp_servers: Any,
    mcp_auth: Any,
    *,
    extra_allowed: frozenset[str] = frozenset(),
) -> tuple[list[Any], frozenset[str]]:
    """The `(middleware, allowed_tools)` pair that gives an agent its MCP tool
    surface: `DnaMcpToolsMiddleware` (lazy discovery + schema injection) THEN
    `DnaAllowlistMiddleware` (fail-closed filter to what `mcp_servers`
    collectively allow) — the SAME two middleware, in the SAME order,
    `LangChainRuntime.build` wires for the mounted agent (order is
    load-bearing: the allowlist must see only what discovery injected).

    Public so `dna.runtime.builder`'s `run_local` reuses this SEAM for a
    delegation target's isolated sub-run, resolving tools from THAT TARGET's
    OWN `mcp_servers` — never the delegator's — so a delegate reaches no more
    than it would reach mounted directly (s-close-the-two-doors A.1's
    allowlist-preserving property: delegation is not privilege escalation).

    `mcp_auth` is threaded through VERBATIM — the exact per-request hook
    object the caller already holds, never wrapped, cloned, or cached into a
    new credential. Reusing it here relies on nothing more than what
    `dna.runtime.mcp_tools.load_mcp_tools` already documents: the hook is
    re-read on every outgoing HTTP request, not snapshotted once — so calling
    it again, later, for a second `DnaMcpToolsMiddleware` instance within the
    SAME inbound request is exactly its documented contract, not a new
    assumption this function introduces.

    Empty `mcp_servers` → `([], allowed)` (no MCP middleware at all) — honest
    about "this agent declared no MCP surface", never silently permissive.
    """
    allowed = _allowed_tools_set(mcp_servers) | extra_allowed
    if not mcp_servers:
        return [], allowed
    import os

    mcp_url = os.environ.get("DNA_MCP_URL") or mcp_servers[0].url
    return (
        [DnaMcpToolsMiddleware(mcp_url, mcp_auth), DnaAllowlistMiddleware(allowed)],
        allowed,
    )


@dataclass
class _LangGraphAGUIApp:
    """The `AGUIApp` `LangChainRuntime.build` returns — `graph` is the
    compiled LangGraph app (the host's rehydration handle); `attach` mounts
    the LangGraph AG-UI bridge (`ag_ui_langgraph`), imported lazily so
    constructing this handle never requires that package to be importable."""

    graph: Any
    agent_name: str

    def attach(self, app: Any, path: str = "/agui") -> None:
        from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint

        add_langgraph_fastapi_endpoint(
            app,
            agent=LangGraphAgent(name=self.agent_name, graph=self.graph),
            path=path,
        )


class LangChainRuntime:
    """The LangChain/LangGraph `RuntimePort` — target `"langchain"`, the
    default backend (`serving.framework` unset)."""

    target = "langchain"

    async def build(self, ctx: Any, hooks: RuntimeHooks) -> _LangGraphAGUIApp:
        # create_agent/init_chat_model stay deferred to here (not module
        # scope) to keep construction lazy until a copilot is actually built
        # — same discipline the pre-port build_copilot followed. Importing
        # this module already pulls langchain (the middleware modules above
        # subclass AgentMiddleware at their own top level) — dna.runtime
        # requires the [runtime] extra by construction, so that's expected;
        # the real invariant is that the DNA KERNEL CORE never imports
        # dna.runtime at all.
        from langchain.agents import create_agent

        from dna.runtime.model import build_chat_model

        # `allowed_tools` is recomputed inside `mcp_tool_stack` below (from the
        # SAME `ctx.mcp_servers` — one rule, `_allowed_tools_set`, not a second
        # copy of it here).
        instructions, model_hint, _allowed_tools, confirm_tools = _project_config(ctx)

        extensions = hooks.extensions or {}
        extra_middleware = extensions.get("middleware") or []
        extra_tools = extensions.get("tools") or []

        mcp_servers = getattr(ctx, "mcp_servers", None) or []
        if not mcp_servers:
            raise ValueError(
                f"copilot {getattr(ctx, 'name', '?')!r} declares no mcp_servers; "
                "LangChainRuntime requires the mounted agent to federate at "
                "least one MCP server"
            )

        # MCP tool discovery is LAZY — deferred to DnaMcpToolsMiddleware's
        # first authenticated model call (the per-request bearer is only
        # present then). At build time there is no user bearer and the prod
        # copilot has no service credential, so an eager load here would 401
        # and crashloop. Build therefore makes ZERO network call and needs
        # ZERO credential. Only the host's LOCAL tools are registered
        # statically with create_agent.
        tools = [*extra_tools]

        extra_confirm = [n for n in (getattr(t, "name", None) for t in extra_tools) if n]

        # DnaMcpToolsMiddleware is OUTERMOST so its schema injection in
        # wrap_model_call runs BEFORE DnaAllowlistMiddleware filters — the
        # allowlist sees (and vets) the injected MCP tools. `mcp_tool_stack`
        # is the SAME seam `dna.runtime.builder`'s delegation `run_local`
        # reuses for a target's isolated sub-run (mcp_url resolution —
        # DNA_MCP_URL env override over the federation's declarative
        # placeholder — lives there now, once, not copy-pasted per caller).
        mcp_middleware, _allowed = mcp_tool_stack(
            mcp_servers, hooks.mcp_auth, extra_allowed=frozenset(extra_confirm)
        )
        middleware = [
            *mcp_middleware,
            DnaComposePromptMiddleware(hooks.compose, fallback=instructions),
            dna_hitl_middleware(confirm_tools, extra_confirm=extra_confirm),
            *extra_middleware,
        ]

        # ctx.model wins — no `OPENAI_MODEL` env override (Global Constraint:
        # kill raw os.environ reads for model/mcp/persistence in the runtime).
        model = model_hint or "gpt-5-mini"

        # Persistence: the host wins if it injected a checkpointer (it owns
        # that connection's lifecycle — e.g. dna-cloud's `open_checkpointer`
        # holds the CM across the app lifespan for a clean shutdown). Only
        # when it did NOT do we fall back to resolving `ctx.persistence`
        # declaratively (`dna.runtime.persistence.resolve_persistence`) —
        # DSN via the `ref -> DNA_<REF>_URL` convention, never a raw env
        # read here.
        checkpointer, store = hooks.checkpointer, hooks.store
        if checkpointer is None:
            from dna.runtime.persistence import resolve_persistence

            checkpointer, store = await resolve_persistence(
                getattr(ctx, "persistence", None)
            )

        graph = create_agent(
            model=build_chat_model(model),
            tools=tools,
            middleware=middleware,
            checkpointer=checkpointer,
            store=store,
        )

        return _LangGraphAGUIApp(graph=graph, agent_name=getattr(ctx, "name", "agent"))
