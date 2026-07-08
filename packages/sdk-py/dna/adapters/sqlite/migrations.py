"""Forward-only numbered migrations for SqliteSource."""

MIGRATIONS: dict[int, str] = {
    1: """
CREATE TABLE IF NOT EXISTS documents (
    scope      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL,
    content    TEXT NOT NULL,
    version    INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (scope, kind, name)
);

CREATE TABLE IF NOT EXISTS versions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    scope      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL,
    content    TEXT NOT NULL,
    version    INTEGER NOT NULL,
    is_draft   INTEGER NOT NULL DEFAULT 1,
    author     TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
""",

    2: """
CREATE TABLE IF NOT EXISTS layer_documents (
    scope      TEXT NOT NULL,
    layer_id   TEXT NOT NULL,
    layer_value TEXT NOT NULL,
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL,
    content    TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (scope, layer_id, layer_value, kind, name)
);
""",

    3: """
CREATE TABLE IF NOT EXISTS bundle_entries (
    scope       TEXT NOT NULL,
    kind        TEXT NOT NULL,
    name        TEXT NOT NULL,
    entry_path  TEXT NOT NULL,
    content     TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (scope, kind, name, entry_path)
);

CREATE INDEX IF NOT EXISTS bundle_entries_scope_kind_idx
    ON bundle_entries (scope, kind);
""",

    4: """
-- Phase 2c: tenant first-class column on all doc tables.
-- NULL means "global / no tenant binding" (back-compat with pre-Phase-2c
-- rows). New TENANTED-kind writes must populate tenant; the kernel
-- enforces this via KindPort.scope before reaching the adapter.
ALTER TABLE documents      ADD COLUMN tenant TEXT;
ALTER TABLE versions       ADD COLUMN tenant TEXT;
ALTER TABLE bundle_entries ADD COLUMN tenant TEXT;

-- Composite indexes for tenant-scoped queries (the most common pattern
-- once multi-tenant routing kicks in).
CREATE INDEX IF NOT EXISTS documents_tenant_idx
    ON documents (tenant, scope, kind, name);
CREATE INDEX IF NOT EXISTS bundle_entries_tenant_idx
    ON bundle_entries (tenant, scope, kind);
""",

    5: """
-- Phase 10g: semver column on versions for the Module catalog.
-- NULL means "no semver published" (Phase 9 unversioned path or
-- non-Module kinds). Partial unique index enforces immutability
-- only when semver is set; non-Module rows + unversioned Modules
-- skip the constraint entirely.
ALTER TABLE versions ADD COLUMN semver TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS versions_semver_unique
    ON versions (scope, kind, name, tenant, semver)
    WHERE semver IS NOT NULL;

CREATE INDEX IF NOT EXISTS versions_module_lookup
    ON versions (kind, scope, tenant, semver)
    WHERE kind = 'Module' AND semver IS NOT NULL;
""",

    6: """
-- Phase 16 cleanup: Module Kind class deleted, Genome replaces it as
-- the catalog-root identity Kind. Drop the v5 ``kind = 'Module'`` partial
-- index and recreate it as ``kind = 'Genome'``. Existing rows (if any)
-- are not migrated here — Phase 16 fixtures already publish under
-- ``kind = 'Genome'`` and the older ``kind = 'Module'`` rows would only
-- exist on databases populated before Phase 16, where ``load_bootstrap_docs``
-- no longer surfaces Module kind anyway.
DROP INDEX IF EXISTS versions_module_lookup;

CREATE INDEX IF NOT EXISTS versions_package_lookup
    ON versions (kind, scope, tenant, semver)
    WHERE kind = 'Genome' AND semver IS NOT NULL;
""",

    7: """
-- s-sqlite-source-query-impl (2026-05-14) — expression indices on hot
-- spec fields. SQLite has supported expression indices since 3.9, with
-- json_extract being deterministic enough to qualify. Without these,
-- WHERE json_extract(content, '$.spec.status') = 'X' does a full table
-- scan; with them, it's index-resolved.
--
-- Same 3 hot fields used by the Postgres adapter (status, feature,
-- updated_at). SQLite has no GIN equivalent — arbitrary spec field
-- queries fall back to scan. The 3 indexed fields cover ~95% of
-- observed Studio request patterns.
CREATE INDEX IF NOT EXISTS docs_status_idx
    ON documents (scope, kind, json_extract(content, '$.spec.status'));

CREATE INDEX IF NOT EXISTS docs_feature_idx
    ON documents (scope, kind, json_extract(content, '$.spec.feature'));

CREATE INDEX IF NOT EXISTS docs_updated_at_idx
    ON documents (scope, kind, json_extract(content, '$.spec.updated_at'));
""",

    8: """
-- s-sqlite-bundle-tenant-pk — bundle_entries' PRIMARY KEY must include tenant.
-- It was created (migration 3) as (scope, kind, name, entry_path) BEFORE the
-- `tenant` column existed (migration 4 ALTER ADD COLUMN), and SQLite can't add
-- a column to a PK via ALTER. The result: two tenants writing the same
-- (scope, kind, name, entry_path) collide — the second UPSERT overwrites the
-- first. Postgres keys on the full 5-tuple; this brings SQLite to parity
-- (i-083 flagged it as a deeper limitation to fix here).
--
-- SQLite can't ALTER a PRIMARY KEY in place, so rebuild the table. tenant
-- becomes NOT NULL DEFAULT '' — '' is the canonical "global / no tenant"
-- sentinel (write_bundle_entry already coalesces None→''). A nullable PK
-- column would let SQLite treat each NULL as distinct and defeat the upsert.
CREATE TABLE bundle_entries_v8 (
    scope       TEXT NOT NULL,
    kind        TEXT NOT NULL,
    name        TEXT NOT NULL,
    entry_path  TEXT NOT NULL,
    content     TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    tenant      TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (scope, kind, name, entry_path, tenant)
);

INSERT OR IGNORE INTO bundle_entries_v8
    (scope, kind, name, entry_path, content, updated_at, tenant)
SELECT scope, kind, name, entry_path, content, updated_at, COALESCE(tenant, '')
FROM bundle_entries;

DROP TABLE bundle_entries;
ALTER TABLE bundle_entries_v8 RENAME TO bundle_entries;

CREATE INDEX IF NOT EXISTS bundle_entries_scope_kind_idx
    ON bundle_entries (scope, kind);
CREATE INDEX IF NOT EXISTS bundle_entries_tenant_idx
    ON bundle_entries (tenant, scope, kind);
""",
}
