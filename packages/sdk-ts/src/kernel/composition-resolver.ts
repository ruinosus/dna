/**
 * The kernel's unified composition motor — TS twin of
 * `packages/sdk-py/dna/kernel/composition_resolver.py`
 * (s-unify-composition-subsystems). One module, four composition
 * concerns:
 *
 *   1. CompositionProfile (V1) — declarative wiring + UI hints
 *      registered by extensions (moved here from `composition.ts`,
 *      now a deprecated re-export shim).
 *   2. `validateRefs` — THE shared cross-kind ref validation core;
 *      target resolution via `resolveDepFilterTargetOver`
 *      (kind-registry.ts) — the same canonical resolver the Kernel
 *      uses, so alias + legacy `kind=` resolve identically everywhere.
 *   3. CompositionEngine — the `mi.composition` namespace (moved here
 *      from `composition-engine.ts`, deleted).
 *   4. CompositionResolver — the Composition-V2 chain-resolution engine.
 *
 * Pure resolution types + merges stay in `resolver.ts` (Py:
 * `kernel/resolver.py`).
 *
 * Record-plane rule (two-planes F2.5) — ONE rule for every reader: a ref
 * whose TARGET Kind is plane="record" resolves when present in the doc
 * index and is DEFERRED otherwise (never false-missing).
 *
 * # CompositionResolver — Composition-V2 (Phase 17 /
 * s-ts-composition-v2-port).
 *
 * Behavior parity is 1:1 with the Python engine on the RESOLUTION SEMANTICS:
 * chain walk (`computeResolutionChain` — cycle guard + MAX_RESOLUTION_DEPTH +
 * V1 fallback to `_lib`), composition-rule lookup (`getCompositionRule` —
 * LayerPolicy.composition_rules else the inherit-by-default denylist),
 * `resolveDocument` (bootstrap bypass, tenant overlay, Catalog splice
 * Local > Catalog > Base, override_full / field_level merge, provenance) and
 * `personalizeDocument`. The behavioral gate is the shared fixture harness
 * `tests/parity-fixtures/composition/` (s-parity-behavioral-harness), executed
 * by BOTH `packages/sdk-py/tests/test_composition_parity_fixtures.py` and
 * `packages/sdk-ts/tests/composition-parity-fixtures.test.ts`.
 *
 * Documented divergences from Python — PERF / infra, NOT semantics:
 *
 * 1. **No granular layer cache.** The Py kernel reads each layer through
 *    `_granular_doc_cached` (LRU 2000 / TTL 60s / single-flight). The TS
 *    kernel has no kernel-level doc cache, so `Kernel._granularDoc` hits the
 *    source directly on every layer read. Same inputs → same outputs; each
 *    resolve just costs O(chain) source reads instead of cache hits.
 * 2. **No `_layer_observers` reverse-dep graph.** That structure exists purely
 *    to invalidate the Py granular cache across scopes on parent/catalog
 *    writes; with no cache there is nothing to invalidate. It is intentionally
 *    NOT ported (would be dead state).
 * 3. **Catalog tier surface.** The TS kernel has no catalog machinery yet
 *    (package scan + tenant lockfile — deferred as `i-185`). The splice HOOK
 *    is fully implemented here (identical to Py: insert after the local
 *    entries, before the first parent, conflict surfacing on ≥2 hits) but
 *    `Kernel._catalogScopes` returns `[]` until i-185 lands, so the Catalog
 *    tier contributes no layers on TS today.
 * 4. **`personalizeDocument` clones spec + envelope only.** The Py engine also
 *    clones binary bundle entries via `source._load_bundle_entries` +
 *    `kernel.write_bundle_entry_async`; the TS kernel has no bundle-entry
 *    write surface yet, so bundle payload cloning is Py-only (best-effort in
 *    Py anyway — failures there are swallowed).
 */

import { sourceCapabilities } from "./capabilities.js";
import {
  BOOTSTRAP_KINDS,
  DEFAULT_NON_INHERITABLE_KINDS_V1,
  MAX_RESOLUTION_DEPTH,
  ResolutionLayer,
  ResolutionPath,
  ResolvedDocument,
  mergeFieldLevel,
  mergeOverrideFull,
  type Contribution,
} from "./resolver.js";
import type { Kernel } from "./index.js";
import type { CompositionResolverHost } from "./collaborator-ports.js";
import type { Document } from "./document.js";
import type { CompositionResult, KindPort } from "./protocols.js";
import type { ManifestInstance } from "./instance.js";
import { resolveDepFilterTargetOver } from "./kind-registry.js";
import { findConsumers } from "./preview.js";

type Raw = Record<string, unknown>;

// ---------------------------------------------------------------------------
// 1. CompositionProfile (V1) — declarative kind-wiring + UI hints
// ---------------------------------------------------------------------------

/** Timeline rendering hints for a composition slot. */
export interface TimelineHint {
  readonly label: string;       // "Skills"
  readonly itemLabel: string;   // "instruction loaded"
}

/** Health check rule for a composition slot. */
export interface HealthCheckHint {
  /** "at-least-one": agent must reference ≥1 doc of this slot.
   *  "has-error-severity": at least one doc of this kind with
   *  severity=error must be referenced. */
  readonly rule: "at-least-one" | "has-error-severity";
  readonly severity: "warn" | "error";
  /** Key in the health report output dict. e.g. "agents_without_guardrails". */
  readonly issueKey: string;
  /** Human message for the issue. */
  readonly message: string;
}

/** Quadrant chart configuration for a composition slot. */
export interface QuadrantHint {
  readonly axis: "x" | "y";
  /** Axis label. e.g. "Few Skills --> Many Skills". */
  readonly label: string;
  /** Divide doc count by this to normalize to 0..1 range. */
  readonly maxScale: number;
}

/**
 * A named slot in a composition profile. Each slot describes how an
 * orchestrator kind connects to a target kind.
 */
export interface CompositionSlot {
  /** The spec field name on the orchestrator that holds refs to this kind.
   *  e.g. "skills", "soul", "guardrails". */
  readonly name: string;

  /** Alias of the target KindPort. e.g. "agentskills-skill". */
  readonly targetAlias: string;

  /** "one" = scalar ref (soul), "many" = array ref (skills, guardrails). */
  readonly cardinality: "one" | "many";

  /** Rendering order in timeline diagrams. Lower = earlier. */
  readonly order: number;

  /** If true, buildPrompt callers can filter this slot via enabledSlots. */
  readonly filterable: boolean;

  /** Timeline rendering hints. Null = skip this slot in timelines. */
  readonly timeline: TimelineHint | null;

  /** Health check rule. Null = no health check for this slot. */
  readonly healthCheck: HealthCheckHint | null;

  /** Quadrant chart configuration. Null = not plotted. */
  readonly quadrant: QuadrantHint | null;
}

/**
 * A CompositionProfile describes how an orchestrator kind connects to
 * other kinds. Registered by extensions via kernel.compositionProfile().
 */
export interface CompositionProfile {
  /** Alias of the orchestrator KindPort. e.g. "helix-agent". */
  readonly orchestratorAlias: string;

  /** Human-readable label for the profile. e.g. "Helix Agent". */
  readonly label: string;

  /** Ordered list of composition slots. */
  readonly slots: readonly CompositionSlot[];
}

/**
 * Find the profile whose orchestrator matches a given alias.
 * Returns null if none registered. Pure helper — no kernel dependency.
 */
export function profileForOrchestrator(
  profiles: readonly CompositionProfile[],
  orchestratorAlias: string,
): CompositionProfile | null {
  return profiles.find((p) => p.orchestratorAlias === orchestratorAlias) ?? null;
}

// ---------------------------------------------------------------------------
// 2. validateRefs — the shared cross-kind ref validation core
// ---------------------------------------------------------------------------

/**
 * Validate declared dep_filter refs of `docs` against `docIndex`
 * (`${kind}\0${name}` keys). The ONE implementation behind
 * `mi.composition.validate()` — target resolution via
 * `resolveDepFilterTargetOver` (canonical s-alias resolver: alias
 * contract + deprecated `kind=` shim). Unresolvable target → warnings;
 * ref in index → resolved; absent + record-plane target → deferred
 * (records resolve lazily via the kernel record plane — never
 * false-missing); absent otherwise → missing.
 * Py twin: `composition_resolver.validate_refs`.
 */
export function validateRefs(
  docs: Iterable<Document>,
  docIndex: Set<string>,
  kinds: Map<string, KindPort>,
): CompositionResult {
  const resolved: string[] = [];
  const missing: string[] = [];
  const warnings: string[] = [];
  const deferred: string[] = [];

  for (const doc of docs) {
    const kp = kinds.get(`${doc.apiVersion}\0${doc.kind}`);
    if (!kp) continue;
    const filters = kp.depFilters();
    if (!filters) continue;

    const spec = doc.spec as Record<string, unknown>;
    for (const [specField, targetValue] of Object.entries(filters)) {
      const targetKp = resolveDepFilterTargetOver(kinds, targetValue);
      if (!targetKp) {
        warnings.push(
          `${doc.kind}/${doc.name}: unknown alias '${targetValue}' in depFilters`,
        );
        continue;
      }
      const targetKind = targetKp.kind;

      const declared = spec[specField] ?? null;
      if (declared == null) continue;
      const refs: string[] = Array.isArray(declared)
        ? declared
        : typeof declared === "string"
          ? [declared]
          : [];

      const targetIsRecord = (targetKp.plane ?? "composition") === "record";
      for (const refName of refs) {
        const label = `${doc.kind}/${doc.name}.${specField}=${refName} -> ${targetKind}/${refName}`;
        if (docIndex.has(`${targetKind}\0${refName}`)) {
          resolved.push(label);
        } else if (targetIsRecord) {
          deferred.push(label + " (record — resolved lazily)");
        } else {
          missing.push(label + " NOT FOUND");
        }
      }
    }
  }

  return { resolved, missing, warnings, deferred };
}

// ---------------------------------------------------------------------------
// 3. CompositionEngine — the `mi.composition` namespace
// ---------------------------------------------------------------------------

export class CompositionEngine {
  constructor(private host: ManifestInstance) {}

  /**
   * Validate all composition references over the MI plane.
   * Equivalent to `mi.compositionResult`. Delegates to `validateRefs` —
   * records are excluded from the MI materialization, so record-target
   * refs land in `deferred` (they resolve lazily via the kernel record
   * plane at read time).
   */
  validate(): CompositionResult {
    const kinds = (this.host as any)._kinds as Map<string, KindPort>;
    const docIndex = new Set<string>();
    for (const d of this.host.documents) {
      docIndex.add(`${d.kind}\0${d.name}`);
    }
    return validateRefs(this.host.documents, docIndex, kinds);
  }

  /**
   * Iterate a document's declared dep_filters dynamically.
   * Equivalent to `mi.iterDocDeps(doc)`.
   */
  iterDocDeps(doc: Document): { label: string; targetKind: string; names: string[] }[] {
    const kinds = (this.host as any)._kinds as Map<string, KindPort>;
    const sourceKp = kinds.get(`${doc.apiVersion}\0${doc.kind}`);
    if (!sourceKp) return [];
    const filters = sourceKp.depFilters();
    if (!filters) return [];

    const spec = (doc.spec as Record<string, unknown>) ?? {};
    const result: { label: string; targetKind: string; names: string[] }[] = [];

    for (const [label, targetValue] of Object.entries(filters)) {
      const targetKp = resolveDepFilterTargetOver(kinds, targetValue);
      if (!targetKp) continue;

      const value = spec[label];
      let names: string[] = [];
      if (Array.isArray(value)) {
        names = value.filter((v): v is string => typeof v === "string");
      } else if (typeof value === "string" && value) {
        names = [value];
      }
      if (names.length === 0) continue;

      result.push({ label, targetKind: targetKp.kind, names });
    }
    return result;
  }

  /**
   * Walk the manifest and return every doc that references this one.
   * Equivalent to `mi.consumersOf(kind, name)`.
   */
  consumersOf(
    kind: string,
    name: string,
  ): Array<{ kind: string; name: string }> {
    return findConsumers(this.host, { kind, name });
  }

  /**
   * Build a dependency tree for the manifest.
   * Equivalent to `mi.dependencyTree()`.
   */
  dependencyTree(): Record<string, unknown> {
    const kinds = (this.host as any)._kinds as Map<string, KindPort>;

    const docIndex = new Map<string, typeof this.host.documents[0]>();
    for (const d of this.host.documents) {
      docIndex.set(`${d.kind}\0${d.name}`, d);
    }

    const tree: Record<string, unknown> = {};

    for (const doc of this.host.documents) {
      const key = `${doc.apiVersion}\0${doc.kind}`;
      const kp = kinds.get(key);
      if (!kp) continue;
      const filters = kp.depFilters();
      if (!filters) continue;

      const dependsOn: Record<string, unknown> = {};
      const spec = doc.spec as Record<string, unknown>;

      for (const [specField, targetValue] of Object.entries(filters)) {
        const targetKp = resolveDepFilterTargetOver(kinds, targetValue);
        if (!targetKp) continue;
        const targetKind = targetKp.kind;

        const declared = spec[specField];
        if (!declared) continue;

        const refs: string[] = Array.isArray(declared)
          ? declared
          : typeof declared === "string"
            ? [declared]
            : [];

        const deps: Record<string, unknown> = {};
        for (const refName of refs) {
          const depEntry: Record<string, unknown> = { kind: targetKind };
          const refDoc = docIndex.get(`${targetKind}\0${refName}`);
          if (refDoc) {
            depEntry.found = true;
            const desc = (refDoc.metadata as Record<string, unknown>).description ?? "";
            if (desc) depEntry.description = desc;
            const extra = targetKp.summary(refDoc);
            if (extra) Object.assign(depEntry, extra);
          } else {
            depEntry.found = false;
          }
          deps[refName] = depEntry;
        }

        if (Object.keys(deps).length > 0) {
          dependsOn[specField] = deps;
        }
      }

      if (Object.keys(dependsOn).length > 0) {
        tree[doc.name] = {
          kind: doc.kind,
          description: (doc.metadata as Record<string, unknown>).description ?? "",
          depends_on: dependsOn,
        };
      }
    }

    return tree;
  }
}

// ---------------------------------------------------------------------------
// 4. CompositionResolver — the Composition-V2 chain-resolution engine
// ---------------------------------------------------------------------------

/** Structural layer equality — mirrors the Python frozen-dataclass `==`
 *  (field-by-field), which `resolve_document` relies on to flag the
 *  contributing layer. Reference equality would diverge when the same
 *  (scope, tenant) pair appears twice in a spliced chain. */
function layerEquals(a: ResolutionLayer, b: ResolutionLayer): boolean {
  return (
    a.scope === b.scope
    && a.tenant === b.tenant
    && a.found === b.found
    && a.contributed === b.contributed
    && a.versionSha === b.versionSha
  );
}

function specOf(raw: unknown): Raw | null {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) return null;
  const spec = (raw as Raw).spec;
  if (spec === null || spec === undefined || typeof spec !== "object" || Array.isArray(spec)) {
    return null;
  }
  return spec as Raw;
}

export class CompositionResolver {
  private readonly _k: CompositionResolverHost;

  constructor(kernel: CompositionResolverHost) {
    this._k = kernel;
  }

  /**
   * Walk `Genome.spec.parent_scope` transitively → ordered chain of
   * `[scope, tenant]` pairs, HIGHEST priority first. Cycle-guarded; depth
   * capped at MAX_RESOLUTION_DEPTH; missing Genome terminates the walk.
   * 1:1 with Py `compute_resolution_chain`.
   */
  async computeResolutionChain(
    scope: string,
    tenant: string | null,
  ): Promise<Array<[string, string | null]>> {
    const k = this._k;
    const inheritParent = (k.constructor as typeof Kernel).INHERIT_PARENT_SCOPE;
    const chain: Array<[string, string | null]> = [];
    const visited = new Set<string>();
    let current: string | null = scope;
    let depth = 0;
    while (current && !visited.has(current) && depth < MAX_RESOLUTION_DEPTH) {
      visited.add(current);
      if (tenant) chain.push([current, tenant]);
      chain.push([current, null]);
      // Fail-soft: a scope absent on the source contributes no parent
      // (chain ends here instead of throwing) — critical under the
      // inherit-by-default denylist where every read computes a chain.
      let pkgRaw: Raw | null = null;
      try {
        pkgRaw = await k._granularDoc([current, "Genome", current, ""]);
      } catch {
        pkgRaw = null;
      }
      let parent: string | null = null;
      const spec = specOf(pkgRaw);
      if (spec) {
        const parentVal = spec.parent_scope;
        if (typeof parentVal === "string" && parentVal) parent = parentVal;
      }
      // V1 back-compat: when Genome omits parent_scope, escalate to the
      // legacy INHERIT_PARENT_SCOPE (default _lib) so existing scopes
      // inherit without migration. Overridden once parent_scope is declared.
      if (
        parent === null
        && current !== inheritParent
        && !visited.has(inheritParent)
      ) {
        parent = inheritParent;
      }
      current = parent;
      depth += 1;
    }
    return chain;
  }

  /**
   * Resolve `[scope_inheritance, merge_strategy, tenant_overlay]` for
   * (scope, kind) — from the scope's LayerPolicy composition_rules, else
   * the inherit-by-default denylist (everything inherits from _lib except
   * the per-scope ledger + structural Kinds). 1:1 with Py
   * `get_composition_rule`.
   */
  async getCompositionRule(
    scope: string,
    kind: string,
  ): Promise<[string, string, string]> {
    const src = this._k.activeSource;
    // s-sourceport-contract-cleanup: declared capabilities, not typeof.
    if (src !== null && sourceCapabilities(src).queryPushdown && typeof src.query === "function") {
      try {
        for await (const raw of src.query(scope, "LayerPolicy", {})) {
          const spec = specOf(raw);
          if (!spec) continue;
          const rules = spec.composition_rules;
          if (rules === null || typeof rules !== "object" || Array.isArray(rules)) continue;
          const rule = (rules as Raw)[kind];
          if (rule !== null && typeof rule === "object" && !Array.isArray(rule)) {
            const r = rule as Raw;
            return [
              String(r.scope_inheritance || "disabled").toLowerCase(),
              String(r.merge_strategy || "override_full").toLowerCase(),
              String(r.tenant_overlay || "none").toLowerCase(),
            ];
          }
        }
      } catch {
        // Fail-soft — a missing scope / query error falls through to defaults.
      }
    }
    if (!DEFAULT_NON_INHERITABLE_KINDS_V1.has(kind)) {
      return ["enabled", "override_full", "field_level"];
    }
    // Non-inheritable Kinds STILL honor tenant overlay (TENANTED Canvas,
    // VoiceEpisode, Story must read tenant=X correctly).
    return ["disabled", "override_full", "field_level"];
  }

  /**
   * Resolve a doc through the composition chain (Phase 17). Returns a
   * ResolvedDocument with merged doc + full provenance. Bootstrap Kinds
   * bypass inheritance (local-only). 1:1 with Py `resolve_document`.
   */
  async resolveDocument(
    scope: string,
    kind: string,
    name: string,
    opts?: { tenant?: string | null },
  ): Promise<ResolvedDocument> {
    const k = this._k;
    const tenant = opts?.tenant ?? null;

    // ── Bootstrap Kinds — local-only ─────────────────────────────
    if (BOOTSTRAP_KINDS.has(kind)) {
      const raw = await k._granularDoc([scope, kind, name, tenant ?? ""]);
      const layer = new ResolutionLayer({
        scope,
        tenant,
        found: raw !== null,
        contributed: raw !== null,
      });
      return new ResolvedDocument({
        doc: raw,
        provenance: new ResolutionPath([layer]),
        isInherited: false,
      });
    }

    // ── Resolve composition rule ─────────────────────────────────
    const [scopeInh, mergeStrat, tenantOv] = await this.getCompositionRule(scope, kind);

    // ── Build resolution chain ───────────────────────────────────
    // Catalog scopes that contributed THIS (kind, name) — used to surface
    // multi-package conflicts after the merge (Phase 3b ch4, i-112).
    let catalogLayerScopes = new Set<string>();
    let chain: Array<[string, string | null]>;
    if (scopeInh === "disabled") {
      // Local-only: bootstrap/structural Kinds never inherit AND never
      // pick up the Catalog tier (matches today's behavior exactly).
      chain = [];
      if (tenant && tenantOv !== "none") chain.push([scope, tenant]);
      chain.push([scope, null]);
    } else {
      chain = await this.computeResolutionChain(
        scope, tenantOv !== "none" ? tenant : null,
      );
      // ── Splice the Catalog tier: Local > Catalog > Base ──────────
      // Insert the tenant's Catalog scopes IMMEDIATELY AFTER the local
      // scope's entries (the leading (scope, …) pairs) and BEFORE the
      // first parent — so the positional merge yields Local > Catalog >
      // Base while preserving mergeFieldLevel (first contributor =
      // primary). Fail-soft: a Catalog glitch must never crash a resolve.
      let catalogScopes: Array<[string, string | null]>;
      try {
        catalogScopes = await k._catalogScopes(tenant, { exclude: new Set([scope]) });
      } catch {
        catalogScopes = []; // fail-soft, never crash a resolve
      }
      if (catalogScopes.length > 0) {
        let localLen = 0;
        for (const [cs] of chain) {
          if (cs === scope) localLen += 1;
          else break;
        }
        const localPart = chain.slice(0, localLen);
        const rest = chain.slice(localLen);
        const catalogEntries: Array<[string, string | null]> =
          catalogScopes.map(([cs, ct]) => [cs, ct]);
        catalogLayerScopes = new Set(catalogEntries.map(([cs]) => cs));
        chain = [...localPart, ...catalogEntries, ...rest];
      }
    }

    // ── Query each layer (direct source reads — see PERF note in the
    // module docstring: the Py twin caches here; TS does not) ──────
    const contributions: Contribution[] = [];
    // Catalog scopes that actually held this (kind, name) — for the
    // multi-package conflict surface below.
    const catalogHits: string[] = [];
    for (const [layerScope, layerTenant] of chain) {
      const raw = await k._granularDoc([layerScope, kind, name, layerTenant ?? ""]);
      // NOTE: the Py twin registers `_layer_observers` reverse-deps here
      // (cache invalidation infra). Intentionally not ported — the TS
      // kernel has no granular cache to invalidate.
      if (raw !== null && catalogLayerScopes.has(layerScope)) {
        catalogHits.push(layerScope);
      }
      contributions.push([
        new ResolutionLayer({
          scope: layerScope,
          tenant: layerTenant,
          found: raw !== null,
        }),
        raw,
      ]);
    }

    // Surface (don't fail) when ≥2 Catalog packages provide the same
    // (kind, name): the sorted-first catalog scope wins positionally; the
    // rest are shadowed. Determinism is guaranteed by _catalogScopes' sort.
    if (catalogHits.length >= 2) {
      console.info(
        `catalog tier conflict: ${kind}/${name} provided by ${catalogHits.length} `
        + `catalog packages ${JSON.stringify(catalogHits)} for scope=${JSON.stringify(scope)} `
        + `tenant=${JSON.stringify(tenant)} — ${JSON.stringify(catalogHits[0])} wins `
        + `(sorted-first); others shadowed.`,
      );
    }

    // ── Apply merge strategy ─────────────────────────────────────
    let mergedDoc: Raw | null;
    let primary: ResolutionLayer | null;
    let contributionsByField: Record<string, string> = {};
    if (mergeStrat === "field_level") {
      [mergedDoc, primary, contributionsByField] = mergeFieldLevel(contributions);
    } else {
      [mergedDoc, primary] = mergeOverrideFull(contributions);
    }

    // ── Build provenance with contributed flag ───────────────────
    const stepsWithContributed: ResolutionLayer[] = [];
    for (const [layer, raw] of contributions) {
      const contributed = (
        (mergeStrat === "field_level" && raw !== null)
        || (primary !== null && layerEquals(layer, primary))
      );
      stepsWithContributed.push(new ResolutionLayer({
        scope: layer.scope,
        tenant: layer.tenant,
        found: layer.found,
        contributed,
        versionSha: layer.versionSha,
      }));
    }

    const provenance = new ResolutionPath(stepsWithContributed);
    const isInherited = primary !== null && primary.scope !== scope;

    return new ResolvedDocument({
      doc: mergedDoc,
      provenance,
      isInherited,
      contributionsByField,
    });
  }

  /**
   * Clone an inherited doc into `targetScope` as a local override
   * (Phase 17). Throws if the doc isn't inherited / target exists (without
   * overwrite). Clones spec + envelope atomically via `writeDocument`.
   * 1:1 with Py `personalize_document` EXCEPT bundle-entry payload cloning
   * (Py-only — see divergence #4 in the module docstring).
   */
  async personalizeDocument(
    targetScope: string,
    kind: string,
    name: string,
    opts?: { tenant?: string | null; overwrite?: boolean },
  ): Promise<ResolvedDocument> {
    const k = this._k;
    const tenant = opts?.tenant ?? null;
    const overwrite = opts?.overwrite ?? false;

    if (BOOTSTRAP_KINDS.has(kind)) {
      throw new Error(`Kind ${JSON.stringify(kind)} is bootstrap and cannot be personalized.`);
    }

    const resolved = await this.resolveDocument(targetScope, kind, name, { tenant });
    if (resolved.doc === null) {
      throw new Error(
        `${kind}/${name} not found in any scope via composition chain from ${targetScope}.`,
      );
    }
    if (!resolved.isInherited) {
      throw new Error(
        `${kind}/${name} is already local to ${targetScope} — no need to personalize.`,
      );
    }

    // Check targetScope local existence (fresh source state — no cache
    // on TS anyway; the loadOne feature-test mirrors Py's getattr guard).
    const src = k.activeSource;
    if (!overwrite && src !== null && sourceCapabilities(src).granularOne && typeof src.loadOne === "function") {
      const existing = await src.loadOne(targetScope, kind, name, { tenant });
      if (existing !== null) {
        throw new Error(
          `${kind}/${name} already exists locally in ${targetScope}. `
          + `Pass overwrite=true to replace.`,
        );
      }
    }

    const eff = resolved.provenance.effectiveLayer;
    if (eff === null) {
      throw new Error("Cannot personalize: provenance has no effective layer.");
    }

    const doc = resolved.doc as Raw;
    const clonedRaw: Raw = {
      apiVersion: doc.apiVersion ?? null,
      kind,
      metadata: { ...((doc.metadata as Raw | undefined) ?? {}), name },
      spec: { ...((doc.spec as Raw | undefined) ?? {}) },
    };
    await k.writeDocument(targetScope, kind, name, clonedRaw, { tenant });

    // Bundle-entry (binary payload) cloning is Py-only today — the TS
    // kernel has no bundle-entry write surface (divergence #4).

    // Return fresh resolution (now local).
    return await this.resolveDocument(targetScope, kind, name, { tenant });
  }
}
