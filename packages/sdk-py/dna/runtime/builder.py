"""build_copilot — assemble a ready LangGraph copilot from a DNA def + host
hooks. The four DNA middlewares + the host's extra middleware/tools, over
langchain create_agent. The machine, written once."""
from __future__ import annotations

import asyncio
import os

from dna.runtime.config import copilot_config
from dna.runtime.middleware.allowlist import DnaAllowlistMiddleware
from dna.runtime.middleware.compose_prompt import DnaComposePromptMiddleware
from dna.runtime.middleware.hitl import dna_hitl_middleware
from dna.runtime.middleware.mcp_tools_mw import DnaMcpToolsMiddleware


async def build_copilot(
    copilot: str,
    *,
    base_dir: str,
    scope: str,
    mcp_url: str,
    mcp_auth,
    compose,
    extra_tools=None,
    extra_middleware=None,
    checkpointer=None,
    store=None,
):
    # dna.runtime requires the [runtime] extra, so langchain is present by
    # construction — importing this module (it imports the middleware
    # modules, which subclass AgentMiddleware) already pulls it in. The real
    # invariant is that the DNA KERNEL CORE never imports dna.runtime at all.
    # create_agent/init_chat_model are still deferred to here (rather than
    # module scope) to keep construction lazy until a copilot is actually
    # built.
    from langchain.agents import create_agent
    from langchain.chat_models import init_chat_model

    # copilot_config (Task 2) is sync and internally bridges to async kernel
    # I/O via a sync-over-async helper that raises loudly when it detects it's
    # already inside a running loop (this coroutine's own). Offload to a
    # worker thread so that bridge sees no running loop and can drive its own
    # asyncio.run safely — no nested-loop conflict.
    cfg = await asyncio.to_thread(copilot_config, copilot, base_dir=base_dir, scope=scope)

    # MCP tool discovery is LAZY — deferred to DnaMcpToolsMiddleware's first
    # authenticated model call (the per-request bearer is only present then). At
    # build time there is no user bearer and the prod copilot has no service
    # credential, so an eager load_mcp_tools here would 401 and crashloop. Build
    # therefore makes ZERO network call and needs ZERO credential. Only the
    # host's LOCAL tools are registered statically with create_agent.
    tools = [*(extra_tools or [])]

    extra_confirm = [getattr(t, "name", None) for t in (extra_tools or [])]
    extra_confirm = [n for n in extra_confirm if n]

    # DnaMcpToolsMiddleware is OUTERMOST so its schema injection in
    # wrap_model_call runs BEFORE DnaAllowlistMiddleware filters — the allowlist
    # sees (and vets) the injected MCP tools.
    middleware = [
        DnaMcpToolsMiddleware(mcp_url, mcp_auth),
        DnaAllowlistMiddleware(cfg.allowed_tools | frozenset(extra_confirm)),
        DnaComposePromptMiddleware(compose, fallback=cfg.instructions),
        dna_hitl_middleware(cfg.confirm_tools, extra_confirm=extra_confirm),
        *(extra_middleware or []),
    ]

    model = os.environ.get("OPENAI_MODEL") or cfg.model or "gpt-5-mini"

    return create_agent(
        model=init_chat_model(f"openai:{model}"),
        tools=tools,
        middleware=middleware,
        checkpointer=checkpointer,
        store=store,
    )
