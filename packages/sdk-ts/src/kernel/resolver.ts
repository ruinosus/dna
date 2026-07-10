/**
 * Composition Engine V2 — resolution types + merge utilities (TS twin).
 *
 * 1:1 parity with python/dna/kernel/resolver.py
 * (Phase 17, Story s-comp-f2-resolver / s-composition-v2-ts-twin).
 *
 * NB: This is the V2 *resolver* — distinct from `composition.ts` (which defines
 * CompositionProfile dependency wiring between Kinds). The two coexist with
 * clear naming until a future Phase 17 cleanup unifies them.
 *
 * This module defines the data shapes returned by `kernel.resolveDocument` plus
 * the pure merge utilities. The actual resolver *method* lives on the Kernel
 * class on the Python side (`Kernel.resolve_document`); porting that full
 * orchestration (parent-chain walk + observers + granular cache) is a separate,
 * larger concern. What the story names — "the resolver" (provenance + field
 * merge) — is this module.
 *
 * Wire parity: `serialize()` emits the SAME snake_case keys as Python
 * (scope/tenant/found/contributed/version_sha/effective_layer/
 * contributions_by_field/is_inherited) so an HTTP consumer cannot tell which
 * runtime produced the response.
 *
 * Resolution chain for (scope=S, tenant=T, kind=K, name=N):
 *   walk Genome.parent_scope transitively, building ordered layers:
 *     L0 = (S, T)    local + tenant overlay
 *     L1 = (S, null) local base
 *     L2 = (P, T)    parent + tenant overlay (if rule allows)
 *     L3 = (P, null) parent base
 *     ...
 *   Apply merge strategy from LayerPolicy.composition_rules[K]:
 *     - override_full → first non-null layer wins entirely
 *     - field_level   → deep-merge specs; later layers contribute individual
 *                       fields and provenance tracks which layer set each field.
 *
 * Bootstrap Kinds (Genome, LayerPolicy, KindDefinition) are NEVER inherited.
 */

// ──────────────────────────────────────────────────────────────────────
// Module-level constants — sensible defaults (V1 → V2 transition)
// ──────────────────────────────────────────────────────────────────────

/** Kinds excluded from inheritance regardless of LayerPolicy. Structural
 *  (Genome = scope identity; LayerPolicy = the policy Kind itself;
 *  KindDefinition = registered before docs parse, can't be overlaid). */
export const BOOTSTRAP_KINDS: ReadonlySet<string> = new Set([
  "Genome",
  "LayerPolicy",
  "KindDefinition",
]);

/** Scope inheritance default = DENYLIST (s-platform-inherit-by-default).
 *  When a scope has NO LayerPolicy with composition_rules, EVERY Kind defaults
 *  to scope_inheritance=enabled EXCEPT the per-scope ledger + structural Kinds
 *  below. Mirrors the kernel's `_NON_INHERITABLE_KINDS`. */
export const DEFAULT_NON_INHERITABLE_KINDS_V1: ReadonlySet<string> = new Set([
  "Story", "Issue", "Feature", "Milestone", "Roadmap",
  "Narrative", "VibeSession", "LessonLearned", "Plan",
  "Genome", "KindDefinition", "LayerPolicy",
]);

/** Display set ONLY (NOT the inheritance source of truth anymore): the
 *  composition-summary endpoint iterates this to surface per-Kind
 *  local/inherited counts in the Studio sidebar. Membership semantics live in
 *  the denylist above. */
export const DEFAULT_INHERITABLE_KINDS_V1: ReadonlySet<string> = new Set([
  "Agent",
  "LottieAsset",
  "HtmlTemplate",
  "Skill",
  "ImagePrompt",
  "Theme",
  "PromptTemplate",
  // s-automation-trio-extinction: JobType/HookType/ScheduleType foram extintos
  // e unificados no Kind Automation (o inheritable herdável).
  "Automation",
]);

/** Hard limit on parent_scope chain depth — guards against runaway loops
 *  (cycle detection runs first, but this is a belt-and-suspenders cap). */
export const MAX_RESOLUTION_DEPTH = 16;

// ──────────────────────────────────────────────────────────────────────
// Provenance + result types
// ──────────────────────────────────────────────────────────────────────

/** A raw manifest document dict (pre-`Document` parse) — the payload half
 *  of a {@link Contribution}. Twin of the Py `Raw = dict[str, Any]` alias. */
export type Raw = Record<string, unknown>;

/** One step in the resolution chain — a single (scope, tenant) pair consulted
 *  by the resolver.
 *
 *  - `found` records whether the source had ANY doc at this layer.
 *  - `contributed` flips true when this layer ACTUALLY influenced the final
 *    merged doc (override_full: only the winning layer; field_level: possibly
 *    several). */
export class ResolutionLayer {
  readonly scope: string;
  readonly tenant: string | null;
  readonly found: boolean;
  readonly contributed: boolean;
  /** Version sha or content hash if the source exposes it (best-effort). */
  readonly versionSha: string | null;

  constructor(opts: {
    scope: string;
    tenant?: string | null;
    found: boolean;
    contributed?: boolean;
    versionSha?: string | null;
  }) {
    this.scope = opts.scope;
    this.tenant = opts.tenant ?? null;
    this.found = opts.found;
    this.contributed = opts.contributed ?? false;
    this.versionSha = opts.versionSha ?? null;
  }
}

/** Ordered list of layers consulted, highest-priority-first.
 *
 *  Layer order is:
 *    [local+tenant, local+base, parent+tenant, parent+base,
 *     grandparent+tenant, grandparent+base, ...]
 *  The HIGHEST priority layer is first — local-tenant beats everything else. */
export class ResolutionPath {
  steps: ResolutionLayer[];

  constructor(steps: ResolutionLayer[] = []) {
    this.steps = steps;
  }

  /** The single layer that became the doc's primary origin. For override_full
   *  this is the layer whose doc was returned wholesale; for field_level it is
   *  the highest-priority layer that contributed metadata/envelope (semantic
   *  primary owner). */
  get effectiveLayer(): ResolutionLayer | null {
    for (const s of this.steps) {
      if (s.found) return s;
    }
    return null;
  }

  /** JSON-friendly serialization for HTTP responses (snake_case = Python). */
  serialize(): Record<string, unknown> {
    const eff = this.effectiveLayer;
    return {
      steps: this.steps.map((s) => ({
        scope: s.scope,
        tenant: s.tenant,
        found: s.found,
        contributed: s.contributed,
        version_sha: s.versionSha,
      })),
      effective_layer: eff ? { scope: eff.scope, tenant: eff.tenant } : null,
    };
  }
}

/** Result of `kernel.resolveDocument` — the doc plus full provenance.
 *
 *  Studio renders banner/badge directly from `provenance` + `isInherited` —
 *  no client-side detection logic needed. */
export class ResolvedDocument {
  /** The merged document (or null if not found in any layer). */
  doc: Raw | null;
  /** Full ordered resolution path. Includes layers consulted but not
   *  contributing. */
  provenance: ResolutionPath;
  /** True when `effectiveLayer.scope != requestedScope`. Convenience derived
   *  from provenance; Studio uses this for badge/banner toggle. */
  isInherited: boolean;
  /** Field-path → scope name. Populated when merge_strategy=field_level. Lets
   *  the Detail page show `spec.persona ← _lib` annotations. */
  contributionsByField: Record<string, string>;

  constructor(opts: {
    doc: Raw | null;
    provenance: ResolutionPath;
    isInherited: boolean;
    contributionsByField?: Record<string, string>;
  }) {
    this.doc = opts.doc;
    this.provenance = opts.provenance;
    this.isInherited = opts.isInherited;
    this.contributionsByField = opts.contributionsByField ?? {};
  }

  serialize(): Record<string, unknown> {
    return {
      doc: this.doc,
      provenance: this.provenance.serialize(),
      is_inherited: this.isInherited,
      contributions_by_field: this.contributionsByField,
    };
  }
}

// ──────────────────────────────────────────────────────────────────────
// Merge strategies — pure functions for testability
// ──────────────────────────────────────────────────────────────────────

/** A (layer, raw-doc-or-null) pair — one contribution, highest-priority-first. */
export type Contribution = [ResolutionLayer, Raw | null];

/** First non-null contribution wins entirely.
 *
 *  Used for assetic Kinds (LottieAsset, ImagePrompt) where partial override
 *  makes no sense (binary payload is atomic).
 *
 *  Input: contributions highest-priority-first.
 *  Output: [winningRawDoc, winningLayer] or [null, null] if all miss. */
export function mergeOverrideFull(
  contributions: Contribution[],
): [Raw | null, ResolutionLayer | null] {
  for (const [layer, raw] of contributions) {
    if (raw !== null && raw !== undefined) return [raw, layer];
  }
  return [null, null];
}

/** Deep-merge `spec` dicts. Higher-priority layers shadow lower per-field.
 *  Returns [mergedDoc, primaryOriginLayer, fieldsByOrigin].
 *
 *  Algorithm:
 *    - First pass: find the PRIMARY layer (highest-priority hit). Its metadata
 *      + envelope (apiVersion, kind) carry over wholesale.
 *    - Second pass: iterate contributions LOWEST → HIGHEST priority, overwriting
 *      spec keys in a fresh merged dict. After the loop the highest-priority
 *      layer's values win per-field.
 *    - Track which layer each FINAL spec field came from so the UI can render
 *      `spec.persona ← _lib` annotations.
 *
 *  Edge cases:
 *    - All-null contributions → [null, null, {}].
 *    - Single hit → equivalent to override_full.
 *    - Spec missing or non-object → that layer skipped silently. */
export function mergeFieldLevel(
  contributions: Contribution[],
): [Raw | null, ResolutionLayer | null, Record<string, string>] {
  // First pass — find primary (highest priority hit).
  let primary: ResolutionLayer | null = null;
  let primaryRaw: Raw | null = null;
  for (const [layer, raw] of contributions) {
    if (raw !== null && raw !== undefined) {
      primary = layer;
      primaryRaw = raw;
      break;
    }
  }

  if (primary === null || primaryRaw === null) return [null, null, {}];

  // Second pass — merge specs LOWEST to HIGHEST so highest wins per-key.
  const mergedSpec: Raw = {};
  const fieldsByOrigin: Record<string, string> = {};
  for (let i = contributions.length - 1; i >= 0; i--) {
    const [layer, raw] = contributions[i]!;
    if (raw === null || raw === undefined) continue;
    const spec = (raw as Raw).spec;
    if (spec === null || spec === undefined || typeof spec !== "object" || Array.isArray(spec)) {
      continue;
    }
    for (const [k, v] of Object.entries(spec as Raw)) {
      mergedSpec[k] = v;
      fieldsByOrigin[`spec.${k}`] = layer.scope;
    }
  }

  const final: Raw = {
    apiVersion: (primaryRaw as Raw).apiVersion ?? null,
    kind: (primaryRaw as Raw).kind ?? null,
    metadata: (primaryRaw as Raw).metadata ?? {},
    spec: mergedSpec,
  };
  return [final, primary, fieldsByOrigin];
}
