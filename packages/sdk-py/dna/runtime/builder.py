"""build_copilot — assemble a ready LangGraph copilot from a DNA def + host
hooks. The four DNA middlewares + the host's extra middleware/tools, over
langchain create_agent. The machine, written once."""
from __future__ import annotations

import asyncio
import os

from dna.runtime.config import copilot_config
from dna.runtime.mcp_tools import load_mcp_tools
from dna.runtime.middleware.allowlist import DnaAllowlistMiddleware
from dna.runtime.middleware.compose_prompt import DnaComposePromptMiddleware
from dna.runtime.middleware.hitl import dna_hitl_middleware


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
    # langchain/langgraph are heavy — deferred so importing dna.runtime.builder
    # (and dna core) never pulls them in unless a copilot is actually built.
    from langchain.agents import create_agent
    from langchain.chat_models import init_chat_model

    # copilot_config (Task 2) is sync and internally bridges to async kernel
    # I/O via a sync-over-async helper that raises loudly when it detects it's
    # already inside a running loop (this coroutine's own). Offload to a
    # worker thread so that bridge sees no running loop and can drive its own
    # asyncio.run safely — no nested-loop conflict.
    cfg = await asyncio.to_thread(copilot_config, copilot, base_dir=base_dir, scope=scope)

    # Freshness is per-request via the httpx.Auth hook threaded into
    # load_mcp_tools (Task 6) — so it's safe, and correct, to load the tool
    # list ONCE here and reuse it, rather than rebuilding per node/call.
    mcp_tools = await load_mcp_tools(mcp_url, mcp_auth)
    tools = [*mcp_tools, *(extra_tools or [])]

    extra_confirm = [getattr(t, "name", None) for t in (extra_tools or [])]
    extra_confirm = [n for n in extra_confirm if n]

    middleware = [
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
