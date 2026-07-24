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


def _compose_ctx(mi: Any, copilot: str) -> Any:
    from dna.emit import build_copilot_context

    return build_copilot_context(mi, copilot)


async def build_runtime(
    copilot: str,
    *,
    base_dir: str,
    scope: str,
    hooks: RuntimeHooks,
) -> AGUIApp:
    """Compose `copilot`'s full `EmitContext` and build the `AGUIApp` its
    `serving.framework` names (`ctx.serving.framework`, default `"langchain"`).

    The def is read from the ENV-configured source (``DNA_SOURCE_URL`` >
    ``base_dir``) via ``build_env_mi`` — a published deploy reads Postgres, not
    a filesystem path baked into the image. ``base_dir`` is the local fallback.
    """
    # Build the instance on THIS loop (build_env_mi sets kernel._main_loop for
    # the loop-bound SQL connection), then offload the sync-over-async
    # `build_copilot_context` to a worker thread: its kernel reads dispatch back
    # to this loop, so a Postgres connection stays on its owning loop.
    from dna.runtime.config import build_env_mi

    mi = await build_env_mi(base_dir=base_dir, scope=scope)
    ctx = await asyncio.to_thread(_compose_ctx, mi, copilot)

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
