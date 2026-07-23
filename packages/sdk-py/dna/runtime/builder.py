"""build_runtime — compose a copilot's full EmitContext through the kernel
and dispatch it to the framework adapter its `serving.framework` names
(`dna.runtime.port`), returning a servable `AGUIApp`.

`build_copilot` is the pre-port entry point kept as a BACK-COMPAT shim: it
wraps its LangChain-shaped arguments into `RuntimeHooks` and returns
`build_runtime(...).graph`, so every existing caller/test that expects a
compiled LangGraph graph keeps working unchanged.
"""
from __future__ import annotations

import asyncio
from typing import Any

from dna.runtime.port import AGUIApp, RuntimeHooks, get_runtime


def _compose_ctx(copilot: str, *, base_dir: str, scope: str) -> Any:
    from dna.emit import build_copilot_context
    from dna.kernel import Kernel

    mi = Kernel.quick(scope, base_dir=base_dir)
    return build_copilot_context(mi, copilot)


async def build_runtime(
    copilot: str,
    *,
    base_dir: str,
    scope: str,
    hooks: RuntimeHooks,
) -> AGUIApp:
    """Compose `copilot`'s full `EmitContext` and build the `AGUIApp` its
    `serving.framework` names (`ctx.serving.framework`, default
    `"langchain"` — the field lands in Task 3; until then every copilot
    dispatches to the LangChain adapter)."""
    # `_compose_ctx` is sync and internally bridges to async kernel I/O via a
    # sync-over-async helper that raises loudly when it detects it's already
    # inside a running loop (this coroutine's own). Offload to a worker
    # thread so that bridge sees no running loop and can drive its own
    # asyncio.run safely — no nested-loop conflict. (Same bridge
    # `copilot_config`/the old `build_copilot` used.)
    ctx = await asyncio.to_thread(_compose_ctx, copilot, base_dir=base_dir, scope=scope)

    framework = getattr(getattr(ctx, "serving", None), "framework", None) or "langchain"
    return await get_runtime(framework).build(ctx, hooks)


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
    """BACK-COMPAT shim over `build_runtime` — every existing caller/test
    that expects a compiled LangGraph graph keeps working verbatim.

    `mcp_url` is accepted for signature compatibility but IGNORED: the
    LangChain adapter reads the MCP url from the declarative
    `ctx.mcp_servers[0].url` (the federation the mounted agent actually
    declares), not from this parameter.
    """
    hooks = RuntimeHooks(
        mcp_auth=mcp_auth,
        compose=compose,
        extensions={"middleware": extra_middleware, "tools": extra_tools},
        checkpointer=checkpointer,
        store=store,
    )
    app = await build_runtime(copilot, base_dir=base_dir, scope=scope, hooks=hooks)
    # Fail loud rather than silently return None: this LangChain-shaped shim can
    # only surface a LangGraph graph. A copilot whose `serving.framework` selects
    # a non-LangGraph backend (e.g. maf, whose AGUIApp.graph is None) must be
    # built through `build_runtime` and served via `AGUIApp.attach`, not this
    # back-compat entry point.
    if app.graph is None:
        raise RuntimeError(
            f"build_copilot() (the back-compat shim) cannot serve copilot "
            f"{copilot!r}: its serving.framework resolves to a non-LangGraph "
            f"backend with no `.graph`. Use build_runtime(...) + AGUIApp.attach."
        )
    return app.graph
