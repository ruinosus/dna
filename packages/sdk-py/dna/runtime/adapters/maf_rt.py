"""MafRuntime — the `dna.runtime.port` adapter for **Microsoft Agent Framework**
(Foundry) served over AG-UI. Target `"maf"`, selected by `serving.framework: maf`.

Where `LangChainRuntime` assembles a LangGraph copilot, this adapter builds the
SAME neutral shapes the `dna.emit.agent_framework` emitter renders as source —
only PROGRAMMATICALLY: a Foundry-backed `ChatAgent`
(`FoundryChatClient(...).as_agent(...)`) that federates the DNA MCP server via
`MCPStreamableHTTPTool`, then serves it at `/agui` through
`add_agent_framework_fastapi_endpoint`.

The four DNA disciplines, wired into MAF's native mechanisms:

- **allowlist (i-038)** — `MCPStreamableHTTPTool(allowed_tools=...)` bounds which
  federated tools the model may call, per the server's declared `allowed_tools`.
- **HITL** — `MCPStreamableHTTPTool(approval_mode=...)`: the tools in
  `ctx.tools_requiring_confirmation` become `always_require_approval`, the rest
  `never_require_approval` (the `MCPSpecificApproval` per-tool shape). No gated
  tool ⇒ the plain `"never_require"` literal (mirrors the emitter).
- **lazy-MCP** — `MCPStreamableHTTPTool.__init__` does NOT dial: it stores config
  and connects lazily when the agent first runs (verified against
  agent-framework-core 1.12.1 — construction with sockets blocked succeeds).
  Build therefore makes ZERO network call and needs ZERO credential; the
  per-request bearer is threaded via `header_provider`, invoked by MAF on every
  outbound MCP request (never at construction).
- **compose (i-040)** — the DNA-composed base prompt is carried as the agent's
  static `instructions` (`ctx.instructions`), byte-equal, exactly as the emitter
  wires `INSTRUCTIONS`. Per-request live re-composition (`hooks.compose`) is NOT
  wired into MAF's neutral core in C0: MAF's `Agent` takes a static `instructions`
  at build and has no per-run request-header context without a host-owned
  serving-layer ContextVar bridge (the same bridge the emitter's tenant
  header_provider needs). That is an explicit follow-on, not this task — see the
  C0 Task 5 report.

Host extensions (the dna-cloud composer draft door, i-061 gate, auth-graceful,
timeline) are LangChain middleware and are deliberately NOT ported here: the MAF
adapter proves the neutral core only (C0 Global Constraints).

All `agent_framework` / `azure` imports are deferred into `build`/`attach`, so
importing this module needs only the base SDK — the `[maf]` extra is required to
`build`, not to register. `dna.runtime.port._ensure_runtimes` imports the class
lazily and guards the import, so a missing extra degrades gracefully.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dna.runtime.port import RuntimeHooks


def _project_config(
    ctx: Any,
) -> tuple[str, str | None, frozenset[str], frozenset[str]]:
    """Project the neutral `(instructions, model, allowed_tools, confirm_tools)`
    from an already-composed `EmitContext`. Same allowlist rule as
    `langchain_rt._project_config` (kept in lockstep), reimplemented locally so
    importing this adapter never pulls the `[runtime]`/langchain extra — the MAF
    backend must be usable with only `[maf]` installed."""
    allowed = {
        t
        for s in (getattr(ctx, "mcp_servers", None) or [])
        for t in (getattr(s, "allowed_tools", None) or [])
    }
    # The Tool-doc alias `list` runs as `list_memories` (federation doc note).
    if "list" in allowed:
        allowed.add("list_memories")
    confirm = frozenset(getattr(ctx, "tools_requiring_confirmation", None) or [])
    return (ctx.instructions or "", ctx.model, frozenset(allowed), confirm)


def _header_provider(mcp_auth: Any):
    """Bridge the host's `hooks.mcp_auth` into a MAF `MCPStreamableHTTPTool`
    `header_provider` — `Callable[[dict], dict[str, str]]`, invoked by MAF on
    EVERY outbound MCP request (not once at construction), which is what makes
    the bearer genuinely per-request.

    The dna-cloud host hook is a zero-arg `Callable[[], dict]` (re-reads the
    request headers at call time — `copilot_hooks.make_mcp_auth`); an
    `httpx.Auth`-style object (per the `RuntimeHooks.mcp_auth` doc) is also
    accepted by driving its `auth_flow` over a throwaway request and lifting the
    stamped headers. `None` ⇒ no provider (no auth)."""
    if mcp_auth is None:
        return None

    if callable(mcp_auth) and not hasattr(mcp_auth, "auth_flow"):

        def provider(_existing: dict) -> dict:
            return dict(mcp_auth() or {})

        return provider

    if hasattr(mcp_auth, "auth_flow"):

        def provider(_existing: dict) -> dict:  # httpx.Auth-style
            import httpx

            req = httpx.Request("POST", "http://dna-mcp.local/")
            before = set(req.headers)
            for _ in mcp_auth.auth_flow(req):
                break
            return {k: v for k, v in req.headers.items() if k not in before}

        return provider

    return None


def _approval_mode(allowed: list[str], confirm: frozenset[str]):
    """The MAF `approval_mode` for one MCP mount. Gated tools (writes in
    `ctx.tools_requiring_confirmation`) become `always_require_approval`; the
    rest `never_require_approval` — the `MCPSpecificApproval` per-tool HITL. No
    gated tool ⇒ the plain `"never_require"` literal (mirrors the emitter)."""
    gated = sorted(t for t in allowed if t in confirm)
    if not gated:
        return "never_require"
    reads = sorted(t for t in allowed if t not in confirm)
    return {"always_require_approval": gated, "never_require_approval": reads}


@dataclass
class _MafAGUIApp:
    """The `AGUIApp` `MafRuntime.build` returns. `graph` is `None` — MAF has no
    LangGraph-shaped state, so host rehydration for MAF is an explicit follow-on
    (not this task). `attach` mounts MAF's native AG-UI endpoint, imported
    lazily so constructing this handle never requires the `[maf]` extra."""

    agent: Any
    graph: Any = None

    def attach(self, app: Any, path: str = "/agui") -> None:
        from agent_framework.ag_ui import add_agent_framework_fastapi_endpoint

        add_agent_framework_fastapi_endpoint(app, agent=self.agent, path=path)


class MafRuntime:
    """The Microsoft Agent Framework / Foundry `RuntimePort` — target `"maf"`,
    selected by `serving.framework: maf`."""

    target = "maf"

    async def build(self, ctx: Any, hooks: RuntimeHooks) -> _MafAGUIApp:
        # Deferred so importing this module (and thus registering "maf") needs
        # only the base SDK; the [maf] extra is required to build, not to list.
        from agent_framework import MCPStreamableHTTPTool
        from agent_framework.foundry import FoundryChatClient
        from azure.identity import DefaultAzureCredential

        instructions, model, allowed_tools, confirm = _project_config(ctx)

        mcp_servers = getattr(ctx, "mcp_servers", None) or []
        if not mcp_servers:
            raise ValueError(
                f"copilot {getattr(ctx, 'name', '?')!r} declares no mcp_servers; "
                "MafRuntime requires the mounted agent to federate at least one "
                "MCP server"
            )

        header_provider = _header_provider(hooks.mcp_auth)

        # Mount each declared MCP server. Construction is LAZY — no dial, no
        # credential (verified: MCPStreamableHTTPTool.__init__ stores config and
        # connects on first run). allowed_tools = the server's declared
        # allowlist (i-038); approval_mode = the HITL projection.
        tools = []
        for s in mcp_servers:
            allowed = sorted(getattr(s, "allowed_tools", None) or [])
            tools.append(
                MCPStreamableHTTPTool(
                    name=f"mcp_{s.ref}",
                    url=s.url,
                    allowed_tools=allowed,
                    approval_mode=_approval_mode(allowed, confirm),
                    header_provider=header_provider,
                )
            )

        # ctx.model wins (declarative-first — no OPENAI_MODEL/env override). A
        # Foundry-backed ChatAgent: DefaultAzureCredential() is lazy (no token
        # fetch at construction — zero credential at build). instructions carry
        # the DNA-composed base prompt byte-equal (see module docstring on the
        # i-040 per-request-compose follow-on).
        client_kwargs: dict[str, Any] = {"credential": DefaultAzureCredential()}
        if model:
            client_kwargs["model"] = model
        client = FoundryChatClient(**client_kwargs)

        agent = client.as_agent(
            name=getattr(ctx, "name", "agent"),
            instructions=instructions,
            tools=tools,
        )

        return _MafAGUIApp(agent=agent)
