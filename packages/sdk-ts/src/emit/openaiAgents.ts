/**
 * DNA → **OpenAI Agents SDK** emitter (the first CODE-FIRST target; TS twin of
 * python `dna.emit.openai_agents`).
 *
 * The OpenAI Agents SDK is code-first — you construct an agent in Python
 * (`Agent(name=..., instructions=..., model=..., tools=[...])`) — so this target
 * is a {@link ScaffoldEmitter}: it fills a curated `{openai-agents × case}`
 * template rather than generating code ad-hoc, and the emitted `INSTRUCTIONS`
 * constant is byte-equal to the DNA-composed prompt.
 *
 * Cases (selected from ctx signals): `prompt-only` (no tools) and `with-tools`
 * (the ReAct idiom — one `@function_tool` stub per DNA Tool). `structured-output`
 * is not shipped yet and falls back with a recorded loss.
 */
import { pyIdentifier, pyStrLiteral, ScaffoldEmitter, type ScaffoldChoice } from "./scaffold.js";
import type { EmitContext } from "./index.js";

const DNA_PROVIDER_TOKENS = new Set([
  "azure", "azureopenai", "azure_openai", "openai", "foundry", "azureaifoundry",
  "vertex", "google", "gemini", "anthropic",
]);

/** Strip a DNA `prov:model` / `prov/model` coordinate to the bare id. */
export function bareModelId(model: string | null): string | null {
  if (!model) return null;
  const ident = model.trim();
  for (const sep of [":", "/"]) {
    const i = ident.indexOf(sep);
    if (i >= 0) {
      const token = ident.slice(0, i).trim().toLowerCase();
      if (DNA_PROVIDER_TOKENS.has(token)) return ident.slice(i + 1).trim();
    }
  }
  return ident;
}

function isOpenAIModel(modelId: string | null): boolean {
  if (!modelId) return false;
  const m = modelId.trim().toLowerCase();
  return m.startsWith("gpt-") || m.startsWith("o1") || m.startsWith("o3") || m.startsWith("o4");
}

export class OpenAIAgentsEmitter extends ScaffoldEmitter {
  readonly framework = "openai-agents";
  readonly target = "openai-agents";
  readonly fileExtension = "py";

  renderContext(ctx: EmitContext, _case: string): Record<string, unknown> {
    const modelId = bareModelId(ctx.model);
    const tools = ctx.tools.map((t) => ({
      name: t.name,
      func_name: pyIdentifier(t.name),
      docstring_literal: pyStrLiteral(t.description || t.name),
    }));
    return {
      has_model: modelId !== null,
      model_literal: modelId ? pyStrLiteral(modelId) : "",
      tools,
      tool_list: tools.map((t) => t.func_name).join(", "),
    };
  }

  losses(ctx: EmitContext, _choice: ScaffoldChoice): string[] {
    const out: string[] = [];
    if (ctx.tools.length > 0) {
      out.push(
        "tool body — each `@function_tool` is a scaffolded STUB (name + " +
          "`raise NotImplementedError`); its real implementation and typed " +
          "signature must be wired (the OpenAI Agents SDK derives the tool schema " +
          "from the Python function signature + docstring)",
      );
    }
    const modelId = bareModelId(ctx.model);
    if (modelId === null) {
      out.push(
        "model unbound in DNA and none supplied — emitted `Agent(...)` has no " +
          "`model=`; the SDK falls back to its default",
      );
    } else if (!isOpenAIModel(modelId)) {
      out.push(
        "model coordinate — the OpenAI Agents SDK `model=` takes an OpenAI model " +
          "name or a `Model` object; a non-OpenAI coordinate needs a custom " +
          "provider / `ModelSettings` at wire-up",
      );
    }
    if (ctx.outputSchema) {
      out.push(
        "output_schema — map DNA's `spec.output_schema` to `Agent(output_type=...)` " +
          "(a Pydantic/TypedDict class) by hand; the scaffold does not synthesize the class",
      );
    }
    return out;
  }

  mapping(): Record<string, string> {
    return {
      "buildPrompt (Soul+guardrails+instruction)": "INSTRUCTIONS constant (byte-equal)",
      "metadata.name": "Agent(name=...)",
      "spec.model / Genome.default_llm": "Agent(model=...) (provider token stripped)",
      "spec.tools[] (Tool Kind)": "@function_tool stubs → Agent(tools=[...])",
    };
  }
}
