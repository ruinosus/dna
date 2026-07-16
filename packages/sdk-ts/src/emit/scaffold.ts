/**
 * `emit/scaffold` — the CODE-FIRST flavor of the {@link EmitterPort} (TS twin of
 * python `dna.emit.scaffold`).
 *
 * Some runtimes have NO declarative agent format — you construct an agent object
 * in code (OpenAI Agents SDK, LangGraph, Agno, DeepAgents all expose a simple
 * constructor). For those the emitter must produce SOURCE CODE, and it does so by
 * **filling a curated template**, never by generating code ad-hoc — the template
 * captures the framework's best-practice idiom; the emitter only routes and fills.
 *
 * The mechanism is a template library indexed by `{framework × case}` plus a tiny
 * case classifier:
 *
 *   scaffolds/<framework>/<case>.py.tmpl     // curated best-practice idiom per case
 *   selectScaffold(framework, ctx)           // inspect ctx's DNA signals → pick a case
 *
 * There is deliberately NO single "one template per framework": a prompt-only, a
 * tool-calling (ReAct), and a structured-output agent are DIFFERENT structures in
 * the SAME framework. The classifier reads the neutral {@link EmitContext} signals
 * (no tools → `prompt-only`; tools → `with-tools`; `outputSchema` →
 * `structured-output`) and falls back down a generality chain when a framework
 * does not ship a case, recording the fallback as a loss.
 *
 * Future direction — Scaffold as a Kind: templates are read through an abstract
 * seam, {@link resolveScaffold} (a {@link ScaffoldResolver}), NOT a hardcoded file
 * path. The MVP resolver reads package-data, but the seam lets a second source
 * plug in with no change to any emitter — a first-class **Scaffold Kind** resolved
 * by the kernel (scope-aware, tenant-overridable). Tracked as `s-scaffold-as-kind`.
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import Mustache from "mustache";

import { EmitError, EmitResult, type EmitContext, type EmitterPort } from "./index.js";

const HERE = dirname(fileURLToPath(import.meta.url));

/** The generality fallback chain (specific → general) per requested case. */
const FALLBACK: Record<string, string[]> = {
  "structured-output": ["structured-output", "with-tools", "prompt-only"],
  "with-tools": ["with-tools", "prompt-only"],
  "prompt-only": ["prompt-only"],
};

/** Render `value` as a Python string literal that round-trips exactly. JSON
 *  string syntax is a valid Python literal (`\n`, `\"`, `\\`, `\uXXXX`), single
 *  line — so the emitted `INSTRUCTIONS` constant is byte-equal-recoverable. */
export function pyStrLiteral(value: string): string {
  return JSON.stringify(value);
}

/** `kb-search` → `kb_search` — a valid Python identifier for a tool stub. */
export function pyIdentifier(name: string): string {
  let ident = String(name)
    .trim()
    .replace(/[^0-9a-zA-Z_]/g, "_")
    .replace(/^_+|_+$/g, "");
  if (!ident) ident = "tool";
  if (/^[0-9]/.test(ident)) ident = `_${ident}`;
  return ident;
}

/** The default case classifier — read the DNA signals the ctx already carries. */
export function classifyCase(ctx: EmitContext): string {
  if (ctx.outputSchema) return "structured-output";
  if (ctx.tools.length > 0) return "with-tools";
  return "prompt-only";
}

// ── the template-resolution seam (package-data today; Scaffold Kind tomorrow) ─

/** Resolve a `{framework × case}` template to its Mustache source — the abstract
 *  seam between an emitter and *where a template lives*. The MVP reads
 *  package-data ({@link PackageDataScaffoldResolver}); a future kernel-backed
 *  resolver returns a per-scope/per-tenant Scaffold Kind body, swappable with no
 *  emitter change. Returns null when the source has no template for the pair. */
export interface ScaffoldResolver {
  resolve(framework: string, kase: string): string | null;
}

/** The MVP resolver: read `emit/scaffolds/<framework>/<case>.py.tmpl`. */
export class PackageDataScaffoldResolver implements ScaffoldResolver {
  resolve(framework: string, kase: string): string | null {
    const path = join(HERE, "scaffolds", framework, `${kase}.py.tmpl`);
    return existsSync(path) ? readFileSync(path, "utf-8") : null;
  }
}

let activeResolver: ScaffoldResolver = new PackageDataScaffoldResolver();

/** Swap the active template resolver — the seam the Scaffold-as-Kind promotion
 *  (`s-scaffold-as-kind`) plugs into. */
export function setScaffoldResolver(resolver: ScaffoldResolver): ScaffoldResolver {
  activeResolver = resolver;
  return resolver;
}

/** Resolve a `{framework × case}` template through the active resolver. */
export function resolveScaffold(framework: string, kase: string): string | null {
  return activeResolver.resolve(framework, kase);
}

/** The outcome of {@link selectScaffold}: which case template to fill. */
export interface ScaffoldChoice {
  /** The case actually selected (a template exists for it). */
  case: string;
  /** The template source (Mustache). */
  template: string;
  /** The case the classifier requested — differs from `case` on a fallback. */
  requested: string;
}

/** Pick the `{framework × case}` template for `ctx`: classify, then resolve to a
 *  real template, falling back down the generality chain when needed. */
export function selectScaffold(
  framework: string,
  ctx: EmitContext,
  classify: (ctx: EmitContext) => string = classifyCase,
  resolver: ScaffoldResolver | null = null,
): ScaffoldChoice {
  const resolve = resolver
    ? (f: string, k: string) => resolver.resolve(f, k)
    : resolveScaffold;
  const requested = classify(ctx);
  for (const kase of FALLBACK[requested] ?? [requested]) {
    const template = resolve(framework, kase);
    if (template !== null) return { case: kase, template, requested };
  }
  throw new EmitError(
    `no scaffold template for framework '${framework}' ` +
      `(looked for case '${requested}' and its fallbacks)`,
  );
}

/** Base for a CODE-FIRST {@link EmitterPort}. A subclass is THIN — it declares the
 *  framework + target ids and supplies the framework-specific template variables
 *  ({@link renderContext}), losses, and field mapping; case selection, template
 *  fill, and the byte-equal invariant hook are inherited. */
export abstract class ScaffoldEmitter implements EmitterPort {
  abstract readonly framework: string;
  abstract readonly target: string;
  readonly fileExtension: string = "py";
  /** Optional template-resolution override (defaults to the active resolver —
   *  package-data today, a Scaffold Kind resolver tomorrow). */
  readonly resolver: ScaffoldResolver | null = null;

  // ── the hooks a subclass overrides ────────────────────────────────────────

  /** Framework-specific template variables (merged over the common ones). */
  renderContext(_ctx: EmitContext, _case: string): Record<string, unknown> {
    return {};
  }

  /** Framework-specific de-para losses (in addition to the common ones). */
  losses(_ctx: EmitContext, _choice: ScaffoldChoice): string[] {
    return [];
  }

  /** Field-level de-para (`dnaField -> targetField`) for reporting. */
  mapping(): Record<string, string> {
    return {};
  }

  /** The case classifier — override to add a framework-specific case. */
  classify(ctx: EmitContext): string {
    return classifyCase(ctx);
  }

  // ── the inherited machinery ───────────────────────────────────────────────

  protected commonContext(ctx: EmitContext): Record<string, unknown> {
    return {
      name: ctx.name,
      name_literal: pyStrLiteral(ctx.name),
      description: ctx.description,
      has_description: Boolean(ctx.description),
      // INSTRUCTIONS constant — byte-equal, recoverable via extractInstructions.
      instructions_literal: pyStrLiteral(ctx.instructions),
    };
  }

  protected commonLosses(ctx: EmitContext, choice: ScaffoldChoice): string[] {
    const losses = [
      "composition structure — Soul reuse + wired Guardrails flatten to one " +
        "`INSTRUCTIONS` string (a code-first agent has no `soul:`/`guardrails:` slot)",
      "tenant overlay — a per-tenant persona without a fork has no code-first field",
      "eval-as-contract — prompt invariants (EvalCases) have no code-first slot",
    ];
    if (choice.case !== choice.requested) {
      losses.push(
        `scaffold case — the '${choice.requested}' idiom is not shipped for ` +
          `'${this.framework}'; fell back to the '${choice.case}' template ` +
          "(structure closest to but not identical to the requested case)",
      );
    }
    return losses;
  }

  emit(ctx: EmitContext): EmitResult {
    const choice = selectScaffold(this.framework, ctx, (c) => this.classify(c), this.resolver);
    const variables = { ...this.commonContext(ctx), ...this.renderContext(ctx, choice.case) };
    const artifact = Mustache.render(choice.template, variables);
    const losses = [...this.commonLosses(ctx, choice), ...this.losses(ctx, choice)];
    return new EmitResult({
      artifact,
      target: this.target,
      filename: `${ctx.name}.${this.fileExtension}`,
      losses,
      mapping: this.mapping(),
    });
  }

  /** Byte-equal invariant hook: read the top-level `INSTRUCTIONS = <literal>`
   *  constant every scaffold template emits (a JSON/Python string literal on one
   *  line), uniform across all code-first targets regardless of constructor shape. */
  extractInstructions(artifact: string): string | null {
    const match = artifact.match(/^INSTRUCTIONS = (.+)$/m);
    if (!match) return null;
    try {
      return JSON.parse(match[1]) as string;
    } catch {
      return null;
    }
  }
}
