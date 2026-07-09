/**
 * Forward-only numbered migrations for the sqlite-vec search store (TS twin of
 * `dna/adapters/search/migrations.py`).
 *
 * The debt rsh-memory-similarity-evolution (f-embeddings-ddl-debt) calls out:
 * the embeddings sidecar had no owning migration upstream. Here the store's
 * schema is OWNED by a numbered, append-only, idempotent migration recorded in
 * the store's own `schema_migrations` control table. The vec0 virtual table
 * needs the embedding width baked in, so `buildMigrations(dims)` interpolates
 * it — the migration still owns the DDL, it just parametrizes the vector width.
 *
 * The TS SDK has no shared migration runner (only the Postgres source has its
 * own), so {@link runSearchMigrations} is the small local analog of the Python
 * `run_migrations` contract: same forward-only/append-only/idempotent-boot
 * semantics, over the synchronous {@link SearchDb} surface.
 */
import type { SearchDb } from "./driver.js";

/** version → one executescript payload (SQLite dialect). Parity with the Py
 *  `build_migrations(dims)`. */
export function buildMigrations(dims: number): Record<number, string> {
  if (dims < 1) throw new Error(`embedding dims must be positive, got ${dims}`);
  return {
    1: `
CREATE TABLE IF NOT EXISTS search_docs (
    rowid      INTEGER PRIMARY KEY AUTOINCREMENT,
    scope      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL,
    tenant     TEXT NOT NULL DEFAULT '',
    text_hash  TEXT NOT NULL,
    title      TEXT,
    snippet    TEXT,
    text       TEXT NOT NULL,
    UNIQUE (scope, kind, name, tenant)
);
CREATE INDEX IF NOT EXISTS search_docs_lookup
    ON search_docs (scope, kind, tenant);
CREATE VIRTUAL TABLE IF NOT EXISTS search_vec USING vec0(
    doc_rowid INTEGER PRIMARY KEY,
    embedding float[${dims}]
);
CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(text);
CREATE TABLE IF NOT EXISTS search_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
`,
  };
}

/**
 * Apply every pending migration in ascending version order (forward-only,
 * append-only, idempotent boot). Returns the versions applied by THIS call —
 * `[]` when the store is already up to date (the idempotent re-boot case).
 */
export function runSearchMigrations(
  db: SearchDb,
  migrations: Record<number, string>,
): number[] {
  db.exec(
    "CREATE TABLE IF NOT EXISTS schema_migrations "
      + "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)",
  );
  const applied = new Set(
    db.all<{ version: number }>("SELECT version FROM schema_migrations").map(
      (r) => r.version,
    ),
  );
  const appliedNow: number[] = [];
  const versions = Object.keys(migrations)
    .map(Number)
    .sort((a, b) => a - b);
  for (const version of versions) {
    if (applied.has(version)) continue;
    db.exec(migrations[version]!);
    db.run("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)", [
      version,
      new Date().toISOString(),
    ]);
    appliedNow.push(version);
  }
  return appliedNow;
}
