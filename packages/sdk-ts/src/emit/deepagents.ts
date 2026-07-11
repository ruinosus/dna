/**
 * DNA → **DeepAgents** emitter (code-first, `deepagents`; TS twin of python
 * `dna.emit.deepagents`).
 *
 * DeepAgents (the LangChain "batteries-included agent harness") is code-first — you
 * call `create_deep_agent(model=..., tools=[...], system_prompt="...")`, there is no
 * declarative agent file to map onto. So this target is a {@link ScaffoldEmitter}: it
 * fills a curated `{deepagents × case}` template rather than generating code ad-hoc,
 * and the emitted `INSTRUCTIONS` constant is byte-equal to the DNA-composed prompt.
 *
 * `system_prompt` sits in FRONT of the deep-agent's built-in harness prompt (the
 * planning / filesystem / sub-agent scaffolding the framework appends) — so the DNA
 * prompt is a PREFIX of the effective system prompt. Model: the DNA coordinate is
 * PRESERVED (resolved via `init_chat_model`). Cases: `prompt-only` and `with-tools`.
 */
import { pyIdentifier, pyStrLiteral, ScaffoldEmitter, type ScaffoldChoice } from "./scaffold.js";
import type { EmitContext } from "./index.js";

export class DeepAgentsEmitter extends ScaffoldEmitter {
  readonly framework = "deepagents";
  readonly target = "deepagents";
  readonly fileExtension = "py";

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
    const out: string[] = [
      "harness prompt — `system_prompt` sits in FRONT of the deep-agent's built-in " +
        "harness prompt (planning / filesystem / sub-agent scaffolding), which the " +
        "framework appends; the DNA prompt is a PREFIX of the effective system prompt, " +
        "not the whole of it",
      "metadata.name — `create_deep_agent` has no declarative name slot; the DNA agent " +
        "name is not carried",
    ];
    if (ctx.tools.length > 0) {
      out.push(
        "tool body — each tool is a scaffolded STUB (a callable + " +
          "`raise NotImplementedError`); its real implementation and typed signature " +
          "must be wired",
      );
    }
    if (ctx.model === null) {
      out.push(
        "model unbound in DNA and none supplied — emitted `create_deep_agent(...)` has " +
          "no `model=`; the framework falls back to its default deep-agent model",
      );
    } else {
      out.push(
        "model coordinate — the DNA coordinate is carried verbatim; " +
          "`create_deep_agent` resolves it via `init_chat_model`, whose provider " +
          "prefixes are `openai` / `anthropic` / `azure_openai` / `google_genai`; a " +
          "DNA `azure/…` coordinate needs the `azure_openai:` prefix at wire-up",
      );
    }
    if (ctx.outputSchema) {
      out.push(
        "output_schema — DNA's `spec.output_schema` has no direct `create_deep_agent` " +
          "slot; enforce structured output via a middleware or a typed sub-agent by hand",
      );
    }
    return out;
  }

  mapping(): Record<string, string> {
    return {
      "buildPrompt (Soul+guardrails+instruction)":
        "INSTRUCTIONS constant (byte-equal, PREFIX of system_prompt)",
      "spec.model / Genome.default_llm": "create_deep_agent(model=...) (DNA coordinate preserved)",
      "spec.tools[] (Tool Kind)": "callable stubs → create_deep_agent(tools=[...])",
    };
  }
}
