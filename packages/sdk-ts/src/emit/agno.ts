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
import { pyIdentifier, pyStrLiteral, ScaffoldEmitter, type ScaffoldChoice } from "./scaffold.js";
import type { EmitContext } from "./index.js";

export class AgnoEmitter extends ScaffoldEmitter {
  readonly framework = "agno";
  readonly target = "agno";
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
}
