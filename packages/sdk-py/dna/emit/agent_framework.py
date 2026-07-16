"""DNA → Microsoft **agent-framework** emitter (the first proven target).

Materializes an :class:`~dna.emit.EmitContext` into the declarative
``PromptAgent`` YAML that ``agent-framework-declarative``'s ``AgentFactory``
loads (``create_agent_from_yaml`` / ``create_agent_from_yaml_path``). Proven in
the pivot spike: the emitted ``instructions`` are byte-equal to the DNA-composed
prompt, and the artifact loads into a live agent-framework ``Agent`` object.

The de-para (DNA field → PromptAgent field):

    metadata.name                     -> name         (CamelCased id)
    metadata.description              -> description
    Soul + guardrails + instruction   -> instructions (flat — kernel-composed)
      (composed by build_prompt)
    spec.model (or Genome default_llm)-> model.{id, provider}
    spec.tools[] (Tool Kind surfaces) -> tools[] (kind: function)
    spec.output_schema                -> outputSchema (only when present)

What does NOT survive (no PromptAgent slot — the DNA-only value, recorded in
``EmitResult.losses``):
    - composition STRUCTURE: Soul reuse + Guardrail-as-a-wired-doc collapse to a
      flat ``instructions`` string. The structure is a DNA authoring-time concept.
    - tenant overlay: a per-tenant persona without a fork — no PromptAgent field.
    - eval-as-contract: prompt invariants asserted as EvalCases — no slot.
"""
from __future__ import annotations

from typing import Any

from dna.emit import EmitArtifact, EmitContext, EmitError, EmitResult

#: Map a DNA provider token → the agent-framework ``model.provider`` value.
#: agent-framework's declarative loader binds a chat client by provider name;
#: these are the providers its ``AgentFactory`` resolves. Unknown tokens pass
#: through unchanged (so a future provider works without a code change).
_PROVIDER_MAP = {
    "azure": "AzureOpenAI",
    "azureopenai": "AzureOpenAI",
    "azure_openai": "AzureOpenAI",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "foundry": "AzureAIFoundry",
    "azureaifoundry": "AzureAIFoundry",
}

#: When the DNA model is bare (no provider token) and no ``--provider`` is given,
#: default to AzureOpenAI — the provider the spike proved and the common Foundry
#: deployment. Documented as an emitter default, never silently wrong.
_DEFAULT_PROVIDER = "AzureOpenAI"


def _camel(name: str) -> str:
    """``concierge-grounded`` → ``ConciergeGrounded`` (a valid PromptAgent id)."""
    return "".join(part.capitalize() for part in str(name).replace("_", "-").split("-") if part)


def _split_model(model: str | None, provider_hint: str | None) -> dict[str, str] | None:
    """Split a DNA model coordinate into agent-framework ``{id, provider}``.

    Accepts ``prov:model`` (``openai:gpt-4o-mini``), ``prov/model``
    (``azure/gpt-4o``), or a bare id (``gpt-4o``). An explicit ``provider_hint``
    (CLI ``--provider``) always wins.
    """
    if not model:
        return None
    token: str | None = None
    ident = model
    for sep in (":", "/"):
        if sep in model:
            token, ident = model.split(sep, 1)
            break
    if provider_hint:
        provider = provider_hint
    elif token:
        provider = _PROVIDER_MAP.get(token.strip().lower(), token)
    else:
        provider = _DEFAULT_PROVIDER
    return {"id": ident.strip(), "provider": provider}


def _emit_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project neutral tool surfaces → agent-framework declarative ``tools``.

    Each Tool becomes a ``kind: function`` entry — the shape the agent-framework
    declarative **AgentSchema** uses for a declared function tool
    (``microsoft.github.io/AgentSchema`` — tool kinds: function, openapi,
    code_interpreter, file_search, mcp, web_search, custom): a ``name``, a
    ``description`` (the text the model reads), and ``parameters`` (the input
    contract the model fills in). This is exactly the surface ``dna.load_tools``
    serves, so the emitted tool is byte-identical to what a Python ``@tool`` or a
    TS ``useCopilotAction`` would show.

    ``parameters`` is carried as the Tool's JSON Schema (``spec.input_schema``) —
    the faithful, source-of-truth representation of the arguments. (AgentSchema
    also accepts a flattened ``{param: {kind, description}}`` map; DNA emits the
    full JSON Schema so nested/required structure is not lost — a documented
    fidelity choice.)
    """
    out: list[dict[str, Any]] = []
    for t in tools:
        entry: dict[str, Any] = {
            "name": t["name"],
            "kind": "function",
            "description": t.get("description", ""),
        }
        params = t.get("parameters") or {}
        if params:
            entry["parameters"] = params
        out.append(entry)
    return out


def _py_list_literal(items: list[str]) -> str:
    """A Python list literal (``['a', 'b']``) built from ``py_str_literal`` so the
    quote style tracks the language (repr single-quotes in Py; the TS twin uses
    JSON double-quotes) — the shared scaffold-literal convention."""
    from dna.emit.scaffold import py_str_literal

    return "[" + ", ".join(py_str_literal(x) for x in items) + "]"


def _approval_mode_literal(gated: list[str], reads: list[str]) -> str:
    """The MS-AF ``approval_mode`` dict literal — ``{'always_require_approval':
    [...writes...], 'never_require_approval': [...reads...]}`` — the tool-level HITL
    the emitted MCP mount carries (the analog of Agno's
    ``external_execution_required_tools``)."""
    from dna.emit.scaffold import py_str_literal

    return (
        "{"
        + py_str_literal("always_require_approval") + ": " + _py_list_literal(gated)
        + ", "
        + py_str_literal("never_require_approval") + ": " + _py_list_literal(reads)
        + "}"
    )


class AgentFrameworkEmitter:
    """Emit a DNA agent as an agent-framework declarative ``PromptAgent`` — or, for
    a ``Copilot`` binder (:func:`~dna.emit.build_copilot_context`), a servable
    Microsoft Agent Framework AG-UI app (the ``copilot`` scaffold case).

    Two shapes share this target, exactly like the Agno emitter:

    - A **single agent** — the config-declarative ``PromptAgent`` YAML the
      ``AgentFactory`` loads (the inherited de-para below).
    - A **servable copilot** (any copilot-only signal on the ctx) — a TWO-artifact
      scaffold emit: an ``agent`` module (``build_agent``/``build_workflow`` factory
      via ``FoundryChatClient(...).as_agent(...)`` + the ``MCPStreamableHTTPTool``
      mount with ``approval_mode`` tool-level HITL + the inbound-tenant ContextVar/
      header_provider bridge) and a ``serving`` module
      (``add_agent_framework_fastapi_endpoint`` → ``/agui``). When the Copilot
      declares a ``workflow.chain`` the agent module emits a ``WorkflowBuilder``
      chain + a workflow-level ``request_info`` escalation node instead of a plain
      single agent.
    """

    target = "agent-framework"
    file_extension = "agent.yaml"
    #: Subdir under ``scaffolds/`` holding this framework's copilot-case templates.
    framework = "agent_framework"

    # ── copilot-case routing (mirrors AgnoEmitter) ──────────────────────────

    def _is_copilot(self, ctx: EmitContext) -> bool:
        """A ctx from :func:`build_copilot_context` carries copilot-only
        projections a single-agent ctx never has; any one present routes the emit
        to the servable Microsoft Agent Framework ``copilot`` case."""
        return bool(
            ctx.mcp_servers
            or ctx.tools_requiring_confirmation
            or ctx.tenant_propagate
            or ctx.knowledge
            or ctx.workflow
        )

    def to_prompt_agent(self, ctx: EmitContext) -> dict[str, Any]:
        """The PURE de-para: :class:`EmitContext` → the PromptAgent dict.

        Parity-critical: the TS twin (`packages/sdk-ts/src/emit/agentFramework.ts`)
        must build the same dict from the same context. Field order is
        intentional and preserved on serialization (``sort_keys=False``)."""
        provider_hint = ctx.options.get("provider") if ctx.options else None
        doc: dict[str, Any] = {"kind": "Prompt", "name": _camel(ctx.name)}
        if ctx.description:
            doc["description"] = ctx.description
        model = _split_model(ctx.model, provider_hint)
        if model:
            doc["model"] = model
        if ctx.tools:
            doc["tools"] = _emit_tools(ctx.tools)
        # instructions carried verbatim — the byte-equal gate.
        doc["instructions"] = ctx.instructions
        if ctx.output_schema:
            doc["outputSchema"] = ctx.output_schema
        return doc

    def emit(self, ctx: EmitContext) -> EmitResult:
        if self._is_copilot(ctx):
            return self._emit_copilot(ctx)
        import yaml

        prompt_agent = self.to_prompt_agent(ctx)
        artifact = yaml.safe_dump(prompt_agent, sort_keys=False, allow_unicode=True)

        losses: list[str] = [
            "composition structure — Soul reuse + wired Guardrails flatten to one "
            "`instructions` string (no `soul:`/`guardrails:` slot in a PromptAgent)",
            "tenant overlay — a per-tenant persona without a fork has no PromptAgent field",
            "eval-as-contract — prompt invariants (EvalCases) have no PromptAgent slot",
        ]
        if ctx.model is None:
            losses.append(
                "model unbound in DNA and none supplied — emitted PromptAgent has no "
                "`model:` block; pass --model or set the agent's spec.model / Genome default_llm"
            )

        mapping = {
            "metadata.name": "name (CamelCase)",
            "metadata.description": "description",
            "build_prompt (Soul+guardrails+instruction)": "instructions",
            "spec.model / Genome.default_llm": "model.{id,provider}",
            "spec.tools[] (Tool Kind)": "tools[] (kind: function)",
            "spec.output_schema": "outputSchema",
        }

        return EmitResult(
            artifact=artifact,
            target=self.target,
            filename=f"{ctx.name}.{self.file_extension}",
            losses=losses,
            mapping=mapping,
        )

    def extract_instructions(self, artifact: str) -> str | None:
        """Byte-equal invariant hook — handles BOTH emit shapes of this target: the
        single-agent ``PromptAgent`` YAML (``instructions:`` field) AND the servable
        copilot scaffold's ``agent`` module (top-level ``INSTRUCTIONS`` constant).

        The scaffold path is tried first (AST-read the ``INSTRUCTIONS`` constant,
        which also proves the source PARSES); a YAML artifact fails ``ast.parse``
        (or has no such constant) and falls through to the YAML read."""
        import ast

        try:
            module = ast.parse(artifact)
        except SyntaxError:
            module = None
        if module is not None:
            for node in module.body:
                if isinstance(node, ast.Assign):
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name) and tgt.id == "INSTRUCTIONS":
                            return ast.literal_eval(node.value)

        import yaml

        try:
            doc = yaml.safe_load(artifact)
        except yaml.YAMLError:
            return None
        return doc.get("instructions") if isinstance(doc, dict) else None

    # ── servable copilot render (the two-artifact scaffold case) ─────────────

    def _copilot_context(self, ctx: EmitContext) -> dict[str, Any]:
        """Template variables for the Microsoft Agent Framework ``copilot`` case.

        The mounted agent's MCP servers become ``MCPStreamableHTTPTool`` mounts; the
        HITL-write intent (``ctx.tools_requiring_confirmation``) becomes each mount's
        ``approval_mode`` (tool-level HITL) — EXCEPT a workflow copilot gates writes
        at the workflow level, so its mounts use ``never_require`` and an
        ``EscalationExecutor`` (``request_info``) node is emitted instead. Everything
        is sorted for a deterministic golden."""
        from dna.emit.scaffold import py_identifier, py_str_literal

        gated = set(ctx.tools_requiring_confirmation)
        has_workflow = bool(ctx.workflow)
        has_hitl = bool(gated)

        servers: list[dict[str, Any]] = []
        for s in ctx.mcp_servers:
            allowed_sorted = sorted(s.allowed_tools)
            gated_in = sorted(t for t in s.allowed_tools if t in gated)
            reads = sorted(t for t in s.allowed_tools if t not in gated)
            if has_workflow or not gated_in:
                approval = py_str_literal("never_require")
            else:
                approval = _approval_mode_literal(gated_in, reads)
            servers.append(
                {
                    "name_literal": py_str_literal(f"mcp_{s.ref}"),
                    "url_literal": py_str_literal(s.url) if s.url else "None",
                    "allowed_tools_literal": _py_list_literal(allowed_sorted),
                    "approval_mode_literal": approval,
                }
            )

        steps: list[dict[str, Any]] = []
        for i, step in enumerate(ctx.workflow):
            steps.append(
                {
                    "step": step,
                    "func": py_identifier(step),
                    "name_literal_step": py_str_literal(step),
                    "is_first": i == 0,
                }
            )
        chain_funcs = [py_identifier(s) for s in ctx.workflow]
        if has_workflow and has_hitl:
            chain_funcs = chain_funcs + ["escalate"]

        build_fn = "build_workflow" if has_workflow else "build_agent"
        mounted_kind = "workflow" if has_workflow else "agent"
        serve_agent_expr = (
            "AgentFrameworkWorkflow(workflow_factory=build_workflow)"
            if has_workflow
            else "build_agent()"
        )

        return {
            "name": ctx.name,
            "name_literal": py_str_literal(ctx.name),
            "instructions_literal": py_str_literal(ctx.instructions),
            "agent_module": py_identifier(ctx.name),
            "has_model": ctx.model is not None,
            "model_literal": py_str_literal(ctx.model) if ctx.model else "",
            "has_mcp": bool(ctx.mcp_servers),
            "mcp_servers": servers,
            "tenant_propagate": bool(ctx.tenant_propagate),
            "has_hitl": has_hitl,
            "has_workflow": has_workflow,
            "workflow_steps": steps,
            "workflow_name_literal": py_str_literal(_camel(ctx.name)),
            "first_func": py_identifier(ctx.workflow[0]) if ctx.workflow else "",
            "chain_func_list": ", ".join(chain_funcs),
            "build_fn": build_fn,
            "mounted_kind": mounted_kind,
            "serve_agent_expr": serve_agent_expr,
        }

    def _copilot_losses(self, ctx: EmitContext) -> list[str]:
        out = [
            "composition structure — Soul reuse + wired Guardrails flatten to one "
            "`INSTRUCTIONS` string (a code-first agent has no `soul:`/`guardrails:` slot)",
            "tenant overlay — a per-tenant persona without a fork has no code-first field",
            "eval-as-contract — prompt invariants (EvalCases) have no code-first slot",
            "MCP tool bodies — the mounted agent calls the DNA MCP server's tools over "
            "Streamable HTTP; the emitted app builds `MCPStreamableHTTPTool(...)` but the "
            "tool implementations live on the remote MCP server, not in the scaffold",
            "frontend console — `frontend`/`knowledge` hints (CopilotKit panels, suggested "
            "prompts, RAG collections) have no code-first backend slot; RAG retrieval "
            "(`AzureAISearchContextProvider`) is per-app",
        ]
        if ctx.workflow:
            out.append(
                "workflow step bodies — each `workflow.chain` step is a scaffolded "
                "agent-executor STUB; per-step instructions + the escalation effect are "
                "per-app bodies to wire at the consumer"
            )
        if ctx.model is None:
            out.append(
                "model unbound in DNA and none supplied — emitted `FoundryChatClient(...)` "
                "has no `model=`; supply one at wire-up"
            )
        return out

    def _copilot_mapping(self) -> dict[str, str]:
        return {
            "build_prompt (Soul+guardrails+instruction)": "INSTRUCTIONS constant (byte-equal)",
            "metadata.name": "as_agent(name=...)",
            "spec.model / Genome.default_llm": "FoundryChatClient(model=...)",
            "Agent.spec.mcp_servers → MCPFederation": "MCPStreamableHTTPTool(url, allowed_tools, approval_mode)",
            "Tool.requires_confirmation": "approval_mode.always_require_approval (tool-level HITL)",
            "Copilot.tenant.propagate": "inbound ContextVar + header_provider (X-DNA-* stamp)",
            "Copilot.workflow.chain": "WorkflowBuilder chain + request_info escalation node",
        }

    def _emit_copilot(self, ctx: EmitContext) -> EmitResult:
        """Render the two servable artifacts (agent module + AG-UI serve app) from an
        enriched copilot ctx (:func:`build_copilot_context`)."""
        try:
            import chevron
        except ModuleNotFoundError as exc:  # pragma: no cover - dev dep always present
            raise EmitError(
                "the scaffold emitter needs `chevron` (Mustache) — it ships with the SDK"
            ) from exc

        from dna.emit.scaffold import resolve_scaffold

        agent_tmpl = resolve_scaffold(self.framework, "copilot_agent")
        serve_tmpl = resolve_scaffold(self.framework, "copilot_serve")
        if agent_tmpl is None or serve_tmpl is None:
            raise EmitError(
                "the agent-framework `copilot` case needs both `copilot_agent.py.tmpl` "
                "and `copilot_serve.py.tmpl` scaffold templates"
            )

        variables = self._copilot_context(ctx)
        agent_src = chevron.render(agent_tmpl, variables)
        serve_src = chevron.render(serve_tmpl, variables)
        module = variables["agent_module"]

        return EmitResult(
            target=self.target,
            artifacts=[
                EmitArtifact(path=f"{module}.py", content=agent_src, role="agent"),
                EmitArtifact(path=f"{module}_serve.py", content=serve_src, role="serving"),
            ],
            losses=self._copilot_losses(ctx),
            mapping=self._copilot_mapping(),
        )
