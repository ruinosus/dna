"""DNA → **Agno** emitter (code-first, ``agno.agent``).

Agno is code-first: you build an agent by constructing an object —
``Agent(name=..., model=..., instructions=..., tools=[...])`` — there is no
declarative agent file to map onto. So this target is a
:class:`~dna.emit.scaffold.ScaffoldEmitter`: it fills a curated ``{agno × case}``
template rather than generating code ad-hoc, and the emitted ``INSTRUCTIONS``
constant is byte-equal to the DNA-composed prompt.

The de-para (DNA field → Agno source):

    build_prompt (Soul+guardrails+instruction) -> INSTRUCTIONS constant (BYTE-EQUAL)
      (composed, flat)                             → Agent(instructions=INSTRUCTIONS)
    metadata.name                     -> Agent(name=...)   (the display name)
    spec.model (or Genome default_llm)-> Agent(model=...)  (DNA coordinate PRESERVED —
                                         Agno accepts a `provider:model` string)
    spec.tools[] (Tool Kind surfaces) -> plain-function stubs passed to tools=[...]
                                         (with-tools case only; Agno auto-wraps
                                         plain callables as tools)

Cases (selected by the classifier from ctx signals):
    - ``prompt-only``  — no tools: the minimal ``Agent(name, model, instructions)``.
    - ``with-tools``   — tools present: one plain-function stub per DNA Tool wired
                         into ``tools=[...]`` (Agno turns a callable into a tool).
    (``structured-output`` — Agno has ``output_schema`` — is not shipped yet; it
    falls back with a recorded loss.)

What does NOT survive (recorded in ``EmitResult.losses``): the DNA-only axes
(composition structure / tenant overlay / eval-as-contract), plus — code-first
specific — a Tool's real BODY and typed signature (each stub is a bare callable),
and the model-coordinate assumption (the string form assumes Agno's string-model
resolution; a specific ``Model`` object — e.g. ``OpenAIChat(id=...)`` — is the
alternative at wire-up).
"""
from __future__ import annotations

from typing import Any

from dna.emit import EmitArtifact, EmitContext, EmitError, EmitResult
from dna.emit.scaffold import (
    ScaffoldChoice,
    ScaffoldEmitter,
    py_identifier,
    py_str_literal,
    resolve_scaffold,
)


class AgnoEmitter(ScaffoldEmitter):
    """Emit a DNA agent as Agno ``Agent(...)`` source (scaffold, code-first).

    Two shapes share this target:

    - A **single agent** (``prompt-only`` / ``with-tools``) — one ``Agent(...)``
      module, byte-equal ``INSTRUCTIONS``. The inherited :class:`ScaffoldEmitter`
      machinery drives it.
    - A **servable copilot** (``copilot`` case, from
      :func:`~dna.emit.build_copilot_context`) — a TWO-artifact emit: an ``agent``
      module (``build_agent`` factory + MCP mount + the HITL write-gate) and a
      ``serving`` module (Agno AgentOS exposing ``/agui``, with inbound-tenant
      derivation). Agno 2.7.x resumes ``external_execution`` gates natively inside
      its AG-UI router, so the emitted app carries no hand-rolled resume machinery
      — the DNA MCP write tools are gated DIRECTLY on the remote tool (Spike 0A:
      gate-remote-directly) and the router pauses/resumes them.
    """

    framework = "agno"
    target = "agno"
    file_extension = "py"

    # ── copilot case routing ────────────────────────────────────────────────

    def _is_copilot(self, ctx: EmitContext) -> bool:
        """A ctx from :func:`build_copilot_context` carries copilot-only
        projections a single-agent ctx never has. Any one of them present routes
        the emit to the servable ``copilot`` case."""
        return bool(
            ctx.mcp_servers
            or ctx.tools_requiring_confirmation
            or ctx.tenant_propagate
            or ctx.knowledge
        )

    def classify(self, ctx: EmitContext) -> str:
        if self._is_copilot(ctx):
            return "copilot"
        return super().classify(ctx)

    def emit(self, ctx: EmitContext) -> EmitResult:
        if self.classify(ctx) == "copilot":
            return self._emit_copilot(ctx)
        return super().emit(ctx)

    # ── single-agent render (prompt-only / with-tools) ──────────────────────

    def render_context(self, ctx: EmitContext, case: str) -> dict[str, Any]:
        tools = [
            {
                "name": t["name"],
                "func_name": py_identifier(t["name"]),
                "docstring_literal": py_str_literal(t.get("description") or t["name"]),
            }
            for t in ctx.tools
        ]
        return {
            "has_model": ctx.model is not None,
            "model_literal": py_str_literal(ctx.model) if ctx.model else "",
            "tools": tools,
            "tool_list": ", ".join(t["func_name"] for t in tools),
        }

    def losses(self, ctx: EmitContext, choice: ScaffoldChoice) -> list[str]:
        out: list[str] = []
        if ctx.tools:
            out.append(
                "tool body — each tool is a scaffolded STUB (a bare callable + "
                "`raise NotImplementedError`); its real implementation and typed "
                "signature must be wired (Agno derives the tool schema from the "
                "function signature + docstring)"
            )
        if ctx.model is None:
            out.append(
                "model unbound in DNA and none supplied — emitted `Agent(...)` has no "
                "`model=`; supply one at wire-up (Agno requires a model)"
            )
        else:
            out.append(
                "model coordinate — the DNA coordinate is carried verbatim as a "
                "string; this assumes Agno's string-model resolution. A specific "
                "`Model` object (e.g. `OpenAIChat(id=...)`) is the alternative at wire-up"
            )
        if ctx.output_schema:
            out.append(
                "output_schema — map DNA's `spec.output_schema` to "
                "`Agent(output_schema=...)` (a Pydantic model) by hand; the scaffold "
                "does not synthesize the class"
            )
        return out

    def mapping(self) -> dict[str, str]:
        return {
            "build_prompt (Soul+guardrails+instruction)": "INSTRUCTIONS constant (byte-equal)",
            "metadata.name": "Agent(name=...)",
            "spec.model / Genome.default_llm": "Agent(model=...) (DNA coordinate preserved)",
            "spec.tools[] (Tool Kind)": "plain-function stubs → Agent(tools=[...])",
        }

    # ── servable copilot render (the two-artifact case) ─────────────────────

    def _copilot_context(self, ctx: EmitContext) -> dict[str, Any]:
        """Template variables for the ``copilot`` case (merged over the common
        ones). The mounted agent's MCP servers become ``MCPTools`` mounts; the
        HITL-write intent (``ctx.tools_requiring_confirmation``) becomes each
        mount's ``external_execution_required_tools`` (Spike 0A: gate-remote-
        directly). Everything is sorted for a deterministic golden."""
        module = py_identifier(ctx.name)
        gated = sorted(ctx.tools_requiring_confirmation)
        servers = []
        for s in ctx.mcp_servers:
            servers.append(
                {
                    "url_literal": py_str_literal(s.url) if s.url else "None",
                    "transport_literal": py_str_literal(s.transport),
                    "has_external_tools": bool(gated),
                    "external_tools_literal": repr(gated),
                }
            )
        return {
            "agent_module": module,
            "has_model": ctx.model is not None,
            "model_literal": py_str_literal(ctx.model) if ctx.model else "",
            "has_mcp": bool(ctx.mcp_servers),
            "mcp_servers": servers,
            "tenant_propagate": bool(ctx.tenant_propagate),
            "has_knowledge": bool(ctx.knowledge),
            "knowledge_refs": ", ".join(ctx.knowledge),
        }

    def _copilot_losses(self, ctx: EmitContext) -> list[str]:
        out = [
            "MCP tool bodies — the mounted agent calls the DNA MCP server's tools "
            "over Streamable HTTP; the emitted app builds `MCPTools(...)` but the "
            "tool implementations live on the remote MCP server, not in the scaffold",
            "frontend console — `frontend` hints (CopilotKit panels, suggested "
            "prompts) are copilot-level metadata with no code-first backend slot; "
            "wire them in the console at the UI layer",
        ]
        if ctx.knowledge:
            out.append(
                "knowledge retrieval impl — the emitted `_knowledge()` factory is a "
                "WIRING POINT carrying the DNA collection refs; the vector store + "
                "embedder behind it (Agno `Knowledge`/`PgVector`) is per-app (§6.3)"
            )
        if ctx.model is None:
            out.append(
                "model unbound in DNA and none supplied — emitted `build_agent()` has "
                "no `model=`; supply one at wire-up (Agno requires a model)"
            )
        return out

    def _emit_copilot(self, ctx: EmitContext) -> EmitResult:
        """Render the two servable artifacts (agent module + AG-UI serve app) from
        an enriched copilot ctx (:func:`build_copilot_context`)."""
        try:
            import chevron
        except ModuleNotFoundError as exc:  # pragma: no cover - dev dep always present
            raise EmitError(
                "the scaffold emitter needs `chevron` (Mustache) — it ships with the SDK"
            ) from exc

        agent_tmpl = resolve_scaffold(self.framework, "copilot_agent")
        serve_tmpl = resolve_scaffold(self.framework, "copilot_serve")
        if agent_tmpl is None or serve_tmpl is None:
            raise EmitError(
                "the agno `copilot` case needs both `copilot_agent.py.tmpl` and "
                "`copilot_serve.py.tmpl` scaffold templates"
            )

        variables = {**self._common_context(ctx), **self._copilot_context(ctx)}
        agent_src = chevron.render(agent_tmpl, variables)
        serve_src = chevron.render(serve_tmpl, variables)
        module = variables["agent_module"]

        # A servable copilot never "falls back" a case — mark case == requested so
        # the common-loss helper adds no spurious fallback note.
        choice = ScaffoldChoice(case="copilot", template="", requested="copilot")
        losses = self._common_losses(ctx, choice) + self._copilot_losses(ctx)

        return EmitResult(
            target=self.target,
            artifacts=[
                EmitArtifact(path=f"{module}.py", content=agent_src, role="agent"),
                EmitArtifact(path=f"{module}_serve.py", content=serve_src, role="serving"),
            ],
            losses=losses,
            mapping=self.mapping(),
        )
