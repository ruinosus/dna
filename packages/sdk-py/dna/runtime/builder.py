"""build_runtime — compose a copilot's full EmitContext through the kernel
and dispatch it to the framework adapter its `serving.framework` names
(`dna.runtime.port`), returning a servable `AGUIApp`.

`build_copilot` is the pre-port entry point kept as a BACK-COMPAT shim: it
wraps its LangChain-shaped arguments into `RuntimeHooks` and returns
`build_runtime(...).graph`, so every existing caller/test that expects a
compiled LangGraph graph keeps working unchanged.

── A.1 (s-close-the-two-doors) — the `delegate_to` wiring ───────────────────

`dna.application.delegation_tool.make_delegate_tool` builds the tool; this is
where it gets HANDED to an agent, because this is where both halves of what
`run_local` needs meet: `mi` (to compose+run ANOTHER named agent, and to read
THAT target's own `mcp_servers`) and the composed `ctx` (to know the
delegator's own name + declaration). The adapter layer
(`dna.runtime.adapters.langchain_rt`) never sees `mi` — only `ctx` +
`RuntimeHooks` (verified by reading `RuntimePort.build`'s signature) — so
building `run_local` there would need `mi` threaded through a new port-wide
field every adapter would have to carry. Instead this module drops the tool
into `hooks.extensions["tools"]`, the SAME escape hatch
`LangChainRuntime.build` already merges into `create_agent(tools=...)`
(`extra_tools = extensions.get("tools") or []`) — no change needed to how a
tool ATTACHES to an agent. `run_local`'s sub-agent DOES reuse one adapter
seam directly: `dna.runtime.adapters.langchain_rt.mcp_tool_stack` (factored
out of `LangChainRuntime.build` for exactly this reuse) resolves the
target's tools from ITS OWN `mcp_servers`/`allowed_tools` — never the
delegator's, and never a hand-rolled second implementation of that
resolution. A future non-LangChain runtime that wants delegation would need
its own `run_local` (this one builds a LangChain sub-agent); noted, not
solved here — `[runtime]` is the only backend this ships against today
(CLAUDE.md's pinned floor).

The gate is `AgentSpec.team_members` read straight from the parsed spec — no
hand-kept name list, and no dependency on the roster resolving non-empty
(`targets_for` re-derives that independently, twice over, inside
`delegate_to` itself): a delegator that declares `team_members` gets the
tool even if every declared target currently refuses it, because the
property this exists to prove is "derived from the declaration", not "derived
from today's roster outcome".
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any, Awaitable, Callable

from dna.runtime.port import AGUIApp, RuntimeHooks, get_runtime


def _compose_ctx(mi: Any, copilot: str) -> Any:
    from dna.emit import build_copilot_context

    return build_copilot_context(mi, copilot)


def _team_members_and_documents(mi: Any, delegator: str) -> tuple[list[str], list[dict]]:
    """Sync kernel read, offloaded via `asyncio.to_thread` — same discipline
    `_compose_ctx` already follows (kernel reads dispatch back to the owning
    loop; see `build_runtime`'s docstring on the loop-bound SQL connection).

    Documents are only materialized (`mi.documents` — a full-scope load) when
    `team_members` is non-empty: the common case (no delegation declared)
    never pays that cost.
    """
    doc = mi.find_agent(delegator)
    spec = getattr(doc, "spec", None) if doc is not None else None
    raw_team = spec.get("team_members") if hasattr(spec, "get") else None
    team_members = list(raw_team or [])
    if not team_members:
        return team_members, []
    documents = [d.raw for d in mi.documents]
    return team_members, documents


def _target_mcp_servers(mi: Any, target_name: str) -> list[Any]:
    """The delegation target's OWN `mcp_servers` projection — sync, offloaded
    via `asyncio.to_thread` alongside `build_emit_context` (same discipline).
    `build_emit_context` alone never fills `EmitContext.mcp_servers` (that
    projection is copilot-only, per its docstring); a delegation target is a
    plain `Agent` doc, never itself a Copilot, so it is read straight off the
    target's own spec via the SAME seam `build_copilot_context` uses for the
    mounted agent (`dna.emit.project_agent_mcp_servers`) — never
    reimplemented, and never the DELEGATOR's `mcp_servers`."""
    from dna.emit import project_agent_mcp_servers

    doc = mi.find_agent(target_name)
    spec = getattr(doc, "spec", None) if doc is not None else None
    if spec is None:
        return []
    return project_agent_mcp_servers(mi, spec)


def _make_run_local(mi: Any, hooks: RuntimeHooks) -> Callable[[str, str], Awaitable[str]]:
    """`run_local(target_name, request) -> str` — compose `target_name`
    through the SAME `mi` (so a target's own model/instructions resolve
    exactly as they would if it were built directly), give it the tools ITS
    OWN `mcp_servers` declares (via `mcp_tool_stack` — the SAME
    discover-then-allowlist seam `LangChainRuntime.build` wires for the
    mounted agent, reused rather than reimplemented, and fail-closed to the
    TARGET's own `allowed_tools` — a delegate reaches no more than it would
    reach mounted directly), and run ONE turn with `request` as the sole
    human message.

    Isolation of context (the stated reason for the market pattern this
    follows — LangChain subagents, current recommendation since March/2026):
    no checkpointer, no store, no prior messages — a fresh graph per call, so
    the sub-run has its own state and never sees the delegator's history.
    Gaining tools is not gaining the delegator's context: the task is still
    the ONLY thing that crosses into the sub-run.

    ── The host's tools and middleware DO cross ─────────────────────────────

    They did not, and that was a defect with two faces.

    The visible one: an agent whose whole job runs on a host tool could not do
    its job when delegated to. `create_agent(tools=[])` meant the sub-run got
    the target's MCP tools and NOTHING the host registered — so a converter
    agent that writes its proposal through a host `update_document_draft`
    reached the model with that tool absent, and the model, having no way to
    do the work, narrated it instead. Nothing errored.

    The quieter one: the sub-run escaped every host MIDDLEWARE — the
    auth-graceful wrapper, the attachment extraction, every post-tool
    projection. A sub-run outside host policy is not isolation; it is a hole
    in policy that only appears on the delegated path.

    Both are fixed by passing `hooks.extensions` through. This is not a
    loosening: host tools are host-wide in this runtime BY CONSTRUCTION — the
    LangChain adapter registers them for the mounted agent without consulting
    its allowlist, and passes their names to `mcp_tool_stack` as
    `extra_allowed` precisely so the per-agent MCP allowlist does not filter
    them out. The sub-run now sees the same host surface the mounted agent
    sees. What stays per-agent and fail-closed is exactly what already was:
    the MCP tools, resolved from the TARGET's own `mcp_servers`.

    `delegate_to` itself is NOT among them, and that needs no filtering: this
    closure captures `hooks` BEFORE `build_runtime` appends the tool to a
    REPLACED hooks object, so the sub-agent cannot delegate onward. That is
    load-bearing (a delegation cycle would recurse until the stack died), so
    it is asserted by a test rather than left to the reader.

    `hooks.mcp_auth` is reused VERBATIM for the target's own
    `DnaMcpToolsMiddleware` — see `mcp_tool_stack`'s docstring for why that is
    not a fabricated credential: it is the same per-request hook, re-read at
    call time, exactly as its own contract already documents.

    Heavy imports deferred to call time, same discipline as
    `LangChainRuntime.build`.
    """

    async def run_local(target_name: str, request: str) -> str:
        from langchain.agents import create_agent
        from langchain.chat_models import init_chat_model
        from langchain_core.messages import HumanMessage

        from dna.emit import build_emit_context
        from dna.runtime.adapters.langchain_rt import mcp_tool_stack

        target_ctx, mcp_servers = await asyncio.to_thread(
            lambda: (
                build_emit_context(mi, target_name),
                _target_mcp_servers(mi, target_name),
            )
        )
        extensions = hooks.extensions or {}
        host_tools = list(extensions.get("tools") or [])
        host_middleware = list(extensions.get("middleware") or [])

        # The host tools' names ride into `extra_allowed` for the same reason
        # the adapter does it for the mounted agent: they are not MCP tools, so
        # the per-agent MCP allowlist would filter them out of the model call.
        extra_allowed = frozenset(
            n for n in (getattr(t, "name", None) for t in host_tools) if n
        )
        middleware, _allowed = mcp_tool_stack(
            mcp_servers, hooks.mcp_auth, extra_allowed=extra_allowed
        )
        model = target_ctx.model or "gpt-5-mini"
        graph = create_agent(
            model=init_chat_model(f"openai:{model}"),
            tools=host_tools,
            system_prompt=target_ctx.instructions or "",
            middleware=[*middleware, *host_middleware],
        )
        result = await graph.ainvoke({"messages": [HumanMessage(content=request)]})
        final_message = result["messages"][-1]
        return str(getattr(final_message, "content", final_message))

    return run_local


def _make_call_remote(hooks: RuntimeHooks) -> Callable[..., Awaitable[str]]:
    """Wired to `dna.application.a2a_transport.call_remote` — never
    reimplemented. `credential_for` is host-supplied via
    `hooks.extensions["delegation_credential_for"]` (a
    `Callable[[str], str | None]`); absent, it defaults to "no credential for
    anyone", which `call_remote` itself turns into a `DelegationRefused`
    (its own documented behavior: absence of a credential refuses rather than
    calling anonymously) — never a silent default identity.
    """
    from dna.application.a2a_transport import call_remote as _a2a_call_remote

    credential_for = (hooks.extensions or {}).get("delegation_credential_for") or (
        lambda _name: None
    )

    async def call_remote(target: Any, request: str) -> str:
        import httpx

        async with httpx.AsyncClient() as client:
            return await _a2a_call_remote(
                target, request, credential_for=credential_for, http=client
            )

    return call_remote


def _maybe_build_delegate_tool(
    mi: Any,
    delegator: str,
    team_members: list[str],
    documents: list[dict],
    hooks: RuntimeHooks,
) -> Any | None:
    """The central A.1 property: gated on `team_members` — the raw
    declaration — never on whether the roster happens to resolve non-empty."""
    if not team_members:
        return None
    from dna.application.delegation_tool import make_delegate_tool

    return make_delegate_tool(
        delegator=delegator,
        documents=documents,
        run_local=_make_run_local(mi, hooks),
        call_remote=_make_call_remote(hooks),
        # O terceiro transporte. O host o fornece por extensão — sem ele um
        # alvo longo roda in-process como sempre, que é a degradação
        # deliberada: um deployment sem worker continua funcionando.
        enqueue=(hooks.extensions or {}).get("delegation_enqueue"),
    )


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

    # A.1 — delegate_to: only when the mounted agent DECLARES team_members
    # (never a hand-kept list of names). See the module docstring for why
    # this lives here and not in the LangChain adapter.
    team_members, documents = await asyncio.to_thread(
        _team_members_and_documents, mi, ctx.name
    )
    tool = _maybe_build_delegate_tool(mi, ctx.name, team_members, documents, hooks)
    if tool is not None:
        extensions = dict(hooks.extensions or {})
        extensions["tools"] = [*(extensions.get("tools") or []), tool]
        hooks = replace(hooks, extensions=extensions)

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
