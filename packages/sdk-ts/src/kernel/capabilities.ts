/**
 * Optional capability interfaces for source/cache/etc adapters.
 *
 * 1:1 parity with python/dna/kernel/capabilities.py.
 *
 * H2 — Replaces ad-hoc structural checks (`"fetchBundleEntry" in src`)
 * with discoverable, type-checkable interface assertions. A developer
 * authoring a custom adapter sees the available capabilities by
 * importing this module, instead of grepping the kernel source.
 *
 * Why these are separate from the core `SourcePort` interface:
 *
 *   - The core interfaces (SourcePort, WritableSourcePort, CachePort,
 *     ...) define the **mandatory** contract every adapter must
 *     implement.
 *   - These capability interfaces define **optional** features —
 *     adapters can declare support by structurally matching the
 *     signature, OR omit the methods entirely without breaking the
 *     core contract.
 *
 * TypeScript's structural typing makes capability detection at runtime
 * a method-presence check (`typeof src.fetchBundleEntry === "function"`).
 * Use the helper guards (`isBundleEntryReadable`, etc.) for clarity.
 *
 * Adding a new capability:
 *   1. Define `MyCapability` interface here.
 *   2. Add an `isMyCapability(x): x is MyCapability` type guard.
 *   3. Replace any `if ("method" in adapter)` checks with
 *      `if (isMyCapability(adapter))`.
 *   4. Document the capability in `docs/PORT-CONTRACT.md`.
 *   5. Cover it in `tests/portContract.test.ts`.
 */

import type { Kernel } from "./index.js";

/**
 * Source adapter capability: fetch a single bundle entry by name.
 *
 * The kernel uses this to read large binary payloads (graph.json,
 * tree.json, ...) without rehydrating the whole bundle through the
 * Reader pipeline. Implementing adapters store bundle entries in
 * their backing store (filesystem dir, `dna_bundle_entries` SQL
 * table) and serve byte payloads directly.
 *
 * Tenant overlay routing: when `tenant` is provided and the adapter
 * supports it, the tenant-scoped copy is preferred over the base
 * layer.
 *
 * Throws `Error` (with code `ENOENT` or message containing "not
 * found") when the bundle or entry is absent.
 */
export interface BundleEntryReadable {
  fetchBundleEntry(
    scope: string,
    container: string,
    name: string,
    entry: string,
    /**
     * Optional knobs:
     *   - ``tenant`` — when set, prefer the tenant overlay row
     *     (with base-layer fallback).
     *   - ``kind`` — disambiguates SQL row collision when two
     *     Kinds share a bundle ``name`` in the same scope (e.g.
     *     a Skill ``foo`` and a GraphifyArtifact ``foo``).
     *     Filesystem adapters ignore this since each container
     *     is a directory namespace.
     */
    options?: { tenant?: string | null; kind?: string | null },
  ): Promise<Uint8Array>;
}

export function isBundleEntryReadable(x: unknown): x is BundleEntryReadable {
  return typeof (x as { fetchBundleEntry?: unknown })?.fetchBundleEntry === "function";
}

/**
 * Source adapter capability: accept post-init kernel wiring.
 *
 * H2 unification: `Kernel.auto({ source })` previously had a
 * hardcoded `source instanceof FilesystemWritableSource` check that
 * wired `_writers` and `setKernel(k)`. SQLite/Postgres adapters
 * required the same wiring but only got it via the harness's
 * source factory — leaving direct
 * `new Kernel().writableSource(new SqliteSource(...))` callers with
 * a half-broken kernel.
 *
 * Adapters now declare attachability by implementing
 * `attachKernel(kernel)`. The kernel calls this method on every
 * source it accepts — uniformly. Implementations install the
 * kernel's `_writers`, `_readers`, and (optionally) a back-ref to
 * the kernel itself for the source's save path to consult
 * `storageForKind`.
 *
 * Idempotent: calling twice with the same kernel produces the same
 * wired state.
 */
export interface KernelAttachable {
  attachKernel(kernel: Kernel): void;
}

export function isKernelAttachable(x: unknown): x is KernelAttachable {
  return typeof (x as { attachKernel?: unknown })?.attachKernel === "function";
}

/**
 * Source adapter capability: per-Kind semver versioning.
 *
 * Backs the catalog versioning flow: a Kind that's `Versionable`
 * supports `getVersion(scope, kind, name, versionId)` and
 * `listVersions(...)`. The harness REST surface checks for this
 * capability via `isVersionable` to decide whether to expose the
 * `/catalog/{owner}/{name}/versions` endpoint (501 otherwise).
 *
 * Custom adapters that don't track per-doc versions can omit and
 * the harness will degrade gracefully with a 501 response.
 */
export interface Versionable {
  getVersion(
    scope: string, kind: string, name: string, versionId: string,
  ): Promise<Record<string, unknown>>;
}

export function isVersionable(x: unknown): x is Versionable {
  return typeof (x as { getVersion?: unknown })?.getVersion === "function";
}

/**
 * Typed view of what a source adapter supports — TS twin of the Py
 * `SourceCapabilities` dataclass (s-sourceport-contract-cleanup).
 *
 * Adapters DECLARE this explicitly (`capabilities()` returns a literal);
 * the kernel consults {@link sourceCapabilities} instead of scattering
 * `typeof src.query === "function"` feature-tests. {@link deriveCapabilities}
 * (structural probing) survives as (a) the conformance-test oracle that
 * keeps declarations honest and (b) the deprecated fallback for external
 * adapters that don't declare yet.
 *
 * Py-only fields with no TS meaning are omitted on purpose:
 * `write_kwargs`/`delete_kwargs`/`tenant_layer_writes` exist in Python
 * because optional kwargs must be probed via `inspect.signature`; the TS
 * write surface is an options bag, so there is nothing to probe.
 */
export interface SourceCapabilities {
  /** Human-readable adapter label ("filesystem", "postgres", ...). */
  source: string;
  drafts: boolean;
  versions: boolean;
  layers: boolean;
  bundleRead: boolean;
  bundleWrite: boolean;
  kernelAttachable: boolean;
  /** Implements the L1 granular reads (independent flags on purpose —
   *  the TS FS source ships `loadOne` but not `listDocRefs`). */
  granularList: boolean;
  granularOne: boolean;
  /** Implements `query`/`count` natively (FS: native but in-memory). */
  queryPushdown: boolean;
}

function _fn(x: unknown, name: string): boolean {
  return typeof (x as Record<string, unknown> | null)?.[name as never] === "function";
}

/**
 * Build a {@link SourceCapabilities} for `source` by structural probing —
 * the reflection oracle. In-repo adapters declare literals instead; the
 * conformance test asserts declaration == derivation.
 */
export function deriveCapabilities(source: unknown, label: string): SourceCapabilities {
  return {
    source: label,
    drafts: _fn(source, "loadDrafts") && _fn(source, "publish"),
    versions: _fn(source, "getVersion"),
    layers: _fn(source, "loadLayer"),
    bundleRead: _fn(source, "fetchBundleEntry"),
    bundleWrite: _fn(source, "writeBundleEntry"),
    kernelAttachable: _fn(source, "attachKernel"),
    granularList: _fn(source, "listDocRefs"),
    granularOne: _fn(source, "loadOne"),
    queryPushdown: _fn(source, "query"),
  };
}

const _capsCache = new WeakMap<object, SourceCapabilities>();
const _warnedUndeclared = new Set<unknown>();

/**
 * THE kernel-side accessor for a source's capabilities (TS twin of the
 * Py `source_capabilities`). Resolution order (memoized per instance):
 *
 * 1. the adapter's own `capabilities()` returning a
 *    {@link SourceCapabilities} — the explicit declaration;
 * 2. DEPRECATED fallback: {@link deriveCapabilities} structural probing,
 *    with a once-per-constructor console warning pointing at the
 *    migration (keeps external adapters working).
 */
export function sourceCapabilities(source: object): SourceCapabilities {
  const cached = _capsCache.get(source);
  if (cached) return cached;

  let caps: SourceCapabilities | null = null;
  const fn = (source as { capabilities?: unknown }).capabilities;
  if (typeof fn === "function") {
    try {
      const declared = fn.call(source) as SourceCapabilities | null;
      if (
        declared !== null && typeof declared === "object"
        && typeof declared.source === "string"
        && typeof declared.queryPushdown === "boolean"
      ) {
        caps = declared;
      }
    } catch {
      caps = null; // a broken declaration degrades to derivation
    }
  }
  if (caps === null) {
    const ctor = (source as { constructor?: unknown }).constructor;
    if (!_warnedUndeclared.has(ctor)) {
      _warnedUndeclared.add(ctor);
      const name = (ctor as { name?: string } | undefined)?.name ?? "source";
      console.warn(
        `[dna-sdk] ${name} does not declare SourceCapabilities via `
        + `capabilities(); deriving structurally (deprecated, `
        + `s-sourceport-contract-cleanup). Declare an explicit `
        + `SourceCapabilities on the adapter to silence this.`,
      );
    }
    caps = deriveCapabilities(source, ((source as { constructor?: { name?: string } }).constructor?.name ?? "source"));
  }
  _capsCache.set(source, caps);
  return caps;
}
