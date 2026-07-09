/**
 * SqliteVecRecordSearchProvider — the embeddable default RecordSearchProvider
 * (TS twin of `dna/adapters/search/sqlite_vec.py`).
 *
 * The FIRST real implementation of the `RecordSearchProvider` port on the TS
 * side. Hybrid search inside one SQLite file per scope, offline, no server:
 *
 *   - dense   — sqlite-vec `vec0` KNN over `kernel.embed()` vectors (the
 *               deterministic `FakeEmbeddingProvider` floor by default).
 *   - lexical — FTS5 BM25 over the same text.
 *   - fusion  — Reciprocal Rank Fusion (`reciprocalRankFusion`, the pure
 *               function shared with the Python twin).
 *
 * The store schema is OWNED by a numbered migration (`migrations.ts`), closing
 * f-embeddings-ddl-debt. Overlay/tenant-aware: `tenant` is a column ('' = base);
 * a tenant search reads base ∪ overlay and the overlay row shadows the base row
 * for the same `(kind, name)`.
 *
 * SQLite access goes through {@link openSearchDb} (bun:sqlite or node:sqlite);
 * sqlite-vec is an OPTIONAL peer dep (`sqlite-vec`), never in the default graph.
 * Both are exercised by the shared record-search conformance kit with the fake
 * embedder, offline.
 */
import { sha256 } from "js-sha256";

import { DEFAULT_RRF_K, reciprocalRankFusion } from "./rrf.js";
import { buildMigrations, runSearchMigrations } from "./migrations.js";
import { openSearchDb, serializeF32, type SearchDb } from "./driver.js";

/** The slice of the kernel this provider needs (embedding surface). */
export interface EmbeddingKernel {
  embed(texts: string[]): Promise<number[][]>;
  readonly embeddingDims: number;
  readonly embeddingModelId: string;
}

/** A record to index. `text` is used verbatim if present; otherwise derived
 *  from `raw` via {@link documentText}. */
export interface SearchRecord {
  scope: string;
  kind: string;
  name: string;
  tenant?: string;
  text?: string;
  raw?: Record<string, unknown>;
  title?: string;
  snippet?: string;
}

export interface SearchHit extends Record<string, unknown> {
  scope: string;
  kind: string;
  name: string;
  score: number;
}

/** An id to delete: `{ scope, kind, name, tenant? }`. */
export interface RecordId {
  scope: string;
  kind: string;
  name: string;
  tenant?: string;
}

const OVERFETCH = 4;
const MIN_CANDIDATES = 40;

/** Derive the searchable text blob for a raw document — every string value in
 *  `spec` plus `metadata.name`, in document order (parity with the Python
 *  `document_text`). */
export function documentText(raw: Record<string, unknown>): string {
  const parts: string[] = [];
  const meta = (raw.metadata as Record<string, unknown> | undefined) ?? {};
  const name = (meta.name as string | undefined) ?? (raw.name as string | undefined);
  if (typeof name === "string") parts.push(name);
  const walk = (node: unknown): void => {
    if (typeof node === "string") parts.push(node);
    else if (Array.isArray(node)) node.forEach(walk);
    else if (node && typeof node === "object") Object.values(node).forEach(walk);
  };
  walk(raw.spec ?? {});
  return parts.filter((p) => p).join("\n");
}

export class SqliteVecRecordSearchProvider {
  private readonly kernel: EmbeddingKernel;
  private readonly dbDir: string | null;
  private readonly singlePath: string | null;
  private readonly rrfK: number;
  private readonly conns = new Map<string, SearchDb>();

  constructor(
    kernel: EmbeddingKernel,
    opts: { dbDir?: string; dbPath?: string; rrfK?: number } = {},
  ) {
    this.kernel = kernel;
    let dbDir = opts.dbDir ?? null;
    if (dbDir === null && !opts.dbPath) {
      const env = (globalThis as { process?: { env?: Record<string, string> } })
        .process?.env;
      dbDir = env?.DNA_SEARCH_DIR ?? ".dna-search";
    }
    this.dbDir = opts.dbPath ? null : dbDir;
    this.singlePath = opts.dbPath ?? null;
    this.rrfK = opts.rrfK ?? DEFAULT_RRF_K;
  }

  // ------------------------------------------------------------------
  // store / schema (migration-owned)
  // ------------------------------------------------------------------

  private pathFor(scope: string): string {
    if (this.singlePath) return this.singlePath;
    const safe = scope.replace(/[/\\]/g, "_");
    return `${this.dbDir}/${safe}.db`;
  }

  private async connFor(scope: string): Promise<SearchDb> {
    const path = this.pathFor(scope);
    const existing = this.conns.get(path);
    if (existing) return existing;
    if (this.dbDir && !this.singlePath) await ensureDir(this.dbDir);
    const db = await openSearchDb(path);
    runSearchMigrations(db, buildMigrations(this.kernel.embeddingDims));
    this.pinIdentity(db);
    this.conns.set(path, db);
    return db;
  }

  private pinIdentity(db: SearchDb): void {
    const dims = String(this.kernel.embeddingDims);
    const modelId = this.kernel.embeddingModelId;
    const rows = db.all<{ key: string; value: string }>(
      "SELECT key, value FROM search_meta",
    );
    if (rows.length === 0) {
      db.run("INSERT INTO search_meta (key, value) VALUES (?, ?)", ["embedding_dims", dims]);
      db.run("INSERT INTO search_meta (key, value) VALUES (?, ?)", ["embedding_model_id", modelId]);
      return;
    }
    const meta = Object.fromEntries(rows.map((r) => [r.key, r.value]));
    if (meta.embedding_dims !== dims || meta.embedding_model_id !== modelId) {
      throw new Error(
        `search store was built for embedding space (${meta.embedding_model_id}, `
          + `dims=${meta.embedding_dims}) but the active provider is (${modelId}, `
          + `dims=${dims}) — the vectors are incomparable. Use a fresh store dir `
          + "or re-index.",
      );
    }
  }

  // ------------------------------------------------------------------
  // index / delete
  // ------------------------------------------------------------------

  /** Index (upsert) records into their scope's store. Idempotent by text hash
   *  (re-indexing unchanged text is skipped). Returns the count actually
   *  (re)embedded. */
  async index(records: SearchRecord[]): Promise<number> {
    if (records.length === 0) return 0;
    const pending = records.map((rec) => {
      const text = rec.text ?? documentText(rec.raw ?? {});
      return { rec, text, hash: sha256(text) };
    });

    const toEmbed: typeof pending = [];
    for (const item of pending) {
      const db = await this.connFor(item.rec.scope);
      const existing = db.get<{ text_hash: string }>(
        "SELECT text_hash FROM search_docs WHERE scope=? AND kind=? AND name=? AND tenant=?",
        [item.rec.scope, item.rec.kind, item.rec.name, item.rec.tenant ?? ""],
      );
      if (existing && existing.text_hash === item.hash) continue;
      toEmbed.push(item);
    }
    if (toEmbed.length === 0) return 0;

    const vectors = await this.kernel.embed(toEmbed.map((i) => i.text));
    toEmbed.forEach((item, i) => this.upsert(item.rec, item.text, item.hash, vectors[i]!));
    return toEmbed.length;
  }

  private upsert(
    rec: SearchRecord, text: string, textHash: string, vector: number[],
  ): void {
    const db = this.conns.get(this.pathFor(rec.scope))!;
    const tenant = rec.tenant ?? "";
    const title = rec.title ?? null;
    const snippet = rec.snippet ?? snippetOf(text);
    const row = db.get<{ rowid: number }>(
      "SELECT rowid FROM search_docs WHERE scope=? AND kind=? AND name=? AND tenant=?",
      [rec.scope, rec.kind, rec.name, tenant],
    );
    let rowid: number;
    if (!row) {
      const info = db.run(
        "INSERT INTO search_docs (scope, kind, name, tenant, text_hash, title, snippet, text) "
          + "VALUES (?,?,?,?,?,?,?,?)",
        [rec.scope, rec.kind, rec.name, tenant, textHash, title, snippet, text],
      );
      rowid = info.lastInsertRowid;
    } else {
      rowid = row.rowid;
      db.run("UPDATE search_docs SET text_hash=?, title=?, snippet=?, text=? WHERE rowid=?", [
        textHash, title, snippet, text, rowid,
      ]);
      db.run("DELETE FROM search_vec WHERE doc_rowid=?", [BigInt(rowid)]);
      db.run("DELETE FROM search_fts WHERE rowid=?", [BigInt(rowid)]);
    }
    // vec0 (and fts5) require an INTEGER rowid binding — node:sqlite binds a JS
    // number as a double and vec0 rejects it, so pass BigInt (both drivers OK).
    db.run("INSERT INTO search_vec (doc_rowid, embedding) VALUES (?, ?)", [
      BigInt(rowid), serializeF32(vector),
    ]);
    db.run("INSERT INTO search_fts (rowid, text) VALUES (?, ?)", [BigInt(rowid), text]);
  }

  /** Delete indexed records. Returns the number of rows removed. */
  async delete(ids: RecordId[]): Promise<number> {
    let removed = 0;
    for (const id of ids) {
      const db = await this.connFor(id.scope);
      const row = db.get<{ rowid: number }>(
        "SELECT rowid FROM search_docs WHERE scope=? AND kind=? AND name=? AND tenant=?",
        [id.scope, id.kind, id.name, id.tenant ?? ""],
      );
      if (!row) continue;
      const rowid = BigInt(row.rowid);
      db.run("DELETE FROM search_vec WHERE doc_rowid=?", [rowid]);
      db.run("DELETE FROM search_fts WHERE rowid=?", [rowid]);
      db.run("DELETE FROM search_docs WHERE rowid=?", [rowid]);
      removed += 1;
    }
    return removed;
  }

  // ------------------------------------------------------------------
  // search (RecordSearchProvider)
  // ------------------------------------------------------------------

  async search(opts: {
    scope: string;
    queryText: string;
    kind?: string | null;
    k?: number;
    tenant?: string;
  }): Promise<SearchHit[]> {
    const { scope, queryText } = opts;
    const kind = opts.kind ?? null;
    const k = opts.k ?? 10;
    const tenant = opts.tenant ?? "";
    if (!queryText.trim() || k <= 0) return [];
    const db = await this.connFor(scope);
    const overfetch = Math.max(MIN_CANDIDATES, k * OVERFETCH);

    const queryVec = (await this.kernel.embed([queryText]))[0]!;
    let denseRanked: number[] = [];
    if (queryVec.some((x) => x !== 0)) {
      denseRanked = db
        .all<{ doc_rowid: number }>(
          "SELECT doc_rowid FROM search_vec WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
          [serializeF32(queryVec), overfetch],
        )
        .map((r) => r.doc_rowid);
    }

    let lexicalRanked: number[] = [];
    const ftsQuery = ftsQueryOf(queryText);
    if (ftsQuery) {
      try {
        lexicalRanked = db
          .all<{ rowid: number }>(
            "SELECT rowid FROM search_fts WHERE search_fts MATCH ? ORDER BY bm25(search_fts) LIMIT ?",
            [ftsQuery, overfetch],
          )
          .map((r) => r.rowid);
      } catch {
        lexicalRanked = [];
      }
    }
    if (denseRanked.length === 0 && lexicalRanked.length === 0) return [];

    const fused = reciprocalRankFusion(
      [denseRanked.map(String), lexicalRanked.map(String)],
      this.rrfK,
    );
    const densePos = new Map(denseRanked.map((r, i) => [r, i + 1]));
    const lexicalPos = new Map(lexicalRanked.map((r, i) => [r, i + 1]));

    const rowids = fused.map(([rid]) => Number(rid));
    const meta = this.resolveMeta(db, rowids);
    const best = new Map<string, SearchHit & { _tenant: string }>();
    for (const [rid, score] of fused) {
      const rowid = Number(rid);
      const m = meta.get(rowid);
      if (!m) continue;
      if (kind !== null && m.kind !== kind) continue;
      const rowTenant = m.tenant ?? "";
      if (rowTenant !== "" && rowTenant !== (tenant || "")) continue; // other tenant — never leaks
      const key = `${m.kind} ${m.name}`;
      const prev = best.get(key);
      const hit = makeHit(scope, m, score, densePos.get(rowid), lexicalPos.get(rowid));
      if (!prev) {
        best.set(key, hit);
      } else {
        const thisIsOverlay = rowTenant !== "" && rowTenant === (tenant || "");
        if (thisIsOverlay && prev._tenant === "") best.set(key, hit);
      }
    }
    const hits = [...best.values()].sort((a, b) => b.score - a.score);
    for (const h of hits) delete (h as { _tenant?: string })._tenant;
    return hits.slice(0, k);
  }

  private resolveMeta(db: SearchDb, rowids: number[]): Map<number, MetaRow> {
    if (rowids.length === 0) return new Map();
    const placeholders = rowids.map(() => "?").join(",");
    const rows = db.all<MetaRow>(
      `SELECT rowid, scope, kind, name, tenant, title, snippet FROM search_docs `
        + `WHERE rowid IN (${placeholders})`,
      rowids,
    );
    return new Map(rows.map((r) => [r.rowid, r]));
  }

  close(): void {
    for (const db of this.conns.values()) {
      try {
        db.close();
      } catch {
        /* ignore */
      }
    }
    this.conns.clear();
  }
}

interface MetaRow {
  rowid: number;
  scope: string;
  kind: string;
  name: string;
  tenant: string | null;
  title: string | null;
  snippet: string | null;
}

function makeHit(
  scope: string, m: MetaRow, score: number,
  rankDense?: number, rankLexical?: number,
): SearchHit & { _tenant: string } {
  const hit: SearchHit & { _tenant: string } = {
    scope, kind: m.kind, name: m.name, score, _tenant: m.tenant ?? "",
  };
  if (m.title) hit.title = m.title;
  if (m.snippet) hit.snippet = m.snippet;
  if (rankDense !== undefined) hit.rank_dense = rankDense;
  if (rankLexical !== undefined) hit.rank_lexical = rankLexical;
  return hit;
}

function snippetOf(text: string, maxLen = 200): string {
  const flat = text.split(/\s+/).filter(Boolean).join(" ");
  return flat.length > maxLen ? flat.slice(0, maxLen) + "…" : flat;
}

/** OR of quoted alphanumeric tokens — parity with the Python `_fts_query`. */
function ftsQueryOf(queryText: string): string {
  const tokens = queryText.toLowerCase().match(/[a-z0-9]+/g) ?? [];
  return tokens.map((t) => `"${t}"`).join(" OR ");
}

async function ensureDir(dir: string): Promise<void> {
  try {
    const fs = (await import("node:fs")) as {
      mkdirSync(p: string, o: { recursive: boolean }): void;
    };
    fs.mkdirSync(dir, { recursive: true });
  } catch {
    /* best effort — open will surface a real failure */
  }
}
