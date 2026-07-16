/**
 * DNA → **Google ADK Agent Config** emitter (TS twin of python
 * `dna.emit.vertex`). Materializes an {@link EmitContext} into a **Google Agent
 * Development Kit (ADK) Agent Config** YAML — the declarative, code-free way to
 * define an ADK `LlmAgent` (loaded with `config_agent_utils.from_config(...)`).
 * The THIRD runtime the SAME DNA source emits to (after Microsoft agent-framework
 * and Amazon Bedrock): the portability proof — author once, emit per runtime.
 *
 * Why the ADK **Agent Config** (not the code-first `LlmAgent` object or Vertex AI
 * Agent Engine): only Agent Config has a published, field-for-field *declarative*
 * schema (`agent_class`, `name`, `model`, `instruction`, `tools`, …), so it is the
 * only honest de-para target. Emitting the YAML gives a lintable artifact that
 * needs no GCP credential to produce or validate structurally (the
 * `# yaml-language-server` header wires the real schema into any editor).
 *
 * The de-para (DNA field → ADK `LlmAgentConfig` field):
 *   (fixed)                           -> agent_class: LlmAgent
 *   metadata.name                     -> name          (snake_cased — valid identifier)
 *   metadata.description              -> description    (when present)
 *   Soul + guardrails + instruction   -> instruction   (flat, BYTE-EQUAL)
 *   spec.model (or Genome default_llm)-> model          (Gemini id; provider stripped)
 *   spec.tools[] (Tool Kind surfaces) -> tools[].name   (a CODE reference — see loss)
 *
 * `toAgentConfig` is the PURE de-para and is parity-critical: it must build the
 * SAME object the Python `to_agent_config` builds from the same context.
 */
import yaml from "js-yaml";

import { EmitResult } from "./index.js";
import type { EmitContext, EmitTool, EmitterPort } from "./index.js";

/** The published ADK Agent Config JSON Schema — emitted as a leading
 *  `# yaml-language-server` header so any editor / validator binds the artifact to
 *  the REAL schema (the credential-free structural-validation hook). */
const ADK_SCHEMA_URL =
  "https://raw.githubusercontent.com/google/adk-python/refs/heads/main/" +
  "src/google/adk/agents/config_schemas/AgentConfig.json";

/** The ADK `agent_class` this emitter targets (the declarative LLM agent). */
const AGENT_CLASS = "LlmAgent";

/** DNA provider tokens (the `prov:model` / `prov/model` prefixes). Stripped to
 *  expose the bare model id; a bare Gemini id passes through unchanged. */
const DNA_PROVIDER_TOKENS = new Set([
  "azure", "azureopenai", "azure_openai", "openai", "foundry", "azureaifoundry",
  "vertex", "google", "gemini", "anthropic",
]);

/** `concierge-grounded` → `concierge_grounded` (a valid ADK agent name — ADK
 *  requires a Python identifier). Mirrors Bedrock's `camel` logical-id transform. */
export function snake(name: string): string {
  let ident = String(name)
    .trim()
    .split("")
    .map((ch) => (/[a-zA-Z0-9_]/.test(ch) ? ch : "_"))
    .join("")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
  if (!ident) ident = "agent";
  if (/^[0-9]/.test(ident)) ident = `_${ident}`;
  return ident;
}

/** Project a DNA model coordinate → an ADK `model` id. A known DNA provider token
 *  (`vertex/gemini-2.0-flash` → `gemini-2.0-flash`, `openai:gpt-4o` → `gpt-4o`) is
 *  stripped; a bare id passes through. */
export function vertexModelId(model: string | null): string | null {
  if (!model) return null;
  const ident = model.trim();
  const slash = ident.indexOf("/");
  if (slash >= 0) {
    const token = ident.slice(0, slash).trim().toLowerCase();
    if (DNA_PROVIDER_TOKENS.has(token)) return ident.slice(slash + 1).trim();
    return ident;
  }
  const colon = ident.indexOf(":");
  if (colon >= 0) {
    const token = ident.slice(0, colon).trim().toLowerCase();
    if (DNA_PROVIDER_TOKENS.has(token)) return ident.slice(colon + 1).trim();
  }
  return ident;
}

/** Whether an emitted `model` id is a native Gemini id (else needs `model_code`). */
export function isGemini(modelId: string | null): boolean {
  return !!modelId && modelId.trim().toLowerCase().startsWith("gemini");
}

/** Project neutral tool surfaces → ADK `tools` code references (`- name: <fqn>`).
 *  ADK has no inline function-schema slot (unlike agent-framework / Bedrock): it
 *  derives a tool's description + parameters from the referenced Python callable at
 *  load, so the faithful de-para carries the tool NAME as a placeholder reference. */
function emitTools(tools: EmitTool[]): Record<string, unknown>[] {
  return tools.map((t) => ({ name: t.name }));
}

export class VertexEmitter implements EmitterPort {
  readonly target = "vertex";
  readonly fileExtension = "adk.yaml";

  /** The PURE de-para: {@link EmitContext} → the ADK Agent Config object. Field
   *  order is intentional; the schema-header comment is prepended at serialization
   *  time, not part of this object. */
  toAgentConfig(ctx: EmitContext): Record<string, unknown> {
    const doc: Record<string, unknown> = { agent_class: AGENT_CLASS, name: snake(ctx.name) };
    if (ctx.description) doc.description = ctx.description;
    const modelId = vertexModelId(ctx.model);
    if (modelId) doc.model = modelId;
    doc.instruction = ctx.instructions; // verbatim — the byte-equal gate
    if (ctx.tools.length > 0) doc.tools = emitTools(ctx.tools);
    return doc;
  }

  emit(ctx: EmitContext): EmitResult {
    const config = this.toAgentConfig(ctx);
    const body = yaml.dump(config, { sortKeys: false, lineWidth: -1 });
    const artifact = `# yaml-language-server: $schema=${ADK_SCHEMA_URL}\n${body}`;

    const losses = [
      "composition structure — Soul reuse + wired Guardrails flatten to one " +
        "`instruction` string (Agent Config has no `soul:`/`guardrails:` slot)",
      "tenant overlay — a per-tenant persona without a fork has no Agent Config field",
      "eval-as-contract — prompt invariants (EvalCases) have no Agent Config slot",
    ];
    if (ctx.tools.length > 0) {
      losses.push(
        "tool binding — ADK binds a tool by a CODE reference (a fully qualified " +
          "Python path or a built-in name), not a declarative schema; a Tool's " +
          "`description` and `parameters` (JSON Schema) have no Agent Config slot " +
          "(ADK derives them from the Python callable at load). Each emitted `- name` " +
          "is a placeholder to repoint to the tool's real FQN",
      );
    }
    if (ctx.outputSchema) {
      losses.push(
        "output_schema — ADK `output_schema` is a `CodeConfig` (a reference to a " +
          "Pydantic class by FQN), not an inline JSON Schema; DNA's inline " +
          "`spec.output_schema` has no inline Agent Config slot",
      );
    }
    const modelId = vertexModelId(ctx.model);
    if (modelId === null) {
      losses.push(
        "model unbound in DNA and none supplied — emitted config has no `model`; " +
          "ADK inherits the ancestor / system default (gemini)",
      );
    } else if (!isGemini(modelId)) {
      losses.push(
        "model coordinate — ADK `model` natively accepts a Gemini id; a DNA " +
          "`azure/openai` coordinate is not a Gemini id and needs `model_code` (a " +
          "`LiteLlm` CodeConfig) at deploy, plus a GCP project/region",
      );
    }

    const mapping: Record<string, string> = {
      "metadata.name": "name (snake_case identifier)",
      "metadata.description": "description",
      "buildPrompt (Soul+guardrails+instruction)": "instruction (byte-equal)",
      "spec.model / Genome.default_llm": "model (Gemini id; provider token stripped)",
      "spec.tools[] (Tool Kind)": "tools[].name (code reference)",
    };

    return new EmitResult({
      artifact,
      target: this.target,
      filename: `${ctx.name}.${this.fileExtension}`,
      losses,
      mapping,
    });
  }

  /** Byte-equal invariant hook: read `instruction` back from the emitted ADK
   *  Agent Config YAML (the `# yaml-language-server` header is a YAML comment). */
  extractInstructions(artifact: string): string | null {
    const config = yaml.load(artifact) as Record<string, unknown> | undefined;
    const value = config?.instruction;
    return typeof value === "string" ? value : null;
  }
}
