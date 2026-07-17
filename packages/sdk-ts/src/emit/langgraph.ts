/**
 * DNA → **LangGraph** emitter (code-first, `langgraph.prebuilt`; TS twin of
 * python `dna.emit.langgraph`).
 *
 * LangGraph is code-first — you build an agent by calling
 * `create_react_agent(model, tools=[...], prompt="...")`, there is no declarative
 * agent file to map onto. So this target is a {@link ScaffoldEmitter}: it fills a
 * curated `{langgraph × case}` template rather than generating code ad-hoc, and the
 * emitted `INSTRUCTIONS` constant is byte-equal to the DNA-composed prompt.
 *
 * Model: the DNA coordinate is PRESERVED (unlike openai-agents, which strips the
 * provider token) — `create_react_agent` resolves the string via `init_chat_model`,
 * which takes a `provider:model` coordinate. Cases: `prompt-only` (no tools) and
 * `with-tools` (the ReAct idiom — one `@tool` stub per DNA Tool). `structured-output`
 * (LangGraph's `response_format`) is not shipped yet and falls back with a loss.
 */
import Mustache from "mustache";

import {
  persistenceFacts,
  pgUrlExpr,
  pyIdentifier,
  pyStrLiteral,
  resolveScaffold,
  ScaffoldEmitter,
  type ScaffoldChoice,
} from "./scaffold.js";
import { EmitError, EmitResult, type EmitArtifact, type EmitContext } from "./index.js";

/** A Python list literal (`["a", "b"]`) built from {@link pyStrLiteral} so the
 *  quote style tracks the language (JSON double-quotes in TS; the Py twin uses
 *  repr single-quotes) — the shared scaffold-literal convention. */
function pyListLiteral(items: string[]): string {
  return "[" + items.map(pyStrLiteral).join(", ") + "]";
}

/** A Python set literal (`{"a", "b"}`) for a membership-tested constant — the
 *  emitted `_READ_TOOLS` gate is a set (`name in _READ_TOOLS`). */
function pySetLiteral(items: string[]): string {
  return "{" + items.map(pyStrLiteral).join(", ") + "}";
}

/** The canonical DNA memory READ tools — the "read-tool → canvas" convention.
 *  A mounted read tool from this set (or a declared `memory-timeline` frontend
 *  panel) turns on the Phase-2 canvas projection: the tool result is projected
 *  into the AG-UI shared-state keys `memory_timeline` + `memory_card_html` the
 *  DNA console's Memória tab reads. Writes (`remember`/`forget`) are the
 *  HITL-gated set and never feed the canvas. TS twin of `_MEMORY_READ_TOOLS`. */
const MEMORY_READ_TOOLS = new Set(["list", "list_memories", "recall"]);

/**
 * Two shapes share this target, exactly like the Agno + agent-framework emitters:
 *  - a **single agent** (`prompt-only` / `with-tools`) — one `create_react_agent`
 *    module, byte-equal `INSTRUCTIONS`; the inherited {@link ScaffoldEmitter} drives it.
 *  - a **servable copilot** (`copilot` case, from `buildCopilotContext`) — a
 *    TWO-artifact emit: an `agent` module (a `StateGraph` compiled to an AG-UI-native
 *    CoAgent — the `MultiServerMCPClient` + `ToolNode` MCP mount, the graph-enforced
 *    `interrupt()` HITL write-gate, and the tenant carried IN the graph state) and a
 *    `serving` module (the AG-UI LangGraph adapter exposing `/agui`). A `Copilot`
 *    with a `workflow.chain` emits the chain AS graph nodes + edges (LangGraph is
 *    graph-native) with an appended `interrupt()` review node. TS twin of
 *    `dna.emit.langgraph`.
 */
export class LanggraphEmitter extends ScaffoldEmitter {
  readonly framework = "langgraph";
  readonly target = "langgraph";
  readonly fileExtension = "py";

  // ── copilot case routing (mirrors AgnoEmitter / AgentFrameworkEmitter) ─────

  /** A ctx from `buildCopilotContext` carries copilot-only projections a
   *  single-agent ctx never has; any one present routes to the `copilot` case. */
  private isCopilot(ctx: EmitContext): boolean {
    // Tolerant of a hand-built single-agent ctx that omits the copilot-only
    // fields (parity with Python's dataclass empty defaults): omitted == not a
    // copilot, so the emit stays on the base create_react_agent scaffold path.
    return (
      (ctx.mcpServers?.length ?? 0) > 0 ||
      (ctx.toolsRequiringConfirmation?.size ?? 0) > 0 ||
      Boolean(ctx.tenantPropagate) ||
      (ctx.knowledge?.length ?? 0) > 0 ||
      (ctx.workflow?.length ?? 0) > 0
    );
  }

  override classify(ctx: EmitContext): string {
    return this.isCopilot(ctx) ? "copilot" : super.classify(ctx);
  }

  override emit(ctx: EmitContext): EmitResult {
    return this.classify(ctx) === "copilot" ? this.emitCopilot(ctx) : super.emit(ctx);
  }

  // ── single-agent render (prompt-only / with-tools) ─────────────────────────

  renderContext(ctx: EmitContext, _case: string): Record<string, unknown> {
    const tools = ctx.tools.map((t) => ({
      name: t.name,
      func_name: pyIdentifier(t.name),
      docstring_literal: pyStrLiteral(t.description || t.name),
    }));
    return {
      has_model: ctx.model !== null,
      model_literal: ctx.model ? pyStrLiteral(ctx.model) : "",
      has_name: Boolean(ctx.name),
      tools,
      tool_list: tools.map((t) => t.func_name).join(", "),
    };
  }

  losses(ctx: EmitContext, _choice: ScaffoldChoice): string[] {
    const out: string[] = [];
    if (ctx.tools.length > 0) {
      out.push(
        "tool body — each `@tool` is a scaffolded STUB (name + " +
          "`raise NotImplementedError`); its real implementation and typed signature " +
          "must be wired (LangChain derives the tool schema from the function " +
          "signature + docstring)",
      );
    }
    if (ctx.model === null) {
      out.push(
        "model unbound in DNA and none supplied — `create_react_agent` REQUIRES a " +
          "model; the emitted call omits `model=`, so supply one at wire-up",
      );
    } else {
      out.push(
        "model coordinate — the DNA coordinate is carried verbatim; " +
          "`create_react_agent` resolves it via `init_chat_model`, whose provider " +
          "prefixes are `openai` / `anthropic` / `azure_openai` / `google_genai`; a " +
          "DNA `azure/…` coordinate needs the `azure_openai:` prefix (or a model " +
          "instance) at wire-up",
      );
    }
    if (ctx.outputSchema) {
      out.push(
        "output_schema — map DNA's `spec.output_schema` to " +
          "`create_react_agent(response_format=...)` (a Pydantic model) by hand; the " +
          "scaffold does not synthesize the class",
      );
    }
    return out;
  }

  mapping(): Record<string, string> {
    return {
      "buildPrompt (Soul+guardrails+instruction)": "INSTRUCTIONS constant (byte-equal)",
      "metadata.name": "create_react_agent(name=...) (graph name)",
      "spec.model / Genome.default_llm": "create_react_agent(model=...) (DNA coordinate preserved)",
      "spec.tools[] (Tool Kind)": "@tool stubs → create_react_agent(tools=[...])",
    };
  }

  // ── servable copilot render (the two-artifact scaffold case) ───────────────

  /** Template variables for the LangGraph `copilot` case. Mirrors the Python
   *  `_copilot_context`: the mounted agent's MCP servers become a
   *  `MultiServerMCPClient` + `ToolNode`; the HITL-write intent becomes a
   *  graph-enforced `interrupt()` review node; the `workflow.chain` becomes graph
   *  nodes + edges. Everything is sorted for a deterministic golden. */
  private copilotContext(ctx: EmitContext): Record<string, unknown> {
    const gated = [...ctx.toolsRequiringConfirmation].sort();
    const hasWorkflow = ctx.workflow.length > 0;
    const hasHitl = gated.length > 0;

    const servers = ctx.mcpServers.map((s) => ({
      name_literal: pyStrLiteral(`mcp_${s.ref}`),
      url_literal: s.url ? pyStrLiteral(s.url) : "None",
    }));

    const steps = ctx.workflow.map((step, i) => ({
      step,
      func: pyIdentifier(step),
      name_literal_step: pyStrLiteral(step),
      is_first: i === 0,
    }));
    // The workflow node chain: the declared steps + an appended `review` interrupt
    // node when writes are gated. Edges thread consecutive nodes.
    const nodes = [...ctx.workflow, ...(hasWorkflow && hasHitl ? ["review"] : [])];
    const edges = nodes.slice(0, -1).map((a, i) => ({
      from_literal: pyStrLiteral(a),
      to_literal: pyStrLiteral(nodes[i + 1]),
    }));

    const buildFn = hasWorkflow ? "build_workflow" : "build_agent";
    const mountedKind = hasWorkflow ? "workflow" : "agent";

    // ── memory canvas (Phase-2 generative-UI over AG-UI shared state) ───────
    // After the tool node runs, a READ tool's result is projected into two
    // shared-state keys the DNA console's Memória tab reads: `memory_timeline`
    // (structured `{id,text,when,tags,personal}` items) + `memory_card_html`
    // (the #152 DNA-branded rawHtml card). The gate is DECLARATIVE, not a memory
    // hardcode: a `memory-timeline` frontend panel declared on the Copilot, OR a
    // known memory read tool in the mounted MCP allowlist (the "read-tool →
    // canvas" convention). Scoped to the single-agent ReAct graph (the
    // `_tool_node` only exists there); a workflow graph or a copilot with neither
    // signal emits NO projection — a clean no-op, so the generic template still
    // emits correctly for a copilot with no memory tools. TS twin of the Python.
    const allowlist = new Set(ctx.mcpServers.flatMap((s) => s.allowedTools));
    let readTools = [...MEMORY_READ_TOOLS].filter((t) => allowlist.has(t)).sort();
    const memoryPanel = (ctx.frontendPanels ?? []).includes("memory-timeline");
    const memoryCanvas =
      ctx.mcpServers.length > 0 && !hasWorkflow && (memoryPanel || readTools.length > 0);
    if (memoryCanvas && readTools.length === 0) {
      // Panel declared but the allowlist is open (empty = "all tools"): fall back
      // to the canonical read set as the emitted gate.
      readTools = [...MEMORY_READ_TOOLS].sort();
    }

    // ── persistence → real LangGraph backends ─────────────────────────────
    // checkpoint=postgres → `PostgresSaver.from_conn_string(...)`;
    // memory=postgres → `PostgresStore.from_conn_string(..., index=...)` with the
    // pgvector RAG expressed via the Store's `index=` (design map). Absent slots
    // keep in-memory `MemorySaver()` (back-compat). DSNs from the infra `ref` via
    // an env var, never a hardcoded literal.
    const facts = persistenceFacts(ctx);
    const cpPg = facts.checkpointPg;
    const memPg = facts.memoryPg;
    // The in-function import block, pre-rendered so the no-persistence path is
    // byte-identical to before (a plain interpolation preserves the blank line the
    // template carries; a conditional section would collapse it).
    const importLines = [
      cpPg
        ? "    from langgraph.checkpoint.postgres import PostgresSaver"
        : "    from langgraph.checkpoint.memory import MemorySaver",
    ];
    if (memPg) importLines.push("    from langgraph.store.postgres import PostgresStore");
    const checkpointImports = importLines.join("\n");
    const checkpointerExpr = cpPg
      ? `PostgresSaver.from_conn_string(${pgUrlExpr(facts.checkpointRef as string)})`
      : "MemorySaver()";
    let storeExpr = "";
    if (memPg) {
      const memoryUrl = pgUrlExpr(facts.memoryRef as string);
      storeExpr = facts.vectorPg
        ? `PostgresStore.from_conn_string(${memoryUrl}, index=${LanggraphEmitter.storeIndexLiteral(
            facts.embedModel,
            facts.embedDims,
          )})`
        : `PostgresStore.from_conn_string(${memoryUrl})`;
    }

    return {
      name: ctx.name,
      name_literal: pyStrLiteral(ctx.name),
      instructions_literal: pyStrLiteral(ctx.instructions),
      agent_module: pyIdentifier(ctx.name),
      has_model: ctx.model !== null,
      model_literal: ctx.model ? pyStrLiteral(ctx.model) : "",
      has_mcp: ctx.mcpServers.length > 0,
      mcp_servers: servers,
      tenant_propagate: ctx.tenantPropagate,
      has_hitl: hasHitl,
      has_workflow: hasWorkflow,
      confirm_tools_literal: pyListLiteral(gated),
      workflow_steps: steps,
      workflow_edges: edges,
      first_node_literal: nodes.length > 0 ? pyStrLiteral(nodes[0]) : '""',
      last_node_literal: nodes.length > 0 ? pyStrLiteral(nodes[nodes.length - 1]) : '""',
      build_fn: buildFn,
      mounted_kind: mountedKind,
      // persistence
      needs_os: cpPg || memPg,
      cp_pg: cpPg,
      has_store: memPg,
      checkpoint_imports: checkpointImports,
      checkpointer_expr: checkpointerExpr,
      store_expr: storeExpr,
      // memory canvas (Phase-2 read-tool → shared-state projection)
      memory_canvas: memoryCanvas,
      read_tools_literal: pySetLiteral(readTools),
      read_tools_doc: readTools.join("/"),
    };
  }

  /** The LangGraph `PostgresStore(index=...)` dict literal that binds pgvector
   *  semantic search — `{'dims': 1536, 'embed': 'openai:<model>'}` (langchain
   *  `init_embeddings` provider:model coordinate). The vector RAG rides on the
   *  Store's index (design map), not a separate vector store. TS twin of Python
   *  `_store_index_literal`. */
  private static storeIndexLiteral(model: string | null, dims: number | null): string {
    const coord = model ? `openai:${model}` : "openai:text-embedding-3-small";
    const d = dims ?? 1536;
    return `{${pyStrLiteral("dims")}: ${d}, ${pyStrLiteral("embed")}: ${pyStrLiteral(coord)}}`;
  }

  private copilotLosses(ctx: EmitContext): string[] {
    const out = [
      "composition structure — Soul reuse + wired Guardrails flatten to one " +
        "`INSTRUCTIONS` string (a code-first graph has no `soul:`/`guardrails:` slot)",
      "tenant overlay — a per-tenant persona without a fork has no code-first field",
      "eval-as-contract — prompt invariants (EvalCases) have no code-first slot",
      "MCP tool bodies — the mounted graph calls the DNA MCP server's tools over " +
        "Streamable HTTP (langchain-mcp-adapters); the emitted app builds the " +
        "`MultiServerMCPClient(...)` but the tool implementations live on the remote " +
        "MCP server, not in the scaffold",
      "MCP allowlist — LangGraph's `MultiServerMCPClient` loads the server's whole " +
        "tool set; the per-agent `allowed_tools` bound is not applied at the client " +
        "config, so enforce it at the MCP server or filter the loaded tools at wire-up",
      "frontend console — `frontend`/`knowledge` hints (CopilotKit panels, suggested " +
        "prompts, RAG collections) have no code-first backend slot; RAG retrieval is per-app",
    ];
    const facts = persistenceFacts(ctx);
    if (facts.checkpointPg || facts.memoryPg) {
      out.push(
        "persistence lifecycle — `PostgresSaver`/`PostgresStore.from_conn_string(...)` " +
          "return CONTEXT MANAGERS; the emitted `build_agent` calls them inline (the " +
          "config shape), so open the pool + call `.setup()` (one-time table create) " +
          "at wire-up per the LangGraph persistence docs",
      );
    }
    if (facts.vectorPg) {
      out.push(
        "pgvector RAG — the vector store rides on the memory `PostgresStore`'s " +
          "`index=` (semantic search over the Store); a standalone corpus index " +
          "(`PGVector` retriever) + the collection CONTENT load are per-app",
      );
    }
    if (ctx.workflow.length > 0) {
      out.push(
        "workflow step bodies — each `workflow.chain` step is a scaffolded graph " +
          "node STUB; per-step instructions + the escalation effect are per-app " +
          "bodies to wire at the consumer",
      );
    }
    if (ctx.model === null) {
      out.push(
        "model unbound in DNA and none supplied — emitted `_model()` raises; " +
          "supply a model coordinate or instance at wire-up",
      );
    }
    if (this.hasMemoryCanvas(ctx)) {
      out.push(
        "memory canvas — the emitted `_tool_node` projects a read tool's result " +
          "into the AG-UI shared-state keys `memory_timeline` + `memory_card_html` " +
          "(the DNA console's Memória canvas). `memory_card_html` is rendered by " +
          "`dna.emit.mcp_ui.memory_list_card_html`, so the emitted app imports the " +
          "`dna` package at runtime (a pure card renderer, no heavy deps); the item " +
          "shape mapping (name/summary/created_at/tags → id/text/when/tags/personal) " +
          "is a per-server convention",
      );
    }
    return out;
  }

  /** The declarative "read-tool → canvas" gate, shared by losses + mapping: a
   *  single-agent MCP copilot that declares a `memory-timeline` frontend panel OR
   *  mounts a known memory read tool. TS twin of the Python inline gate. */
  private hasMemoryCanvas(ctx: EmitContext): boolean {
    if (ctx.mcpServers.length === 0 || ctx.workflow.length > 0) return false;
    const allowlist = new Set(ctx.mcpServers.flatMap((s) => s.allowedTools));
    const memoryPanel = (ctx.frontendPanels ?? []).includes("memory-timeline");
    return memoryPanel || [...MEMORY_READ_TOOLS].some((t) => allowlist.has(t));
  }

  private copilotMapping(ctx: EmitContext): Record<string, string> {
    const mapping: Record<string, string> = {
      "buildPrompt (Soul+guardrails+instruction)": "INSTRUCTIONS constant (byte-equal)",
      "metadata.name": "LangGraphAgent(name=...) / StateGraph node ids",
      "spec.model / Genome.default_llm": "init_chat_model(...) (DNA coordinate preserved)",
      "Agent.spec.mcp_servers → MCPFederation": "MultiServerMCPClient(...) + ToolNode",
      "Tool.requires_confirmation": "interrupt() review node (graph-enforced HITL)",
      "Copilot.tenant.propagate":
        "inbound ContextVar → graph state['tenant'] + X-DNA-* MCP headers",
      "Copilot.workflow.chain":
        "StateGraph nodes + edges (graph-native chain) + interrupt() review node",
    };
    if (this.hasMemoryCanvas(ctx)) {
      mapping["Copilot.frontend.panels / read-tool result"] =
        "State.memory_timeline + State.memory_card_html (AG-UI shared-state canvas)";
    }
    return mapping;
  }

  /** Render the two servable artifacts (agent graph module + AG-UI serve app) from
   *  an enriched copilot ctx (`buildCopilotContext`). */
  private emitCopilot(ctx: EmitContext): EmitResult {
    const agentTmpl = resolveScaffold(this.framework, "copilot_agent");
    const serveTmpl = resolveScaffold(this.framework, "copilot_serve");
    if (agentTmpl === null || serveTmpl === null) {
      throw new EmitError(
        "the langgraph `copilot` case needs both `copilot_agent.py.tmpl` and " +
          "`copilot_serve.py.tmpl` scaffold templates",
      );
    }
    const variables = this.copilotContext(ctx);
    const agentSrc = Mustache.render(agentTmpl, variables);
    const serveSrc = Mustache.render(serveTmpl, variables);
    const moduleName = variables.agent_module as string;

    const artifacts: EmitArtifact[] = [
      { path: `${moduleName}.py`, content: agentSrc, role: "agent" },
      { path: `${moduleName}_serve.py`, content: serveSrc, role: "serving" },
    ];
    return new EmitResult({
      target: this.target,
      artifacts,
      losses: this.copilotLosses(ctx),
      mapping: this.copilotMapping(ctx),
    });
  }
}
