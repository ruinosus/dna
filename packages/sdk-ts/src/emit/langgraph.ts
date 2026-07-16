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
    };
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
    return out;
  }

  private copilotMapping(): Record<string, string> {
    return {
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
      mapping: this.copilotMapping(),
    });
  }
}
