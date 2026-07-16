/**
 * DNA → **Agno** emitter (code-first, `agno.agent`; TS twin of python
 * `dna.emit.agno`).
 *
 * Agno is code-first — you construct `Agent(name=..., model=..., instructions=...,
 * tools=[...])`, there is no declarative agent file to map onto. So this target is a
 * {@link ScaffoldEmitter}: it fills a curated `{agno × case}` template rather than
 * generating code ad-hoc, and the emitted `INSTRUCTIONS` constant is byte-equal to
 * the DNA-composed prompt.
 *
 * Model: the DNA coordinate is PRESERVED as a string (Agno accepts a `provider:model`
 * string). Cases: `prompt-only` (no tools) and `with-tools` (one plain-function stub
 * per DNA Tool — Agno auto-wraps callables as tools). `structured-output` (Agno's
 * `output_schema`) is not shipped yet and falls back with a recorded loss.
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

/**
 * Two shapes share this target:
 *  - a **single agent** (`prompt-only` / `with-tools`) — one `Agent(...)` module,
 *    byte-equal `INSTRUCTIONS`; the inherited {@link ScaffoldEmitter} drives it.
 *  - a **servable copilot** (`copilot` case, from `buildCopilotContext`) — a
 *    TWO-artifact emit: an `agent` module (`build_agent` factory + MCP mount +
 *    the HITL write-gate) and a `serving` module (Agno AgentOS exposing `/agui`,
 *    with inbound-tenant derivation). Agno 2.7.x resumes `external_execution`
 *    gates natively, so the emitted app carries no hand-rolled resume machinery —
 *    the DNA MCP write tools are gated DIRECTLY on the remote tool (Spike 0A:
 *    gate-remote-directly). TS twin of `dna.emit.agno`.
 */
export class AgnoEmitter extends ScaffoldEmitter {
  readonly framework = "agno";
  readonly target = "agno";
  readonly fileExtension = "py";

  // ── copilot case routing ──────────────────────────────────────────────────

  /** A ctx from `buildCopilotContext` carries copilot-only projections a
   *  single-agent ctx never has; any one present routes to the `copilot` case. */
  private isCopilot(ctx: EmitContext): boolean {
    return (
      ctx.mcpServers.length > 0 ||
      ctx.toolsRequiringConfirmation.size > 0 ||
      ctx.tenantPropagate ||
      ctx.knowledge.length > 0
    );
  }

  override classify(ctx: EmitContext): string {
    return this.isCopilot(ctx) ? "copilot" : super.classify(ctx);
  }

  override emit(ctx: EmitContext): EmitResult {
    return this.classify(ctx) === "copilot" ? this.emitCopilot(ctx) : super.emit(ctx);
  }

  // ── single-agent render (prompt-only / with-tools) ────────────────────────

  renderContext(ctx: EmitContext, _case: string): Record<string, unknown> {
    const tools = ctx.tools.map((t) => ({
      name: t.name,
      func_name: pyIdentifier(t.name),
      docstring_literal: pyStrLiteral(t.description || t.name),
    }));
    return {
      has_model: ctx.model !== null,
      model_literal: ctx.model ? pyStrLiteral(ctx.model) : "",
      tools,
      tool_list: tools.map((t) => t.func_name).join(", "),
    };
  }

  losses(ctx: EmitContext, _choice: ScaffoldChoice): string[] {
    const out: string[] = [];
    if (ctx.tools.length > 0) {
      out.push(
        "tool body — each tool is a scaffolded STUB (a bare callable + " +
          "`raise NotImplementedError`); its real implementation and typed signature " +
          "must be wired (Agno derives the tool schema from the function signature + " +
          "docstring)",
      );
    }
    if (ctx.model === null) {
      out.push(
        "model unbound in DNA and none supplied — emitted `Agent(...)` has no " +
          "`model=`; supply one at wire-up (Agno requires a model)",
      );
    } else {
      out.push(
        "model coordinate — the DNA coordinate is carried verbatim as a string; this " +
          "assumes Agno's string-model resolution. A specific `Model` object (e.g. " +
          "`OpenAIChat(id=...)`) is the alternative at wire-up",
      );
    }
    if (ctx.outputSchema) {
      out.push(
        "output_schema — map DNA's `spec.output_schema` to `Agent(output_schema=...)` " +
          "(a Pydantic model) by hand; the scaffold does not synthesize the class",
      );
    }
    return out;
  }

  mapping(): Record<string, string> {
    return {
      "buildPrompt (Soul+guardrails+instruction)": "INSTRUCTIONS constant (byte-equal)",
      "metadata.name": "Agent(name=...)",
      "spec.model / Genome.default_llm": "Agent(model=...) (DNA coordinate preserved)",
      "spec.tools[] (Tool Kind)": "plain-function stubs → Agent(tools=[...])",
    };
  }

  // ── servable copilot render (the two-artifact case) ───────────────────────

  /** Template variables for the `copilot` case (merged over the common ones).
   *  The mounted agent's MCP servers become `MCPTools` mounts; the HITL-write
   *  intent (`ctx.toolsRequiringConfirmation`) becomes each mount's
   *  `external_execution_required_tools` (Spike 0A: gate-remote-directly).
   *  Everything is sorted for a deterministic golden. */
  private copilotContext(ctx: EmitContext): Record<string, unknown> {
    const gated = [...ctx.toolsRequiringConfirmation].sort();
    const externalToolsLiteral = `[${gated.map(pyStrLiteral).join(", ")}]`;
    const servers = ctx.mcpServers.map((s) => ({
      url_literal: s.url ? pyStrLiteral(s.url) : "None",
      transport_literal: pyStrLiteral(s.transport),
      has_external_tools: gated.length > 0,
      external_tools_literal: externalToolsLiteral,
    }));
    return {
      agent_module: pyIdentifier(ctx.name),
      has_model: ctx.model !== null,
      model_literal: ctx.model ? pyStrLiteral(ctx.model) : "",
      has_mcp: ctx.mcpServers.length > 0,
      mcp_servers: servers,
      tenant_propagate: ctx.tenantPropagate,
    };
  }

  private copilotLosses(ctx: EmitContext): string[] {
    const out = [
      "MCP tool bodies — the mounted agent calls the DNA MCP server's tools over " +
        "Streamable HTTP; the emitted app builds `MCPTools(...)` but the tool " +
        "implementations live on the remote MCP server, not in the scaffold",
      "frontend console — `frontend`/`knowledge` hints (CopilotKit panels, suggested " +
        "prompts, RAG collections) are copilot-level metadata with no code-first " +
        "backend slot; wire them in the console at the UI layer",
    ];
    if (ctx.model === null) {
      out.push(
        "model unbound in DNA and none supplied — emitted `build_agent()` has no " +
          "`model=`; supply one at wire-up (Agno requires a model)",
      );
    }
    return out;
  }

  /** Render the two servable artifacts (agent module + AG-UI serve app) from an
   *  enriched copilot ctx (`buildCopilotContext`). */
  private emitCopilot(ctx: EmitContext): EmitResult {
    const agentTmpl = resolveScaffold(this.framework, "copilot_agent");
    const serveTmpl = resolveScaffold(this.framework, "copilot_serve");
    if (agentTmpl === null || serveTmpl === null) {
      throw new EmitError(
        "the agno `copilot` case needs both `copilot_agent.py.tmpl` and " +
          "`copilot_serve.py.tmpl` scaffold templates",
      );
    }
    const variables = { ...this.commonContext(ctx), ...this.copilotContext(ctx) };
    const agentSrc = Mustache.render(agentTmpl, variables);
    const serveSrc = Mustache.render(serveTmpl, variables);
    const moduleName = variables.agent_module as string;

    // A servable copilot never "falls back" a case — case == requested so the
    // common-loss helper adds no spurious fallback note.
    const choice: ScaffoldChoice = { case: "copilot", template: "", requested: "copilot" };
    const losses = [...this.commonLosses(ctx, choice), ...this.copilotLosses(ctx)];

    const artifacts: EmitArtifact[] = [
      { path: `${moduleName}.py`, content: agentSrc, role: "agent" },
      { path: `${moduleName}_serve.py`, content: serveSrc, role: "serving" },
    ];
    return new EmitResult({ target: this.target, artifacts, losses, mapping: this.mapping() });
  }
}
