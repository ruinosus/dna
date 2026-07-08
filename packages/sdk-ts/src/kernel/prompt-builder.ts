/**
 * PromptBuilder — namespace class extracting prompt-related logic
 * from ManifestInstance.
 *
 * Usage: `mi.prompt.build()` — equivalent to `mi.buildPrompt()`.
 *
 * This is an extraction (Chunk 2 of the kernel simplification plan).
 * The original methods on ManifestInstance are preserved; both APIs
 * return identical results.
 */

import Mustache from "mustache";

import type { Document } from "./document.js";
import type { HookContext } from "./hooks.js";
import type { ManifestInstance, BuildPromptOpts } from "./instance.js";

// ---------------------------------------------------------------------------
// PromptBuilder
// ---------------------------------------------------------------------------

export class PromptBuilder {
  constructor(private host: ManifestInstance) {}

  /**
   * Build the final prompt string for the given (or default) agent.
   * Equivalent to `mi.buildPrompt(opts)`.
   */
  async build(opts?: BuildPromptOpts): Promise<string> {
    const agentOpt = opts?.agent;
    const extra = opts?.context;

    // Resolve agent name
    let agentName = agentOpt ?? null;
    if (!agentName) {
      const root = this.host.root;
      if (root) {
        const kp = (this.host as any)._kinds.get(`${root.apiVersion}\0${root.kind}`);
        if (kp) {
          agentName = kp.getDefaultAgentName(root);
        }
      }
    }

    const agentDoc = agentName ? this._findAgent(agentName) : null;
    if (!agentDoc) {
      return `Agent '${agentName}' not found`;
    }

    // Build context — merge backwards-compat params into enabledSlots
    const enabledSlots: Record<string, string[]> = { ...(opts?.enabledSlots ?? {}) };
    if (opts?.enabledSkills && !enabledSlots.skills) enabledSlots.skills = opts.enabledSkills;
    if (opts?.enabledGuardrails && !enabledSlots.guardrails) enabledSlots.guardrails = opts.enabledGuardrails;
    let ctx = await this._buildContext(agentDoc, extra, enabledSlots);

    // Hook: pre_build_prompt — middleware can modify context
    const kernel = (this.host as any)._kernel as { hooks?: { has(h: string): boolean; runMiddleware(h: string, c: HookContext): HookContext; emit(h: string, c: HookContext): void } } | null;
    if (kernel?.hooks?.has("pre_build_prompt")) {
      const hookCtx: HookContext = {
        scope: this.host.scope,
        agent: agentName ?? undefined,
        data: { context: ctx },
      };
      const result = kernel.hooks.runMiddleware("pre_build_prompt", hookCtx);
      ctx = (result.data.context as Record<string, unknown>) ?? ctx;
    }

    // Render via template cascade
    const prompt = await this._renderPrompt(ctx, agentDoc);

    // Hook: post_build_prompt — event notification
    if (kernel?.hooks?.has("post_build_prompt")) {
      kernel.hooks.emit("post_build_prompt", {
        scope: this.host.scope,
        agent: agentName ?? undefined,
        prompt,
        data: {},
      });
    }

    return prompt;
  }

  // -------------------------------------------------------------------------
  // Private helpers
  // -------------------------------------------------------------------------

  private _findAgent(name: string): Document | null {
    let best: Document | null = null;
    let bestPriority = -1;
    const kinds = (this.host as any)._kinds as Map<string, any>;
    for (const d of this.host.documents) {
      const kp = kinds.get(`${d.apiVersion}\0${d.kind}`);
      if (kp?.isPromptTarget && d.name === name) {
        const priority = kp.promptTargetPriority ?? 0;
        if (priority > bestPriority) {
          best = d;
          bestPriority = priority;
        }
      }
    }
    return best;
  }

  private async _buildContext(
    agentDoc: Document,
    extra?: Record<string, unknown>,
    enabledSlots?: Record<string, string[]>,
  ): Promise<Record<string, unknown>> {
    const ctx: Record<string, unknown> = {};
    const kinds = (this.host as any)._kinds as Map<string, any>;

    // Root metadata + spec
    const root = this.host.root;
    if (root) {
      ctx.metadata = { ...root.metadata };
      ctx.spec = { ...root.spec };
    }

    // Agent entry
    const agentSpec = agentDoc.spec;
    const instructionRef = (agentSpec.instruction as string) ?? "";
    ctx.agent = {
      name: agentDoc.name,
      description: PromptBuilder._getDescription(agentDoc),
      instruction: instructionRef ? await this.host.ref(instructionRef) : "",
    };
    ctx.agentId = agentDoc.name;

    // All documents grouped by alias (for Mustache sections)
    for (const doc of this.host.documents) {
      const kp = kinds.get(`${doc.apiVersion}\0${doc.kind}`);
      if (!kp) continue;
      const alias = kp.alias;
      if (!ctx[alias]) ctx[alias] = [];

      const entry: Record<string, unknown> = {
        name: doc.name,
        description: PromptBuilder._getDescription(doc),
      };
      const spec = doc.spec;
      for (const [k, v] of Object.entries(spec)) {
        if (k.startsWith("_") || v == null) continue;
        entry[k] = typeof v === "string" ? await this.host.ref(v) : v;
      }
      (ctx[alias] as Record<string, unknown>[]).push(entry);
    }

    // Dep filtering: agent's dep_filters restrict which docs appear per alias
    const agentKp = kinds.get(
      `${agentDoc.apiVersion}\0${agentDoc.kind}`,
    );
    if (agentKp) {
      const filters = agentKp.depFilters();
      if (filters) {
        for (const [specField, targetAlias] of Object.entries(filters)) {
          if (!(targetAlias as string in ctx)) continue;
          const declared = agentSpec[specField];

          if (declared == null || declared === "") {
            // Field not declared or empty -> filter to empty
            ctx[targetAlias as string] = [];
            continue;
          }
          if (typeof declared === "string") {
            ctx[targetAlias as string] = (
              ctx[targetAlias as string] as Record<string, unknown>[]
            ).filter((e) => e.name === declared);
          } else if (Array.isArray(declared)) {
            if (declared.length === 0) {
              ctx[targetAlias as string] = [];
            } else {
              ctx[targetAlias as string] = (
                ctx[targetAlias as string] as Record<string, unknown>[]
              ).filter((e) => declared.includes(e.name as string));
            }
          }
        }
      }
    }

    // Generic slot filtering: caller restricts which docs appear per slot.
    if (agentKp && enabledSlots && Object.keys(enabledSlots).length > 0) {
      const filters = agentKp.depFilters();
      if (filters) {
        for (const [slotName, enabledNames] of Object.entries(enabledSlots)) {
          const alias = (filters as Record<string, string>)[slotName];
          if (alias && alias in ctx) {
            ctx[alias] = (ctx[alias] as Record<string, unknown>[])
              .filter((e) => enabledNames.includes(e.name as string));
          }
        }
      }
    }

    // Flatten: kinds with flattenInContext have their spec entries merged into ctx
    for (const doc of this.host.documents) {
      const kp = kinds.get(`${doc.apiVersion}\0${doc.kind}`);
      if (!kp?.flattenInContext) continue;
      const spec = doc.spec;
      for (const [k, v] of Object.entries(spec)) {
        if (k.startsWith("_") || v == null) continue;
        ctx[k] = typeof v === "string" ? await this.host.ref(v) : v;
      }
    }

    // Extra context from caller
    if (extra) {
      Object.assign(ctx, extra);
    }

    return ctx;
  }

  private async _renderPrompt(
    ctx: Record<string, unknown>,
    agentDoc: Document,
  ): Promise<string> {
    const agentSpec = agentDoc.spec;
    const kinds = (this.host as any)._kinds as Map<string, any>;

    // 1. Agent-level template override
    const agentTemplate =
      (agentSpec.promptTemplate as string) ??
      (agentSpec.prompt_template as string) ??
      null;
    if (agentTemplate) {
      return await this._mustacheRender(agentTemplate, ctx);
    }

    // 2. Kind default template
    const agentKp = kinds.get(
      `${agentDoc.apiVersion}\0${agentDoc.kind}`,
    );
    if (agentKp) {
      const kindTemplate = agentKp.promptTemplate();
      if (kindTemplate) {
        return await this._mustacheRender(kindTemplate, ctx);
      }
    }

    // 3. Fallback: agent instruction as plain text
    const agent = ctx.agent as Record<string, unknown> | undefined;
    return (agent?.instruction as string) ?? "";
  }

  private async _mustacheRender(
    template: string,
    ctx: Record<string, unknown>,
  ): Promise<string> {
    // Resolve template if it's a file reference
    let tmpl = template;
    if (
      tmpl.includes("/") ||
      tmpl.endsWith(".mustache") ||
      tmpl.endsWith(".md")
    ) {
      tmpl = await this.host.ref(tmpl);
    }

    // Double render: first pass resolves Mustache tags, second pass resolves
    // any tags that were inside resolved content.
    const firstPass = Mustache.render(tmpl, ctx);
    return Mustache.render(firstPass, ctx);
  }

  private static _getDescription(doc: Document): string {
    return (doc.metadata.description as string) ?? "";
  }
}
