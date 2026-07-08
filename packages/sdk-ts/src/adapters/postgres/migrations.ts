/**
 * Postgres schema migrations for the SDK adapter.
 *
 * 1:1 parity (subset) with python/dna/adapters/postgres/source.py.
 * v1.0 cut ships migrations 1-3:
 *
 *   v1 — initial: dna_documents, dna_bundle_entries
 *   v2 — dna_layer_documents (layer overlays)
 *   v3 — tenant column on documents + bundle_entries (Phase 2c)
 *
 * Future migrations (versions table, lockfile, eventbus) land here as
 * the TS Postgres adapter grows toward full Python parity.
 */

export const MIGRATIONS: Record<number, string[]> = {
  1: [
    `CREATE TABLE IF NOT EXISTS {schema}.dna_documents (
       scope      TEXT NOT NULL,
       kind       TEXT NOT NULL,
       name       TEXT NOT NULL,
       content    JSONB NOT NULL,
       version    INTEGER NOT NULL DEFAULT 1,
       updated_at TEXT NOT NULL,
       PRIMARY KEY (scope, kind, name)
     )`,
    `CREATE TABLE IF NOT EXISTS {schema}.dna_bundle_entries (
       scope      TEXT NOT NULL,
       kind       TEXT NOT NULL,
       name       TEXT NOT NULL,
       entry_path TEXT NOT NULL,
       content    TEXT NOT NULL,
       updated_at TEXT NOT NULL,
       PRIMARY KEY (scope, kind, name, entry_path)
     )`,
    `CREATE INDEX IF NOT EXISTS dna_bundle_entries_scope_kind_idx
       ON {schema}.dna_bundle_entries (scope, kind)`,
  ],
  2: [
    `CREATE TABLE IF NOT EXISTS {schema}.dna_layer_documents (
       scope       TEXT NOT NULL,
       layer_id    TEXT NOT NULL,
       layer_value TEXT NOT NULL,
       kind        TEXT NOT NULL,
       name        TEXT NOT NULL,
       content     JSONB NOT NULL,
       updated_at  TEXT NOT NULL,
       PRIMARY KEY (scope, layer_id, layer_value, kind, name)
     )`,
  ],
  3: [
    `ALTER TABLE {schema}.dna_documents ADD COLUMN IF NOT EXISTS tenant TEXT NOT NULL DEFAULT ''`,
    `ALTER TABLE {schema}.dna_bundle_entries ADD COLUMN IF NOT EXISTS tenant TEXT NOT NULL DEFAULT ''`,
    `ALTER TABLE {schema}.dna_documents DROP CONSTRAINT IF EXISTS dna_documents_pkey`,
    `ALTER TABLE {schema}.dna_documents ADD PRIMARY KEY (scope, kind, name, tenant)`,
    `ALTER TABLE {schema}.dna_bundle_entries DROP CONSTRAINT IF EXISTS dna_bundle_entries_pkey`,
    `ALTER TABLE {schema}.dna_bundle_entries ADD PRIMARY KEY (scope, kind, name, entry_path, tenant)`,
  ],
  4: [
    // v1.0 — Module catalog versioning (Phase 10 parity).
    //
    // `dna_versions` stores immutable per-version snapshots. Module
    // catalog publish flow (publishModuleVersion) inserts here; list/
    // deprecation queries read from here. Same semver pinning rules
    // as the Python adapter — `(scope, kind, name, tenant, semver)`
    // is unique when semver is non-NULL (immutable releases).
    `CREATE TABLE IF NOT EXISTS {schema}.dna_versions (
       id          BIGSERIAL PRIMARY KEY,
       scope       TEXT NOT NULL,
       kind        TEXT NOT NULL,
       name        TEXT NOT NULL,
       content     JSONB NOT NULL,
       version     INTEGER NOT NULL,
       semver      TEXT,
       deprecated  BOOLEAN NOT NULL DEFAULT false,
       deprecation_message TEXT,
       author      TEXT,
       created_at  TEXT NOT NULL,
       tenant      TEXT NOT NULL DEFAULT ''
     )`,
    `CREATE UNIQUE INDEX IF NOT EXISTS dna_versions_semver_unique
       ON {schema}.dna_versions (scope, kind, name, tenant, semver)
       WHERE semver IS NOT NULL`,
    `CREATE INDEX IF NOT EXISTS dna_versions_module_lookup
       ON {schema}.dna_versions (kind, scope, tenant, semver)
       WHERE kind = 'Module' AND semver IS NOT NULL`,
    `CREATE INDEX IF NOT EXISTS dna_versions_scope_kind_name_idx
       ON {schema}.dna_versions (scope, kind, name, tenant)`,
  ],
};
