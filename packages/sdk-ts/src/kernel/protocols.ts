/**
 * v3 Kernel Protocols — the 5 ports + shared types.
 *
 * Parity with Python dna.kernel.protocols is SURFACE-TRACKED, not
 * assumed (s-dna-port-surface-parity): every port's member list — and every
 * INTENTIONAL asymmetry, with its justification — lives in the shared
 * fixture `tests/parity-fixtures/port-surface-parity.json`, enforced by
 * `tests/port-surface-parity.test.ts` (via the keyof-bound PORT_SURFACE
 * manifest in `./port-surface.ts`) and by the Python twin
 * `packages/sdk-py/tests/test_port_surface_parity.py` (real Protocol
 * introspection). Adding/removing a member on either side without updating
 * the fixture turns the suites red.
 */

import type { BundleHandle } from "./bundle-handle.js";
import type { Document } from "./document.js";
import type { PreviewBlock } from "./preview.js";
import type { HookContext, HookRegistry, VetoHandler } from "./hooks.js";
import type { CompositionProfile } from "./composition-resolver.js";

export type { BundleHandle };

// ---------------------------------------------------------------------------
// Layer policy
// ---------------------------------------------------------------------------

export const LayerPolicy = {
  OPEN: "open",
  RESTRICTED: "restricted",
  LOCKED: "locked",
} as const;

export type LayerPolicy = (typeof LayerPolicy)[keyof typeof LayerPolicy];

// ---------------------------------------------------------------------------
// Tenant scope (Kubernetes-style: each KindPort declares its scope)
// ---------------------------------------------------------------------------

/**
 * Whether a Kind's documents belong to a tenant or are globally shared.
 *
 * Mirrors the Kubernetes CRD `scope: Namespaced | Cluster` model. Each
 * KindPort declares its scope; the kernel enforces it on every write.
 *
 * - `TENANTED` (default): documents belong to one tenant. Writing
 *   requires a tenant arg; reading is filtered by tenant.
 *   Agent, EvalCase, EvalRun, AssessmentRun, Finding, etc.
 * - `GLOBAL`: documents are shared across all tenants. Writes must
 *   not pass a tenant; reads ignore the bound tenant.
 *   Doc, KindDefinition, Module-level configs, etc.
 */
export const TenantScope = {
  TENANTED: "tenanted",
  GLOBAL: "global",
} as const;

export type TenantScope = (typeof TenantScope)[keyof typeof TenantScope];

/** Reserved tenant slugs — never accepted as user input. */
export const RESERVED_TENANT_SLUGS = new Set<string>([
  "_global",
  "_legacy",
  "_system",
  "",
]);

/**
 * Raised when a TENANTED kind is written without a tenant arg.
 *
 * Bind a tenant on construction (`new Kernel({ tenant: X })`) or
 * per-call (`kernel.withTenant(X).writeDocument(...)`).
 */
export class TenantRequired extends Error {
  constructor(message?: string) {
    super(message);
    this.name = "TenantRequired";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Raised when a GLOBAL kind is written with a tenant arg.
 *
 * Global kinds (Doc, KindDefinition, ...) are shared across
 * tenants. Writes must explicitly omit `tenant`.
 */
export class TenantNotAllowed extends Error {
  constructor(message?: string) {
    super(message);
    this.name = "TenantNotAllowed";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** Raised when a tenant slug is reserved or empty. */
export class InvalidTenantSlug extends Error {
  constructor(message?: string) {
    super(message);
    this.name = "InvalidTenantSlug";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Validate a tenant slug.
 *
 * Phase 1 only checks the reserved set + non-empty/length. Character
 * rules (DNS-label, lowercase) are NOT enforced at the kernel boundary
 * so existing tests/data using uppercase ("T1", "Acme") keep working.
 * Path-traversal safety lives in the adapter.
 *
 * Phase 2 may tighten to k8s namespace rules (`[a-z0-9-]{1,63}`) once
 * the migration is complete.
 */
export function validateTenantSlug(tenant: string | null | undefined): void {
  if (tenant === null || tenant === undefined) return;
  if (RESERVED_TENANT_SLUGS.has(tenant)) {
    const reserved = Array.from(RESERVED_TENANT_SLUGS).sort();
    throw new InvalidTenantSlug(
      `tenant slug ${JSON.stringify(tenant)} is reserved (one of ${JSON.stringify(reserved)})`,
    );
  }
  if (tenant.length < 1 || tenant.length > 253) {
    throw new InvalidTenantSlug(
      `tenant slug ${JSON.stringify(tenant)} must be 1-253 chars (got ${tenant.length})`,
    );
  }
}

/**
 * Raised when a write to a layer violates the declared LayerPolicy in
 * `Module.spec.layers`. Thrown by `Kernel.writeDocument` before the adapter
 * is touched. Harness endpoints translate to HTTP 403.
 */
export class LayerPolicyViolationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "LayerPolicyViolationError";
    Object.setPrototypeOf(this, LayerPolicyViolationError.prototype);
  }
}

// ---------------------------------------------------------------------------
// Composition result
// ---------------------------------------------------------------------------

export interface CompositionResult {
  resolved: string[];
  missing: string[];
  warnings: string[];
  /**
   * Refs whose target Kind is plane="record" (two-planes F2.5, spec D6).
   * Records are excluded from the MI materialization on the Py side, so
   * the engine can't check them against the doc index — they resolve
   * lazily via the kernel record plane at read time. Deferred refs are
   * NOT missing: `isCompositionValid` ignores them.
   */
  deferred: string[];
}

export function isCompositionValid(result: CompositionResult): boolean {
  return result.missing.length === 0;
}

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

export interface CacheItem {
  name: string;
  kind: string;
  contentPath: string;
  raw?: Record<string, unknown>;
}

export interface ResolvedItem {
  name: string;
  kind: string;
  sourcePath: string;
}

// ---------------------------------------------------------------------------
// Record-plane query surface — two-planes F2 (spec D2).
//
// 1:1 port of the Python pure helpers in dna.kernel.protocols
// (_resolve_field_path / _match_filter / _apply_order_by, POST-i-121) plus
// the in-memory query/count core the FilesystemSource delegates to. The
// operators are the same set the Py PG adapter pushes down (_PG_OP_MAP)
// plus `in`. Exported so the shared parity fixture
// (tests/fixtures/f2-parity.json) can drive both SDKs over the exact same
// code path.
// ---------------------------------------------------------------------------

/**
 * Filter shape — dict of dotted `field_path` → expected value.
 *
 *   { "status": "in-progress" }                  // shorthand equality
 *   { "status": { "in": ["todo", "done"] } }     // operator form
 *   { "spec.priority": { "gte": 2 } }
 *
 * Unprefixed paths resolve under `spec.`; `name` is a reserved short for
 * `metadata.name`. Implicit AND across keys; no OR (issue two queries).
 */
export type QueryFilter = Record<string, unknown>;

/**
 * Ordering — list of field paths optionally prefixed with `-` for
 * descending. Applied in declaration order. `null`/missing values sort
 * LAST regardless of direction (parity with PG `DESC NULLS LAST`; the Py
 * side was fixed in i-121 — TS is born correct).
 */
export type QueryOrder = string[];

/** Shape returned by `count()` — groups ordered by count DESC, then key
 *  ASC with `null` last. `groups` is `null` when no `groupBy` was asked. */
export interface CountResult {
  total: number;
  groups: Array<{ key: unknown; count: number }> | null;
}

/**
 * Raised when a query filter / order_by is malformed in a way the
 * adapter can detect statically (unknown operator, …). 1:1 with the Py
 * `QueryError`.
 */
export class QueryError extends Error {
  constructor(message?: string) {
    super(message);
    this.name = "QueryError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** Operators recognized by `matchFilter` — the Py `_PG_OP_MAP` set + `in`. */
export const QUERY_OPS: ReadonlySet<string> = new Set([
  "eq", "in", "like", "gt", "gte", "lt", "lte", "neq",
]);

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/**
 * Deep structural equality for filter matching. Py uses `==` which
 * deep-compares dicts/lists; mirror that. Best-effort divergence: Py
 * `1 == 1.0 == True` numeric cross-type equality is NOT replicated for
 * booleans (JS `1 !== true`) — filters should use the field's real type.
 */
function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((v, i) => deepEqual(v, b[i]));
  }
  if (isPlainObject(a) && isPlainObject(b)) {
    const ka = Object.keys(a);
    const kb = Object.keys(b);
    return (
      ka.length === kb.length
      && ka.every((k) => k in b && deepEqual(a[k], b[k]))
    );
  }
  return false;
}

/**
 * Walk a dotted `fieldPath` through `doc`. Unprefixed paths resolve under
 * `spec.`; `name` is a reserved short for `metadata.name`. Returns `null`
 * when any segment is missing (never `undefined` — parity with Py `None`).
 */
export function resolveFieldPath(
  doc: Record<string, unknown>,
  path: string,
): unknown {
  if (path === "name") {
    const meta = doc.metadata;
    return isPlainObject(meta) ? (meta.name ?? null) : null;
  }
  if (path === "kind") return doc.kind ?? null;
  if (path === "apiVersion") return doc.apiVersion ?? null;
  const segments =
    path.startsWith("metadata.") || path.startsWith("spec.") || path.startsWith("apiVersion.")
      ? path.split(".")
      : ["spec", ...path.split(".")];
  let cur: unknown = doc;
  for (const seg of segments) {
    if (!isPlainObject(cur)) return null;
    cur = cur[seg];
    if (cur === null || cur === undefined) return null;
  }
  return cur ?? null;
}

/**
 * Evaluate a `QueryFilter` against a single doc. Unknown operators throw
 * `QueryError` so callers can debug instead of silently matching. 1:1
 * port of the Py `_match_filter` (only single-key dicts enter the
 * operator branch; anything else is shorthand equality).
 */
export function matchFilter(
  doc: Record<string, unknown>,
  filter: QueryFilter,
): boolean {
  for (const [path, expected] of Object.entries(filter)) {
    const actual = resolveFieldPath(doc, path);
    if (isPlainObject(expected) && Object.keys(expected).length === 1) {
      const [op, val] = Object.entries(expected)[0] as [string, unknown];
      if (!QUERY_OPS.has(op)) {
        throw new QueryError(
          `unknown query operator ${JSON.stringify(op)} on field `
          + `${JSON.stringify(path)}; valid: ${[...QUERY_OPS].sort().join(", ")}`,
        );
      }
      if (op === "eq" && !deepEqual(actual, val)) return false;
      if (op === "neq" && deepEqual(actual, val)) return false;
      if (op === "in") {
        // Py: `actual not in (val or ())` — null/empty list matches nothing.
        // DIVERGENCE vs Py: Py `actual in <str>` does substring membership on
        // a malformed string operand; TS coerces non-array to [] (matches nothing).
        const candidates = Array.isArray(val) ? val : [];
        if (!candidates.some((v) => deepEqual(actual, v))) return false;
      }
      if (op === "like") {
        if (actual === null || typeof val !== "string") return false;
        // SQL LIKE: % = any, _ = single char. Tokenize so ONLY literals
        // are regex-escaped (same approach as the Py fallback).
        const parts: string[] = [];
        for (const ch of val) {
          if (ch === "%") parts.push(".*");
          else if (ch === "_") parts.push(".");
          else parts.push(ch.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
        }
        if (!new RegExp(`^${parts.join("")}$`).test(String(actual))) return false;
      }
      // Range ops: null never matches (Py: `actual is not None and …`).
      // DIVERGENCE vs Py: Py raises TypeError on cross-type range compares;
      // TS coerces (NaN) and silently excludes the row — don't rely on
      // cross-type range filters.
      /* eslint-disable @typescript-eslint/no-explicit-any */
      if (op === "gt" && !(actual !== null && (actual as any) > (val as any))) return false;
      if (op === "gte" && !(actual !== null && (actual as any) >= (val as any))) return false;
      if (op === "lt" && !(actual !== null && (actual as any) < (val as any))) return false;
      if (op === "lte" && !(actual !== null && (actual as any) <= (val as any))) return false;
      /* eslint-enable @typescript-eslint/no-explicit-any */
    } else if (!deepEqual(actual, expected)) {
      // Shorthand: {"status": "in-progress"} == {"status": {"eq": ...}}
      return false;
    }
  }
  return true;
}

/**
 * Stable sort `rows` by each `orderBy` field, last-first to achieve the
 * desired primary/secondary precedence. Prefixed `-` means descending.
 * `null` values sort LAST regardless of direction: the None-flag is
 * `(v === null) !== descending` — immune to the reversed comparator
 * (i-121: parity with PG `DESC NULLS LAST`; a plain `v === null` flag
 * would flip under reversal and shove nulls to the FRONT in DESC).
 *
 * Mixed-type values (number + string across rows on the same field) fall
 * back to stringified compare to mirror the Py TypeError fallback. Does
 * not mutate the input. Best-effort like the Py protocol-default —
 * adapters with native push-down use the backend's type semantics.
 */
export function applyOrderBy(
  rows: Record<string, unknown>[],
  orderBy: QueryOrder,
): Record<string, unknown>[] {
  let out = rows.slice();
  for (const spec of [...orderBy].reverse()) {
    const descending = spec.startsWith("-");
    const path = descending ? spec.slice(1) : spec;

    const decorated = out.map((row) => {
      const v = resolveFieldPath(row, path);
      return { row, v, flag: (v === null) !== descending };
    });
    // Py first pass keeps int/float (and bool, a Py int subtype) numeric
    // and stringifies the rest; a mixed numeric/string field raises
    // TypeError there → stringify-everything fallback. Detect the mix
    // upfront instead of try/catch.
    const isNumeric = (v: unknown): boolean =>
      typeof v === "number" || typeof v === "boolean";
    const nonNull = decorated.filter((d) => d.v !== null);
    const mixed =
      nonNull.some((d) => isNumeric(d.v)) && nonNull.some((d) => !isNumeric(d.v));
    const sortable = (v: unknown): number | string => {
      if (v === null) return "";
      if (mixed) return v ? String(v) : ""; // Py fallback: str(v or "")
      return isNumeric(v) ? Number(v) : String(v);
    };
    const keyed = decorated.map((d) => ({ ...d, key: sortable(d.v) }));
    const cmp = (
      a: { flag: boolean; key: number | string },
      b: { flag: boolean; key: number | string },
    ): number => {
      if (a.flag !== b.flag) return a.flag ? 1 : -1;
      if (typeof a.key === "number" && typeof b.key === "number") {
        return a.key - b.key;
      }
      const sa = String(a.key);
      const sb = String(b.key);
      return sa < sb ? -1 : sa > sb ? 1 : 0;
    };
    // JS sort is stable; the negated comparator under `descending`
    // preserves original order for ties — same as Py `reverse=True`.
    keyed.sort((a, b) => (descending ? -cmp(a, b) : cmp(a, b)));
    out = keyed.map((d) => d.row);
  }
  return out;
}

/** Options accepted by the query half of the record-plane port (TS).
 *  NOTE: no `projection` on the TS surface — Py-only for now. */
export interface SourceQueryOpts {
  filter?: QueryFilter;
  limit?: number;
  offset?: number;
  orderBy?: QueryOrder;
  tenant?: string;
}

/** Options accepted by the count half of the record-plane port (TS). */
export interface SourceCountOpts {
  filter?: QueryFilter;
  groupBy?: string;
  tenant?: string;
}

/**
 * In-memory query core — mirror of the Py `SourcePort.query`
 * protocol-default minus the IO: kind filter first (cheap), then
 * `matchFilter`, then `applyOrderBy`, then limit/offset paging.
 * `FilesystemSource.query` is `loadAll` + this; the shared parity
 * fixture drives it directly.
 */
export function queryDocs(
  docs: Record<string, unknown>[],
  kind: string,
  opts: Omit<SourceQueryOpts, "tenant"> = {},
): Record<string, unknown>[] {
  let kindDocs = docs.filter((d) => d.kind === kind);
  if (opts.filter && Object.keys(opts.filter).length > 0) {
    kindDocs = kindDocs.filter((d) => matchFilter(d, opts.filter!));
  }
  if (opts.orderBy && opts.orderBy.length > 0) {
    kindDocs = applyOrderBy(kindDocs, opts.orderBy);
  }
  const start = opts.offset ?? 0;
  const end = opts.limit != null ? start + opts.limit : undefined;
  return kindDocs.slice(start, end);
}

/**
 * In-memory count core — mirror of the Py `SourcePort.count`
 * protocol-default: total of docs matching the filter, optionally
 * grouped by a field path. Groups ordered by count DESC, then key ASC
 * with `null` LAST (matches PG `ORDER BY count DESC, key ASC NULLS
 * LAST` and the spirit of i-121).
 */
export function countDocs(
  docs: Record<string, unknown>[],
  kind: string,
  opts: Omit<SourceCountOpts, "tenant"> = {},
): CountResult {
  const rows = queryDocs(docs, kind, { filter: opts.filter });
  const total = rows.length;
  let groups: CountResult["groups"] = null;
  if (opts.groupBy != null) {
    const counter = new Map<unknown, number>();
    for (const row of rows) {
      const v = resolveFieldPath(row, opts.groupBy);
      // DIVERGENCE vs Py (unreachable with primitive keys, pinned for record):
      // Py str(True)="True" / str(dict)="{'k': 1}"; JS String(true)="true" /
      // String({})="[object Object]". Complex group keys should be avoided.
      const key =
        v === null || ["string", "number", "boolean"].includes(typeof v)
          ? v
          : String(v);
      counter.set(key, (counter.get(key) ?? 0) + 1);
    }
    groups = [...counter.entries()]
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
 * Two-planes F2 (spec D2): semantic search over record docs. The PG
 * adapter (pgvector+RRF) lives in harness-shared (Py) and registers
 * itself on the kernel at app boot — the kernel core gains NO
 * LLM/embedding deps. Without a provider, `kernel.search()` degrades to
 * an in-memory lexical scan (explicit `degraded: true` — never fake
 * similarity). 1:1 with the Py `RecordSearchProvider` Protocol.
 *
 * Hit shape: the guaranteed intersection across providers and the
 * lexical fallback is `{scope, kind, name, score}` — richer providers
 * may carry extra fields that callers must treat as optional.
 */
export interface RecordSearchProvider {
  search(opts: {
    scope: string;
    queryText: string;
    kind?: string | null;
    k?: number;
    tenant?: string;
  }): Promise<Array<Record<string, unknown>>>;
}

/**
 * @deprecated s-sourceport-contract-cleanup — the record-plane contract was
 * UNIFIED into `WritableSourcePort` (+ the `query`/`count` read half declared
 * on `SourcePort`). This alias preserves the old name for existing importers;
 * its shape is exactly the four ops the F2 D2 port formalized:
 * `saveDocument`/`deleteDocument` (write half) + non-optional `query`/`count`
 * (read half). The fifth record-plane operation, `search`, still lives on
 * `RecordSearchProvider` registered on the kernel. New code should reference
 * `WritableSourcePort` / `SourcePort` directly.
 */
export type RecordStorePort =
  Pick<WritableSourcePort, "saveDocument" | "deleteDocument"> &
  Required<Pick<SourcePort, "query" | "count">>;

// ---------------------------------------------------------------------------
// Error hierarchy
// ---------------------------------------------------------------------------

export class ResolveError extends Error {
  constructor(message?: string) {
    super(message);
    this.name = "ResolveError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class ResolveNotFoundError extends ResolveError {
  constructor(message?: string) {
    super(message);
    this.name = "ResolveNotFoundError";
  }
}

export class ResolveAuthError extends ResolveError {
  constructor(message?: string) {
    super(message);
    this.name = "ResolveAuthError";
  }
}

export class ResolveNetworkError extends ResolveError {
  constructor(message?: string) {
    super(message);
    this.name = "ResolveNetworkError";
  }
}

// ---------------------------------------------------------------------------
// Storage types
// ---------------------------------------------------------------------------

export type StoragePattern = "bundle" | "yaml" | "root" | "standalone";
export type BodyMode = "text" | "list" | "sections";

export interface StorageDescriptor {
  container: string;
  pattern: StoragePattern;
  marker?: string;
  bodyAs?: BodyMode;
  bodyField?: string;
  bodyParser?: (body: string) => Record<string, unknown>;
}

export const SD = {
  bundle(container: string, marker: string, bodyAs: BodyMode = "text", bodyField = "instruction"): StorageDescriptor {
    return { container, pattern: "bundle", marker, bodyAs, bodyField };
  },
  yaml(container: string): StorageDescriptor {
    return { container, pattern: "yaml" };
  },
  root(filename = "manifest.yaml"): StorageDescriptor {
    return { container: "", pattern: "root", marker: filename };
  },
  standalone(filename: string, bodyAs: BodyMode = "text", bodyField = "content"): StorageDescriptor {
    return { container: "", pattern: "standalone", marker: filename, bodyAs, bodyField };
  },
};

export function defaultVisibleInBackend(
  storage: StorageDescriptor | null | undefined,
): boolean {
  if (!storage) return false;
  if (storage.pattern === "bundle" || storage.pattern === "standalone") return true;
  return false;
}

export function resolveVisibleInBackend(kp: KindPort): boolean {
  // Duck-typing on KindPort — third-party extensions may not extend a base
  // class, so we read the optional field via `any` rather than extend the
  // protocol with a required property.
  const explicit = (kp as any).visibleInBackend;
  if (explicit !== undefined && explicit !== null) return Boolean(explicit);
  return defaultVisibleInBackend(kp.storage ?? null);
}

// ---------------------------------------------------------------------------
// Port interfaces
// ---------------------------------------------------------------------------

/** WHERE — load documents from storage.
 *
 * v1.0 async refactor: read methods return `Promise<...>` so adapters
 * with non-local backends (Postgres, HTTP, S3) can implement them
 * naturally. Filesystem adapter wraps sync impls in `Promise.resolve`
 * for back-compat.
 */
export interface SourcePort {
  readonly supportsReaders: boolean;
  /**
   * Phase 16 — return the docs the kernel needs registered/parsed
   * BEFORE ``loadAll`` fires (Genome + KindDefinition + LayerPolicy).
   * Adapters that can filter cheaply (SQL ``WHERE kind IN (...)``)
   * SHOULD do so. Filesystem adapters MAY return a superset.
   *
   * Tenant semantics: when ``opts.tenant`` is set, the tenant-published
   * Genome shadows the platform Genome (Phase 9 multi-tenant
   * publishing). KindDefinition + LayerPolicy stay platform-only
   * (non-overlayable per Phase 16).
   *
   * 1:1 parity with Python ``SourcePort.load_bootstrap_docs``.
   */
  loadBootstrapDocs(
    scope: string,
    opts?: { tenant?: string },
  ): Promise<Record<string, unknown>[]>;
  loadAll(scope: string, readers?: ReaderPort[]): Promise<Record<string, unknown>[]>;
  resolveRef(scope: string, ref: string): Promise<string>;
  loadLayer(
    scope: string,
    layerId: string,
    layerValue: string,
    readers?: ReaderPort[],
  ): Promise<Record<string, unknown>[]>;

  /**
   * Release adapter-held resources (connection pools, file handles, …).
   * Mirror of the Py `SourcePort.close` (a SOURCE_PORT_CORE_MEMBERS entry
   * behind the Py boot gate). OPTIONAL on the TS interface — the kernel
   * treats a missing `close` as a no-op: `FilesystemSource` implements a
   * documented no-op (nothing to release), `PostgresSource` ends its
   * owned pool.
   */
  close?(): Promise<void>;

  /**
   * OPTIONAL L1 granular access — `[kind, name]` refs of every doc in
   * the scope, metadata only (no bundle entries, no parse). Mirror of
   * the Py `SourcePort.list_doc_refs`. `opts.kind` filters; tenant is
   * the union of base + overlay with the overlay shadowing base.
   * Declared via `SourceCapabilities.granularList`
   * (s-dna-port-surface-parity closed this TS gap).
   */
  listDocRefs?(scope: string, opts?: {
    kind?: string | null; tenant?: string | null;
  }): Promise<Array<[string, string]>>;

  /**
   * Two-planes F2 — OPTIONAL record-plane reads. The Kernel consults the
   * declared capabilities (`sourceCapabilities(src).queryPushdown`,
   * s-sourceport-contract-cleanup) and raises a clear capability error
   * otherwise. `FilesystemSource` implements both over `loadAll` + the
   * pure helpers (`queryDocs`/`countDocs`); PG TS gets no push-down this
   * phase (Py-only).
   */
  query?(
    scope: string, kind: string, opts?: SourceQueryOpts,
  ): AsyncIterable<Record<string, unknown>>;
  count?(
    scope: string, kind: string, opts?: SourceCountOpts,
  ): Promise<CountResult>;

  /**
   * OPTIONAL L1 granular access — one raw doc for (scope, kind, name),
   * tenant overlay shadowing base (mirror of the Py `SourcePort.load_one`).
   * The Kernel consults `sourceCapabilities(src).granularOne`
   * (s-sourceport-contract-cleanup) and falls back to `loadAll` + find
   * (base layer only) when absent — same as the Python
   * `_granular_doc_cached` legacy-adapter fallback.
   */
  loadOne?(scope: string, kind: string, name: string, opts?: {
    readers?: ReaderPort[]; tenant?: string | null;
  }): Promise<Record<string, unknown> | null>;

  /**
   * OPTIONAL explicit capability declaration (s-sourceport-contract-cleanup)
   * — a literal `SourceCapabilities` from `kernel/capabilities.ts`. When
   * absent, `sourceCapabilities()` derives structurally (deprecated path).
   * Optional so existing third-party implementers stay source-compatible.
   */
  capabilities?(): import("./capabilities.js").SourceCapabilities;
}

/**
 * Phase 16 — Kinds the kernel needs registered/parsed BEFORE
 * ``loadAll`` fires. Order is meaningful: KindDefinition first
 * (custom Kinds need to be registered before parsing other docs),
 * LayerPolicy next (kernel reads at write-time), Genome last
 * (root identity).
 */
export const BOOTSTRAP_KIND_NAMES = ["KindDefinition", "LayerPolicy", "Genome"] as const;

/**
 * Phase 16 helper — return the Genome doc for ``scope`` (or ``null``
 * if missing). Pulls bootstrap docs and filters for the Genome Kind.
 * Tenant-aware: when ``opts.tenant`` is set, the underlying adapter
 * applies tenant-overlay routing (tenant-published Genome shadows
 * platform).
 *
 * 1:1 parity with Python ``package_doc_for_scope``.
 */
export async function packageDocForScope(
  source: SourcePort,
  scope: string,
  opts?: { tenant?: string },
): Promise<Record<string, unknown> | null> {
  const bootstrap = await source.loadBootstrapDocs(scope, opts);
  for (const d of bootstrap) {
    if (d.kind === "Genome") return d;
  }
  return null;
}

/** WHERE — store/retrieve installed deps.
 *
 * v1.0: fully async. All four methods may do filesystem / network IO
 * (FilesystemCache uses fs/promises; Redis/HTTP caches are inherently
 * async). Hot path concerns about prompt-building are addressed by
 * caching results in-memory at higher layers, not by sync IO. */
export interface CachePort {
  has(scope: string, key: string): Promise<boolean>;
  store(scope: string, key: string, items: CacheItem[]): Promise<void>;
  loadKey(scope: string, key: string, readers?: ReaderPort[]): Promise<Record<string, unknown>[]>;
  loadAll(scope: string, readers?: ReaderPort[]): Promise<Record<string, unknown>[]>;
}

/** FROM — fetch external deps. v1.0: async (network IO is inherently
 * async; sync HTTP would block the event loop). */
export interface ResolverPort {
  resolve(uri: string, dep: Record<string, unknown>): Promise<ResolvedItem[]>;
  cacheKey(uri: string): string;
}

/** Reads a bundle directory and produces a raw dict.
 *
 * v1.0 BundleHandle migration: signatures take a `BundleHandle`
 * instead of a filesystem path string, so adapters with non-FS
 * backends (Postgres, in-memory) can rehydrate bundles uniformly.
 *
 * Methods are async because backends may need to fetch entries
 * from a network/database. Filesystem readers can return
 * `Promise.resolve(...)` if their existing impl is sync.
 */
export interface ReaderPort {
  detect(bundle: BundleHandle): boolean | Promise<boolean>;
  read(bundle: BundleHandle): Record<string, unknown> | Promise<Record<string, unknown>>;

  /** Container this Reader's Kind is rooted at (e.g. `"skills"`), or
   *  undefined for unscoped readers (tried as fallback in every
   *  container). Lets the scanner route bundles to the right Reader
   *  without trying every reader's `detect()` on every subdir — H3
   *  container-aware routing. Formal port member since
   *  s-dna-rw-roundtrip-suite (the scanner previously duck-typed it);
   *  Python twin: `ReaderPort._owner_container` (default None). */
  readonly _ownerContainer?: string;
}

export interface SerializedFile {
  relativePath: string;
  /** Text content (UTF-8). Mutually exclusive with `contentBytes`. */
  content?: string;
  /** Binary content. Set when the entry is a non-text payload (PNG,
   * audio, etc). Mutually exclusive with `content`. Introduced in L3
   * (s-writer-binary-entries 2026-05-25) for parity with Python. */
  contentBytes?: Uint8Array;
}

export interface SerializedDocument {
  files: SerializedFile[];
}

export interface WritableSourcePort extends SourcePort {
  /**
   * Persist a raw document. Adapters decide their own serialization
   * strategy (filesystem writes bundles, HTTP adapters POST raw JSON,
   * DB adapters insert rows). Returns an opaque version id; adapters
   * without real versioning return "1".
   */
  saveDocument(
    scope: string, kind: string, name: string,
    raw: Record<string, unknown>,
    options?: {
      author?: string;
      tenant?: string | null;
      layer?: [string, string];
    },
  ): Promise<string>;

  /**
   * Delete a document. Adapters handle the mechanics (rm -rf for
   * bundle filesystems, DELETE for HTTP, DELETE FROM for SQL, etc.).
   */
  deleteDocument(
    scope: string, kind: string, name: string,
    options?: {
      author?: string;
      tenant?: string | null;
      layer?: [string, string];
    },
  ): Promise<void>;

  /**
   * Optional version history. Stub adapters return []; real adapters
   * (Postgres, etc.) return { id: string }[] newest first.
   */
  listVersions?(
    scope: string, kind: string, name: string,
  ): Promise<Array<{ id: string }>>;

  /**
   * Optional single-version fetch (the `Versionable` capability;
   * `PostgresSource` implements it). Mirror of the Py
   * `WritableSourcePort.get_version`.
   */
  getVersion?(
    scope: string, kind: string, name: string, versionId: string,
  ): Promise<Record<string, unknown>>;

  /**
   * Optional draft→published promotion. Mirror of the Py
   * `WritableSourcePort.publish`. The TS PG adapter is a documented
   * single-step no-op (writes go live immediately; no draft state) —
   * adapters with a real draft store return the published version id.
   * The Py-only `save_manifest` / `load_drafts` / `list_scopes` half is
   * a JUSTIFIED asymmetry — see
   * tests/parity-fixtures/port-surface-parity.json.
   */
  publish?(scope: string, kind: string, name: string): Promise<string>;
}

/** Writes a raw dict back to a bundle directory. Inverse of ReaderPort.
 *
 * v1.0 BundleHandle migration: write signature takes BundleHandle
 * (was: filesystem path string). Adapters provide the right handle
 * for their backend; the writer's job is purely to format files into
 * `bundle.writeText/writeBytes` calls.
 *
 * s-dna-rw-roundtrip-suite: `serialize` is REQUIRED — part of the
 * contract (it was load-bearing but optional: `kernel.serializeDocument`
 * consumed it behind a presence check, so a conforming writer could
 * silently miss it and only fail at emission time). `write` and
 * `serialize` must stay COHERENT: `write(bundle, raw)` must produce
 * exactly the entries `serialize(raw)` returns. The round-trip
 * conformance suite enforces this for every registered pair.
 * Python twin: `WriterPort.serialize` returning
 * `[{relativePath, content | content_bytes}]`.
 */
export interface WriterPort {
  canWrite(raw: Record<string, unknown>): boolean;
  write(bundle: BundleHandle, raw: Record<string, unknown>): void | Promise<void>;
  serialize(raw: Record<string, unknown>): SerializedFile[];
}

/** WHO — identity + composition role. */
export interface KindPort {
  readonly apiVersion: string;
  readonly kind: string;
  readonly alias: string;
  readonly origin?: string;

  /**
   * Optional tenant scope declaration. When unset (Phase 1 default),
   * the kernel treats the kind permissively (back-compat). Phase 2
   * iterates through every Extension to set TENANTED or GLOBAL
   * explicitly, flipping enforcement on per-Kind. See TenantScope.
   */
  readonly scope?: TenantScope;
  /** Canonical prose documentation. May be overridden at load time by a DOCS.md file
   *  alongside the extension's source. Resolved prose is cached on `_resolvedDocs`. */
  readonly docs?: string;

  readonly isRoot: boolean;
  readonly isPromptTarget: boolean;
  readonly promptTargetPriority: number;
  readonly flattenInContext: boolean;
  readonly storage: StorageDescriptor;

  /**
   * `true` for Kinds whose documents are produced by runtime workflows
   * (eval engine, GAIA pipeline, autolab loop, evidence-capture hooks)
   * rather than authored as source-of-truth. Tools that replicate "the
   * inputs to the system" — filesystem→Postgres seed, catalog publish,
   * manifest export — MUST skip Kinds where this is true so they don't
   * re-inject historical execution data as canonical configuration.
   * Default `false` (provided by KindBase) keeps existing extensions
   * unchanged.
   */
  readonly isRuntimeArtifact: boolean;

  // Kernel classification (s-kernel-kindport-classification-attrs). Optional so
  // KindPort-direct implementers don't break; the kernel derives with sensible
  // defaults (isSchemaAffecting=false, isOverlayable=true, scopeInheritable=true).
  // KindBase provides concrete defaults. 1:1 parity with the Python KindPort.
  readonly isSchemaAffecting?: boolean;
  readonly isOverlayable?: boolean;
  readonly scopeInheritable?: boolean;
  // Two-planes (spec 2026-06-09-kinds-two-planes-design): "composition" (default)
  // participates in agent composition; "record" is a pure typed document.
  readonly plane?: "record" | "composition";

  depFilters(): Record<string, string> | null;
  getDefaultAgentName(doc: Document): string | null;
  getLayerPolicies(doc: Document): Record<string, LayerPolicy | string> | null;
  parse(raw: Record<string, unknown>): unknown;
  describe(doc: Document): string | null;
  summary(doc: Document): Record<string, unknown> | null;
  promptTemplate(): string | null;

  /** JSON Schema for this kind's spec. Zod-based kinds convert their schema;
   *  declarative kinds return native JSON Schema. */
  schema?(): Record<string, unknown> | null;

  /** Which spec fields reference other kinds by alias.
   *  Clearer name for depFilters(). */
  dependencies?(): Record<string, string> | null;

  /**
   * Optional: returns renderable blocks for the Studio's preview pane.
   * Each extension implements this for its own kinds. When undefined,
   * the kernel falls back to `genericSpecDump` from preview.ts.
   */
  preview?(doc: Document): PreviewBlock[];

  // -- Rendering hints (all optional) -------------------------------------

  /** Colors for mermaid diagrams, graph nodes, and other visualizations. */
  readonly graphStyle?: {
    fill: string;
    stroke: string;
    textColor: string;
  };
  /** Single emoji or character for ASCII tree / compact views. */
  readonly asciiIcon?: string;
  /** Human-friendly plural label (e.g. "Agents" for Agent). */
  readonly displayLabel?: string;

  /** Per-doc annotations for graph rendering and health checks.
   *  e.g. Guardrail returns {severity, scope, rules}.
   *  Agent returns {model, soul, skills_count}. */
  graphMeta?(doc: Document): Record<string, unknown> | null;
}

// ---------------------------------------------------------------------------
// Tool port — TS twin of the Py ToolPort/ToolDefinition
// (s-dna-tool-decorator 2026-05-24; ported by s-dna-port-surface-parity).
//
// DNA discovery metadata for an invocable agent tool. The Python side wraps
// langchain's StructuredTool via the @dna_tool decorator; the TS SDK has no
// langchain runtime, so `getCallable()` returns whatever framework-native
// invocable the registrant provided (a plain function is fine). Extensions
// register via `kernel.tool(td)` (see ExtensionHost); consumers query via
// `kernel.getTools({ group })` — pure metadata, no execution path.
// ---------------------------------------------------------------------------

/**
 * An invocable tool exposed to agents. This port carries the DNA discovery
 * metadata (group, hitl, scope); the underlying callable stays framework-
 * native and is never wrapped or serialized.
 */
export interface ToolPort {
  readonly name: string;
  /** Tool group (cognitive | manifest | code | docs | web | write | eval |
   *  eval_lab | …). `null` = registered but not group-filterable (rare). */
  readonly group: string | null;
  /** Full docstring / long description. */
  readonly description: string;
  /** First paragraph of the description. */
  readonly summary: string;
  /** JSON Schema of the tool's arguments (best-effort; may be `{}`). */
  readonly argsSchema: Record<string, unknown>;
  /** Write tool that needs a HumanInTheLoop interrupt at the root graph. */
  readonly hitl: boolean;
  /** Layer-policy hint — "tenant" respects tenant overlay, "global"
   *  doesn't. Reserved for future use. */
  readonly scope: string | null;
  /** Module file name that defined the tool (best-effort). */
  readonly source: string;
  /** Return the underlying invocable (framework-native tool or function). */
  getCallable(): unknown;
}

/**
 * Concrete ToolPort implementation, stored in the kernel's ToolRegistry.
 * Twin of the Py `ToolDefinition` dataclass — the `callable` init field
 * holds the framework-native invocable; `getCallable()` is the canonical
 * accessor (never serialize or wrap-replace it).
 */
export class ToolDefinition implements ToolPort {
  readonly name: string;
  readonly group: string | null;
  readonly description: string;
  readonly summary: string;
  readonly argsSchema: Record<string, unknown>;
  readonly hitl: boolean;
  readonly scope: string | null;
  readonly source: string;
  private readonly _callable: unknown;

  constructor(init: {
    name: string;
    group?: string | null;
    description?: string;
    summary?: string;
    argsSchema?: Record<string, unknown>;
    hitl?: boolean;
    scope?: string | null;
    source?: string;
    callable?: unknown;
  }) {
    this.name = init.name;
    this.group = init.group ?? null;
    this.description = init.description ?? "";
    this.summary = init.summary ?? "";
    this.argsSchema = init.argsSchema ?? {};
    this.hitl = init.hitl ?? false;
    this.scope = init.scope ?? null;
    this.source = init.source ?? "";
    this._callable = init.callable ?? null;
  }

  getCallable(): unknown {
    return this._callable;
  }
}

/**
 * The registration-time surface the Kernel offers to `Extension.register()`.
 *
 * This is the *explicit contract* of what an extension may call while it is
 * being loaded (s-dna-extension-host-contract). It is a narrow slice of the
 * Kernel — the registration vocabulary — NOT the whole Kernel API. Derived
 * from actual usage across every builtin extension:
 *
 * - `kind(kp)`              — register a KindPort (identity + composition)
 * - `kindFromDescriptor()`  — register a record Kind from a
 *                             `kinds/*.kind.yaml` descriptor (F3 — Kinds as
 *                             data). Pair with `loadDescriptors()` from
 *                             `./descriptor-loader.js`.
 * - `reader(r)`             — register a ReaderPort (detect/scan a format)
 * - `writer(w)`             — register a WriterPort (write a format)
 * - `on(hook, fn)`          — subscribe to an event (e.g. `post_save`)
 * - `onVeto(hook, fn)`      — register a veto listener (e.g. `pre_save`
 *                             write guards — throwing vetoes the operation)
 * - `tool(td)`              — register a ToolDefinition (DNA tool discovery
 *                             metadata; queried via `kernel.getTools()`)
 * - `compositionProfile()`  — register orchestrator kind wiring
 * - `hooks`                 — the HookRegistry itself, for advanced listener
 *                             management (`kernel.hooks.onVeto(..., {key})`)
 *
 * The real `Kernel` satisfies this interface structurally (statically
 * asserted in `tests/extension-host-contract.test.ts`). Py twin:
 * `ExtensionHost` in `dna/kernel/protocols.py`.
 */
export interface ExtensionHost {
  /** The HookRegistry the `on`/`onVeto` conveniences delegate to. */
  readonly hooks: HookRegistry;
  kind(kp: KindPort): void;
  kindFromDescriptor(raw: Record<string, unknown>): KindPort;
  reader(r: ReaderPort): void;
  writer(w: WriterPort): void;
  on(hook: string, fn: (ctx: HookContext) => void): void;
  onVeto(
    hook: string,
    fn: VetoHandler,
    opts?: { priority?: number; key?: string },
  ): void;
  tool(td: ToolDefinition): void;
  compositionProfile(profile: CompositionProfile): void;
}

/**
 * Registers kinds, readers, and writers on the Kernel.
 *
 * The `templates?()` method is INTENTIONALLY OPTIONAL so extensions that
 * predate Phase 0 (i.e. shipped before the Template contract existed)
 * keep satisfying the `Extension` contract without modification. When
 * present, `Kernel.listTemplates()` aggregates entries from every loaded
 * extension so UIs (Tauri Studio, CLI) can offer `scaffold()` for any
 * extension-shipped file tree. See `./templates.ts` for the payload
 * shape.
 */
export interface Extension {
  readonly name: string;
  readonly version: string;
  /**
   * Wire the extension into the kernel. `kernel.load(ext)` fail-loud
   * validates the whole contract first (`name` non-empty string,
   * `version` string, `register` callable → `ExtensionLoadError`
   * otherwise), then calls `register()` with the registration-time
   * host slice — see {@link ExtensionHost} for the exact vocabulary.
   */
  register(kernel: ExtensionHost): void;
  /** Optional — return the file-tree scaffolds this extension ships. */
  templates?(): Template[];
}

// Re-export Template / OnConflict / MaterializeOptions at the protocols
// surface so downstream code can do
// `import { Template } from "./protocols.js"` alongside the other port
// types. The `templates()` method on Extension is intentionally OPTIONAL
// (feature-tested via `typeof ext.templates === "function"` in the
// kernel) to preserve backwards compatibility with third-party
// extensions that predate Phase 0.
export type {
  Template,
  OnConflict,
  MaterializeOptions,
} from "./templates.js";

import type { Template } from "./templates.js";
