/**
 * Kernel v3 — Mediator connecting 5 ports.
 *
 * 1:1 parity with Python dna.v3.kernel.__init__.
 */

import { Document } from "./document.js";
import { deriveFirstLine } from "./_text.js";
import type { CompositionProfile } from "./composition-resolver.js";
import {
  ExtensionLoadError,
  KindRegistrationError,
  ReaderRegistrationError,
  WriterRegistrationError,
} from "./errors.js";
import { HookRegistry, type HookContext, type HookNameArg } from "./hooks.js";
import { WritePipeline } from "./write-pipeline.js";
import { ManifestInstance } from "./instance.js";
import {
  type CacheItem,
  type CachePort,
  type Extension,
  type KindPort,
  type ReaderPort,
  type ResolverPort,
  ResolveError,
  type SourcePort,
  type WriterPort,
  type StorageDescriptor,
  type SerializedFile,
  type SerializedDocument,
  type WritableSourcePort,
  type ToolDefinition,
  LayerPolicyViolationError,
  validateTenantSlug,
} from "./protocols.js";
import { ToolRegistry } from "./tool-registry.js";
import {
  type Template,
  type MaterializeOptions,
  materialize,
} from "./templates.js";
import yaml from "js-yaml";
// s-invert-layer-resolver-dep (2026-07-07): the resolver is kernel-owned —
// the kernel imports NO extension modules (guarded by
// tests/kernel-extension-boundary.test.ts).
import { DefaultLayerResolver } from "./layer-resolver.js";
import { CompositionResolver } from "./composition-resolver.js";
import { KindRegistry } from "./kind-registry.js";
import type { RegistryHost } from "./collaborator-ports.js";
import { sourceCapabilities } from "./capabilities.js";
import { DEFAULT_INHERITABLE_KINDS_V1, type ResolvedDocument } from "./resolver.js";
import { GenericBundleReader, GenericBundleWriter } from "./generic-rw.js";
import { nodeFS } from "./fs.js";
import type { FSLike } from "./fs.js";

// s-kernel-decomp-ts-parity — alias generation + the KIND_NAME collision
// ratchet moved into the KindRegistry module (Py twin: kind_registry.py).
// Re-exported here so the historical `from "../src/kernel"` import path (tests,
// tooling) keeps resolving them.
export {
  kebabKindName,
  generateAlias,
  EXPLICIT_ALIAS_ALLOWLIST,
  KIND_NAME_COLLISION_ALLOWLIST,
} from "./kind-registry.js";

// ---------------------------------------------------------------------------
// Write-facade public types — 1:1 parity with Python dna.kernel.
// ---------------------------------------------------------------------------

/** Raised when writeDocument/deleteDocument is called but no
 *  WritableSourcePort is registered on the Kernel. */
export class NotWritableError extends Error {
  constructor(message?: string) {
    super(message);
    this.name = "NotWritableError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Return value of Kernel.previewDocument().
 *
 * - `target` — absolute path for filesystem sources, synthetic URL
 *   (e.g. "sqlite://<scope>/<kind>/<name>") for others.
 * - `files` — the exact bytes that would be written. Readonly.
 * - `existsAlready` — true iff the target is already present; UIs use
 *   this to render "create" vs "overwrite" affordances. Optimistic
 *   concurrency (ifMatch) is deferred per
 *   docs/superpowers/specs/2026-04-04-kernel-write-path-design.md
 *   Out-of-Scope.
 */
export interface PreviewResult {
  readonly target: string;
  /** L3 (2026-05-25): files may have `content` (str) or `contentBytes`
   * (Uint8Array). Preview UIs that only render text should fallback
   * to an empty-string display when contentBytes is set. */
  readonly files: readonly import("./protocols.js").SerializedFile[];
  readonly existsAlready: boolean;
}

/** i-112 Phase 1 — single source of truth para os special-scope names.
 *  Dois papéis distintos (paridade 1:1 com Python protocols.py):
 *  DEFAULT_BASE_SCOPE = fallback de herança; SYSTEM_SCOPE = casa dos lookups globais.
 *  Ambos "_lib" hoje; nomeados separados pra Fases 2-3 divergirem. */
export const DEFAULT_BASE_SCOPE = "_lib";
export const SYSTEM_SCOPE = "_lib";

/**
 * The scope that owns the canonical ModelProfile registry.
 * Queried directly by `modelProfile()` — regardless of the caller's scope.
 * 1:1 parity with Python `Kernel._MODEL_REGISTRY_SCOPE`.
 */
export const MODEL_REGISTRY_SCOPE = SYSTEM_SCOPE;

/**
 * The scope that owns the canonical VoicePolicy registry. GLOBAL like
 * ModelProfile — queried directly regardless of the caller's scope.
 * 1:1 parity with Python `Kernel._VOICE_POLICY_SCOPE`.
 */
export const VOICE_POLICY_SCOPE = SYSTEM_SCOPE;

export class Kernel {
  // ── Kind classification — DERIVED from KindPort attributes ──────────────
  // s-kernel-kindport-classification-attrs: the kernel no longer hardcodes
  // Kind-name sets; it reads each registered Kind's declared attribute
  // (isOverlayable / scopeInheritable). The membership API (`k.X.has(kind)`) is
  // unchanged — these became instance getters — but the source of truth is now
  // the Kind, not a literal list. 1:1 parity with the Python kernel.
  //
  // Structural bootstrap Kinds (scope identity / schema / policy) are
  // non-overlayable AND non-inheritable BY DEFINITION (mirrors
  // resolver BOOTSTRAP_KINDS); the legacy ledger names have no registered
  // KindPort to carry an attribute. Both are unioned in so the classification
  // is identical even on a kernel that hasn't registered those Kinds.
  private static readonly _BOOTSTRAP_KINDS: ReadonlySet<string> = new Set([
    "Genome", "KindDefinition", "LayerPolicy",
  ]);
  private static readonly _LEGACY_NON_INHERITABLE: ReadonlySet<string> = new Set([
    "Milestone", "VibeSession",
  ]);
  static readonly INHERIT_PARENT_SCOPE = DEFAULT_BASE_SCOPE;

  private _classifyKinds(pred: (kp: KindPort) => boolean): Set<string> {
    const out = new Set<string>();
    for (const kp of this._kinds.values()) {
      if (kp.kind && pred(kp)) out.add(kp.kind);
    }
    return out;
  }

  /** Kinds structurally never overlayable. Derived from KindPort.isOverlayable
   *  (s-kernel-kindport-classification-attrs). 1:1 with Python
   *  Kernel._NON_OVERLAYABLE_KINDS. */
  get NON_OVERLAYABLE_KINDS(): ReadonlySet<string> {
    const s = this._classifyKinds((kp) => kp.isOverlayable === false);
    for (const k of Kernel._BOOTSTRAP_KINDS) s.add(k);
    return s;
  }

  /** Per-scope ledger + structural Kinds that do NOT inherit across scopes.
   *  Derived from KindPort.scopeInheritable. 1:1 with Python
   *  Kernel._NON_INHERITABLE_KINDS. */
  get NON_INHERITABLE_KINDS(): ReadonlySet<string> {
    const s = this._classifyKinds((kp) => kp.scopeInheritable === false);
    for (const k of Kernel._BOOTSTRAP_KINDS) s.add(k);
    for (const k of Kernel._LEGACY_NON_INHERITABLE) s.add(k);
    return s;
  }

  /** `k.INHERITABLE_KINDS.has(kind)` — denylist-backed membership (everything
   *  inherits EXCEPT NON_INHERITABLE_KINDS). 1:1 with Python _INHERITABLE_KINDS. */
  get INHERITABLE_KINDS(): { has(kind: string): boolean } {
    const deny = this.NON_INHERITABLE_KINDS;
    return { has: (kind: string): boolean => !deny.has(kind) };
  }

  private _source: SourcePort | null = null;
  private _cache: CachePort | null = null;
  private _resolvers = new Map<string, ResolverPort>();
  /** @internal — public so the KindRegistry `RegistryHost` slice reaches the
   *  rescan gate. Convention `_`-private; not a supported API surface. */
  _readers: ReaderPort[] = [];
  private _writers: WriterPort[] = [];
  private _writableSource: WritableSourcePort | null = null;
  private _profiles: CompositionProfile[] = [];
  /** Registered-Kind identity map + the registration funnel (Fase 3,
   *  s-kernel-decomp-ts-parity). OWNS the `_kinds` Map; the kernel's `_kinds`
   *  getter proxies to it, and `kind()`/`kindFromDescriptor()`/
   *  `_registerKindDefinitions()`/`_registerCustomKinds()`/`validateDepFilters()`
   *  are thin facades. Shared across withTenant copies (Object.assign copies the
   *  ref) — Kinds are global, registered once at boot. Py twin:
   *  `Kernel._kindreg`. */
  private _kindreg: KindRegistry = new KindRegistry(undefined, this as RegistryHost);
  /** The registered-Kind dict — proxied to `this._kindreg` so the ~20 inline
   *  `this._kinds` read sites across the kernel keep working after the Fase 3
   *  extraction. Key: "apiVersion\0kind". Py twin: `Kernel._kinds` property. */
  get _kinds(): Map<string, KindPort> {
    return this._kindreg.kinds;
  }
  /** Extensions that successfully registered, in load() order. Used by
   *  listTemplates() to aggregate scaffolds from every loaded extension. */
  private _extensions: Extension[] = [];
  /** Tool-definition registry (s-dna-port-surface-parity — TS twin of the
   *  Py `Kernel._toolreg`). Tools are global (not tenant-scoped), so one
   *  registry is safely shared across withTenant shallow copies. */
  private _toolreg = new ToolRegistry();
  /** Composition-V2 engine (Phase 17 — s-ts-composition-v2-port). Holds a
   *  back-ref to this kernel; the kernel keeps the public methods
   *  (resolveDocument / computeResolutionChain / personalizeDocument /
   *  compositionSummary) as thin delegators, 1:1 with the Python layout. */
  private readonly _composition = new CompositionResolver(this);
  /** Document write/delete execution (tenant resolve, layer-policy check,
   *  pre_save veto, persist, post_save/post_delete) — extracted collaborator
   *  (Fase 2, s-kernel-decomp-f2-writepipeline). The kernel keeps
   *  writeDocument/deleteDocument as thin facades. Non-readonly: withTenant
   *  re-instantiates it against the copy so a tenant-bound kernel resolves its
   *  own tenant. Py twin: `Kernel._write_pipeline`. */
  private _writePipeline = new WritePipeline(this);
  readonly hooks = new HookRegistry();
  /** @internal — public for the KindRegistry `RegistryHost` slice. */
  _genericsResolved = false;
  private _fs: FSLike = nodeFS;
  /** s-alias-generated-not-typed — owner context for alias generation of
   *  the Kinds registered by the Extension currently inside load().
   *  @internal — public for the KindRegistry `RegistryHost` slice.
   *  Py twin: Kernel._loading_ext_owner. */
  _loadingExtOwner: string | null = null;
  /** Two-planes F2 — pluggable semantic-search provider (see search()). */
  private _searchProvider: import("./protocols.js").RecordSearchProvider | null = null;
  /** Damper: warn once per provider-failure episode, then debug. */
  private _searchProviderWarned = false;

  /**
   * Tenant binding (Phase 1 — tenant-as-first-class).
   *
   * `null` means unbound — only GLOBAL kinds may be written; TENANTED
   * kinds raise `TenantRequired`. Set via the constructor (Sanity
   * `withConfig` pattern) or per-call via `withTenant(other)` (Stripe
   * Connect pattern).
   */
  tenant: string | null = null;

  constructor(opts?: { tenant?: string | null }) {
    if (opts?.tenant !== undefined) {
      validateTenantSlug(opts.tenant);
      this.tenant = opts.tenant;
    }
  }

  /**
   * Return a shallow-copy Kernel bound to `tenant`. Original Kernel is
   * unchanged — call sites can hand off the copy to per-request
   * handlers without mutating shared state (Sanity `client.withConfig`
   * pattern).
   *
   * Pass `tenant=null` to obtain an unbound kernel (writes only allowed
   * for GLOBAL kinds).
   */
  withTenant(tenant: string | null): Kernel {
    validateTenantSlug(tenant);
    // Shallow object copy — shares source/cache/extensions/hooks
    const copy: Kernel = Object.create(Object.getPrototypeOf(this));
    Object.assign(copy, this);
    copy.tenant = tenant;
    // Re-point the write pipeline at the copy so a tenant-bound kernel
    // resolves its OWN tenant in writeDocument/deleteDocument (Fase 2).
    copy._writePipeline = new WritePipeline(copy);
    return copy;
  }

  /** Return the registered KindPort for a kind name (case-sensitive).
   *  With apiVersion the lookup is EXACT on (apiVersion, kind) — bare
   *  lookups on a name shared by multiple apiVersions resolve
   *  extension-first then registration order (i-195, Py twin:
   *  KindRegistry.port_for). */
  private _kindPortFor(kind: string, apiVersion?: string): KindPort | null {
    return this._kindreg.portFor(kind, apiVersion);
  }

  /** Public lookup for a registered KindPort by kind name. Use from
   *  tooling that needs to consult Kind metadata (isRuntimeArtifact,
   *  scope, storage, ...) without reaching into Kernel internals. Pass
   *  apiVersion for exact resolution on ambiguous names (i-195). */
  kindPortFor(kind: string, apiVersion?: string): KindPort | null {
    return this._kindPortFor(kind, apiVersion);
  }

  /** Validate a Kind-Writer Agent's slot↔schema contract
   *  (feat/kind-writer-pilot, Task 2). Called from writeDocument only when
   *  spec.writes_kind is set — fail early so a malformed Kind-Writer is
   *  rejected before runtime emission. Twin of Python _validate_kind_writer.
   *
   *  Contract:
   *  - writes_kind must resolve to a registered KindPort whose schema() is an
   *    object (schema-bearing); unknown / schema-less → Error (mentions schema).
   *  - every creative_slots name must be a property in the schema.
   *  - every required schema field must be covered by
   *    creative_slots ∪ Object.keys(system_slots); uncovered → "unmapped". */
  /** @internal — called by the Helix extension's Kind-Writer pre_save
   *  guard (s-write-path-despecialize). Thin delegator to
   *  `WritePipeline.validateKindWriter` (Fase 2,
   *  s-kernel-decomp-f2-writepipeline). */
  _validateKindWriter(spec: Record<string, unknown>): void {
    this._writePipeline.validateKindWriter(spec);
  }

  /** All registered KindPorts. Order matches registration. Facade over
   *  `this._kindreg.allPorts()` (Fase 3). */
  kindPorts(): KindPort[] {
    return this._kindreg.allPorts();
  }

  /** F3 D4 (spec 2026-06-10-kinds-descriptor-f3): kind names whose port
   *  declares `embedFields` — via descriptor `embed:` or a class-level
   *  `embedFields` (the KindBase parity hook for not-yet-migrated
   *  classes). Py twin: `Kernel.embeddable_kinds()` (frozenset). */
  embeddableKinds(): Set<string> {
    const out = new Set<string>();
    for (const kp of this.kindPorts()) {
      const ef = (kp as { embedFields?: string[] | null }).embedFields;
      if (ef !== null && ef !== undefined) out.add(kp.kind);
    }
    return out;
  }

  /** Return the TenantScope for a registered kind, or null if unset.
   *  Phase 1 keeps undeclared kinds permissive (back-compat). @internal —
   *  read by WritePipeline.resolveTenantArg via the back-ref. */
  _kindScope(kind: string): string | null {
    const kp = this._kindPortFor(kind);
    if (!kp) return null;
    return (kp as { scope?: string }).scope ?? null;
  }

  // `_resolveTenantArg` moved to `WritePipeline.resolveTenantArg` (Fase 2,
  // s-kernel-decomp-f2-writepipeline) — it was only ever used by the two
  // write/delete bodies, which now live in the pipeline.

  // -- Registration ---------------------------------------------------------
  // Hook names are typed (`HookName` vocabulary + string back-compat,
  // s-dna-typed-hook-names); the HookRegistry warns once per (registry,
  // name) on names outside the vocabulary.

  use(hook: HookNameArg, fn: (ctx: HookContext) => HookContext): void {
    this.hooks.use(hook, fn);
  }

  on(hook: HookNameArg, fn: (ctx: HookContext) => void): void {
    this.hooks.on(hook, fn);
  }

  /** Register a veto listener (e.g. 'pre_save') — throwing vetoes the
   *  operation. See HookRegistry.onVeto for priority/key semantics. */
  onVeto(
    hook: HookNameArg,
    fn: import("./hooks.js").VetoHandler,
    opts?: { priority?: number; key?: string },
  ): void {
    this.hooks.onVeto(hook, fn, opts);
  }

  source(s: SourcePort): void {
    this._source = s;
  }

  /** The SourcePort registered via source(), or null. Read-only getter.
   *  The setter method is `source(src)`. Named `activeSource` to avoid
   *  collision between a method and a property of the same name.
   *  Parity: python Kernel.active_source. */
  get activeSource(): SourcePort | null {
    return this._source;
  }

  // ── Two-planes F2 — record-plane public surface (query/count/search) ─────

  /**
   * Kernel-level record query — push-down delegated to `source.query`
   * (two-planes F2; TS twin of the Py `kernel.query`).
   *
   * Adds on top of the source:
   * - Tenant binding auto-stamp: `opts.tenant` > `Kernel.tenant` > unset
   *   (Stripe Connect pattern, same as writeDocument).
   * - Cross-scope `scopes` (F2.4): iterates the scopes with per-scope
   *   queries and CONCATENATES without dedup — records from distinct
   *   scopes are distinct docs. Mutually exclusive with a diverging
   *   positional `scope`: `scopes` wins (the positional is ignored).
   *   `limit`/`offset` apply PER scope.
   *
   * Divergence from Py (documented): the TS kernel has NO
   * origin/inheritance machinery (no `origin=` param, no scope-inheritance
   * chain, no catalog pass) — those live in the Py QueryEngine only.
   * Records are per-scope, so the record plane loses nothing.
   *
   * Sources without the optional `query` capability (e.g. PostgresSource
   * TS, no push-down this phase) raise a clear capability error.
   */
  async *query(
    scope: string,
    kind: string,
    opts: {
      filter?: import("./protocols.js").QueryFilter;
      limit?: number;
      offset?: number;
      orderBy?: string[];
      tenant?: string;
      scopes?: string[];
    } = {},
  ): AsyncIterable<Record<string, unknown>> {
    if (!this._source) {
      throw new Error("No source registered. Call kernel.source() first.");
    }
    const { scopes, ...rest } = opts;
    if (scopes != null) {
      // F2.4 cross-scope: per-scope queries, concat no dedup. Recursion
      // rebinds tenant per call (passes the raw opt through).
      for (const sc of scopes) yield* this.query(sc, kind, rest);
      return;
    }
    const src = this._source;
    // s-sourceport-contract-cleanup: consult the DECLARED capabilities
    // instead of a typeof feature-test.
    if (!sourceCapabilities(src).queryPushdown || typeof src.query !== "function") {
      throw new Error(
        "source does not implement query — use FilesystemSource or a query-capable adapter",
      );
    }
    // Tenant binding: opt > Kernel.tenant > unset.
    const effectiveTenant = rest.tenant ?? this.tenant ?? undefined;
    yield* src.query(scope, kind, {
      filter: rest.filter,
      limit: rest.limit,
      offset: rest.offset,
      orderBy: rest.orderBy,
      tenant: effectiveTenant,
    });
  }

  /**
   * F2 D2 — public aggregation count alongside `query` (TS twin of the
   * Py `kernel.count`). Push-down to `source.count` (FS: in-memory core).
   *
   * Returns `CountResult`: `{ total, groups }` — groups by count DESC,
   * key ASC with `null` last; `groups` is `null` without `groupBy`.
   *
   * NO origin/inheritance on purpose — records are per-scope (spec D5:
   * derived views build on top of `kernel.query` in code). Cross-scope
   * via `scopes` (totals SUMMED, groups MERGED by key and re-sorted;
   * `scopes` wins over a diverging positional `scope`).
   *
   * Example (Studio velocity):
   *   const res = await kernel.count("dna-development", "Story", {
   *     groupBy: "spec.status",
   *   });
   *   // { total: 950, groups: [{ key: "done", count: 700 }, …] }
   */
  async count(
    scope: string,
    kind: string,
    opts: {
      filter?: import("./protocols.js").QueryFilter;
      groupBy?: string;
      tenant?: string;
      scopes?: string[];
    } = {},
  ): Promise<import("./protocols.js").CountResult> {
    if (!this._source) {
      throw new Error("No source registered. Call kernel.source() first.");
    }
    const src = this._source;
    // s-sourceport-contract-cleanup: declared capabilities, not typeof.
    if (!sourceCapabilities(src).queryPushdown || typeof src.count !== "function") {
      throw new Error(
        "source does not implement count — use FilesystemSource or a count-capable adapter",
      );
    }
    const effectiveTenant = opts.tenant ?? this.tenant ?? undefined;
    const targetScopes = opts.scopes ?? [scope];
    let total = 0;
    const merged = new Map<unknown, number>();
    for (const sc of targetScopes) {
      const res = await src.count(sc, kind, {
        filter: opts.filter,
        groupBy: opts.groupBy,
        tenant: effectiveTenant,
      });
      total += res.total ?? 0;
      for (const g of res.groups ?? []) {
        merged.set(g.key, (merged.get(g.key) ?? 0) + (g.count ?? 0));
      }
    }
    let groups: import("./protocols.js").CountResult["groups"] = null;
    if (opts.groupBy != null) {
      // Same tie-break as the in-memory core + the Py merge:
      // count DESC, then key ASC with null LAST (i-121 spirit).
      groups = [...merged.entries()]
        .map(([key, count]) => ({ key, count }))
        .sort((a, b) => {
          if (a.count !== b.count) return b.count - a.count;
          if ((a.key === null) !== (b.key === null)) return a.key === null ? 1 : -1;
          const sa = String(a.key);
          const sb = String(b.key);
          return sa < sb ? -1 : sa > sb ? 1 : 0;
        });
    }
    return { total, groups };
  }

  /**
   * Register the semantic-search provider (two-planes F2). One per
   * kernel; later registration replaces (boot-time wiring) and resets
   * the failure-warning damper (new provider → fresh episode).
   */
  recordSearchProvider(provider: import("./protocols.js").RecordSearchProvider): void {
    this._searchProvider = provider;
    this._searchProviderWarned = false;
  }

  /**
   * Public record search (F2 D2; TS twin of the Py `kernel.search`).
   * Provider registered → semantic (degraded=false). No provider OR
   * provider error → lexical token-match fallback over `query()`
   * (degraded=true; requires `kind` — without it returns empty
   * degraded). Tenant binding same as `query()`.
   */
  async search(
    scope: string,
    queryText: string,
    opts: { kind?: string | null; k?: number; tenant?: string } = {},
  ): Promise<{ hits: Array<Record<string, unknown>>; degraded: boolean }> {
    const k = opts.k ?? 10;
    const effectiveTenant = opts.tenant ?? this.tenant ?? "";
    const prov = this._searchProvider;
    if (prov !== null) {
      try {
        const hits = await prov.search({
          scope,
          queryText,
          kind: opts.kind ?? null,
          k,
          tenant: effectiveTenant || "",
        });
        this._searchProviderWarned = false; // episode over
        return { hits, degraded: false };
      } catch (err) {
        // Search is a read — degrade, never crash. Damped: warn ONCE per
        // failure episode, then debug until a successful call resets.
        if (!this._searchProviderWarned) {
          this._searchProviderWarned = true;
          console.warn(
            "[kernel] search provider failed; lexical fallback "
            + "(further failures logged at debug until recovery)",
            err,
          );
        } else {
          console.debug("[kernel] search provider still failing; lexical fallback", err);
        }
      }
    }
    return {
      hits: await this._lexicalSearch(scope, queryText, {
        kind: opts.kind ?? null,
        k,
        tenant: effectiveTenant || undefined,
      }),
      degraded: true,
    };
  }

  /**
   * Degraded fallback for `search()` — honest DEV lexical scan, NOT
   * similarity (two-planes F2; 1:1 with the Py `_lexical_search`).
   *
   * Matches by token-set over the STRING VALUES of each doc's spec
   * (recursive walk; never substring over serialized JSON —
   * `json.dumps` Py and `JSON.stringify` TS diverge in separators and
   * would break parity). Requires `kind` (records are scanned per-kind);
   * without it there is nothing safe to scan → empty.
   * Score = query tokens present ÷ total query tokens.
   */
  private async _lexicalSearch(
    scope: string,
    queryText: string,
    opts: { kind: string | null; k: number; tenant?: string },
  ): Promise<Array<Record<string, unknown>>> {
    if (!opts.kind) return [];
    const qTokens = queryText.toLowerCase().split(/\s+/).filter(Boolean);
    if (qTokens.length === 0) return [];

    const specTokens = (node: unknown, out: Set<string>): void => {
      if (typeof node === "string") {
        for (const t of node.toLowerCase().split(/\s+/)) if (t) out.add(t);
      } else if (Array.isArray(node)) {
        for (const v of node) specTokens(v, out);
      } else if (typeof node === "object" && node !== null) {
        for (const v of Object.values(node)) specTokens(v, out);
      }
    };

    const hits: Array<{ scope: string; kind: string; name: unknown; score: number }> = [];
    for await (const row of this.query(scope, opts.kind, {
      tenant: opts.tenant,
      limit: 500,
    })) {
      const tokens = new Set<string>();
      specTokens(row.spec ?? {}, tokens);
      const score = qTokens.filter((t) => tokens.has(t)).length / qTokens.length;
      if (score > 0) {
        const meta = row.metadata as Record<string, unknown> | undefined;
        const name = meta?.name ?? row.name ?? "";
        hits.push({ scope, kind: opts.kind, name, score });
      }
    }
    hits.sort((a, b) => b.score - a.score); // stable — input order on ties
    return hits.slice(0, opts.k);
  }

  // ────────────────────────────────────────────────────────────────
  // Composition Engine V2 (Phase 17 — s-ts-composition-v2-port, TS twin
  // of the Py Kernel composition surface) — declarative cross-scope +
  // tenant overlay resolution with provenance. Orchestration lives in
  // `kernel/composition-resolver.ts`; these are thin delegators (same
  // layout as Python: kernel keeps the public methods, the engine holds
  // a back-ref). Behavioral gate: tests/parity-fixtures/composition/.
  // ────────────────────────────────────────────────────────────────

  /**
   * Internal — one raw doc for a `(scope, kind, name, tenant)` layer key
   * (tenant is "" for the base layer). TS twin of the Py
   * `_granular_doc_cached` MINUS the cache: the TS kernel has no
   * kernel-level doc cache, so this is a direct source read on every
   * call. PERF divergence only — same inputs, same outputs (see
   * composition-resolver.ts module docstring, divergence #1).
   */
  async _granularDoc(
    key: [string, string, string, string],
  ): Promise<Record<string, unknown> | null> {
    const [scope, kind, name, tenantOrEmpty] = key;
    const tenant = tenantOrEmpty || null;
    const src = this._source;
    if (!src) throw new Error("No source registered. Call kernel.source() first.");
    // s-sourceport-contract-cleanup: declared capabilities, not typeof.
    if (sourceCapabilities(src).granularOne && typeof src.loadOne === "function") {
      return await src.loadOne(scope, kind, name, { readers: this._readers, tenant });
    }
    // Legacy adapter — fall back to loadAll + find. Mirrors the Py legacy
    // fallback exactly, INCLUDING ignoring tenant (base layer only).
    const docs = await src.loadAll(scope, this._readers);
    for (const d of docs) {
      if (d.kind !== kind) continue;
      const meta = d.metadata as Record<string, unknown> | undefined;
      const n = meta?.name ?? d.name ?? "";
      if (n === name) return d;
    }
    return null;
  }

  /**
   * Internal — the ordered Catalog scope set for `tenant` (Phase 3b ch1,
   * i-112 on the Py side). The TS kernel has NO catalog machinery yet
   * (Genome scan + tenant lockfile — TS parity tracked as `i-185`), so
   * this hook returns `[]`: the resolver's Catalog splice is fully
   * implemented but contributes no layers on TS today (see
   * composition-resolver.ts module docstring, divergence #3).
   */
  async _catalogScopes(
    tenant: string | null,
    opts?: { exclude?: Set<string> },
  ): Promise<Array<[string, string | null]>> {
    void tenant;
    void opts;
    return [];
  }

  /**
   * Walk `Genome.spec.parent_scope` transitively → ordered resolution
   * chain of `[scope, tenant]` pairs, HIGHEST priority first:
   *   [[scope, tenant], [scope, null], [parent, tenant], [parent, null], …]
   * When `tenant` is null, only base layers are emitted per scope.
   * Cycle detection via visited set; depth capped at MAX_RESOLUTION_DEPTH;
   * missing Genome / missing parent_scope terminates the walk (with the
   * V1 back-compat escalation to `_lib`).
   * Py twin: `Kernel._compute_resolution_chain`.
   */
  async computeResolutionChain(
    scope: string,
    tenant: string | null = null,
  ): Promise<Array<[string, string | null]>> {
    return await this._composition.computeResolutionChain(scope, tenant);
  }

  /**
   * Resolve the composition rule `[scope_inheritance, merge_strategy,
   * tenant_overlay]` for (scope, kind) — the scope's
   * `LayerPolicy.composition_rules[kind]`, else the inherit-by-default
   * denylist. Py twin: `Kernel._get_composition_rule`.
   */
  async getCompositionRule(
    scope: string,
    kind: string,
  ): Promise<[string, string, string]> {
    return await this._composition.getCompositionRule(scope, kind);
  }

  /**
   * Resolve a doc through the composition chain — Phase 17 primitive.
   * Returns `ResolvedDocument` with merged doc + full provenance.
   * Bootstrap Kinds (Genome, LayerPolicy, KindDefinition) bypass
   * inheritance entirely (local-only, single-layer provenance).
   * Py twin: `Kernel.resolve_document`.
   */
  async resolveDocument(
    scope: string,
    kind: string,
    name: string,
    opts?: { tenant?: string | null },
  ): Promise<ResolvedDocument> {
    return await this._composition.resolveDocument(scope, kind, name, opts);
  }

  /**
   * Clone an inherited doc into `targetScope` as a local override.
   * Throws when the doc isn't inherited or the target already exists
   * (without `overwrite`). Py twin: `Kernel.personalize_document`
   * (bundle-entry payload cloning is Py-only — divergence #4 in
   * composition-resolver.ts).
   */
  async personalizeDocument(
    targetScope: string,
    kind: string,
    name: string,
    opts?: { tenant?: string | null; overwrite?: boolean },
  ): Promise<ResolvedDocument> {
    return await this._composition.personalizeDocument(targetScope, kind, name, opts);
  }

  /**
   * Cheap aggregate of the scope's parent chain + per-Kind local /
   * inherited / installed counts (Py twin: `Kernel.composition_summary`;
   * same snake_case wire shape:
   * `{scope, parent_chain, resources: {Kind: {local, inherited, installed,
   * total}}}`). The Py twin rides its QueryEngine origin filters; the TS
   * kernel has no origin machinery, so the three passes are computed here
   * directly with the SAME dedup semantics (local names shadow catalog +
   * parent names; catalog names do NOT shadow inherited — mirroring the
   * three independent origin-filtered queries Python makes). `installed`
   * is always 0 until the TS catalog surface lands (i-185).
   */
  async compositionSummary(
    scope: string,
    opts?: { tenant?: string | null },
  ): Promise<Record<string, unknown>> {
    const tenant = opts?.tenant ?? null;
    // Parent chain: derived from Genome.parent_scope + V1 fallback,
    // deduped (chain has (scope, null) pairs; collapse to unique parents).
    const chain = await this.computeResolutionChain(scope, null);
    const parentChain: string[] = [];
    for (const [s] of chain) {
      if (s !== scope && !parentChain.includes(s)) parentChain.push(s);
    }

    const resources: Record<string, Record<string, number>> = {};
    const src = this._source;
    // s-sourceport-contract-cleanup: declared capabilities, not typeof.
    if (!src || !sourceCapabilities(src).queryPushdown || typeof src.query !== "function") {
      // No record-plane source → every per-Kind count is skipped
      // (mirrors Python's best-effort per-Kind `except: continue`).
      return { scope, parent_chain: parentChain, resources };
    }
    // Tenant binding mirrors the Py QueryEngine: kwarg > Kernel.tenant.
    const effectiveTenant = tenant ?? this.tenant ?? undefined;
    const nameOf = (row: Record<string, unknown>): string => {
      const meta = row.metadata as Record<string, unknown> | undefined;
      return String(meta?.name ?? row.name ?? "");
    };

    for (const kind of [...DEFAULT_INHERITABLE_KINDS_V1].sort()) {
      try {
        // Local pass — always collects names (they shadow later passes).
        const seenLocal = new Set<string>();
        let localCount = 0;
        for await (const row of src.query(scope, kind, { tenant: effectiveTenant })) {
          const n = nameOf(row);
          if (n) seenLocal.add(n);
          localCount += 1;
        }
        // Catalog/installed pass — dedup vs local (Local wins). [] until
        // i-185; loop kept so the semantics are already wired.
        let installedCount = 0;
        const catalogSeen = new Set(seenLocal);
        if (this.INHERITABLE_KINDS.has(kind) && scope !== Kernel.INHERIT_PARENT_SCOPE) {
          let catalogScopes: Array<[string, string | null]>;
          try {
            catalogScopes = await this._catalogScopes(tenant, { exclude: new Set([scope]) });
          } catch {
            catalogScopes = [];
          }
          for (const [catScope, catTenant] of catalogScopes) {
            try {
              for await (const row of src.query(catScope, kind, {
                tenant: catTenant ?? undefined,
              })) {
                const n = nameOf(row);
                if (n && catalogSeen.has(n)) continue;
                if (n) catalogSeen.add(n);
                installedCount += 1;
              }
            } catch {
              continue;
            }
          }
        }
        // Parent/inherited pass — dedup vs LOCAL names only (catalog names
        // intentionally excluded — Python's origin="inherited" query never
        // runs its catalog pass). Same gate as the Py QueryEngine.
        let inheritedCount = 0;
        if (this.INHERITABLE_KINDS.has(kind) && scope !== Kernel.INHERIT_PARENT_SCOPE) {
          const parentSeen = new Set(seenLocal);
          for (const parent of parentChain) {
            try {
              for await (const row of src.query(parent, kind, { tenant: effectiveTenant })) {
                const n = nameOf(row);
                if (n && parentSeen.has(n)) continue;
                if (n) parentSeen.add(n);
                inheritedCount += 1;
              }
            } catch {
              continue; // fail-soft per parent scope, exactly like Py
            }
          }
        }
        if (localCount || inheritedCount || installedCount) {
          resources[kind] = {
            local: localCount,
            inherited: inheritedCount,
            installed: installedCount,
            total: localCount + inheritedCount + installedCount,
          };
        }
      } catch {
        continue; // best-effort — skip Kind if source errors (parity w/ Py)
      }
    }

    return { scope, parent_chain: parentChain, resources };
  }

  /** WriterPorts registered via writer(w). Returns a FROZEN snapshot of
   *  the internal writer list — mutating the returned array throws in
   *  strict mode and never affects the Kernel's internal state.
   *  Parity: python Kernel.active_writers (which returns a tuple). */
  get activeWriters(): readonly WriterPort[] {
    return Object.freeze([...this._writers]);
  }

  /** ReaderPorts registered via reader(r). Frozen snapshot — mirror of
   *  activeWriters (s-dna-rw-roundtrip-suite: the round-trip conformance
   *  suite enumerates registered pairs through this surface).
   *  Parity: python Kernel.active_readers. */
  get activeReaders(): readonly ReaderPort[] {
    return Object.freeze([...this._readers]);
  }

  cache(c: CachePort): void {
    this._cache = c;
  }

  resolver(scheme: string, r: ResolverPort): void {
    this._resolvers.set(scheme, r);
  }

  reader(r: ReaderPort): void {
    // H1 — structural conformance check. TypeScript can't use
    // runtime_checkable Protocol like Python, so we test method
    // presence + arity manually. Catches the typo-on-detect bug at
    // registration time instead of in production scans.
    if (typeof (r as { detect?: unknown })?.detect !== "function" ||
        typeof (r as { read?: unknown })?.read !== "function") {
      throw new ReaderRegistrationError(
        `Reader ${(r as { constructor?: { name?: string } })?.constructor?.name ?? typeof r} ` +
        `does not satisfy ReaderPort interface (missing detect/read ` +
        `methods). See typescript/src/kernel/protocols.ts.`,
      );
    }
    // Idempotent re-registration — same class is a no-op
    if (this._readers.some((existing) => existing.constructor === r.constructor)) {
      return;
    }
    this._readers.push(r);
  }

  writer(w: WriterPort): void {
    // H1 — structural conformance check (mirror of reader()).
    // serialize is part of the contract since s-dna-rw-roundtrip-suite.
    if (typeof (w as { canWrite?: unknown })?.canWrite !== "function" ||
        typeof (w as { write?: unknown })?.write !== "function" ||
        typeof (w as { serialize?: unknown })?.serialize !== "function") {
      throw new WriterRegistrationError(
        `Writer ${(w as { constructor?: { name?: string } })?.constructor?.name ?? typeof w} ` +
        `does not satisfy WriterPort interface (missing canWrite/write/` +
        `serialize methods — serialize is part of the contract since ` +
        `s-dna-rw-roundtrip-suite). See typescript/src/kernel/protocols.ts.`,
      );
    }
    if (this._writers.some((existing) => existing.constructor === w.constructor)) {
      return;
    }
    this._writers.push(w);
  }

  writableSource(ws: WritableSourcePort): void {
    this._writableSource = ws;
  }

  fs(f: FSLike): void {
    this._fs = f;
  }

  /** Register a Kind (H1 validation funnel). Thin facade over
   *  `this._kindreg.registerKind()` (Fase 3, s-kernel-decomp-ts-parity —
   *  the funnel moved into the KindRegistry; Py twin: `Kernel.kind()`
   *  delegating to `self._kindreg.register_kind`). */
  kind(k: KindPort): void {
    this._kindreg.registerKind(k);
  }

  /** F3 (spec D3): register a BUILTIN Kind from a KindDefinition
   *  descriptor (`kinds/*.kind.yaml` package data). Thin facade over the
   *  KindRegistry funnel (Fase 3). Py twin: `Kernel.kind_from_descriptor`. */
  kindFromDescriptor(raw: Record<string, unknown>): KindPort {
    return this._kindreg.registerFromDescriptor(raw);
  }

  /** Summary dict for a registered kind, including resolved docs. Facade
   *  over `this._kindreg.describe()` (Fase 3). */
  describeKind(kindName: string): Record<string, unknown> | null {
    return this._kindreg.describe(kindName);
  }

  /** Register a composition profile that declares how an orchestrator
   *  kind connects to other kinds. Called by extensions (e.g.
   *  HelixExtension) during register(). */
  compositionProfile(profile: CompositionProfile): void {
    this._profiles.push(profile);
  }

  // -- Tools (s-dna-port-surface-parity — Py twin: s-dna-tool-decorator) ----
  // Analogous to `.kind()` — extensions register tool definitions via
  // `kernel.tool(td)` inside register(); consumers query via
  // `kernel.getTools({ group })`. Pure metadata layer — the execution path
  // stays framework-native (`td.getCallable()`).

  /** Register a tool definition (delegates to the ToolRegistry;
   *  last-write-wins on same name). Py twin: `Kernel.tool`. */
  tool(td: ToolDefinition): void {
    this._toolreg.register(td);
  }

  /** Return a tool definition by name, or `null` if unknown.
   *  Py twin: `Kernel.get_tool`. */
  getTool(name: string): ToolDefinition | null {
    return this._toolreg.get(name);
  }

  /** Return registered tool definitions, optionally filtered by group(s)
   *  (`groups: ["read"]` expands the umbrella alias).
   *  Py twin: `Kernel.get_tools`. */
  getTools(opts: {
    group?: string | null;
    groups?: Iterable<string> | null;
  } = {}): ToolDefinition[] {
    return this._toolreg.getMany(opts);
  }

  /** Reverse-build `{group: [toolNames…]}` from the registry.
   *  Py twin: `Kernel.list_tool_groups`. */
  listToolGroups(): Record<string, string[]> {
    return this._toolreg.groups();
  }

  /** Canonical dep_filter target resolution (s-alias-generated-not-typed).
   *
   *  The CONTRACT is alias-valued dep_filters (`"soulspec-soul"`). The
   *  legacy `"kind=<Name>"` format resolves through a DEPRECATED shim so
   *  per-scope KindDefinition docs keep working. Builtin extensions must
   *  be alias-pure (validateDepFilters rejects `kind=` there). Delegates
   *  to the shared `resolveDepFilterTargetOver` — since
   *  s-unify-composition-subsystems the ONE resolver every dep_filter
   *  reader (`validateRefs` / `mi.composition` / the Kernel) consumes.
   *  Facade over `this._kindreg.resolveDepFilterTarget()` (Fase 3).
   *  Py twin: KindRegistry.resolve_dep_filter_target. */
  resolveDepFilterTarget(value: string): KindPort | null {
    return this._kindreg.resolveDepFilterTarget(value);
  }

  /** s-alias-generated-not-typed — every dep_filter target of an
   *  EXTENSION-registered Kind must resolve to a registered alias.
   *
   *  Aliases are the wire key of dep_filters / Mustache sections /
   *  LayerPolicy — a typo used to degrade the prompt SILENTLY (the dep
   *  just vanished from the context, warning buried in logs). Called at
   *  the end of `loadBuiltins()` (the TS twin of `Kernel.auto()`).
   *
   *  - Extension/builtin port with an unknown alias OR the legacy
   *    `kind=` format → `KindRegistrationError` (boot fails loud).
   *  - Per-scope declarative ports (user KindDefinition docs) only WARN
   *    — user docs never take the boot down (same posture as the
   *    parse_error / plane-lint funnels).
   *  Facade over `this._kindreg.validateDepFilters()` (Fase 3).
   *  Py twin: Kernel.validate_dep_filters. */
  validateDepFilters(): void {
    this._kindreg.validateDepFilters();
  }

  load(ext: Extension): void {
    // H1 — structural check before calling register(). Catches
    // "loaded an instance of the wrong class" — invisible in
    // entry-point discovery (e.g. registering a Kind class instead
    // of an Extension class as the entry-point target).
    if (typeof (ext as { register?: unknown })?.register !== "function") {
      throw new ExtensionLoadError(
        `Extension ${(ext as { constructor?: { name?: string } })?.constructor?.name ?? typeof ext} ` +
        `has no callable register() method. Extensions must implement ` +
        `\`register(kernel)\` per the Extension interface.`,
      );
    }
    // s-dna-extension-host-contract — validate the WHOLE Extension
    // contract fail-loud, not just register(). name identifies the
    // extension in logs / alias-owner generation; version identifies it
    // in diagnostics. Py twin: Kernel.load().
    const extName = (ext as { name?: unknown }).name;
    if (typeof extName !== "string" || extName.trim() === "") {
      throw new ExtensionLoadError(
        `Extension ${(ext as { constructor?: { name?: string } })?.constructor?.name ?? typeof ext} ` +
        `has no valid \`name\` (got ${JSON.stringify(extName)}). Extensions ` +
        `must declare \`name: string\` (non-empty) per the Extension interface.`,
      );
    }
    const extVersion = (ext as { version?: unknown }).version;
    if (typeof extVersion !== "string" || extVersion.trim() === "") {
      throw new ExtensionLoadError(
        `Extension ${JSON.stringify(extName)} has no valid \`version\` ` +
        `(got ${JSON.stringify(extVersion)}). Extensions must declare ` +
        `\`version: string\` per the Extension interface.`,
      );
    }
    try {
      // s-alias-generated-not-typed — owner context p/ geração de
      // alias dos Kinds registrados por esta Extension (declarado
      // 1× por extension, não por Kind). Py twin: Kernel.load().
      this._loadingExtOwner =
        (ext as unknown as { aliasOwner?: string | null }).aliasOwner ??
        ext.name ??
        null;
      try {
        ext.register(this);
      } finally {
        this._loadingExtOwner = null;
      }
      this._extensions.push(ext);
    } catch (e) {
      // H1 — registration validation errors propagate cleanly, not
      // swallowed by the hook path. They represent a *configuration*
      // problem the operator must fix before boot can continue.
      if (
        e instanceof KindRegistrationError ||
        e instanceof ReaderRegistrationError ||
        e instanceof WriterRegistrationError
      ) {
        const name = ext.name ?? String(ext);
        console.error(`Extension ${name} failed registration validation: ${e}`);
        throw e;
      }
      const name = ext.name ?? String(ext);
      console.error(`Extension ${name} failed to register: ${e}`);
      if (this.hooks.has("extension_error")) {
        this.hooks.emit("extension_error", {
          scope: name,
          kind: "Extension",
          name,
          data: { error: String(e) },
        });
      } else {
        throw e;
      }
    }
  }

  // -- Templates (Phase 0 contract) -----------------------------------------

  /**
   * Aggregate `templates()` from every loaded extension.
   *
   * The `templates()` method is feature-tested via
   * `typeof ext.templates === "function"` so extensions that predate
   * Phase 0 (and don't declare the method) still work. A misbehaving
   * extension that throws inside its `templates()` is logged to
   * `console.warn` but never breaks discovery for the other
   * extensions.
   */
  listTemplates(): Template[] {
    const out: Template[] = [];
    for (const ext of this._extensions) {
      if (typeof ext.templates !== "function") continue;
      try {
        out.push(...ext.templates());
      } catch (e) {
        const name = ext.name ?? String(ext);
        console.warn(`extension ${name}.templates() raised: ${e}`);
      }
    }
    return out;
  }

  /**
   * Materialize a template by id into `opts.targetRoot`.
   *
   * Throws `Error("template not found: <id>")` if no loaded extension
   * advertises a template with the given id (the TS equivalent of
   * Python's `KeyError`). `opts.onConflict` is passed through to
   * {@link materialize}.
   */
  scaffold(templateId: string, opts: MaterializeOptions): string[] {
    for (const t of this.listTemplates()) {
      if (t.id === templateId) {
        return materialize(t, opts);
      }
    }
    throw new Error(`template not found: ${templateId}`);
  }

  // -- Generic reader/writer auto-registration ------------------------------

  /** @internal — public for the KindRegistry `RegistryHost` slice (the
   *  2-phase-load rescan re-resolves generic BUNDLE readers/writers here). */
  _ensureGenericReadersWriters(): void {
    if (this._genericsResolved) return;
    this._genericsResolved = true;

    for (const kp of this._kinds.values()) {
      const sd = kp.storage;
      if (!sd || sd.pattern !== "bundle") continue;

      // Check if any existing reader already handles this marker
      const hasReader = this._readers.some(
        (r) => (r as ReaderPort & { _marker?: string })._marker === sd.marker,
      );
      if (!hasReader) {
        this._readers.push(new GenericBundleReader(sd, kp.apiVersion, kp.kind, this._fs));
      }

      // Check if any existing writer already handles this kind
      const hasWriter = this._writers.some(
        (w) => (w as WriterPort & { _kind?: string })._kind === kp.kind,
      );
      if (!hasWriter) {
        this._writers.push(new GenericBundleWriter(sd, kp.kind, this._fs));
      }
    }
  }

  // -- Kernel storage helpers (facades over this._kindreg — Fase 3) ---------

  containerForKind(kindName: string): string | null {
    return this._kindreg.containerFor(kindName);
  }

  storageForKind(kindName: string): StorageDescriptor | null {
    return this._kindreg.storageFor(kindName);
  }

  kindByContainer(container: string): string | null {
    return this._kindreg.byContainer(container);
  }

  /**
   * Stable human-readable locator for a document.
   *
   * - Filesystem sources (detected by the presence of a `baseDir`
   *   property) → "<baseDir>/<scope>/<kindSubdir>/<name>"
   * - Other sources → "<scheme>://<scope>/<kind>/<name>" where scheme
   *   comes from source.urlScheme, falling back to the class name with
   *   the trailing "source" suffix stripped.
   *
   * Parity: python Kernel._target_locator.
   */
  _targetLocator(scope: string, kind: string, name: string): string {
    const src = this._source as (SourcePort & { baseDir?: string; urlScheme?: string }) | null;
    if (src && typeof src.baseDir === "string") {
      const sd = this.storageForKind(kind);
      const subdir = sd?.container ? sd.container : `${kind.toLowerCase()}s`;
      return `${src.baseDir}/${scope}/${subdir}/${name}`;
    }
    const scheme =
      src?.urlScheme ??
      (src
        ? src.constructor.name.toLowerCase().replace(/source$/, "")
        : "unknown");
    return `${scheme}://${scope}/${kind}/${name}`;
  }

  // -- Write path -----------------------------------------------------------

  serializeDocument(_scope: string, kind: string, name: string, raw: Record<string, unknown>): SerializedDocument {
    this._ensureGenericReadersWriters();

    // Find KindPort
    let kp: KindPort | undefined;
    for (const k of this._kinds.values()) {
      if (k.kind === kind) { kp = k; break; }
    }
    if (!kp) throw new Error(`Unknown kind: ${kind}`);
    const sd = kp.storage;

    // serialize() is part of the WriterPort contract (enforced at
    // registration since s-dna-rw-roundtrip-suite) — the first writer
    // that claims the kind serializes.
    const writer = this._writers.find(w => w.canWrite(raw));

    let rawFiles: SerializedFile[];

    if (writer) {
      rawFiles = writer.serialize(raw);
    } else if (sd.pattern === "yaml") {
      rawFiles = [{ relativePath: `${name}.yaml`, content: yaml.dump(raw, { flowLevel: -1, sortKeys: false }) }];
      return { files: rawFiles.map(f => ({
        relativePath: sd.container ? `${sd.container}/${f.relativePath}` : f.relativePath,
        content: f.content,
      })) };
    } else if (sd.pattern === "root") {
      return { files: [{ relativePath: sd.marker!, content: yaml.dump(raw, { flowLevel: -1, sortKeys: false }) }] };
    } else if (sd.pattern === "standalone") {
      const spec = (raw.spec ?? {}) as Record<string, unknown>;
      const content = sd.bodyField ? String(spec[sd.bodyField] ?? "") : yaml.dump(raw, { flowLevel: -1 });
      return { files: [{ relativePath: sd.marker!, content }] };
    } else {
      // BUNDLE without serialize() — fallback to YAML dump of raw
      rawFiles = [{ relativePath: sd.marker ?? `${name}.yaml`, content: yaml.dump(raw, { flowLevel: -1 }) }];
    }

    // Prefix paths for BUNDLE: container/name/file
    const prefix = sd.pattern === "bundle"
      ? (sd.container ? `${sd.container}/${name}/` : `${name}/`)
      : "";

    // Preserve the entry payload as-is: text entries carry `content`,
    // binary ones `contentBytes` (the WriterPort serialize contract).
    return {
      files: rawFiles.map(f => ({
        relativePath: `${prefix}${f.relativePath}`,
        ...(f.contentBytes !== undefined
          ? { contentBytes: f.contentBytes }
          : { content: f.content }),
      })),
    };
  }

  /**
   * Pure preview — returns target, serialized files, existsAlready.
   *
   * Does NOT touch disk. ``existsAlready`` is a UI hint so callers can
   * render "create" vs "overwrite" affordances. Parity: Python
   * Kernel.preview_document.
   */
  async previewDocument(
    scope: string,
    kind: string,
    name: string,
    raw: Record<string, unknown>,
  ): Promise<PreviewResult> {
    const payload = this.serializeDocument(scope, kind, name, raw);
    const target = this._targetLocator(scope, kind, name);
    const existsAlready = await this._targetExists(scope, kind, name);
    return { target, files: payload.files, existsAlready };
  }

  /**
   * Best-effort probe: is the target document already present?
   *
   * Uses the writable source's `listVersions` when available (non-empty
   * = exists). Returns false on any adapter failure — this is a UI hint,
   * not a correctness gate. Parity: Python Kernel._target_exists.
   */
  private async _targetExists(scope: string, kind: string, name: string): Promise<boolean> {
    const src = this._writableSource ?? this._source;
    if (!src) return false;
    const listVersions = (src as unknown as {
      listVersions?: (s: string, k: string, n: string) => Promise<Array<{ id: string }>>;
    }).listVersions;
    if (typeof listVersions !== "function") return false;
    try {
      const versions = await listVersions.call(src, scope, kind, name);
      return versions.length > 0;
    } catch {
      return false;
    }
  }

  async writeDocument(
    scope: string,
    kind: string,
    name: string,
    raw: Record<string, unknown>,
    options?: {
      skipHooks?: boolean;
      author?: string;
      tenant?: string | null;
      layer?: [string, string];
    },
  ): Promise<string> {
    // Thin facade (Fase 2, s-kernel-decomp-f2-writepipeline) — the fat body
    // (tenant resolve, layer-policy check, pre_save veto, persist,
    // post_save) lives in WritePipeline.write.
    return this._writePipeline.write(scope, kind, name, raw, options);
  }

  async deleteDocument(
    scope: string,
    kind: string,
    name: string,
    options?: {
      skipHooks?: boolean;
      author?: string;
      tenant?: string | null;
      layer?: [string, string];
    },
  ): Promise<void> {
    // Thin facade (Fase 2) — delegates to WritePipeline.delete. Deletes have
    // NO pre_save veto (only writes do).
    return this._writePipeline.delete(scope, kind, name, options);
  }

  /** @internal — resolve the registered writable source or throw
   *  NotWritableError. Used by WritePipeline (Py twin:
   *  `Kernel._require_writable_source`). */
  _requireWritableSource(): WritableSourcePort {
    if (!this._writableSource) {
      throw new NotWritableError("No writable source registered. Call kernel.writableSource() first.");
    }
    return this._writableSource;
  }

  /**
   * Per-scope cache of the base (no-layer) ManifestInstance. Used by the
   * layer-policy check so it does not re-resolve layers per call. Mirrors
   * Python KernelCache._base (the kernel's extracted cache collaborator).
   */
  private _baseInstanceCache: Map<string, ManifestInstance | null> | undefined;
  /** LRU bound on _baseInstanceCache (scopes). Mirrors Py _BASE_INSTANCE_MAX (i-036). */
  private static readonly BASE_INSTANCE_MAX = 64;

  private async _ensureBaseInstance(scope: string): Promise<ManifestInstance | null> {
    if (!this._baseInstanceCache) this._baseInstanceCache = new Map();
    const cache = this._baseInstanceCache;
    if (cache.has(scope)) {
      // LRU touch — move to the MRU end so a hot scope survives eviction.
      const v = cache.get(scope) ?? null;
      cache.delete(scope);
      cache.set(scope, v);
      return v;
    }
    let mi: ManifestInstance | null;
    try {
      mi = await this.instance(scope);
    } catch {
      mi = null;
    }
    cache.set(scope, mi);
    // Evict least-recently-used (oldest insertion) over the bound.
    while (cache.size > Kernel.BASE_INSTANCE_MAX) {
      const oldest = cache.keys().next().value as string;
      cache.delete(oldest);
    }
    return mi;
  }

  /**
   * Resolve a kind name to its globally-unique alias (`<owner>-<kind>`).
   * Falls back to `kind.toLowerCase()` when no registered port provides one.
   * Facade over `this._kindreg.aliasFor()` (Fase 3). Parity: Python
   * Kernel._alias_for delegating to `self._kindreg.alias_for`.
   */
  private _aliasFor(kind: string): string {
    return this._kindreg.aliasFor(kind);
  }

  /**
   * Validate that writing/deleting `kind/name` in `scope` against the given
   * layer overlay satisfies the Module's LayerPolicy (OPEN / RESTRICTED /
   * LOCKED). Parity: Python Kernel._check_layer_policy.
   *
   * Policy modes (resolved via alias `<owner>-<kind>`):
   * - LOCKED — any write throws.
   * - RESTRICTED — adding a new doc (not present in base) throws; adding a
   *   *new top-level spec key* on an existing doc throws; overriding
   *   existing top-level spec keys is allowed.
   * - OPEN (default) — never throws.
   *
   * When the scope has no Module doc, policy defaults to OPEN (no-op).
   */
  /** @internal — read by WritePipeline (write/delete policy gate). */
  async _checkLayerPolicyAsync(
    scope: string,
    kind: string,
    name: string,
    raw: unknown,
    layer: [string, string],
  ): Promise<void> {
    const [layerId] = layer;

    // Phase 16 — hardcoded allowlist: Genome / KindDefinition /
    // LayerPolicy can never be written to a layer overlay regardless
    // of declared policy. Identity, schema-bootstrap and policy Kinds
    // are structurally non-overlayable (a tenant must not be able to
    // redefine its own visibility, version, or the policy that
    // constrains its overlay).
    if (this.NON_OVERLAYABLE_KINDS.has(kind)) {
      throw new LayerPolicyViolationError(
        `${kind} is structurally non-overlayable; ` +
          `cannot write to layer '${layerId}'`,
      );
    }

    const mi = await this._ensureBaseInstance(scope);
    if (!mi) return; // no manifest / unreadable → no policy to enforce

    const alias = this._aliasFor(kind);

    // Phase 16 commit 4 — policies come exclusively from LayerPolicy
    // docs in the scope. Module.spec.layers legacy path is GONE.
    // Iterate; the last doc whose spec.layer_id matches wins.
    let policyStr = "open";
    let layerPolicyDocs: Document[] = [];
    try {
      layerPolicyDocs = mi._all("LayerPolicy");
    } catch {
      layerPolicyDocs = [];
    }
    for (const lpDoc of layerPolicyDocs) {
      const lpSpec = (lpDoc.spec ?? {}) as Record<string, unknown>;
      if (lpSpec.layer_id !== layerId) continue;
      const lpPolicies = (lpSpec.policies ?? {}) as Record<string, unknown>;
      const value = lpPolicies[alias];
      if (typeof value === "string" && value) {
        policyStr = value.toLowerCase();
      }
    }

    if (policyStr === "locked") {
      throw new LayerPolicyViolationError(
        `${alias} is LOCKED in layer '${layerId}' per LayerPolicy docs`,
      );
    }
    if (policyStr === "restricted") {
      const existing = mi._one(kind, name);
      if (!existing) {
        throw new LayerPolicyViolationError(
          `${alias} in layer '${layerId}' is RESTRICTED — ` +
            `cannot add new document '${name}' not present in base`,
        );
      }
      // Compare against the doc's RAW spec (what was actually authored), not
      // the typed spec (which exposes every field defined on the model —
      // including unset defaults). Fall back to typed spec only when raw is
      // unavailable. Mirrors Python Task 5's fix.
      const existingRaw = (existing.raw ?? {}) as Record<string, unknown>;
      const existingRawSpec = existingRaw.spec;
      let existingKeys: Set<string>;
      if (existingRawSpec && typeof existingRawSpec === "object") {
        existingKeys = new Set(Object.keys(existingRawSpec as Record<string, unknown>));
      } else {
        const existingSpec = (existing.spec ?? {}) as Record<string, unknown>;
        existingKeys = new Set(Object.keys(existingSpec));
      }
      const newSpecVal = (raw as { spec?: unknown } | null)?.spec;
      const newSpec =
        newSpecVal && typeof newSpecVal === "object"
          ? (newSpecVal as Record<string, unknown>)
          : {};
      const added = Object.keys(newSpec)
        .filter((k) => !existingKeys.has(k))
        .sort();
      if (added.length > 0) {
        throw new LayerPolicyViolationError(
          `${alias} in layer '${layerId}' is RESTRICTED — ` +
            `cannot add new top-level spec keys [${added.join(", ")}]; ` +
            `may only override existing`,
        );
      }
    }
    // OPEN: allow
  }

  // -- Instance creation ----------------------------------------------------

  async instance(scope: string, layers?: Record<string, string>): Promise<ManifestInstance> {
    this._ensureGenericReadersWriters();

    if (!this._source) {
      throw new Error("No source registered. Call kernel.source() first.");
    }
    if (!this._cache) {
      throw new Error("No cache registered. Call kernel.cache() first.");
    }

    // 1. Load bootstrap docs (Phase 16 — Genome + KindDefinition +
    // LayerPolicy in one shot). Replaces the legacy ``loadManifest``
    // cardinality-1 contract.
    const bootstrapDocs = await this._source.loadBootstrapDocs(scope);
    let manifest: Record<string, unknown> = {};
    for (const d of bootstrapDocs) {
      if (d.kind === "Genome") { manifest = d; break; }
    }

    // 1b. Register custom_kinds from manifest (legacy ``Module.spec
    // .custom_kinds`` field). KindDefinition docs from bootstrapDocs
    // get registered later via the existing 2-phase loader path.
    this._registerCustomKinds(manifest);

    // 2. Resolve deps (auto on cache miss)
    const resolveErrors: string[] = [];
    const spec = (manifest.spec as Record<string, unknown>) ?? {};
    const deps = (spec.dependencies as Record<string, unknown>[]) ?? [];

    for (const dep of deps) {
      const uri = (dep.source as string) ?? "";
      const scheme = uri.includes(":") ? uri.split(":")[0] : "";
      const resolver = this._resolvers.get(scheme);
      if (!resolver) {
        resolveErrors.push(`No resolver for scheme: ${scheme}`);
        continue;
      }
      const key = resolver.cacheKey(uri);
      if (!this._cache.has(scope, key)) {
        try {
          const resolved = await resolver.resolve(uri, dep);
          const cacheItems: CacheItem[] = resolved.map((r) => ({
            name: r.name,
            kind: r.kind,
            contentPath: r.sourcePath,
          }));
          this._cache.store(scope, key, cacheItems);
        } catch (e) {
          if (e instanceof ResolveError) {
            resolveErrors.push(String(e));
          } else {
            throw e;
          }
        }
      }
    }

    // 3. Load local + cache docs (per-key for correct origin tagging)
    const localRaws = await this._source.loadAll(scope, this._readers);

    type RawWithOrigin = { raw: Record<string, unknown>; origin: string };
    const allRaws: RawWithOrigin[] = [];

    for (const raw of localRaws) {
      allRaws.push({ raw, origin: "local" });
    }

    // Scope-level inheritance — Story s-platform-agent-fallback (2026-05-28).
    // Eager MI: carrega docs do INHERIT_PARENT_SCOPE filtrados pra kinds
    // em INHERITABLE_KINDS, merge com local (local ganha por (kind, name)).
    // 1:1 parity com Python Kernel.instance_async.
    if (scope !== Kernel.INHERIT_PARENT_SCOPE) {
      let parentRaws: Record<string, unknown>[] = [];
      try {
        parentRaws = await this._source.loadAll(
          Kernel.INHERIT_PARENT_SCOPE, this._readers,
        );
      } catch {
        // defensive — parent scope inacessível, scope local segue normal
      }
      const localKeys = new Set(
        localRaws.map((r) => {
          const meta = r.metadata as Record<string, unknown> | undefined;
          const name = (meta?.name as string | undefined) ?? (r.name as string | undefined);
          return `${r.kind ?? ""}\0${name ?? ""}`;
        }),
      );
      for (const praw of parentRaws) {
        const pkind = praw.kind as string | undefined;
        if (!pkind || !this.INHERITABLE_KINDS.has(pkind)) continue;
        const pmeta = praw.metadata as Record<string, unknown> | undefined;
        const pname = (pmeta?.name as string | undefined) ?? (praw.name as string | undefined);
        const pkey = `${pkind}\0${pname ?? ""}`;
        if (localKeys.has(pkey)) continue;
        allRaws.push({ raw: praw, origin: `inherited:${Kernel.INHERIT_PARENT_SCOPE}` });
      }
    }
    for (const dep of deps) {
      const uri = (dep.source as string) ?? "";
      const scheme = uri.includes(":") ? uri.split(":")[0] : "";
      const resolver = this._resolvers.get(scheme);
      if (!resolver) continue;
      const key = resolver.cacheKey(uri);
      const keyRaws = await this._cache.loadKey(scope, key, this._readers);
      for (const raw of keyRaws) {
        allRaws.push({ raw, origin: uri });
      }
    }

    // 5. Apply layers (if requested)
    let finalRaws = allRaws;
    if (layers && Object.keys(layers).length > 0) {
      finalRaws = await this._applyLayers(scope, allRaws, layers);
    }

    // ── Phase 1: parse + register KindDefinitions ──
    const addedReaders = this._registerKindDefinitions(finalRaws.map((r) => r.raw));

    // If new declarative kinds introduced new generic readers, re-scan the
    // source so instance documents of those new kinds are picked up.
    if (addedReaders && this._source) {
      try {
        const extra = await this._source.loadAll(scope, this._readers);
        const seen = new Set(
          finalRaws.map(
            ({ raw }) =>
              `${raw.apiVersion ?? ""}\0${raw.kind ?? ""}\0${((raw.metadata as Record<string, unknown> | undefined)?.name) ?? ""}`,
          ),
        );
        for (const r of extra) {
          const key = `${r.apiVersion ?? ""}\0${r.kind ?? ""}\0${((r.metadata as Record<string, unknown> | undefined)?.name) ?? ""}`;
          if (!seen.has(key)) {
            finalRaws.push({ raw: r, origin: "local" });
            seen.add(key);
          }
        }
      } catch {
        // defensive
      }
    }

    // ── Phase 2: parse all docs via KindPorts ──
    const documents: Document[] = [];
    for (const { raw, origin } of finalRaws) {
      documents.push(this._parseDoc(raw, origin));
    }

    return new ManifestInstance({
      scope,
      documents,
      kinds: this._kinds,
      source: this._source,
      resolveErrors,
      kernel: this,
      profiles: this._profiles,
    });
  }

  async resolveLayers(
    mi: ManifestInstance,
    layers: Record<string, string>,
  ): Promise<ManifestInstance> {
    return this.instance(mi.scope, layers);
  }

  // -- Layer application ----------------------------------------------------

  private async _applyLayers(
    scope: string,
    baseRaws: { raw: Record<string, unknown>; origin: string }[],
    layers: Record<string, string>,
  ): Promise<{ raw: Record<string, unknown>; origin: string }[]> {
    // Get policies from root document
    const policies: Record<string, string> = {};
    for (const { raw } of baseRaws) {
      const av = (raw.apiVersion as string) ?? "";
      const kn = (raw.kind as string) ?? "";
      const key = `${av}\0${kn}`;
      const kp = this._kinds.get(key);
      if (kp?.isRoot) {
        const doc = this._parseDoc(raw);
        const rawPolicies = kp.getLayerPolicies(doc);
        if (rawPolicies) {
          for (const [alias, ps] of Object.entries(rawPolicies)) {
            policies[alias] = String(ps);
          }
        }
        break;
      }
    }

    // Load overlay docs — source uses readers to detect bundles (SKILL.md etc)
    const overlayRaws: Record<string, unknown>[] = [];
    for (const [layerId, value] of Object.entries(layers)) {
      const loaded = await this._source!.loadLayer(scope, layerId, value, this._readers);
      overlayRaws.push(...loaded);
    }

    if (overlayRaws.length === 0) return baseRaws;

    // Merge using DefaultLayerResolver with a direct adapter
    // so the resolver doesn't need to hit disk again
    const resolver = new DefaultLayerResolver();
    const directSource = {
      loadLayer: () => overlayRaws,
    };

    const rawsOnly = baseRaws.map((r) => r.raw);
    const merged = resolver.resolve(rawsOnly, layers, directSource, scope, policies);
    return merged.map((raw) => ({ raw, origin: "local" }));
  }

  // -- Parsing --------------------------------------------------------------

  /**
   * If a kind declares `descriptionFallbackField` and metadata.description
   * is missing/empty, derive it from the named spec field. Mutates `raw`.
   */
  static _fillDerivedDescription(
    raw: Record<string, unknown>,
    kindPort: unknown,
  ): void {
    const field = (kindPort as { descriptionFallbackField?: string })
      .descriptionFallbackField;
    if (!field) return;
    let meta = raw.metadata as Record<string, unknown> | undefined;
    if (!meta) {
      meta = {};
      raw.metadata = meta;
    }
    if (meta.description) return;
    const text = (
      (raw.spec as Record<string, unknown> | undefined) ?? {}
    )[field] as string | undefined;
    const derived = deriveFirstLine(text);
    if (derived) meta.description = derived;
  }

  _parseDoc(raw: Record<string, unknown>, origin = "local"): Document {
    const av = (raw.apiVersion as string) ?? "";
    const kn = (raw.kind as string) ?? "";
    const name =
      ((raw.metadata as Record<string, unknown>)?.name as string) ?? "";
    const key = `${av}\0${kn}`;
    const kindPort = this._kinds.get(key);
    let typed: unknown = null;

    if (kindPort) {
      try {
        Kernel._fillDerivedDescription(raw, kindPort);
        typed = kindPort.parse(raw);
      } catch (e) {
        console.warn(`Parse error for ${av}/${kn}: ${e}`);
        if (this.hooks.has("parse_error")) {
          this.hooks.emit("parse_error", {
            scope: "",
            kind: kn,
            name,
            data: { error: String(e), apiVersion: av, raw },
          });
        }
      }
    }

    return Document.fromRaw(raw, typed ?? undefined, origin);
  }

  /**
   * Phase 1 of 2-phase loading: parse KindDefinition docs + register
   * synthetic DeclarativeKindPorts. Thin facade over the KindRegistry
   * funnel (Fase 3, s-kernel-decomp-ts-parity). Returns true iff new
   * BUNDLE readers were added (the rescan gate). Py twin:
   * `Kernel._register_kind_definitions`.
   */
  private _registerKindDefinitions(rawDocs: Record<string, unknown>[]): boolean {
    return this._kindreg.registerKindDefinitions(rawDocs);
  }

  // -- Custom kinds ---------------------------------------------------------

  /** Register dynamic `Module.spec.custom_kinds`. Thin facade over the
   *  KindRegistry funnel (Fase 3). Py twin: `Kernel._register_custom_kinds`. */
  private _registerCustomKinds(manifest: Record<string, unknown>): void {
    this._kindreg.registerCustomKinds(manifest);
  }

  // Quick-start helpers (quick / auto) have been moved to
  // typescript/src/bootstrap.ts — use createKernelWithBuiltins() or
  // quickInstance() instead. The kernel itself should NOT import from
  // extensions/ (microkernel principle).

  // -- Model registry helpers -----------------------------------------------

  /**
   * Resolve a ModelProfile from the `_lib` scope by `model_id` (pass 1)
   * or `aliases[]` (pass 2). Returns the matching Document or null on miss.
   *
   * Always queries `MODEL_REGISTRY_SCOPE` ("_lib") directly — ModelProfile
   * is GLOBAL and NOT in `INHERITABLE_KINDS`; any caller scope is irrelevant.
   *
   * 1:1 parity with Python `Kernel.model_profile(model_id_or_alias)`.
   *
   * @param modelIdOrAlias - The model_id string or an alias declared in the profile.
   * @returns The matching Document, or null on miss or error.
   */
  async modelProfile(modelIdOrAlias: string): Promise<import("./document.js").Document | null> {
    let rows: import("./document.js").Document[];
    try {
      const mi = await this.instance(MODEL_REGISTRY_SCOPE);
      rows = mi._all("ModelProfile");
    } catch {
      return null;
    }

    // Pass 1: exact model_id match
    for (const row of rows) {
      const spec = (row.spec ?? {}) as Record<string, unknown>;
      if (spec.model_id === modelIdOrAlias) {
        return row;
      }
    }

    // Pass 2: aliases[]
    for (const row of rows) {
      const spec = (row.spec ?? {}) as Record<string, unknown>;
      const aliases = (spec.aliases ?? []) as unknown[];
      if (aliases.includes(modelIdOrAlias)) {
        return row;
      }
    }

    return null;
  }

  /**
   * Resolve a VoicePolicy from the `_lib` scope by metadata name.
   * Returns the matching Document, the first policy as a fallback, or null
   * on miss/error. Always queries `VOICE_POLICY_SCOPE` ("_lib")
   * directly — VoicePolicy is GLOBAL and NOT in `INHERITABLE_KINDS`.
   *
   * 1:1 parity with Python `Kernel.voice_policy(name)`.
   */
  async voicePolicy(name = "default"): Promise<import("./document.js").Document | null> {
    let rows: import("./document.js").Document[];
    try {
      const mi = await this.instance(VOICE_POLICY_SCOPE);
      rows = mi._all("VoicePolicy");
    } catch {
      return null;
    }
    for (const row of rows) {
      if (row.name === name) {
        return row;
      }
    }
    return rows.length > 0 ? rows[0] : null;
  }
}

export { ManifestInstance } from "./instance.js";
