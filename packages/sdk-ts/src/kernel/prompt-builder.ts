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

import { stripPromptBlock } from "./_text.js";
import { AgentNotFound, UnknownLayout } from "./errors.js";
import { documentHash } from "./lock.js";
import type { Document } from "./document.js";
import type { HookContext } from "./hooks.js";
import type { ManifestInstance, BuildPromptOpts } from "./instance.js";

// ---------------------------------------------------------------------------
// Explain mode — per-section prompt provenance (s-dna-explain-provenance).
// 1:1 with Python dna.kernel.prompt_builder (SectionProvenance / PromptExplanation).
// ---------------------------------------------------------------------------

/** Provenance for ONE composed prompt section (instruction / soul / skill /
 *  guardrail). Reconstructed from the layout template + depFilters +
 *  flattenInContext plus the layer provenance `resolveDocument` returns — NOT
 *  by re-running composition. */
export interface SectionProvenance {
  /** Label, e.g. `instruction` / `soul:warm` / `skill:greeting`. */
  section: string;
  /** Contributing Kind (`Agent` / `Soul` / `Skill` / `Guardrail`). */
  kind: string;
  /** Contributing document name. */
  name: string;
  /** Canonical source artifact path, e.g. `skills/greeting/SKILL.md`. */
  source: string;
  /** SHA-256 of the resolved (effective) raw doc, or null. */
  hash: string | null;
  /** `metadata.version` of the resolved doc, when the author set one. */
  version: string | null;
  /** Effective layer scope the section resolved from. */
  origin: string;
  /** True when `origin` differs from the requested scope (inherited). */
  isInherited: boolean;
  /** True when a TENANT overlay changed this section vs the base. */
  overriddenByTenant: boolean;
}

/** The composed prompt PLUS a section→provenance map. `prompt` is
 *  byte-identical to `buildPrompt` — explain mode never re-renders. */
export interface PromptExplanation {
  prompt: string;
  sections: SectionProvenance[];
}

/** Options for {@link PromptBuilder.explain}. */
export interface ExplainOpts extends BuildPromptOpts {
  /** Resolve with this tenant's overlays (marks overridden sections). */
  tenant?: string | null;
}

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
      // Fail loud (s-dx-build-prompt-fail-loud): throw a typed error instead
      // of returning a placeholder string that would become the literal
      // instruction.
      throw new AgentNotFound(agentName);
    }

    // Build context — merge backwards-compat params into enabledSlots. An
    // explicit empty array means "disable all", ONLY undefined means "no
    // filter" — guarding on truthiness would treat `[]` as unset and leak
    // every skill/guardrail into the prompt (load-bearing after i-031).
    const enabledSlots: Record<string, string[]> = { ...(opts?.enabledSlots ?? {}) };
    if (opts?.enabledSkills !== undefined && !enabledSlots.skills) enabledSlots.skills = opts.enabledSkills;
    if (opts?.enabledGuardrails !== undefined && !enabledSlots.guardrails) enabledSlots.guardrails = opts.enabledGuardrails;
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

    // Clean output (s-dx-clean-composition-output): template sections can pad
    // the composed prompt with trailing newlines; consumers used to strip them
    // themselves. Return it already clean.
    return prompt.replace(/\n+$/, "");
  }

  // -------------------------------------------------------------------------
  // Explain mode — per-section provenance (s-dna-explain-provenance)
  // -------------------------------------------------------------------------

  /**
   * Compose the agent AND return per-section provenance.
   *
   * Returns the composed prompt (byte-identical to {@link build} — explain
   * mode never re-renders) plus a section→provenance map: the source artifact,
   * content hash, version, and layer/overlay origin of each declared
   * composition input (instruction, soul, skills, guardrails). Provenance is
   * reconstructed from the kernel's own declared blocks (layout template +
   * depFilters + flattenInContext) + the layer provenance `resolveDocument`
   * already returns. 1:1 with Python `PromptBuilder.explain`.
   */
  async explain(opts?: ExplainOpts): Promise<PromptExplanation> {
    // Prompt = the ONE canonical composition (byte-equal gate: same path).
    const prompt = await this.build(opts);

    const tenant = opts?.tenant ?? null;
    let agentName = opts?.agent ?? this._defaultAgentName();
    const agentDoc = agentName ? this._findAgent(agentName) : null;
    if (!agentDoc) throw new AgentNotFound(agentName);

    const slots = this._mergeSlots(opts);
    const template = await this._effectiveTemplate(agentDoc);
    const specs = this._sectionSpecs(agentDoc, template, slots);

    const sections: SectionProvenance[] = [];
    for (const [label, kp, docName] of specs) {
      const base = await this._resolve(kp.kind, docName, null);
      const effective = tenant ? await this._resolve(kp.kind, docName, tenant) : base;
      sections.push(this._sectionProvenance(label, kp, docName, effective, base, tenant));
    }
    return { prompt, sections };
  }

  private _defaultAgentName(): string | null {
    const root = this.host.root;
    if (root) {
      const kp = (this.host as any)._kinds.get(`${root.apiVersion}\0${root.kind}`);
      if (kp) return kp.getDefaultAgentName(root);
    }
    return null;
  }

  private _mergeSlots(opts?: ExplainOpts): Record<string, string[]> {
    const slots: Record<string, string[]> = { ...(opts?.enabledSlots ?? {}) };
    if (opts?.enabledSkills !== undefined && !slots.skills) slots.skills = opts.enabledSkills;
    if (opts?.enabledGuardrails !== undefined && !slots.guardrails)
      slots.guardrails = opts.enabledGuardrails;
    return slots;
  }

  private async _effectiveTemplate(agentDoc: Document): Promise<string> {
    const spec = agentDoc.spec;
    const kinds = (this.host as any)._kinds as Map<string, any>;
    const agentKp = kinds.get(`${agentDoc.apiVersion}\0${agentDoc.kind}`);
    let tmpl =
      (spec.promptTemplate as string) ?? (spec.prompt_template as string) ?? null;
    if (!tmpl) {
      const layout = spec.layout as string | undefined;
      if (layout && agentKp) tmpl = agentKp.layoutTemplate(layout);
      else if (agentKp) tmpl = agentKp.promptTemplate();
    }
    if (!tmpl) return "";
    if (tmpl.includes("/") || tmpl.endsWith(".mustache") || tmpl.endsWith(".md")) {
      tmpl = await this.host.ref(tmpl);
    }
    return tmpl ?? "";
  }

  private _kpByAlias(alias: string): any | null {
    const kinds = (this.host as any)._kinds as Map<string, any>;
    for (const kp of kinds.values()) {
      if (kp?.alias === alias) return kp;
    }
    return null;
  }

  /**
   * Reconstruct the ordered composition inputs → `[label, kp, name]`. A
   * depFilter field contributes a section iff the layout actually renders it —
   * a flatten Kind whose flatten var appears in the template (Soul →
   * soul_content) or a Kind whose alias appears as a Mustache section
   * (Skill/Guardrail). Non-prompt deps (tools, actors) fall out.
   */
  private _sectionSpecs(
    agentDoc: Document,
    template: string,
    enabledSlots: Record<string, string[]>,
  ): Array<[string, any, string]> {
    const specs: Array<[string, any, string]> = [];
    const kinds = (this.host as any)._kinds as Map<string, any>;
    const agentKp = kinds.get(`${agentDoc.apiVersion}\0${agentDoc.kind}`);

    // The agent's own instruction always leads ({{{agent.instruction}}}).
    specs.push(["instruction", agentKp, agentDoc.name]);
    if (!agentKp) return specs;

    const filters = agentKp.depFilters() ?? {};
    const agentSpec = agentDoc.spec;
    for (const [specField, alias] of Object.entries(filters as Record<string, string>)) {
      const declared = agentSpec[specField];
      if (declared == null || declared === "" || (Array.isArray(declared) && declared.length === 0))
        continue;
      let names = typeof declared === "string" ? [declared] : [...(declared as string[])];
      if (specField in enabledSlots) {
        const allowed = new Set(enabledSlots[specField]);
        names = names.filter((n) => allowed.has(n));
      }
      if (names.length === 0) continue;
      const kp = this._kpByAlias(alias);
      if (!kp) continue;
      if (!this._contributesToPrompt(kp, alias, names, template)) continue;
      const singular = specField.endsWith("s") ? specField.slice(0, -1) : specField;
      for (const n of names) {
        const label = typeof declared === "string" ? singular : `${singular}:${n}`;
        specs.push([label, kp, n]);
      }
    }
    return specs;
  }

  private _contributesToPrompt(
    kp: any,
    alias: string,
    names: string[],
    template: string,
  ): boolean {
    if (kp?.flattenInContext) {
      // Flatten Kind (Soul): spec string keys become top-level vars
      // (soul_content). Contributes iff one of those vars is in template.
      for (const doc of this.host.documents) {
        if (doc.kind !== kp.kind || !names.includes(doc.name)) continue;
        for (const [k, v] of Object.entries(doc.spec)) {
          if (typeof v === "string" && (template.includes(`{{{${k}}}}`) || template.includes(`{{${k}}}`)))
            return true;
        }
      }
      return false;
    }
    // Section Kind (Skill/Guardrail): rendered as {{#alias}} ... {{/alias}}.
    return template.includes(`{{#${alias}}}`);
  }

  private async _resolve(kind: string, name: string, tenant: string | null): Promise<any | null> {
    const kernel = (this.host as any)._kernel;
    if (!kernel?.resolveDocument) return null;
    try {
      return await kernel.resolveDocument(this.host.scope, kind, name, { tenant });
    } catch {
      return null; // read path, fail-soft
    }
  }

  private static _docHash(raw: any): string | null {
    if (!raw || typeof raw !== "object") return null;
    try {
      return documentHash(raw as Record<string, unknown>);
    } catch {
      return null;
    }
  }

  private _sectionProvenance(
    section: string,
    kp: any,
    name: string,
    effective: any | null,
    base: any | null,
    tenant: string | null,
  ): SectionProvenance {
    const source = PromptBuilder._sourcePath(kp, name);
    const effRaw = effective?.doc ?? null;
    const baseRaw = base?.doc ?? null;

    const hash = PromptBuilder._docHash(effRaw);
    let version: string | null = null;
    if (effRaw && typeof effRaw === "object") {
      const meta = (effRaw as any).metadata ?? {};
      const v = meta?.version;
      version = v != null ? String(v) : null;
    }

    // Layer origin from the base resolution (tenant-independent). The FS
    // tenant→base fallback would otherwise stamp every section with the
    // tenant even without an overlay.
    let origin = "?";
    let isInherited = false;
    const originSrc = base ?? effective;
    if (originSrc) {
      const eff = originSrc.provenance?.effectiveLayer ?? null;
      if (eff) origin = eff.scope;
      else if (originSrc.doc == null) origin = "(not found)";
      isInherited = Boolean(originSrc.isInherited);
    }

    // Overridden iff a tenant was requested AND the tenant-resolved content
    // actually differs from the base content.
    const overriddenByTenant = Boolean(
      tenant && hash !== null && hash !== PromptBuilder._docHash(baseRaw),
    );
    return { section, kind: kp?.kind ?? "?", name, source, hash, version, origin, isInherited, overriddenByTenant };
  }

  private static _sourcePath(kp: any, name: string): string {
    const storage = kp?.storage;
    if (!storage) return "?";
    const pattern = storage.pattern;
    const container = storage.container ?? "";
    const marker = storage.marker;
    if (pattern === "bundle") return container ? `${container}/${name}/${marker}` : `${name}/${marker}`;
    if (pattern === "yaml") return container ? `${container}/${name}.yaml` : `${name}.yaml`;
    if (pattern === "root" || pattern === "standalone") return marker ?? `${name}`;
    return container ? `${container}/${name}` : name;
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
      // stripPromptBlock: composition-only trailing-whitespace
      // normalization (i-013) — storage stays byte-faithful.
      instruction: instructionRef
        ? stripPromptBlock(await this.host.ref(instructionRef))
        : "",
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

    // Flatten: kinds with flattenInContext have their spec entries merged into ctx.
    // String values (soul_content, agents_content, ...) get trailing
    // whitespace normalized — the template supplies the joiners (i-013).
    for (const doc of this.host.documents) {
      const kp = kinds.get(`${doc.apiVersion}\0${doc.kind}`);
      if (!kp?.flattenInContext) continue;
      const spec = doc.spec;
      for (const [k, v] of Object.entries(spec)) {
        if (k.startsWith("_") || v == null) continue;
        ctx[k] =
          typeof v === "string"
            ? stripPromptBlock(await this.host.ref(v))
            : v;
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

    // 1. Agent-level raw template override (poweruser escape hatch).
    const agentTemplate =
      (agentSpec.promptTemplate as string) ??
      (agentSpec.prompt_template as string) ??
      null;
    if (agentTemplate) {
      return await this._mustacheRender(agentTemplate, ctx);
    }

    const agentKp = kinds.get(
      `${agentDoc.apiVersion}\0${agentDoc.kind}`,
    );

    // 2. Named layout preset (s-dx-named-layouts) — author picks the
    // composition order by NAME; the kernel resolves it to an embedded
    // template so the common case never hand-writes Mustache.
    const layout = agentSpec.layout as string | undefined;
    if (layout && agentKp) {
      const layoutTmpl = agentKp.layoutTemplate(layout);
      if (layoutTmpl == null) {
        throw new UnknownLayout(layout, agentKp.layoutNames(), agentDoc.name);
      }
      return await this._mustacheRender(layoutTmpl, ctx);
    }

    // 3. Kind default template
    if (agentKp) {
      const kindTemplate = agentKp.promptTemplate();
      if (kindTemplate) {
        return await this._mustacheRender(kindTemplate, ctx);
      }
    }

    // 4. Fallback: agent instruction as plain text
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
