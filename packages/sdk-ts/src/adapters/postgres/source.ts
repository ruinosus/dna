/**
 * PostgresSource — TypeScript adapter for the SDK's WritableSourcePort.
 *
 * 1:1 parity (MVP) with python/dna/adapters/postgres/source.py.
 * Implements:
 *   - WritableSourcePort: loadBootstrapDocs, loadAll, resolveRef, loadLayer,
 *     saveDocument, deleteDocument, publish (no-op for MVP), close
 *   - BundleEntryReadable: fetchBundleEntry — port-aware byte fetch
 *   - KernelAttachable: attachKernel — uniform writer/reader wiring
 *   - Versionable: getVersion — basic single-version support
 *
 * Out of scope for v1.0 (lands in v1.1 follow-up):
 *   - Module versioning catalog (Phase 10 lockfile flow)
 *   - Tenant overlay routing (multi-tenant scopes endpoint)
 *   - LISTEN/NOTIFY event bus (Phase 15.1)
 *   - Draft → published two-step write flow
 *
 * The schema mirrors Python's `dna_documents` / `dna_bundle_entries` /
 * `dna_layer_documents` — already-existing Python deployments are
 * read-compatible with this adapter.
 */

import { Pool, type PoolConfig } from "pg";
import type { Kernel } from "../../kernel/index.js";
import { DictBundleHandle } from "../../kernel/bundle-handle.js";
import type {
  ReaderPort,
  WritableSourcePort,
  WriterPort,
} from "../../kernel/protocols.js";
import type { SourceCapabilities } from "../../kernel/capabilities.js";
import { MIGRATIONS } from "./migrations.js";

function nowIso(): string {
  return new Date().toISOString();
}

export interface PostgresSourceOptions {
  /** Postgres connection string (postgresql://user:pass@host/db). */
  connectionString?: string;
  /** Schema to create tables in. Defaults to "public". */
  schema?: string;
  /**
   * Optional pre-built Pool. When provided the adapter uses it
   * verbatim and does NOT close it on `close()`. Useful for sharing
   * pools across adapters or test fixtures.
   */
  pool?: Pool;
  /** Initial writers (filled by attachKernel if empty). */
  writers?: WriterPort[];
  /** Initial readers (filled by attachKernel if empty). */
  readers?: ReaderPort[];
  /** Extra Pool options (max, idleTimeoutMillis, ...). */
  poolOptions?: PoolConfig;
}

// Two-planes F2: query/count push-down is Py-only — the TS PG adapter
// doesn't even have `query` yet (the optional SourcePort methods stay
// unimplemented; the Kernel raises a clear capability error). Candidate
// for F2.5+ alongside the Py `_build_pg_where`/`_build_pg_order` port.
export class PostgresSource implements WritableSourcePort {
  readonly supportsReaders = false;

  private _pool: Pool;
  private readonly _ownsPool: boolean;
  private readonly _schema: string;
  private _migrated = false;
  _writers: WriterPort[];
  _readers: ReaderPort[];
  private _kernel: Kernel | null = null;

  constructor(opts: PostgresSourceOptions) {
    this._schema = opts.schema ?? "public";
    if (opts.pool) {
      this._pool = opts.pool;
      this._ownsPool = false;
    } else {
      if (!opts.connectionString) {
        throw new Error(
          "PostgresSource: provide either `connectionString` or `pool` option.",
        );
      }
      this._pool = new Pool({ connectionString: opts.connectionString, ...opts.poolOptions });
      this._ownsPool = true;
    }
    this._writers = opts.writers ?? [];
    this._readers = opts.readers ?? [];
  }

  // ---------------------------------------------------------------------
  // Lifecycle
  // ---------------------------------------------------------------------

  async init(): Promise<void> {
    await this._runMigrations();
  }

  /**
   * Explicit contract declaration (s-sourceport-contract-cleanup) — kept
   * honest by the adapter conformance test. The TS PG adapter has the
   * write half + versions/bundle-read + the granular ref list
   * (listDocRefs, s-dna-port-surface-parity); query/count push-down and
   * loadOne are Py-only this phase (F2.5+ candidates).
   */
  capabilities(): SourceCapabilities {
    return {
      source: "postgres",
      drafts: false,
      versions: true,
      layers: true,
      bundleRead: true,
      bundleWrite: false,
      kernelAttachable: true,
      granularList: true,
      granularOne: false,
      queryPushdown: false,
    };
  }

  async close(): Promise<void> {
    if (this._ownsPool) await this._pool.end();
  }

  /**
   * KernelAttachable interface impl. Idempotent: copies the kernel's
   * registered writers + readers into this source so bundle writes
   * (which depend on `_writers` producing serialised entries via
   * `WriterPort.serialize`) work even when this source was
   * instantiated without explicit injection.
   */
  attachKernel(kernel: Kernel): void {
    this._kernel = kernel;
    if (this._writers.length === 0) {
      this._writers = [...((kernel as unknown as { _writers: WriterPort[] })._writers ?? [])];
    }
    if (this._readers.length === 0) {
      this._readers = [...((kernel as unknown as { _readers: ReaderPort[] })._readers ?? [])];
    }
  }

  // ---------------------------------------------------------------------
  // Migrations
  // ---------------------------------------------------------------------

  private async _runMigrations(): Promise<void> {
    if (this._migrated) return;
    const client = await this._pool.connect();
    try {
      await client.query(`CREATE SCHEMA IF NOT EXISTS "${this._schema}"`);
      await client.query(`
        CREATE TABLE IF NOT EXISTS "${this._schema}".dna_schema_migrations (
          version INTEGER PRIMARY KEY,
          applied_at TEXT NOT NULL
        )
      `);
      const { rows } = await client.query<{ version: number }>(
        `SELECT version FROM "${this._schema}".dna_schema_migrations`,
      );
      const applied = new Set(rows.map((r) => r.version));

      const versions = Object.keys(MIGRATIONS)
        .map((v) => Number(v))
        .sort((a, b) => a - b);

      for (const version of versions) {
        if (applied.has(version)) continue;
        const stmts = MIGRATIONS[version]!;
        await client.query("BEGIN");
        try {
          for (const stmt of stmts) {
            const sql = stmt.replace(/\{schema\}/g, `"${this._schema}"`);
            await client.query(sql);
          }
          await client.query(
            `INSERT INTO "${this._schema}".dna_schema_migrations (version, applied_at) VALUES ($1, $2)`,
            [version, nowIso()],
          );
          await client.query("COMMIT");
        } catch (e) {
          await client.query("ROLLBACK");
          throw e;
        }
      }
    } finally {
      client.release();
    }
    this._migrated = true;
  }

  // ---------------------------------------------------------------------
  // SourcePort (read)
  // ---------------------------------------------------------------------

  async loadBootstrapDocs(
    scope: string,
    opts?: { tenant?: string },
  ): Promise<Record<string, unknown>[]> {
    // Phase 16 — fast WHERE filter over Kind name set. 1:1 parity
    // with Python ``PostgresSource.load_bootstrap_docs``.
    //
    // Tenant semantics: when ``opts.tenant`` is set, the
    // tenant-published Genome shadows the platform Genome (Phase 9).
    // KindDefinition + LayerPolicy are non-overlayable per Phase 16 —
    // always read from platform (tenant='').
    await this._runMigrations();
    const { BOOTSTRAP_KIND_NAMES } = await import("../../kernel/protocols.js");
    const platform = await this._pool.query<{ content: Record<string, unknown> | string }>(
      `SELECT content FROM "${this._schema}".dna_documents
       WHERE scope=$1 AND kind = ANY($2::text[]) AND tenant=''`,
      [scope, [...BOOTSTRAP_KIND_NAMES]],
    );
    let out = platform.rows.map((r) => parseJsonish(r.content));

    const tenant = opts?.tenant;
    if (tenant) {
      const tpkg = await this._pool.query<{ content: Record<string, unknown> | string }>(
        `SELECT content FROM "${this._schema}".dna_documents
         WHERE scope=$1 AND kind='Genome' AND tenant=$2 LIMIT 1`,
        [scope, tenant],
      );
      if (tpkg.rows.length > 0) {
        const tenantPkg = parseJsonish(tpkg.rows[0]!.content);
        out = out.filter((d) => d.kind !== "Genome");
        out.push(tenantPkg);
      }
    }
    return out;
  }

  async loadAll(
    scope: string,
    readers?: ReaderPort[],
  ): Promise<Record<string, unknown>[]> {
    await this._runMigrations();
    const effectiveReaders: ReaderPort[] = [...this._readers];
    for (const r of readers ?? []) {
      if (!effectiveReaders.includes(r)) effectiveReaders.push(r);
    }

    const { rows } = await this._pool.query<{
      kind: string; name: string; content: Record<string, unknown> | string;
    }>(
      `SELECT kind, name, content FROM "${this._schema}".dna_documents
       WHERE scope=$1 AND tenant=''`,
      [scope],
    );

    const out: Record<string, unknown>[] = [];
    for (const row of rows) {
      const entries = await this._loadBundleEntries(scope, row.kind, row.name, "");
      if (Object.keys(entries).length > 0 && effectiveReaders.length > 0) {
        // Rehydrate via DictBundleHandle so Reader pipeline runs on
        // SQL-stored bundles identically to filesystem-stored ones.
        const handle = new DictBundleHandle(row.name, entries);
        let matched = false;
        for (const reader of effectiveReaders) {
          try {
            if (await reader.detect(handle)) {
              out.push(await reader.read(handle));
              matched = true;
              break;
            }
          } catch {
            continue;
          }
        }
        if (matched) continue;
      }
      out.push(parseJsonish(row.content));
    }
    return out;
  }

  async resolveRef(_scope: string, ref: string): Promise<string> {
    return ref;
  }

  /**
   * L1 granular access (s-dna-port-surface-parity — mirror of the Py
   * `PostgresSource.list_doc_refs`): one indexed SELECT of `[kind, name]`
   * refs, metadata only — no bundle entries, no reader rehydration. This
   * is where the granular read actually pays off vs `loadAll` (which is
   * an N+1 over bundle entries). Tenant: union of the base layer
   * (`tenant=''`) with the overlay; refs are DISTINCT so an overlay
   * shadow contributes a single entry.
   */
  async listDocRefs(scope: string, opts?: {
    kind?: string | null; tenant?: string | null;
  }): Promise<Array<[string, string]>> {
    await this._runMigrations();
    const params: unknown[] = [scope];
    let tenantClause = "tenant=''";
    if (opts?.tenant) {
      params.push(opts.tenant);
      tenantClause = `tenant IN ('', $${params.length})`;
    }
    let kindClause = "";
    if (opts?.kind) {
      params.push(opts.kind);
      kindClause = ` AND kind=$${params.length}`;
    }
    const { rows } = await this._pool.query<{ kind: string; name: string }>(
      `SELECT DISTINCT kind, name FROM "${this._schema}".dna_documents
       WHERE scope=$1 AND ${tenantClause}${kindClause}
       ORDER BY kind, name`,
      params,
    );
    return rows.map((r) => [r.kind, r.name]);
  }

  async loadLayer(
    scope: string, layerId: string, layerValue: string,
    _readers?: ReaderPort[],
  ): Promise<Record<string, unknown>[]> {
    await this._runMigrations();
    const { rows } = await this._pool.query<{ content: Record<string, unknown> | string }>(
      `SELECT content FROM "${this._schema}".dna_layer_documents
       WHERE scope=$1 AND layer_id=$2 AND layer_value=$3`,
      [scope, layerId, layerValue],
    );
    return rows.map((r) => parseJsonish(r.content));
  }

  // ---------------------------------------------------------------------
  // BundleEntryReadable capability
  // ---------------------------------------------------------------------

  private async _loadBundleEntries(
    scope: string, kind: string, name: string, tenant: string,
  ): Promise<Record<string, string>> {
    const { rows } = await this._pool.query<{
      entry_path: string; content: string;
    }>(
      `SELECT entry_path, content FROM "${this._schema}".dna_bundle_entries
       WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4`,
      [scope, kind, name, tenant],
    );
    const out: Record<string, string> = {};
    for (const r of rows) out[r.entry_path] = r.content;
    return out;
  }

  /**
   * Fetch a single bundle entry by name. Mirrors Python.
   *
   * Disambiguation: when the kernel supplies ``kind`` (e.g.
   * ``"GraphifyArtifact"``), the WHERE clause includes ``kind=$N``
   * so a Skill ``foo`` and a GraphifyArtifact ``foo`` in the same
   * scope don't collide. Without ``kind`` we fall back to
   * ``(scope, name, entry_path)`` and accept the rare collision
   * risk — older callers that built the kernel before the
   * protocol gained the kwarg fall through this path.
   */
  async fetchBundleEntry(
    scope: string,
    container: string,
    name: string,
    entry: string,
    options?: { tenant?: string | null; kind?: string | null },
  ): Promise<Uint8Array> {
    await this._runMigrations();
    const tenant = options?.tenant ?? null;
    const kind = options?.kind ?? null;
    const candidates = tenant ? [tenant, ""] : [""];
    for (const tval of candidates) {
      const { rows } = kind
        ? await this._pool.query<{ content: string }>(
            `SELECT content FROM "${this._schema}".dna_bundle_entries
             WHERE scope=$1 AND kind=$2 AND name=$3
             AND entry_path=$4 AND tenant=$5 LIMIT 1`,
            [scope, kind, name, entry, tval],
          )
        : await this._pool.query<{ content: string }>(
            `SELECT content FROM "${this._schema}".dna_bundle_entries
             WHERE scope=$1 AND name=$2 AND entry_path=$3
             AND tenant=$4 LIMIT 1`,
            [scope, name, entry, tval],
          );
      if (rows.length > 0) {
        return new TextEncoder().encode(rows[0]!.content);
      }
    }
    const err = new Error(
      `Bundle entry not found: scope=${JSON.stringify(scope)} ` +
      `container=${JSON.stringify(container)} ` +
      `kind=${JSON.stringify(kind)} ` +
      `name=${JSON.stringify(name)} entry=${JSON.stringify(entry)} ` +
      `tenant=${JSON.stringify(tenant)}`,
    ) as Error & { code: string };
    err.code = "ENOENT";
    throw err;
  }

  // ---------------------------------------------------------------------
  // WritableSourcePort (write)
  // ---------------------------------------------------------------------

  async saveDocument(
    scope: string, kind: string, name: string,
    raw: Record<string, unknown>,
    // versionRetention (s-version-prune-record-plane-churn / i-182): mirrors the
    // Py adapter param. No-op TODAY because this MVP adapter doesn't keep a
    // general version history (see the MVP return below) — so there's no
    // record-plane churn to cap. When the versions table lands (the v1.1 TODO),
    // apply it here: keep only the last N snapshots for churn Kinds.
    options?: {
      author?: string; tenant?: string | null; layer?: [string, string];
      versionRetention?: number | null;
    },
  ): Promise<string> {
    await this._runMigrations();

    let tenant = options?.tenant ?? "";
    if (tenant === null) tenant = "";
    if (options?.layer && options.layer[0] === "tenant" && tenant === "") {
      tenant = options.layer[1];
    } else if (options?.layer && options.layer[0] !== "tenant") {
      throw new Error(
        `PostgresSource MVP does not yet support non-tenant layers ` +
        `(got layer=${JSON.stringify(options.layer)}). v1.1 follow-up.`,
      );
    }

    // 1. Try registered writers — bundle path
    let bundleEntries: Record<string, string> | null = null;
    // L3 (s-writer-binary-entries 2026-05-25): binary entries
    // accumulate alongside text. Adapter writes content_binary when
    // contentBytes is set, content when content is a string.
    let bundleBinaryEntries: Record<string, Uint8Array> | null = null;
    for (const w of this._writers) {
      if (w.canWrite(raw)) {
        if (typeof w.serialize === "function") {
          bundleEntries = {};
          bundleBinaryEntries = {};
          for (const f of w.serialize(raw)) {
            if (f.contentBytes !== undefined) {
              bundleBinaryEntries[f.relativePath] = f.contentBytes;
            } else {
              bundleEntries[f.relativePath] = f.content ?? "";
            }
          }
        } else {
          // Writer doesn't implement serialize() — use a virtual
          // DictBundleHandle to capture the entries written.
          const handle = new DictBundleHandle(name, {});
          await w.write(handle, raw);
          bundleEntries = {};
          for (const ep of await handle.iterEntries(true)) {
            bundleEntries[ep] = await handle.readText(ep);
          }
        }
        break;
      }
    }

    const client = await this._pool.connect();
    try {
      await client.query("BEGIN");

      // 2. UPSERT into dna_documents
      await client.query(
        `INSERT INTO "${this._schema}".dna_documents
           (scope, kind, name, content, version, updated_at, tenant)
         VALUES ($1, $2, $3, $4::jsonb, 1, $5, $6)
         ON CONFLICT (scope, kind, name, tenant) DO UPDATE SET
           content = EXCLUDED.content,
           version = "${this._schema}".dna_documents.version + 1,
           updated_at = EXCLUDED.updated_at`,
        [scope, kind, name, JSON.stringify(raw), nowIso(), tenant],
      );

      // 3. Replace bundle entries (full-replace semantics)
      if (bundleEntries !== null) {
        await client.query(
          `DELETE FROM "${this._schema}".dna_bundle_entries
           WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4`,
          [scope, kind, name, tenant],
        );
        const ts = nowIso();
        for (const [entryPath, body] of Object.entries(bundleEntries)) {
          await client.query(
            `INSERT INTO "${this._schema}".dna_bundle_entries
               (scope, kind, name, entry_path, content, updated_at, tenant)
             VALUES ($1, $2, $3, $4, $5, $6, $7)`,
            [scope, kind, name, entryPath, body, ts, tenant],
          );
        }
      }

      await client.query("COMMIT");
    } catch (e) {
      await client.query("ROLLBACK");
      throw e;
    } finally {
      client.release();
    }
    // MVP: no general version history yet (v1.1 adds the versions table). When
    // it lands, insert the snapshot here AND honor options.versionRetention —
    // cap record-plane churn Kinds to the last N (mirror the Py guard +
    // VERSION_CHURN_KINDS; i-182 / s-version-prune-record-plane-churn).
    return "1";
  }

  async deleteDocument(
    scope: string, kind: string, name: string,
    options?: { author?: string; tenant?: string | null; layer?: [string, string] },
  ): Promise<void> {
    await this._runMigrations();
    let tenant = options?.tenant ?? "";
    if (tenant === null) tenant = "";
    if (options?.layer && options.layer[0] === "tenant" && tenant === "") {
      tenant = options.layer[1];
    }
    const client = await this._pool.connect();
    try {
      await client.query("BEGIN");
      await client.query(
        `DELETE FROM "${this._schema}".dna_bundle_entries
         WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4`,
        [scope, kind, name, tenant],
      );
      await client.query(
        `DELETE FROM "${this._schema}".dna_documents
         WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4`,
        [scope, kind, name, tenant],
      );
      await client.query("COMMIT");
    } catch (e) {
      await client.query("ROLLBACK");
      throw e;
    } finally {
      client.release();
    }
  }

  /**
   * MVP no-op: PostgresSource saves directly to dna_documents
   * (no draft state). Future v1.1 may introduce drafts → publish
   * promotion; the method exists today so callers expecting it
   * (e.g. cross-language migrations from Python) don't break.
   */
  async publish(_scope: string, _kind: string, _name: string): Promise<string> {
    return "1";
  }

  // ---------------------------------------------------------------------
  // Versionable capability (basic)
  // ---------------------------------------------------------------------

  async getVersion(
    scope: string, kind: string, name: string, versionId: string,
  ): Promise<Record<string, unknown>> {
    await this._runMigrations();

    // v1.0 — versionId can be either the BIGSERIAL id (numeric) or a
    // semver string. Numeric → exact version row; otherwise → latest
    // matching the semver. Falls back to current dna_documents when
    // no dna_versions row matches (back-compat with pre-Phase-10
    // unversioned writes).
    const isNumeric = /^\d+$/.test(versionId);
    if (isNumeric) {
      const { rows } = await this._pool.query<{ content: Record<string, unknown> | string }>(
        `SELECT content FROM "${this._schema}".dna_versions
         WHERE id=$1 AND scope=$2 AND kind=$3 AND name=$4 LIMIT 1`,
        [Number(versionId), scope, kind, name],
      );
      if (rows.length > 0) return parseJsonish(rows[0]!.content);
    } else {
      const { rows } = await this._pool.query<{ content: Record<string, unknown> | string }>(
        `SELECT content FROM "${this._schema}".dna_versions
         WHERE scope=$1 AND kind=$2 AND name=$3 AND semver=$4 AND tenant=''
         LIMIT 1`,
        [scope, kind, name, versionId],
      );
      if (rows.length > 0) return parseJsonish(rows[0]!.content);
    }
    // Back-compat: fall through to latest dna_documents row
    const { rows: cur } = await this._pool.query<{ content: Record<string, unknown> | string }>(
      `SELECT content FROM "${this._schema}".dna_documents
       WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant='' LIMIT 1`,
      [scope, kind, name],
    );
    if (cur.length === 0) {
      throw new Error(`Version not found: ${scope}/${kind}/${name}@${versionId}`);
    }
    return parseJsonish(cur[0]!.content);
  }

  // ---------------------------------------------------------------------
  // Module catalog versioning (Phase 10 parity)
  // ---------------------------------------------------------------------

  /**
   * Publish an immutable Module version with semver. Mirrors the Python
   * Phase 10 `publishModuleVersion` flow:
   *
   *   1. Reject re-publish of an existing (scope, name, semver, tenant).
   *   2. Insert the row into dna_versions with semver set.
   *   3. Mirror the row to dna_documents (latest-stable view) so
   *      `loadAll` continues returning the freshest content.
   *
   * Throws `VersionAlreadyPublished` when the (scope, kind, name,
   * tenant, semver) tuple already exists. This is the immutability
   * guarantee — once published, that version is frozen.
   */
  async publishModuleVersion(
    scope: string,
    name: string,
    raw: Record<string, unknown>,
    semver: string,
    options?: { tenant?: string | null; author?: string },
  ): Promise<{ id: number; semver: string }> {
    await this._runMigrations();
    const tenant = (options?.tenant ?? "") || "";
    const author = options?.author ?? null;

    const client = await this._pool.connect();
    try {
      await client.query("BEGIN");

      // 1. Immutability check
      const { rows: existing } = await client.query<{ id: number }>(
        `SELECT id FROM "${this._schema}".dna_versions
         WHERE scope=$1 AND kind='Module' AND name=$2 AND tenant=$3 AND semver=$4
         LIMIT 1`,
        [scope, name, tenant, semver],
      );
      if (existing.length > 0) {
        const err = new Error(
          `Module ${name}@${semver} already published to scope ${scope} ` +
          `(tenant=${tenant || "''"}). Bump and republish.`,
        ) as Error & { code: string };
        err.code = "VERSION_ALREADY_PUBLISHED";
        throw err;
      }

      // 2. Determine next monotonic version number
      const { rows: maxRow } = await client.query<{ max: number | null }>(
        `SELECT MAX(version) AS max FROM "${this._schema}".dna_versions
         WHERE scope=$1 AND kind='Module' AND name=$2 AND tenant=$3`,
        [scope, name, tenant],
      );
      const nextVersion = (maxRow[0]?.max ?? 0) + 1;

      // 3. Insert immutable version row
      const { rows: ins } = await client.query<{ id: number }>(
        `INSERT INTO "${this._schema}".dna_versions
           (scope, kind, name, content, version, semver, author, created_at, tenant)
         VALUES ($1, 'Module', $2, $3::jsonb, $4, $5, $6, $7, $8)
         RETURNING id`,
        [scope, name, JSON.stringify(raw), nextVersion, semver, author, nowIso(), tenant],
      );

      // 4. Mirror to dna_documents as latest-stable
      await client.query(
        `INSERT INTO "${this._schema}".dna_documents
           (scope, kind, name, content, version, updated_at, tenant)
         VALUES ($1, 'Module', $2, $3::jsonb, $4, $5, $6)
         ON CONFLICT (scope, kind, name, tenant) DO UPDATE SET
           content = EXCLUDED.content,
           version = EXCLUDED.version,
           updated_at = EXCLUDED.updated_at`,
        [scope, name, JSON.stringify(raw), nextVersion, nowIso(), tenant],
      );

      await client.query("COMMIT");
      return { id: ins[0]!.id, semver };
    } catch (e) {
      await client.query("ROLLBACK");
      throw e;
    } finally {
      client.release();
    }
  }

  /**
   * List published versions of a Module. Returns newest-first by
   * semver lexicographic order (good enough for typical X.Y.Z;
   * v1.1 may add proper semver comparison).
   */
  async listModuleVersions(
    scope: string,
    name: string,
    options?: { tenant?: string | null; includeDeprecated?: boolean },
  ): Promise<Array<{
    id: number;
    semver: string;
    version: number;
    deprecated: boolean;
    deprecationMessage: string | null;
    author: string | null;
    createdAt: string;
  }>> {
    await this._runMigrations();
    const tenant = (options?.tenant ?? "") || "";
    const includeDeprecated = options?.includeDeprecated ?? true;
    const where = includeDeprecated
      ? `WHERE scope=$1 AND kind='Module' AND name=$2 AND tenant=$3 AND semver IS NOT NULL`
      : `WHERE scope=$1 AND kind='Module' AND name=$2 AND tenant=$3 AND semver IS NOT NULL AND deprecated=false`;
    const { rows } = await this._pool.query<{
      id: number;
      semver: string;
      version: number;
      deprecated: boolean;
      deprecation_message: string | null;
      author: string | null;
      created_at: string;
    }>(
      `SELECT id, semver, version, deprecated, deprecation_message, author, created_at
       FROM "${this._schema}".dna_versions ${where}
       ORDER BY semver DESC`,
      [scope, name, tenant],
    );
    return rows.map((r) => ({
      id: r.id,
      semver: r.semver,
      version: r.version,
      deprecated: r.deprecated,
      deprecationMessage: r.deprecation_message,
      author: r.author,
      createdAt: r.created_at,
    }));
  }

  /**
   * Mark a published Module version as deprecated. The row stays
   * (immutability), but listModuleVersions can filter it out via
   * `includeDeprecated: false`.
   */
  async deprecateModuleVersion(
    scope: string,
    name: string,
    semver: string,
    message?: string,
    options?: { tenant?: string | null },
  ): Promise<void> {
    await this._runMigrations();
    const tenant = (options?.tenant ?? "") || "";
    const result = await this._pool.query(
      `UPDATE "${this._schema}".dna_versions
       SET deprecated=true, deprecation_message=$1
       WHERE scope=$2 AND kind='Module' AND name=$3 AND tenant=$4 AND semver=$5`,
      [message ?? null, scope, name, tenant, semver],
    );
    if ((result.rowCount ?? 0) === 0) {
      throw new Error(
        `Module ${name}@${semver} not found in scope ${scope} ` +
        `(tenant=${tenant || "''"}).`,
      );
    }
  }
}

/** Postgres returns JSONB as parsed object; legacy text columns as string. */
function parseJsonish(c: Record<string, unknown> | string): Record<string, unknown> {
  if (typeof c === "string") return JSON.parse(c);
  return c;
}

// Two-planes F2 — RecordStorePort conformance BY COMPOSITION (compile-time;
// lives in src because tsconfig excludes tests/ from `tsc --noEmit`). The
// PG TS adapter provides the WRITE half (`saveDocument`|`deleteDocument`);
// the read half (`query`|`count` push-down) is Py-only this phase — full
// conformance arrives with the PG TS push-down (F2.5+). Never called.
function _pgRecordStoreWriteHalfConformance(
  src: PostgresSource,
): Pick<import("../../kernel/protocols.js").RecordStorePort, "saveDocument" | "deleteDocument"> {
  return src;
}
void _pgRecordStoreWriteHalfConformance;
