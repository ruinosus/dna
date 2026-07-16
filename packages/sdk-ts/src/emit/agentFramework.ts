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

import { EmitResult } from "./index.js";
import type { EmitContext, EmitTool, EmitterPort } from "./index.js";

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

export class AgentFrameworkEmitter implements EmitterPort {
  readonly target = "agent-framework";
  readonly fileExtension = "agent.yaml";

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

  /** Byte-equal invariant hook: read `instructions` back from the emitted YAML. */
  extractInstructions(artifact: string): string | null {
    const doc = yaml.load(artifact) as Record<string, unknown> | undefined;
    const value = doc?.instructions;
    return typeof value === "string" ? value : null;
  }
}
