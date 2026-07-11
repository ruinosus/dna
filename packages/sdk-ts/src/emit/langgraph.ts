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
import { pyIdentifier, pyStrLiteral, ScaffoldEmitter, type ScaffoldChoice } from "./scaffold.js";
import type { EmitContext } from "./index.js";

export class LanggraphEmitter extends ScaffoldEmitter {
  readonly framework = "langgraph";
  readonly target = "langgraph";
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
}
