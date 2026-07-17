"""DNA → **LangGraph** emitter (code-first, ``langgraph.prebuilt``).

LangGraph is code-first: you build an agent by calling a constructor —
``create_react_agent(model, tools=[...], prompt="...")`` — there is no declarative
agent file to map onto. So this target is a
:class:`~dna.emit.scaffold.ScaffoldEmitter`: it fills a curated
``{langgraph × case}`` template rather than generating code ad-hoc, and the
emitted ``INSTRUCTIONS`` constant is byte-equal to the DNA-composed prompt.

The de-para (DNA field → LangGraph source):

    build_prompt (Soul+guardrails+instruction) -> INSTRUCTIONS constant (BYTE-EQUAL)
      (composed, flat)                             → create_react_agent(prompt=INSTRUCTIONS)
    metadata.name                     -> create_react_agent(name=...)  (graph name)
    spec.model (or Genome default_llm)-> create_react_agent(model=...) (DNA coordinate
                                         PRESERVED — LangGraph resolves it via
                                         `init_chat_model`, which takes `provider:model`)
    spec.tools[] (Tool Kind surfaces) -> @tool stubs passed to tools=[...]
                                         (with-tools case only)

Cases (selected by the classifier from ctx signals):
    - ``prompt-only``  — no tools: a ReAct agent with an empty tool list.
    - ``with-tools``   — tools present: the canonical ReAct idiom, one
                         ``@tool`` stub per DNA Tool wired into ``tools=[...]``.
    (``structured-output`` — LangGraph has ``response_format`` — is not shipped
    yet; it falls back with a recorded loss.)

What does NOT survive (recorded in ``EmitResult.losses``): the DNA-only axes
(composition structure / tenant overlay / eval-as-contract), plus — code-first
specific — a Tool's real BODY and typed signature (each ``@tool`` is a scaffolded
stub), and the model-coordinate convention (``create_react_agent`` resolves the
string via ``init_chat_model``, whose provider prefixes are ``openai`` /
``anthropic`` / ``azure_openai`` / ``google_genai`` — a DNA ``azure/…`` coordinate
needs the ``azure_openai:`` prefix, or a model instance, at wire-up).
"""
from __future__ import annotations

from typing import Any

from dna.emit import EmitArtifact, EmitContext, EmitError, EmitResult
from dna.emit.scaffold import (
    ScaffoldChoice,
    ScaffoldEmitter,
    persistence_facts,
    pg_url_expr,
    py_identifier,
    py_str_literal,
    resolve_scaffold,
)


def _py_list_literal(items: list[str]) -> str:
    """A Python list literal (``['a', 'b']``) built from ``py_str_literal`` so the
    quote style tracks the language (repr single-quotes in Py; the TS twin uses
    JSON double-quotes) — the shared scaffold-literal convention."""
    return "[" + ", ".join(py_str_literal(x) for x in items) + "]"


def _py_set_literal(items: list[str]) -> str:
    """A Python set literal (``{'a', 'b'}``) for a membership-tested constant —
    the emitted ``_READ_TOOLS`` gate is a set (``name in _READ_TOOLS``)."""
    return "{" + ", ".join(py_str_literal(x) for x in items) + "}"


#: The canonical DNA memory READ tools — the "read-tool → canvas" convention.
#: A mounted read tool from this set (or a declared ``memory-timeline`` frontend
#: panel) turns on the Phase-2 canvas projection: the tool result is projected
#: into the AG-UI shared-state keys ``memory_timeline`` + ``memory_card_html``
#: the DNA console's Memória tab reads. Writes (``remember``/``forget``) are the
#: HITL-gated set and never feed the canvas.
_MEMORY_READ_TOOLS = frozenset({"list", "list_memories", "recall"})


class LanggraphEmitter(ScaffoldEmitter):
    """Emit a DNA agent as LangGraph source (scaffold, code-first).

    Two shapes share this target, exactly like the Agno + agent-framework emitters:

    - A **single agent** (``prompt-only`` / ``with-tools``) — one
      ``create_react_agent`` module, byte-equal ``INSTRUCTIONS``. The inherited
      :class:`ScaffoldEmitter` machinery drives it.
    - A **servable copilot** (``copilot`` case, from
      :func:`~dna.emit.build_copilot_context`) — a TWO-artifact emit: an ``agent``
      module (a ``StateGraph`` compiled to an AG-UI-native CoAgent — the MCP mount
      via ``MultiServerMCPClient`` + ``ToolNode``, the graph-enforced ``interrupt()``
      HITL for the write-gate, and the tenant carried IN the graph state) and a
      ``serving`` module (the AG-UI LangGraph adapter exposing ``/agui``, with
      inbound-tenant derivation into graph state). When the ``Copilot`` declares a
      ``workflow.chain`` the agent module emits the chain AS graph nodes + edges (a
      ``review`` interrupt node) instead of the single-agent ReAct loop — LangGraph
      IS a graph, so the workflow is its most natural shape.
    """

    framework = "langgraph"
    target = "langgraph"
    file_extension = "py"

    # ── copilot case routing (mirrors AgnoEmitter / AgentFrameworkEmitter) ───

    def _is_copilot(self, ctx: EmitContext) -> bool:
        """A ctx from :func:`build_copilot_context` carries copilot-only
        projections a single-agent ctx never has; any one present routes the emit
        to the servable LangGraph ``copilot`` case."""
        return bool(
            ctx.mcp_servers
            or ctx.tools_requiring_confirmation
            or ctx.tenant_propagate
            or ctx.knowledge
            or ctx.workflow
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
            "has_name": bool(ctx.name),
            "tools": tools,
            "tool_list": ", ".join(t["func_name"] for t in tools),
        }

    def losses(self, ctx: EmitContext, choice: ScaffoldChoice) -> list[str]:
        out: list[str] = []
        if ctx.tools:
            out.append(
                "tool body — each `@tool` is a scaffolded STUB (name + "
                "`raise NotImplementedError`); its real implementation and typed "
                "signature must be wired (LangChain derives the tool schema from the "
                "function signature + docstring)"
            )
        if ctx.model is None:
            out.append(
                "model unbound in DNA and none supplied — `create_react_agent` "
                "REQUIRES a model; the emitted call omits `model=`, so supply one at "
                "wire-up"
            )
        else:
            out.append(
                "model coordinate — the DNA coordinate is carried verbatim; "
                "`create_react_agent` resolves it via `init_chat_model`, whose "
                "provider prefixes are `openai` / `anthropic` / `azure_openai` / "
                "`google_genai`; a DNA `azure/…` coordinate needs the `azure_openai:` "
                "prefix (or a model instance) at wire-up"
            )
        if ctx.output_schema:
            out.append(
                "output_schema — map DNA's `spec.output_schema` to "
                "`create_react_agent(response_format=...)` (a Pydantic model) by hand; "
                "the scaffold does not synthesize the class"
            )
        return out

    def mapping(self) -> dict[str, str]:
        return {
            "build_prompt (Soul+guardrails+instruction)": "INSTRUCTIONS constant (byte-equal)",
            "metadata.name": "create_react_agent(name=...) (graph name)",
            "spec.model / Genome.default_llm": "create_react_agent(model=...) (DNA coordinate preserved)",
            "spec.tools[] (Tool Kind)": "@tool stubs → create_react_agent(tools=[...])",
        }

    # ── servable copilot render (the two-artifact scaffold case) ─────────────

    def _copilot_context(self, ctx: EmitContext) -> dict[str, Any]:
        """Template variables for the LangGraph ``copilot`` case.

        The mounted agent's MCP servers become a ``MultiServerMCPClient`` +
        ``ToolNode``; the HITL-write intent (``ctx.tools_requiring_confirmation``)
        becomes a graph-enforced ``interrupt()`` review node (the LangGraph-native
        equivalent of Agno's ``external_execution`` / MS-AF's ``request_info``); the
        ``workflow.chain`` becomes graph nodes + edges (LangGraph is graph-native).
        Everything is sorted for a deterministic golden."""
        gated = sorted(ctx.tools_requiring_confirmation)
        has_workflow = bool(ctx.workflow)
        has_hitl = bool(gated)

        servers: list[dict[str, Any]] = []
        for s in ctx.mcp_servers:
            servers.append(
                {
                    "name_literal": py_str_literal(f"mcp_{s.ref}"),
                    "url_literal": py_str_literal(s.url) if s.url else "None",
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
        # The workflow node chain: the declared steps + an appended ``review``
        # interrupt node when writes are gated. Edges thread consecutive nodes.
        nodes = list(ctx.workflow) + (["review"] if (has_workflow and has_hitl) else [])
        edges = [
            {"from_literal": py_str_literal(a), "to_literal": py_str_literal(b)}
            for a, b in zip(nodes, nodes[1:])
        ]

        build_fn = "build_workflow" if has_workflow else "build_agent"
        mounted_kind = "workflow" if has_workflow else "agent"

        # ── memory canvas (Phase-2 generative-UI over AG-UI shared state) ────
        # After the tool node runs, a READ tool's result is projected into two
        # shared-state keys the DNA console's Memória tab reads:
        # ``memory_timeline`` (structured `{id,text,when,tags,personal}` items)
        # and ``memory_card_html`` (the #152 DNA-branded rawHtml card). The gate
        # is DECLARATIVE, not a memory hardcode: a `memory-timeline` frontend
        # panel declared on the Copilot, OR a known memory read tool present in
        # the mounted MCP allowlist (the "read-tool → canvas" convention). It is
        # scoped to the single-agent ReAct graph (the `_tool_node` only exists
        # there); a workflow graph or a copilot with neither signal emits NO
        # projection — the block is a clean no-op, so the generic template still
        # emits correctly for a copilot with no memory tools.
        allowlist = {tool for s in ctx.mcp_servers for tool in s.allowed_tools}
        read_tools = sorted(allowlist & _MEMORY_READ_TOOLS)
        memory_panel = "memory-timeline" in (ctx.frontend_panels or [])
        memory_canvas = (
            bool(ctx.mcp_servers)
            and not has_workflow
            and bool(memory_panel or read_tools)
        )
        if memory_canvas:
            # The emitted gate matches RUNTIME tool NAMES on the ToolMessage. A copilot's
            # allowlist carries scope aliases (e.g. `list`), but the DNA MCP serves that
            # read under its impl name (`list_memories`) at runtime — so a `list` in the
            # allowlist must ALSO gate `list_memories`, else the canvas never populates on
            # a list. (A projection gate is safe to over-include.)
            read_gate = set(read_tools)
            if "list" in read_gate:
                read_gate.add("list_memories")
            if not read_gate:
                # Panel declared over an open allowlist (empty = "all tools"): the
                # canonical read set is the gate.
                read_gate = set(_MEMORY_READ_TOOLS)
            read_tools = sorted(read_gate)

        # ── persistence → real LangGraph backends ───────────────────────────
        # checkpoint=postgres → `PostgresSaver.from_conn_string(...)`;
        # memory=postgres → `PostgresStore.from_conn_string(..., index=...)`
        # with the pgvector RAG expressed via the Store's `index=` (design map).
        # Absent slots keep the in-memory `MemorySaver()` (back-compat). DSNs come
        # from the infra `ref` via an env var, never a hardcoded literal.
        facts = persistence_facts(ctx)
        cp_pg = facts["checkpoint_pg"]
        mem_pg = facts["memory_pg"]
        # The in-function import block, pre-rendered so the no-persistence path is
        # byte-identical to before (a plain interpolation preserves the blank line
        # the template carries; a conditional section would collapse it).
        import_lines = [
            "    from langgraph.checkpoint.postgres import PostgresSaver"
            if cp_pg
            else "    from langgraph.checkpoint.memory import MemorySaver"
        ]
        if mem_pg:
            import_lines.append("    from langgraph.store.postgres import PostgresStore")
        checkpoint_imports = "\n".join(import_lines)
        if cp_pg:
            checkpointer_expr = (
                f"PostgresSaver.from_conn_string({pg_url_expr(facts['checkpoint_ref'])})"
            )
        else:
            checkpointer_expr = "MemorySaver()"
        store_expr = ""
        if mem_pg:
            memory_url = pg_url_expr(facts["memory_ref"])
            if facts["vector_pg"]:
                index_literal = self._store_index_literal(
                    facts["embed_model"], facts["embed_dims"]
                )
                store_expr = f"PostgresStore.from_conn_string({memory_url}, index={index_literal})"
            else:
                store_expr = f"PostgresStore.from_conn_string({memory_url})"

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
            "confirm_tools_literal": _py_list_literal(gated),
            "workflow_steps": steps,
            "workflow_edges": edges,
            "first_node_literal": py_str_literal(nodes[0]) if nodes else '""',
            "last_node_literal": py_str_literal(nodes[-1]) if nodes else '""',
            "build_fn": build_fn,
            "mounted_kind": mounted_kind,
            # persistence
            "needs_os": bool(cp_pg or mem_pg),
            "cp_pg": bool(cp_pg),
            "has_store": bool(mem_pg),
            "checkpoint_imports": checkpoint_imports,
            "checkpointer_expr": checkpointer_expr,
            "store_expr": store_expr,
            # memory canvas (Phase-2 read-tool → shared-state projection)
            "memory_canvas": memory_canvas,
            "read_tools_literal": _py_set_literal(read_tools),
            "read_tools_doc": "/".join(read_tools),
        }

    @staticmethod
    def _store_index_literal(model: str | None, dims: int | None) -> str:
        """The LangGraph ``PostgresStore(index=...)`` dict literal that binds
        pgvector semantic search — ``{'dims': 1536, 'embed': 'openai:<model>'}``
        (langchain ``init_embeddings`` provider:model coordinate). The vector RAG
        rides on the Store's index (design map), not a separate vector store."""
        coord = f"openai:{model}" if model else "openai:text-embedding-3-small"
        d = dims if dims is not None else 1536
        return (
            "{"
            + py_str_literal("dims") + ": " + str(d) + ", "
            + py_str_literal("embed") + ": " + py_str_literal(coord)
            + "}"
        )

    def _copilot_losses(self, ctx: EmitContext) -> list[str]:
        out = [
            "composition structure — Soul reuse + wired Guardrails flatten to one "
            "`INSTRUCTIONS` string (a code-first graph has no `soul:`/`guardrails:` slot)",
            "tenant overlay — a per-tenant persona without a fork has no code-first field",
            "eval-as-contract — prompt invariants (EvalCases) have no code-first slot",
            "MCP tool bodies — the mounted graph calls the DNA MCP server's tools over "
            "Streamable HTTP (langchain-mcp-adapters); the emitted app builds the "
            "`MultiServerMCPClient(...)` but the tool implementations live on the remote "
            "MCP server, not in the scaffold",
            "MCP allowlist — LangGraph's `MultiServerMCPClient` loads the server's whole "
            "tool set; the per-agent `allowed_tools` bound is not applied at the client "
            "config, so enforce it at the MCP server or filter the loaded tools at wire-up",
            "frontend console — `frontend`/`knowledge` hints (CopilotKit panels, suggested "
            "prompts, RAG collections) have no code-first backend slot; RAG retrieval is per-app",
        ]
        facts = persistence_facts(ctx)
        if facts["checkpoint_pg"] or facts["memory_pg"]:
            out.append(
                "persistence lifecycle — `PostgresSaver`/`PostgresStore."
                "from_conn_string(...)` return CONTEXT MANAGERS; the emitted "
                "`build_agent` calls them inline (the config shape), so open the "
                "pool + call `.setup()` (one-time table create) at wire-up per the "
                "LangGraph persistence docs"
            )
        if facts["vector_pg"]:
            out.append(
                "pgvector RAG — the vector store rides on the memory `PostgresStore`'s "
                "`index=` (semantic search over the Store); a standalone corpus index "
                "(`PGVector` retriever) + the collection CONTENT load are per-app"
            )
        if ctx.workflow:
            out.append(
                "workflow step bodies — each `workflow.chain` step is a scaffolded graph "
                "node STUB; per-step instructions + the escalation effect are per-app "
                "bodies to wire at the consumer"
            )
        if ctx.model is None:
            out.append(
                "model unbound in DNA and none supplied — emitted `_model()` raises; "
                "supply a model coordinate or instance at wire-up"
            )
        allowlist = {tool for s in ctx.mcp_servers for tool in s.allowed_tools}
        if (
            ctx.mcp_servers
            and not ctx.workflow
            and ("memory-timeline" in (ctx.frontend_panels or []) or (allowlist & _MEMORY_READ_TOOLS))
        ):
            out.append(
                "memory canvas — the emitted `_tool_node` projects a read tool's "
                "result into the AG-UI shared-state keys `memory_timeline` + "
                "`memory_card_html` (the DNA console's Memória canvas). "
                "`memory_card_html` is rendered by "
                "`dna.emit.mcp_ui.memory_list_card_html`, so the emitted app "
                "imports the `dna` package at runtime (a pure card renderer, no "
                "heavy deps); the item shape mapping (name/summary/created_at/tags "
                "→ id/text/when/tags/personal) is a per-server convention"
            )
        return out

    def _copilot_mapping(self, ctx: EmitContext) -> dict[str, str]:
        mapping = {
            "build_prompt (Soul+guardrails+instruction)": "INSTRUCTIONS constant (byte-equal)",
            "metadata.name": "LangGraphAgent(name=...) / StateGraph node ids",
            "spec.model / Genome.default_llm": "init_chat_model(...) (DNA coordinate preserved)",
            "Agent.spec.mcp_servers → MCPFederation": "MultiServerMCPClient(...) + ToolNode",
            "Tool.requires_confirmation": "interrupt() review node (graph-enforced HITL)",
            "Copilot.tenant.propagate": "inbound ContextVar → graph state['tenant'] + X-DNA-* MCP headers",
            "Copilot.workflow.chain": "StateGraph nodes + edges (graph-native chain) + interrupt() review node",
        }
        allowlist = {tool for s in ctx.mcp_servers for tool in s.allowed_tools}
        if (
            ctx.mcp_servers
            and not ctx.workflow
            and ("memory-timeline" in (ctx.frontend_panels or []) or (allowlist & _MEMORY_READ_TOOLS))
        ):
            mapping["Copilot.frontend.panels / read-tool result"] = (
                "State.memory_timeline + State.memory_card_html (AG-UI shared-state canvas)"
            )
        return mapping

    def _emit_copilot(self, ctx: EmitContext) -> EmitResult:
        """Render the two servable artifacts (agent graph module + AG-UI serve app)
        from an enriched copilot ctx (:func:`build_copilot_context`)."""
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
                "the langgraph `copilot` case needs both `copilot_agent.py.tmpl` "
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
            mapping=self._copilot_mapping(ctx),
        )
