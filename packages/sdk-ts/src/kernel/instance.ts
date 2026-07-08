/**
 * ManifestInstance v3 — public API for querying manifest documents.
 *
 * Provides query (all/one/root), navigation (get/describe/listKinds/summary),
 * prompt building (buildPrompt with template cascade), and layer resolution.
 *
 * Method bodies delegate to namespace classes (PromptBuilder, CompositionEngine,
 * Navigator, LockManager) and viz/ functions. The old API surface is preserved
 * as one-line delegates for backwards compatibility.
 *
 * 1:1 parity with Python dna.v3.kernel.instance.
 */

import { Document } from "./document.js";
import { readSpecString, readSpecStringArray } from "./spec-access.js";
import { ScannerPipeline } from "./safety-scanner.js";
import type { Lockfile } from "./lock.js";
import type { CompositionResult, KindPort, SourcePort } from "./protocols.js";
import type { CompositionProfile } from "./composition-resolver.js";
import { profileForOrchestrator } from "./composition-resolver.js";
import type { PreviewBlock } from "./preview.js";
import { PromptBuilder } from "./prompt-builder.js";
import { CompositionEngine } from "./composition-resolver.js";
import { Navigator } from "./navigator.js";
import { LockManager } from "./lock-manager.js";
import { ReportBuilder } from "./reports.js";

// Viz imports — all use `import type { ManifestInstance }` so no circular issue at runtime.
import {
  dependencyTreeMermaid as vizDependencyTreeMermaid,
  compositionFlowchartMermaid as vizCompositionFlowchartMermaid,
  c4ComponentMermaid as vizC4ComponentMermaid,
  erDiagramMermaid as vizErDiagramMermaid,
  erModel as vizErModel,
  mindmapMermaid as vizMindmapMermaid,
  pieChartMermaid as vizPieChartMermaid,
  quadrantMermaid as vizQuadrantMermaid,
  timelineMermaid as vizTimelineMermaid,
  sankeyMermaid as vizSankeyMermaid,
  kindCatalogMermaid as vizKindCatalogMermaid,
  exportDiagramsMd as vizExportDiagramsMd,
} from "../viz/mermaid.js";
import { healthReport as vizHealthReport, impact as vizImpact } from "../viz/health.js";
import { matrix as vizMatrix, matrixMarkdown as vizMatrixMarkdown } from "../viz/matrix.js";
import { asciiTree as vizAsciiTree } from "../viz/ascii.js";

export type { PreviewBlock };

/**
 * s-kernel-sandbox-hook-exec — whether a Hook's `action: "script"` may run
 * arbitrary code from `spec.body` via `new Function(...)`. OFF by default: a
 * Hook doc is reachable via the normal doc-write path, so executing its body is
 * an unauthenticated RCE in the host process. Opt in with
 * `DNA_ALLOW_HOOK_SCRIPT_EXEC=1` only in trusted single-tenant deployments.
 * 1:1 with the Python twin (dna.operations._hook_script_exec_allowed).
 */
function hookScriptExecAllowed(): boolean {
  return (
    typeof process !== "undefined" &&
    process.env?.DNA_ALLOW_HOOK_SCRIPT_EXEC === "1"
  );
}

// ---------------------------------------------------------------------------
// Deprecation plumbing (s-blessed-query-surface)
// ---------------------------------------------------------------------------

/** Methods that already fired their once-per-process deprecation warning. */
const _deprecationWarned = new Set<string>();

/** `console.warn` a deprecation message once per method per process —
 *  mirror of the Python `DeprecationWarning` on the same members. */
function warnDeprecatedOnce(method: string, message: string): void {
  if (_deprecationWarned.has(method)) return;
  _deprecationWarned.add(method);
  console.warn(message);
}

/** @internal Test hook — reset the once-per-process deprecation state. */
export function _resetDeprecationWarnings(): void {
  _deprecationWarned.clear();
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ManifestInstanceOpts {
  scope: string;
  documents: Document[];
  kinds: Map<string, KindPort>;
  source?: SourcePort | null;
  resolveErrors?: string[];
  kernel?: unknown;
  profiles?: CompositionProfile[];
}

export interface BuildPromptOpts {
  agent?: string;
  context?: Record<string, unknown>;
  /** Generic slot filtering: keys are slot names from the CompositionProfile,
   *  values are arrays of doc names to keep. */
  enabledSlots?: Record<string, string[]>;
  /** @deprecated Use enabledSlots.skills instead. Kept for backwards compat. */
  enabledSkills?: string[];
  /** @deprecated Use enabledSlots.guardrails instead. */
  enabledGuardrails?: string[];
}

// ---------------------------------------------------------------------------
// ManifestInstance
// ---------------------------------------------------------------------------

export class ManifestInstance {
  readonly scope: string;
  readonly documents: Document[];
  readonly resolveErrors: string[];

  private _kinds: Map<string, KindPort>;
  private _source: SourcePort | null;
  private _kernel: unknown;
  private _root: Document | null | undefined = undefined; // undefined = not computed
  private _compositionResult: CompositionResult | undefined = undefined;
  /** Composition profiles registered by extensions. */
  readonly _profiles: readonly CompositionProfile[];

  // -- Namespace instances (lazy) --------------------------------------------
  private _promptBuilder: PromptBuilder | null = null;
  private _compositionEngine: CompositionEngine | null = null;
  private _navigator: Navigator | null = null;
  private _lockManager: LockManager | null = null;
  private _reportBuilder: ReportBuilder | null = null;

  constructor(opts: ManifestInstanceOpts) {
    this.scope = opts.scope;
    this.documents = opts.documents;
    this._kinds = opts.kinds;
    this._source = opts.source ?? null;
    this._kernel = opts.kernel ?? null;
    this.resolveErrors = opts.resolveErrors ?? [];
    this._profiles = opts.profiles ?? [];
  }

  // -- Namespace getters (lazy, memoized) ------------------------------------

  get prompt(): PromptBuilder {
    return this._promptBuilder ??= new PromptBuilder(this);
  }

  get composition(): CompositionEngine {
    return this._compositionEngine ??= new CompositionEngine(this);
  }

  get nav(): Navigator {
    return this._navigator ??= new Navigator(this);
  }

  get lock(): LockManager {
    return this._lockManager ??= new LockManager(this);
  }

  get reports(): ReportBuilder {
    return this._reportBuilder ??= new ReportBuilder(this);
  }

  /**
   * Find the CompositionProfile for a document's kind (via its alias).
   * Returns null if no profile covers this kind.
   */
  profileFor(doc: Document): CompositionProfile | null {
    const kp = this._kinds.get(`${doc.apiVersion}\0${doc.kind}`);
    if (!kp) return null;
    return profileForOrchestrator(this._profiles, kp.alias);
  }

  // -- Query ----------------------------------------------------------------

  /**
   * Return all docs of `kind`.
   *
   * @deprecated Will be removed in 1.0 — filter `mi.documents`
   * (e.g. `mi.documents.filter((d) => d.kind === kind)`) or use
   * `kernel.query(scope, kind)` for indexed/record-plane reads.
   * (s-blessed-query-surface)
   */
  all(kind: string): Document[] {
    warnDeprecatedOnce(
      "all",
      "ManifestInstance.all() is deprecated and will be removed in 1.0 — " +
        "filter mi.documents (e.g. `mi.documents.filter((d) => d.kind === " +
        "kind)`) or use `kernel.query(scope, kind)` for " +
        "indexed/record-plane reads.",
    );
    return this._all(kind);
  }

  /** @internal Non-warning twin of `all()` — used by the SDK's own
   *  collaborators (`applyHooks`, `ReportBuilder`, viz). External
   *  callers use the blessed surface (`mi.documents` / `kernel.query`). */
  _all(kind: string): Document[] {
    return this.documents.filter((d) => d.kind === kind);
  }

  /**
   * Lookup a single doc by (kind, name).
   *
   * @deprecated Will be removed in 1.0 — search `mi.documents`
   * (e.g. `mi.documents.find((d) => d.kind === kind && d.name === name) ??
   * null`) or use `kernel.query(scope, kind)` with a filter for
   * indexed/record-plane reads. (s-blessed-query-surface)
   */
  one(kind: string, name: string): Document | null {
    warnDeprecatedOnce(
      "one",
      "ManifestInstance.one() is deprecated and will be removed in 1.0 — " +
        "search mi.documents (e.g. `mi.documents.find((d) => d.kind === " +
        "kind && d.name === name) ?? null`) or use `kernel.query(scope, " +
        "kind)` with a filter for indexed/record-plane reads.",
    );
    return this._one(kind, name);
  }

  /** @internal Non-warning twin of `one()` — used by the SDK's own
   *  collaborators (`readSpec*`, `readMetadata`). External callers use
   *  the blessed surface (`mi.documents` / `kernel.query`). */
  _one(kind: string, name: string): Document | null {
    return (
      this.documents.find((d) => d.kind === kind && d.name === name) ?? null
    );
  }

  /**
   * Return the KindPort registered for `kind` (by kind name), or null.
   */
  kindFor(kind: string): KindPort | null {
    for (const [key, kp] of this._kinds) {
      const kn = key.split("\0")[1] ?? "";
      if (kn === kind) return kp;
    }
    return null;
  }

  /**
   * True when the document's KindPort is marked as the manifest root.
   */
  isRootDoc(doc: Document): boolean {
    const kp = this._kinds.get(`${doc.apiVersion}\0${doc.kind}`);
    return kp?.isRoot === true;
  }

  /**
   * Return all documents whose registered KindPort satisfies a predicate.
   */
  allWhere(predicate: (kp: KindPort) => boolean): Document[] {
    return this.documents.filter((d) => {
      const kp = this._kinds.get(`${d.apiVersion}\0${d.kind}`);
      return kp ? predicate(kp) : false;
    });
  }

  /**
   * Return the KindPort whose `alias` matches, or null.
   */
  kindForAlias(alias: string): KindPort | null {
    for (const kp of this._kinds.values()) {
      if (kp.alias === alias) return kp;
    }
    return null;
  }

  /**
   * Iterate a document's declared dep_filters dynamically.
   * Delegates to CompositionEngine.
   */
  iterDocDeps(doc: Document): { label: string; targetKind: string; names: string[] }[] {
    return this.composition.iterDocDeps(doc);
  }

  get root(): Document | null {
    if (this._root !== undefined) return this._root;
    // Phase 16 — Genome is the canonical root Kind. ModuleKind class
    // is gone; legacy ``kind: Module`` docs no longer parse.
    for (const d of this.documents) {
      const kp = this._kinds.get(`${d.apiVersion}\0${d.kind}`);
      if (kp?.isRoot) {
        this._root = d;
        return d;
      }
    }
    this._root = null;
    return null;
  }

  // -- Spec-access sugar (mirrors Python mi.read_spec) ---------------------

  readSpec(kind: string, name: string, field: string): unknown {
    const doc = this._one(kind, name);
    if (!doc) {
      throw new Error(`${kind}/${name}: document not found in manifest`);
    }
    return (doc.spec as Record<string, unknown>)[field];
  }

  readSpecString(kind: string, name: string, field: string): string | undefined {
    const doc = this._one(kind, name);
    if (!doc) throw new Error(`${kind}/${name}: document not found in manifest`);
    return readSpecString(doc, field);
  }

  readSpecStringArray(kind: string, name: string, field: string): string[] {
    const doc = this._one(kind, name);
    if (!doc) throw new Error(`${kind}/${name}: document not found in manifest`);
    return readSpecStringArray(doc, field);
  }

  readMetadata(kind: string, name: string, field: string): unknown {
    const doc = this._one(kind, name);
    if (!doc) throw new Error(`${kind}/${name}: document not found in manifest`);
    return (doc.metadata as Record<string, unknown>)[field];
  }

  defaultAgent(): Document | null {
    const root = this.root;
    if (!root) return null;
    const kp = this._kinds.get(`${root.apiVersion}\0${root.kind}`);
    if (!kp) return null;
    const agentName = kp.getDefaultAgentName(root);
    if (!agentName) return null;
    return this._findAgent(agentName);
  }

  // -- Composition validation → CompositionEngine ---------------------------

  get compositionResult(): CompositionResult {
    if (this._compositionResult !== undefined)
      return this._compositionResult;
    this._compositionResult = this.composition.validate();
    return this._compositionResult;
  }

  // -- Navigation → Navigator -----------------------------------------------

  listKinds(): string[] {
    return [...new Set(this.documents.map((d) => d.kind))].sort();
  }

  /**
   * Return every kind REGISTERED in this manifest (not just those that have
   * documents on disk).
   */
  allKinds(): Array<{
    kind: string;
    alias: string;
    apiVersion: string;
    origin: string | null;
  }> {
    const out: Array<{
      kind: string;
      alias: string;
      apiVersion: string;
      origin: string | null;
    }> = [];
    for (const kp of this._kinds.values()) {
      out.push({
        kind: kp.kind,
        alias: kp.alias,
        apiVersion: kp.apiVersion,
        origin: kp.origin ?? null,
      });
    }
    out.sort((a, b) => a.kind.localeCompare(b.kind));
    return out;
  }

  renderDoc(kind: string, name: string): PreviewBlock[] {
    return this.nav.renderDoc(kind, name);
  }

  consumersOf(kind: string, name: string): Array<{ kind: string; name: string }> {
    return this.composition.consumersOf(kind, name);
  }

  get(kind?: string): Array<{ kind: string; name: string; apiVersion: string }> {
    const docs = kind != null ? this._all(kind) : this.documents;
    return docs.map((d) => ({
      kind: d.kind,
      name: d.name,
      apiVersion: d.apiVersion,
    }));
  }

  describe(kind: string, name: string): string {
    return this.nav.describe(kind, name);
  }

  summary(): string {
    return this.nav.summary();
  }

  inventory(): Record<string, unknown> {
    return this.nav.inventory();
  }

  dependencyTree(): Record<string, unknown> {
    return this.composition.dependencyTree();
  }

  // -- ER Model → viz -------------------------------------------------------

  erModel(): {
    entities: { id: string; kind: string; name: string; attrs: { key: string; type: string; value: string }[] }[];
    relationships: { sourceId: string; targetId: string; label: string; isMany: boolean }[];
  } {
    return vizErModel(this);
  }

  // -- Mermaid diagrams → viz ------------------------------------------------

  dependencyTreeMermaid(): string { return vizDependencyTreeMermaid(this); }
  compositionFlowchartMermaid(): string { return vizCompositionFlowchartMermaid(this); }
  c4ComponentMermaid(): string { return vizC4ComponentMermaid(this); }
  erDiagramMermaid(): string { return vizErDiagramMermaid(this); }
  mindmapMermaid(): string { return vizMindmapMermaid(this); }
  pieChartMermaid(): string { return vizPieChartMermaid(this); }
  quadrantMermaid(): string { return vizQuadrantMermaid(this); }
  timelineMermaid(): string { return vizTimelineMermaid(this); }
  sankeyMermaid(): string { return vizSankeyMermaid(this); }
  kindCatalogMermaid(): string { return vizKindCatalogMermaid(this); }
  exportDiagramsMd(path?: string): Record<string, string> { return vizExportDiagramsMd(this, path); }

  // -- Matrix → viz ----------------------------------------------------------

  matrix(): Record<string, unknown> { return vizMatrix(this); }
  matrixMarkdown(): string { return vizMatrixMarkdown(this); }

  // -- Health / Impact → viz -------------------------------------------------

  health(): Record<string, unknown> { return vizHealthReport(this); }
  impact(kind: string, name: string): Record<string, unknown> { return vizImpact(this, kind, name); }

  // -- ASCII tree → viz ------------------------------------------------------

  asciiTree(): string { return vizAsciiTree(this); }

  // -- Ref resolution -------------------------------------------------------

  /**
   * Resolve a ref-like value (path or markdown/yaml/txt filename).
   *
   * v1.0 async refactor: SourcePort.resolveRef is async, so this is
   * async too. Cascades to PromptBuilder.build() and
   * ManifestInstance.buildPrompt() — every prompt build is async.
   * That's the honest contract — the alternative (cache-based sync
   * ref) requires knowing every ref at scope load time, which doesn't
   * hold for dynamic context fields.
   */
  async ref(value: string): Promise<string> {
    if (!value) return "";
    if (
      this._source &&
      (value.includes("/") || /\.(md|txt|yaml)$/.test(value))
    ) {
      const resolved = await this._source.resolveRef(this.scope, value);
      if (resolved) return resolved;
    }
    return value;
  }

  // -- Prompt → PromptBuilder ------------------------------------------------

  async buildPrompt(opts?: BuildPromptOpts): Promise<string> {
    return this.prompt.build(opts);
  }

  // -- Layers ---------------------------------------------------------------

  resolve(layers?: Record<string, string>): ManifestInstance {
    if (!layers) return this;
    const kernel = this._kernel as { resolveLayers?(mi: ManifestInstance, l: Record<string, string>): ManifestInstance } | null;
    if (kernel?.resolveLayers) {
      return kernel.resolveLayers(this, layers);
    }
    // Fallback if no kernel ref (e.g., constructed directly in tests)
    return this;
  }

  // -- Lock → LockManager ---------------------------------------------------

  generateLock(): Lockfile {
    return this.lock.generate();
  }

  // -- Hook auto-registration ------------------------------------------------

  /** Auto-register Hook documents on the kernel's HookRegistry. */
  applyHooks(): void {
    const kernel = this._kernel as { hooks?: { use(h: string, fn: (ctx: any) => any): void; on(h: string, fn: (ctx: any) => void): void } } | null;
    if (!kernel?.hooks) return;

    const hooks = this._all("Hook");
    for (const doc of hooks) {
      const spec = doc.spec as Record<string, unknown>;
      const target = spec.target as string;
      const type = spec.type as string;
      const action = spec.action as string;

      if (type === "middleware" && target) {
        if (action === "inject_fields") {
          const fields = (spec.fields ?? {}) as Record<string, unknown>;
          kernel.hooks.use(target, (ctx: any) => {
            const context = (ctx.data?.context ?? {}) as Record<string, unknown>;
            for (const [k, v] of Object.entries(fields)) {
              context[k] = v;
            }
            return { ...ctx, data: { ...ctx.data, context } };
          });
        } else if (action === "script") {
          const body = (spec.body as string) ?? "";
          if (body.trim() && !hookScriptExecAllowed()) {
            console.warn(
              `Hook ${doc.name}: action='script' skipped — exec of Hook spec.body ` +
              `is disabled (RCE surface). Use a declarative action, or set ` +
              `DNA_ALLOW_HOOK_SCRIPT_EXEC=1 in a trusted deployment. (s-kernel-sandbox-hook-exec)`,
            );
          } else if (body.trim()) {
            try {
              const fn = new Function("ctx", `return (${body.trim()})(ctx);`);
              kernel.hooks.use(target, (ctx: any) => fn(ctx));
            } catch (e) {
              console.warn(`Hook ${doc.name}: script compilation failed: ${e}`);
            }
          }
        }
      } else if (type === "event" && target) {
        if (action === "log") {
          kernel.hooks.on(target, (ctx: any) => {
            console.log(`[Hook:${doc.name}] ${target}`, {
              agent: ctx.agent,
              scope: ctx.scope,
              promptLength: ctx.prompt?.length,
            });
          });
        } else if (action === "script") {
          const body = (spec.body as string) ?? "";
          if (body.trim() && !hookScriptExecAllowed()) {
            console.warn(
              `Hook ${doc.name}: event action='script' skipped — exec of Hook ` +
              `spec.body is disabled (RCE surface). Use action='log', or set ` +
              `DNA_ALLOW_HOOK_SCRIPT_EXEC=1 in a trusted deployment. (s-kernel-sandbox-hook-exec)`,
            );
          } else if (body.trim()) {
            try {
              const fn = new Function("ctx", `(${body.trim()})(ctx);`);
              kernel.hooks.on(target, (ctx: any) => fn(ctx));
            } catch (e) {
              console.warn(`Hook ${doc.name}: script compilation failed: ${e}`);
            }
          }
        }
      }
    }

    // -- SafetyPolicy input enforcement ----------------------------------------
    const policies = this._all("SafetyPolicy");
    for (const doc of policies) {
      const spec = doc.spec as Record<string, unknown>;
      const scope = spec.scope as string;
      const action = spec.action as string;
      const rules = (spec.rules ?? []) as Array<Record<string, unknown>>;

      if ((scope === "input" || scope === "both") && rules.length > 0) {
        kernel.hooks.use("pre_build_prompt", (ctx: any) => {
          const pipeline = new ScannerPipeline(rules);
          const context = (ctx.data?.context ?? {}) as Record<string, unknown>;
          for (const [key, val] of Object.entries(context)) {
            if (typeof val === "string") {
              try {
                context[key] = pipeline.apply(val, action);
              } catch {
                /* block action throws — skip field */
              }
            }
          }
          return { ...ctx, data: { ...ctx.data, context } };
        });
      }
    }
  }

  // -- Agent lookup -----------------------------------------------------------

  /** Find the best prompt-target document matching `name`.
   *  Considers promptTargetPriority when multiple kinds match. */
  findAgent(name: string): Document | null {
    return this._findAgent(name);
  }

  /** @internal */
  _findAgent(name: string): Document | null {
    let best: Document | null = null;
    let bestPriority = -1;
    for (const d of this.documents) {
      const kp = this._kinds.get(`${d.apiVersion}\0${d.kind}`);
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
}
