/**
 * DNA → Microsoft **agent-framework** emitter (TS twin of python
 * `dna.emit.agent_framework`). Materializes an {@link EmitContext} into the
 * declarative `PromptAgent` YAML that `agent-framework-declarative`'s
 * `AgentFactory` loads.
 *
 * The de-para (DNA field → PromptAgent field):
 *   metadata.name                     -> name         (CamelCased id)
 *   metadata.description              -> description
 *   Soul + guardrails + instruction   -> instructions (flat — kernel-composed)
 *   spec.model (or Genome default_llm)-> model.{id, provider}
 *   spec.tools[] (Tool Kind surfaces) -> tools[] (kind: function)
 *   spec.output_schema                -> outputSchema (only when present)
 *
 * `toPromptAgent` is the PURE de-para and is parity-critical: it must build the
 * SAME object the Python `to_prompt_agent` builds from the same context.
 */
import yaml from "js-yaml";
import Mustache from "mustache";

import { EmitError, EmitResult } from "./index.js";
import type { EmitArtifact, EmitContext, EmitTool, EmitterPort } from "./index.js";
import { pyIdentifier, pyStrLiteral, resolveScaffold } from "./scaffold.js";

/** DNA provider token → agent-framework `model.provider` value. Unknown tokens
 *  pass through unchanged so a future provider needs no code change. */
const PROVIDER_MAP: Record<string, string> = {
  azure: "AzureOpenAI",
  azureopenai: "AzureOpenAI",
  azure_openai: "AzureOpenAI",
  openai: "OpenAI",
  anthropic: "Anthropic",
  foundry: "AzureAIFoundry",
  azureaifoundry: "AzureAIFoundry",
};

/** Bare model with no provider token and no `--provider` → AzureOpenAI (the
 *  provider the spike proved). Documented default, never silently wrong. */
const DEFAULT_PROVIDER = "AzureOpenAI";

/** `concierge-grounded` → `ConciergeGrounded`. */
export function camel(name: string): string {
  return String(name)
    .replace(/_/g, "-")
    .split("-")
    .filter(Boolean)
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join("");
}

/** Split a DNA model coordinate into agent-framework `{id, provider}`. */
export function splitModel(
  model: string | null,
  providerHint?: string | null,
): { id: string; provider: string } | null {
  if (!model) return null;
  let token: string | null = null;
  let ident = model;
  for (const sep of [":", "/"]) {
    const i = model.indexOf(sep);
    if (i >= 0) {
      token = model.slice(0, i);
      ident = model.slice(i + 1);
      break;
    }
  }
  let provider: string;
  if (providerHint) provider = providerHint;
  else if (token) provider = PROVIDER_MAP[token.trim().toLowerCase()] ?? token;
  else provider = DEFAULT_PROVIDER;
  return { id: ident.trim(), provider };
}

function emitTools(tools: EmitTool[]): Record<string, unknown>[] {
  return tools.map((t) => {
    const entry: Record<string, unknown> = {
      name: t.name,
      kind: "function", // AgentSchema function-tool kind (NOT `type`)
      description: t.description ?? "",
    };
    if (t.parameters && Object.keys(t.parameters).length > 0) {
      entry.parameters = t.parameters;
    }
    return entry;
  });
}

/** A Python list literal (`["a", "b"]`) built from {@link pyStrLiteral} so the
 *  quote style tracks the language (JSON double-quotes in TS; the Py twin uses
 *  repr single-quotes) — the shared scaffold-literal convention. */
function pyListLiteral(items: string[]): string {
  return "[" + items.map(pyStrLiteral).join(", ") + "]";
}

/** The MS-AF `approval_mode` dict literal — `{"always_require_approval": [...],
 *  "never_require_approval": [...]}` — the tool-level HITL the emitted MCP mount
 *  carries (the analog of Agno's `external_execution_required_tools`). */
function approvalModeLiteral(gated: string[], reads: string[]): string {
  return (
    "{" +
    pyStrLiteral("always_require_approval") + ": " + pyListLiteral(gated) +
    ", " +
    pyStrLiteral("never_require_approval") + ": " + pyListLiteral(reads) +
    "}"
  );
}

/**
 * Emit a DNA agent as an agent-framework declarative `PromptAgent` — or, for a
 * `Copilot` binder (`buildCopilotContext`), a servable Microsoft Agent Framework
 * AG-UI app (the `copilot` scaffold case). Two shapes share this target, exactly
 * like the Agno emitter: a single agent (the config-declarative PromptAgent YAML)
 * and a servable copilot (a TWO-artifact scaffold — an `agent` module via
 * `FoundryChatClient(...).as_agent(...)` + `MCPStreamableHTTPTool` mount + the
 * inbound-tenant ContextVar/header_provider bridge, and a `serving` module via
 * `add_agent_framework_fastapi_endpoint` → `/agui`; a `WorkflowBuilder` chain +
 * `request_info` escalation node when `Copilot.workflow.chain` is declared). TS
 * twin of `dna.emit.agent_framework`.
 */
export class AgentFrameworkEmitter implements EmitterPort {
  readonly target = "agent-framework";
  readonly fileExtension = "agent.yaml";
  /** Subdir under `scaffolds/` holding this framework's copilot-case templates. */
  readonly framework = "agent_framework";

  /** A ctx from `buildCopilotContext` carries copilot-only projections a
   *  single-agent ctx never has; any one present routes to the servable
   *  Microsoft Agent Framework `copilot` case. */
  private isCopilot(ctx: EmitContext): boolean {
    // Tolerant of a hand-built single-agent ctx that omits the copilot-only
    // fields (parity with Python's dataclass empty defaults): omitted == not a
    // copilot, so the emit stays on the config-declarative PromptAgent path.
    return (
      (ctx.mcpServers?.length ?? 0) > 0 ||
      (ctx.toolsRequiringConfirmation?.size ?? 0) > 0 ||
      Boolean(ctx.tenantPropagate) ||
      (ctx.knowledge?.length ?? 0) > 0 ||
      (ctx.workflow?.length ?? 0) > 0
    );
  }

  /** The PURE de-para: {@link EmitContext} → the PromptAgent object. Field
   *  order is intentional and preserved by js-yaml (insertion order). */
  toPromptAgent(ctx: EmitContext): Record<string, unknown> {
    const providerHint = (ctx.options?.provider as string | undefined) ?? null;
    const doc: Record<string, unknown> = { kind: "Prompt", name: camel(ctx.name) };
    if (ctx.description) doc.description = ctx.description;
    const model = splitModel(ctx.model, providerHint);
    if (model) doc.model = model;
    if (ctx.tools.length > 0) doc.tools = emitTools(ctx.tools);
    doc.instructions = ctx.instructions; // verbatim — the byte-equal gate
    if (ctx.outputSchema) doc.outputSchema = ctx.outputSchema;
    return doc;
  }

  emit(ctx: EmitContext): EmitResult {
    if (this.isCopilot(ctx)) return this.emitCopilot(ctx);
    const promptAgent = this.toPromptAgent(ctx);
    const artifact = yaml.dump(promptAgent, { sortKeys: false, lineWidth: -1 });

    const losses = [
      "composition structure — Soul reuse + wired Guardrails flatten to one " +
        "`instructions` string (no `soul:`/`guardrails:` slot in a PromptAgent)",
      "tenant overlay — a per-tenant persona without a fork has no PromptAgent field",
      "eval-as-contract — prompt invariants (EvalCases) have no PromptAgent slot",
    ];
    if (ctx.model === null) {
      losses.push(
        "model unbound in DNA and none supplied — emitted PromptAgent has no " +
          "`model:` block; pass provider/model or set spec.model / Genome default_llm",
      );
    }

    const mapping: Record<string, string> = {
      "metadata.name": "name (CamelCase)",
      "metadata.description": "description",
      "buildPrompt (Soul+guardrails+instruction)": "instructions",
      "spec.model / Genome.default_llm": "model.{id,provider}",
      "spec.tools[] (Tool Kind)": "tools[] (kind: function)",
      "spec.output_schema": "outputSchema",
    };

    return new EmitResult({
      artifact,
      target: this.target,
      filename: `${ctx.name}.${this.fileExtension}`,
      losses,
      mapping,
    });
  }

  /** Byte-equal invariant hook — handles BOTH emit shapes of this target: the
   *  single-agent `PromptAgent` YAML (`instructions:` field) AND the servable
   *  copilot scaffold's `agent` module (top-level `INSTRUCTIONS` constant, a JSON
   *  string literal on one line). The scaffold path is tried first. */
  extractInstructions(artifact: string): string | null {
    const match = artifact.match(/^INSTRUCTIONS = (.+)$/m);
    if (match) {
      try {
        return JSON.parse(match[1]) as string;
      } catch {
        /* fall through to the YAML read */
      }
    }
    const doc = yaml.load(artifact) as Record<string, unknown> | undefined;
    const value = doc?.instructions;
    return typeof value === "string" ? value : null;
  }

  // ── servable copilot render (the two-artifact scaffold case) ───────────────

  /** Template variables for the Microsoft Agent Framework `copilot` case. Mirrors
   *  the Python `_copilot_context`: the mounted agent's MCP servers become
   *  `MCPStreamableHTTPTool` mounts; the HITL-write intent becomes each mount's
   *  `approval_mode` (tool-level HITL) EXCEPT a workflow copilot gates writes at
   *  the workflow level (`never_require` + an `EscalationExecutor`). Everything is
   *  sorted for a deterministic golden. */
  private copilotContext(ctx: EmitContext): Record<string, unknown> {
    const gated = ctx.toolsRequiringConfirmation;
    const hasWorkflow = ctx.workflow.length > 0;
    const hasHitl = gated.size > 0;

    const servers = ctx.mcpServers.map((s) => {
      const allowedSorted = [...s.allowedTools].sort();
      const gatedIn = s.allowedTools.filter((t) => gated.has(t)).sort();
      const reads = s.allowedTools.filter((t) => !gated.has(t)).sort();
      const approval =
        hasWorkflow || gatedIn.length === 0
          ? pyStrLiteral("never_require")
          : approvalModeLiteral(gatedIn, reads);
      return {
        name_literal: pyStrLiteral(`mcp_${s.ref}`),
        url_literal: s.url ? pyStrLiteral(s.url) : "None",
        allowed_tools_literal: pyListLiteral(allowedSorted),
        approval_mode_literal: approval,
      };
    });

    const steps = ctx.workflow.map((step, i) => ({
      step,
      func: pyIdentifier(step),
      name_literal_step: pyStrLiteral(step),
      is_first: i === 0,
    }));
    let chainFuncs = ctx.workflow.map((s) => pyIdentifier(s));
    if (hasWorkflow && hasHitl) chainFuncs = [...chainFuncs, "escalate"];

    const buildFn = hasWorkflow ? "build_workflow" : "build_agent";
    const mountedKind = hasWorkflow ? "workflow" : "agent";
    const serveAgentExpr = hasWorkflow
      ? "AgentFrameworkWorkflow(workflow_factory=build_workflow)"
      : "build_agent()";

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
      workflow_steps: steps,
      workflow_name_literal: pyStrLiteral(camel(ctx.name)),
      first_func: ctx.workflow.length > 0 ? pyIdentifier(ctx.workflow[0]) : "",
      chain_func_list: chainFuncs.join(", "),
      build_fn: buildFn,
      mounted_kind: mountedKind,
      serve_agent_expr: serveAgentExpr,
    };
  }

  private copilotLosses(ctx: EmitContext): string[] {
    const out = [
      "composition structure — Soul reuse + wired Guardrails flatten to one " +
        "`INSTRUCTIONS` string (a code-first agent has no `soul:`/`guardrails:` slot)",
      "tenant overlay — a per-tenant persona without a fork has no code-first field",
      "eval-as-contract — prompt invariants (EvalCases) have no code-first slot",
      "MCP tool bodies — the mounted agent calls the DNA MCP server's tools over " +
        "Streamable HTTP; the emitted app builds `MCPStreamableHTTPTool(...)` but the " +
        "tool implementations live on the remote MCP server, not in the scaffold",
      "frontend console — `frontend`/`knowledge` hints (CopilotKit panels, suggested " +
        "prompts, RAG collections) have no code-first backend slot; RAG retrieval " +
        "(`AzureAISearchContextProvider`) is per-app",
    ];
    if (ctx.workflow.length > 0) {
      out.push(
        "workflow step bodies — each `workflow.chain` step is a scaffolded " +
          "agent-executor STUB; per-step instructions + the escalation effect are " +
          "per-app bodies to wire at the consumer",
      );
    }
    if (ctx.model === null) {
      out.push(
        "model unbound in DNA and none supplied — emitted `FoundryChatClient(...)` " +
          "has no `model=`; supply one at wire-up",
      );
    }
    return out;
  }

  private copilotMapping(): Record<string, string> {
    return {
      "buildPrompt (Soul+guardrails+instruction)": "INSTRUCTIONS constant (byte-equal)",
      "metadata.name": "as_agent(name=...)",
      "spec.model / Genome.default_llm": "FoundryChatClient(model=...)",
      "Agent.spec.mcp_servers → MCPFederation":
        "MCPStreamableHTTPTool(url, allowed_tools, approval_mode)",
      "Tool.requires_confirmation": "approval_mode.always_require_approval (tool-level HITL)",
      "Copilot.tenant.propagate": "inbound ContextVar + header_provider (X-DNA-* stamp)",
      "Copilot.workflow.chain": "WorkflowBuilder chain + request_info escalation node",
    };
  }

  /** Render the two servable artifacts (agent module + AG-UI serve app) from an
   *  enriched copilot ctx (`buildCopilotContext`). */
  private emitCopilot(ctx: EmitContext): EmitResult {
    const agentTmpl = resolveScaffold(this.framework, "copilot_agent");
    const serveTmpl = resolveScaffold(this.framework, "copilot_serve");
    if (agentTmpl === null || serveTmpl === null) {
      throw new EmitError(
        "the agent-framework `copilot` case needs both `copilot_agent.py.tmpl` " +
          "and `copilot_serve.py.tmpl` scaffold templates",
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
