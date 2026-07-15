/**
 * FilesystemSource — SourcePort backed by local .dna/ directories.
 *
 * 1:1 parity with Python dna.v3.adapters.filesystem.source.
 */

import { access, readFile, readdir, stat } from "node:fs/promises";
import { resolve, join } from "node:path";

async function pathExists(p: string): Promise<boolean> {
  try { await access(p); return true; } catch { return false; }
}

/**
 * Map a tenant value to a cross-platform-safe on-disk directory segment — 1:1
 * with Python `fs_tenant_segment` (ADR-personal-memory). The reserved
 * `personal:<oid>` partition's `:` scheme sigil is not a portable path segment,
 * so it is percent-escaped to `%3A` for the FS directory; the canonical tenant
 * value (the read predicate, the API) is unchanged. A no-op for every ordinary
 * tenant (they carry no `:`).
 */
export function fsTenantSegment(tenant: string): string {
  return tenant.replace(/:/g, "%3A");
}
import yaml from "js-yaml";
import type {
  CountResult,
  ReaderPort,
  RecordStorePort,
  SourceCountOpts,
  SourcePort,
  SourceQueryOpts,
} from "../../kernel/protocols.js";
import { countDocs, queryDocs } from "../../kernel/protocols.js";
import type { SourceCapabilities } from "../../kernel/capabilities.js";
import { FilesystemBundleHandle } from "../../kernel/bundle-handle.js";

export class FilesystemSource implements SourcePort {
  readonly baseDir: string;
  readonly supportsReaders = true;

  constructor(baseDir: string) {
    this.baseDir = resolve(baseDir);
  }

  // v1.0 — true async via fs/promises. Concurrent reads don't block
  // the event loop, which matters for repos with many bundles or any
  // parallel scope-load workload.

  async loadBootstrapDocs(
    scope: string,
    opts?: { tenant?: string },
  ): Promise<Record<string, unknown>[]> {
    // Phase 16 — filesystem walks ``loadAll`` and filters by Kind
    // name. SQL adapters override with a fast WHERE filter.
    //
    // Tenant semantics: when ``opts.tenant`` is set, the
    // tenant-published Genome shadows the platform Genome (Phase 9).
    // KindDefinition + LayerPolicy are non-overlayable per Phase 16 —
    // always read from platform.
    //
    // 1:1 parity with Python ``FilesystemSource.load_bootstrap_docs``.
    const { BOOTSTRAP_KIND_NAMES } = await import("../../kernel/protocols.js");
    const bootstrapSet = new Set<string>(BOOTSTRAP_KIND_NAMES);
    let allRaws: Record<string, unknown>[];
    try {
      allRaws = await this.loadAll(scope);
    } catch {
      // Platform scope dir absent — tenant-only scopes still resolve.
      allRaws = [];
    }
    let out = allRaws.filter((d) => bootstrapSet.has((d.kind as string) ?? ""));

    const tenant = opts?.tenant;
    if (tenant) {
      const tenantPath = join(
        this.baseDir, "tenants", fsTenantSegment(tenant), "scopes", scope, "Genome.yaml",
      );
      if (await pathExists(tenantPath)) {
        const tenantPkg = yaml.load(
          await readFile(tenantPath, "utf-8"),
        ) as Record<string, unknown> | null;
        if (
          tenantPkg
          && typeof tenantPkg === "object"
          && tenantPkg.kind === "Genome"
        ) {
          out = out.filter((d) => d.kind !== "Genome");
          out.push(tenantPkg);
        }
      }
    }
    return out;
  }

  async loadAll(
    scope: string,
    readers?: ReaderPort[],
  ): Promise<Record<string, unknown>[]> {
    const scopeDir = join(this.baseDir, scope);
    if (!(await pathExists(scopeDir))) throw new Error(`Scope not found: ${scopeDir}`);
    return await this._loadDir(scopeDir, readers ?? [], new Set(["layers", "tenants"]));
  }

  /**
   * Two-planes F2 — record-plane query over `loadAll` + the shared pure
   * helpers (mirror of the Py `SourcePort.query` protocol-default). FS
   * is dev-mode with small scopes; native push-down is the purview of
   * the SQL adapters.
   *
   * `opts.tenant` is a documented NO-OP here: the FS TS adapter has no
   * tenant-aware overlay merge in `loadAll` (divergence from the Py FS
   * source, which unions base + tenant layer with shadowing) — overlay
   * support is an F2.5 candidate alongside the writable FS source.
   *
   * Bundle-format kinds are not visible to this query (no kernel reader
   * back-ref on the TS source) — record-plane docs are plain YAML.
   */
  async *query(
    scope: string,
    kind: string,
    opts: SourceQueryOpts = {},
  ): AsyncIterable<Record<string, unknown>> {
    const docs = await this.loadAll(scope);
    for (const row of queryDocs(docs, kind, opts)) yield row;
  }

  /**
   * Two-planes F2 — record-plane count over `loadAll` + `countDocs`
   * (mirror of the Py protocol-default). Same `opts.tenant` NO-OP
   * caveat as `query`.
   */
  async count(
    scope: string,
    kind: string,
    opts: SourceCountOpts = {},
  ): Promise<CountResult> {
    const docs = await this.loadAll(scope);
    return countDocs(docs, kind, opts);
  }

  /**
   * Explicit contract declaration (s-sourceport-contract-cleanup) — kept
   * honest by the adapter conformance test (declaration == structural
   * derivation). Read-only FS source: in-memory query/count + the L1
   * granular reads (loadOne + listDocRefs, s-dna-port-surface-parity);
   * no bundle/write surface on the TS twin yet.
   */
  capabilities(): SourceCapabilities {
    return {
      source: "filesystem",
      drafts: false,
      versions: false,
      layers: true,
      bundleRead: false,
      bundleWrite: false,
      kernelAttachable: false,
      granularList: true,
      granularOne: true,
      queryPushdown: true,
    };
  }

  /**
   * Documented NO-OP — the FS source holds no pooled resources (each read
   * opens/closes its own file handles via fs/promises). The member exists
   * for SourcePort surface parity with Python, where `close` is a
   * SOURCE_PORT_CORE_MEMBERS boot-gate entry.
   */
  async close(): Promise<void> {
    // nothing to release
  }

  /**
   * L1 granular access — FS impl projects from `loadAll` (mirror of the
   * Py `FilesystemSource.list_doc_refs`): `[kind, name]` refs only, no
   * bundle rehydration. No perf gain over `loadAll` on FS, but keeps the
   * SourcePort contract consistent across adapters (PG is where the gain
   * lives). Tenant: union of base + overlay with the overlay shadowing
   * base, same as the Py twin. Result sorted by (kind, name).
   */
  async listDocRefs(scope: string, opts?: {
    kind?: string | null; tenant?: string | null;
  }): Promise<Array<[string, string]>> {
    const refOf = (d: Record<string, unknown>): [string, string] => {
      const meta = d.metadata as Record<string, unknown> | undefined;
      return [
        typeof d.kind === "string" ? d.kind : "",
        String(meta?.name ?? d.name ?? ""),
      ];
    };
    let docs: Record<string, unknown>[];
    if (opts?.tenant) {
      const overlay = await this.loadLayer(scope, "tenant", opts.tenant);
      const overlayKeys = new Set(overlay.map((d) => refOf(d).join("\0")));
      const base = (await this.loadAll(scope)).filter(
        (d) => !overlayKeys.has(refOf(d).join("\0")),
      );
      docs = [...overlay, ...base];
    } else {
      docs = await this.loadAll(scope);
    }
    const refs: Array<[string, string]> = [];
    for (const d of docs) {
      const [k, n] = refOf(d);
      if (!k || !n) continue;
      if (opts?.kind && k !== opts.kind) continue;
      refs.push([k, n]);
    }
    refs.sort((a, b) =>
      a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0,
    );
    return refs;
  }

  async resolveRef(scope: string, ref: string): Promise<string> {
    const path = join(this.baseDir, scope, ref);
    if (!(await pathExists(path))) return "";
    return await readFile(path, "utf-8");
  }

  /**
   * L1 granular access — FS impl projects from `loadAll` (mirror of the
   * Py `FilesystemSource.load_one`). No perf gain over `loadAll` on FS
   * (cheap in-process disk reads) but keeps the SourcePort contract
   * consistent across adapters. Tenant overlay shadows base: when
   * `opts.tenant` is set the tenant layer is consulted first and the
   * BASE layer is the fallback (same as Python — a tenant read of a doc
   * with no overlay still returns the base doc).
   */
  async loadOne(
    scope: string,
    kind: string,
    name: string,
    opts?: { readers?: ReaderPort[]; tenant?: string | null },
  ): Promise<Record<string, unknown> | null> {
    const readers = opts?.readers ?? [];
    const matches = (d: Record<string, unknown>): boolean => {
      if (d.kind !== kind) return false;
      const meta = d.metadata as Record<string, unknown> | undefined;
      return meta?.name === name || d.name === name;
    };
    if (opts?.tenant) {
      const overlay = await this.loadLayer(scope, "tenant", opts.tenant, readers);
      for (const d of overlay) if (matches(d)) return d;
    }
    const base = await this.loadAll(scope, readers);
    for (const d of base) if (matches(d)) return d;
    return null;
  }

  async loadLayer(
    scope: string,
    layerId: string,
    layerValue: string,
    readers?: ReaderPort[],
  ): Promise<Record<string, unknown>[]> {
    // Phase 2b (parity with the Py FS source): tenant layers live at
    // tenants/<X>/scopes/<S>/; other layers (branch, region, user) keep
    // the legacy <scope>/layers/ path. Tenant reads check the new path
    // first, falling back to the legacy layers/tenant/<X>/ for
    // pre-migration data.
    if (layerId === "tenant") {
      const newDir = join(this.baseDir, "tenants", fsTenantSegment(layerValue), "scopes", scope);
      if (await pathExists(newDir)) {
        return await this._loadDir(newDir, readers ?? [], new Set());
      }
      const legacyDir = join(this.baseDir, scope, "layers", "tenant", layerValue);
      if (await pathExists(legacyDir)) {
        return await this._loadDir(legacyDir, readers ?? [], new Set());
      }
      return [];
    }
    const layerDir = join(this.baseDir, scope, "layers", layerId, layerValue);
    if (!(await pathExists(layerDir))) return [];
    return await this._loadDir(layerDir, readers ?? [], new Set());
  }

  private async _loadDir(
    directory: string,
    readers: ReaderPort[],
    skip: Set<string>,
  ): Promise<Record<string, unknown>[]> {
    const documents: Record<string, unknown>[] = [];
    const readerMatched = new Set<string>();

    // 1. Readers first (bundles take priority over YAML)
    if (readers.length > 0) {
      // Readers on the scope root directory itself (Python parity — a
      // standalone marker like AGENTS.md at the scope root is a document
      // of the scope; agents.md/v1 uses exactly that layout).
      const rootHandle = new FilesystemBundleHandle(directory);
      for (const reader of readers) {
        try {
          if (await reader.detect(rootHandle)) {
            const doc = await reader.read(rootHandle);
            if (doc != null && typeof doc === "object" && "kind" in doc) {
              documents.push(doc);
            }
            readerMatched.add(directory.split("/").filter(Boolean).pop() ?? "");
          }
        } catch {
          // Skip reader errors (Python logs a warning and continues)
        }
      }
      await this._readRecursive(directory, readers, documents, skip, readerMatched);
    }

    // 2. YAML files, skipping stems already matched by readers
    await this._collectYaml(directory, directory, skip, documents, readerMatched);

    // 3. Deduplicate by kind/name — readers (first) take priority over YAML (later)
    const seen = new Set<string>();
    const deduped: Record<string, unknown>[] = [];
    for (const doc of documents) {
      const meta = (doc as Record<string, Record<string, unknown>>).metadata ?? {};
      const key = `${doc.kind}/${meta.name ?? ""}`;
      if (!seen.has(key)) {
        seen.add(key);
        deduped.push(doc);
      }
    }
    return deduped;
  }

  private async _collectYaml(
    root: string,
    directory: string,
    skip: Set<string>,
    documents: Record<string, unknown>[],
    readerMatched: Set<string>,
  ): Promise<void> {
    const entries = (await readdir(directory)).sort();
    for (const entry of entries) {
      const full = join(directory, entry);
      const relParts = full.slice(root.length + 1).split("/");
      if (relParts.some((p) => skip.has(p))) continue;

      const st = await stat(full);
      if (st.isDirectory()) {
        await this._collectYaml(root, full, skip, documents, readerMatched);
      } else if (entry.endsWith(".yaml") || entry.endsWith(".yml")) {
        // Dedup of reader-loaded bundles vs same-named YAML siblings is
        // handled by step 3 ((kind, name) key) in _loadDir. Stem-only
        // skip here would drop YAMLs of a DIFFERENT kind that happen to
        // share a name with a bundle (e.g. Skill/create-initiative +
        // UseCase/create-initiative — both valid, different kinds).
        try {
          const content = yaml.load(await readFile(full, "utf-8"));
          if (
            content != null &&
            typeof content === "object" &&
            "kind" in (content as Record<string, unknown>)
          ) {
            documents.push(content as Record<string, unknown>);
          }
        } catch {
          // Skip unparseable YAML
        }
      }
    }
  }

  private async _readRecursive(
    directory: string,
    readers: ReaderPort[],
    documents: Record<string, unknown>[],
    skip: Set<string>,
    readerMatched: Set<string>,
  ): Promise<void> {
    // H3 — container-aware reader routing.
    //
    // The scanner walks subdirs of `directory`. Each subdir IS a
    // bundle (or a non-bundle subdir). The PARENT directory's name
    // equals the bundle's *container* (e.g.
    // `pageindex-documents/frank-hutter-cv/` → container =
    // `pageindex-documents`).
    //
    // Pre-H3, we tried every registered reader in order and stopped
    // at first match. That broke when two readers detected the same
    // marker file (PageIndex + Graphify both used MANIFEST.md): the
    // alphabetically-first extension's reader silently captured the
    // other's bundles.
    //
    // H3 fix: prefer readers whose `_ownerContainer` member matches the
    // parent dir name. Unscoped readers (undefined — a formal ReaderPort
    // member since s-dna-rw-roundtrip-suite, no longer duck-typed) are
    // tried only as fallback.
    const containerName = directory.split("/").filter(Boolean).pop() ?? "";
    const ownedReaders = readers.filter((r) => r._ownerContainer === containerName);
    const globalReaders = readers.filter((r) => r._ownerContainer == null);
    const orderedReaders = [...ownedReaders, ...globalReaders];

    const entries = (await readdir(directory)).sort();
    for (const entry of entries) {
      const full = join(directory, entry);
      if (!(await stat(full)).isDirectory() || skip.has(entry)) continue;

      let matched = false;
      const handle = new FilesystemBundleHandle(full);
      for (const reader of orderedReaders) {
        try {
          if (await reader.detect(handle)) {
            const doc = await reader.read(handle);
            if (
              doc != null &&
              typeof doc === "object" &&
              "kind" in doc
            ) {
              documents.push(doc);
            }
            readerMatched.add(entry);
            matched = true;
            break;
          }
        } catch {
          // Skip reader errors
        }
      }
      if (!matched) {
        await this._readRecursive(full, readers, documents, skip, readerMatched);
      }
    }
  }
}

// Two-planes F2 — RecordStorePort conformance BY COMPOSITION (compile-time;
// lives in src because tsconfig excludes tests/ from `tsc --noEmit`). The
// FS TS adapter provides the READ half (`query`|`count`) — it has no
// save/delete yet; full conformance arrives with the writable FS source
// (F2.5+). Function is never called — it exists for the typecheck.
function _fsRecordStoreReadHalfConformance(
  src: FilesystemSource,
): Pick<RecordStorePort, "query" | "count"> {
  return src;
}
void _fsRecordStoreReadHalfConformance;
