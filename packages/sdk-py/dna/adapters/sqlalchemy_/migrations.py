"""SqlAlchemySource schema payloads — the SAME tables the raw adapters built.

Moved VERBATIM from the retired raw SQL adapters (s-retire-raw-sql-adapters):

  - ``PG_MIGRATIONS``     — formerly ``dna.adapters.postgres.source._MIGRATIONS``
    (list[str] of statements per version, ``{schema}`` placeholder, one
    transaction per version).
  - ``SQLITE_MIGRATIONS`` — formerly ``dna.adapters.sqlite.migrations.MIGRATIONS``
    (one multi-statement executescript payload per version).

The payload SHAPES stay deliberately different (see ``adapters/_migrations.py``
for why the shared runner takes callables instead of flattening them). Version
numbers are append-only and already recorded in existing control tables
(SQLite ``schema_migrations``, Postgres ``{schema}.dna_schema_migrations``) —
NEVER edit an existing version, add a new one. A DB bootstrapped by the raw
adapters is indistinguishable from one bootstrapped here: switching to
``SqlAlchemySource`` is pure instantiation, zero data migration.
"""
from __future__ import annotations

# Migrations: each value is a list of individual SQL statements (asyncpg
# does not support multiple statements in a single execute call).
PG_MIGRATIONS: dict[int, list[str]] = {
    1: [
        """
CREATE TABLE IF NOT EXISTS {schema}.dna_documents (
    scope      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL,
    content    TEXT NOT NULL,
    version    INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (scope, kind, name)
)
""",
        """
CREATE TABLE IF NOT EXISTS {schema}.dna_versions (
    id         SERIAL PRIMARY KEY,
    scope      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL,
    content    TEXT NOT NULL,
    version    INTEGER NOT NULL,
    is_draft   BOOLEAN NOT NULL DEFAULT true,
    author     TEXT,
    created_at TEXT NOT NULL
)
""",
        """
CREATE TABLE IF NOT EXISTS {schema}.dna_layer_documents (
    scope       TEXT NOT NULL,
    layer_id    TEXT NOT NULL,
    layer_value TEXT NOT NULL,
    kind        TEXT NOT NULL,
    name        TEXT NOT NULL,
    content     TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (scope, layer_id, layer_value, kind, name)
)
""",
    ],
    2: [
        """
CREATE TABLE IF NOT EXISTS {schema}.dna_bundle_entries (
    scope       TEXT NOT NULL,
    kind        TEXT NOT NULL,
    name        TEXT NOT NULL,
    entry_path  TEXT NOT NULL,
    content     TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (scope, kind, name, entry_path)
)
""",
        """
CREATE INDEX IF NOT EXISTS dna_bundle_entries_scope_kind_idx
    ON {schema}.dna_bundle_entries (scope, kind)
""",
    ],
    3: [
        # Phase 8a — tenant first-class column. Empty string ('') means
        # "legacy/global write" (back-compat with pre-Phase-2c rows). The
        # default lets us include tenant in the PRIMARY KEY without NULLs
        # killing uniqueness (Postgres treats NULLs as distinct).
        # New TENANTED writes populate tenant via the KindPort.scope check
        # in the kernel.
        """
ALTER TABLE {schema}.dna_documents
    ADD COLUMN IF NOT EXISTS tenant TEXT NOT NULL DEFAULT ''
""",
        """
ALTER TABLE {schema}.dna_versions
    ADD COLUMN IF NOT EXISTS tenant TEXT NOT NULL DEFAULT ''
""",
        """
ALTER TABLE {schema}.dna_bundle_entries
    ADD COLUMN IF NOT EXISTS tenant TEXT NOT NULL DEFAULT ''
""",
        # Swap PKs to include tenant. Same (scope, kind, name) across two
        # tenants is now legal. NULLs not in play because of the default.
        """
ALTER TABLE {schema}.dna_documents DROP CONSTRAINT IF EXISTS dna_documents_pkey
""",
        """
ALTER TABLE {schema}.dna_documents
    ADD CONSTRAINT dna_documents_pkey
    PRIMARY KEY (scope, kind, name, tenant)
""",
        """
ALTER TABLE {schema}.dna_bundle_entries DROP CONSTRAINT IF EXISTS dna_bundle_entries_pkey
""",
        """
ALTER TABLE {schema}.dna_bundle_entries
    ADD CONSTRAINT dna_bundle_entries_pkey
    PRIMARY KEY (scope, kind, name, entry_path, tenant)
""",
        # Composite indexes for tenant-scoped queries.
        """
CREATE INDEX IF NOT EXISTS dna_documents_tenant_idx
    ON {schema}.dna_documents (tenant, scope, kind, name)
""",
        """
CREATE INDEX IF NOT EXISTS dna_versions_tenant_idx
    ON {schema}.dna_versions (tenant, scope, kind, name)
""",
        """
CREATE INDEX IF NOT EXISTS dna_bundle_entries_tenant_idx
    ON {schema}.dna_bundle_entries (tenant, scope, kind)
""",
    ],
    4: [
        # Phase 10g — semver column on dna_versions for the Module
        # catalog. NULL means "no semver published" (Phase 9 unversioned
        # path or non-Module kinds). When set, (scope, kind, name,
        # tenant, semver) is unique — that's what immutable releases
        # mean.
        """
ALTER TABLE {schema}.dna_versions ADD COLUMN IF NOT EXISTS semver TEXT
""",
        """
CREATE UNIQUE INDEX IF NOT EXISTS dna_versions_semver_unique
    ON {schema}.dna_versions (scope, kind, name, tenant, semver)
    WHERE semver IS NOT NULL
""",
        """
CREATE INDEX IF NOT EXISTS dna_versions_module_lookup
    ON {schema}.dna_versions (kind, scope, tenant, semver)
    WHERE kind = 'Module' AND semver IS NOT NULL
""",
    ],
    5: [
        # Phase 15.1 — KernelEventBus (Outbox + LISTEN/NOTIFY).
        """
CREATE TABLE IF NOT EXISTS {schema}.dna_outbox (
    id           BIGSERIAL PRIMARY KEY,
    occurred_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    scope        TEXT NOT NULL,
    tenant       TEXT NOT NULL DEFAULT '',
    kind         TEXT NOT NULL,
    name         TEXT NOT NULL,
    op           TEXT NOT NULL,
    doc_version  INTEGER NOT NULL,
    actor        TEXT,
    cause        TEXT
)
""",
        """
CREATE INDEX IF NOT EXISTS dna_outbox_scope_id_idx
    ON {schema}.dna_outbox (scope, tenant, id)
""",
        """
CREATE INDEX IF NOT EXISTS dna_outbox_occurred_at_idx
    ON {schema}.dna_outbox (occurred_at)
""",
        """
CREATE TABLE IF NOT EXISTS {schema}.dna_versions_seq (
    scope    TEXT NOT NULL,
    tenant   TEXT NOT NULL DEFAULT '',
    last_id  BIGINT NOT NULL,
    last_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, tenant)
)
""",
    ],
    6: [
        # Phase 16 cleanup: Module Kind class deleted, Genome replaces it.
        # Drop the v4 ``kind = 'Module'`` partial index and recreate it as
        # ``kind = 'Genome'``. Existing Module rows on databases populated
        # before Phase 16 stay untouched — ``load_bootstrap_docs`` no longer
        # surfaces them, the catalog/install path queries Genome, and the
        # old index simply has nothing to match against post-cleanup.
        """
DROP INDEX IF EXISTS {schema}.dna_versions_module_lookup
""",
        """
CREATE INDEX IF NOT EXISTS dna_versions_package_lookup
    ON {schema}.dna_versions (kind, scope, tenant, semver)
    WHERE kind = 'Genome' AND semver IS NOT NULL
""",
    ],
    8: [
        # s-postgres-source-query-impl (2026-05-14) — hot-field indices
        # for the new Source.query push-down. Without these, the WHERE
        # `content->'spec'->>'status' = $N` does a full table scan; with
        # them, the filter is index-resolved in <50ms for typical scopes.
        #
        # We index ONLY the 3 hottest fields observed in Studio request
        # logs (status, feature, updated_at) plus a GIN over content->
        # 'spec' for arbitrary spec.X equality queries we can't predict.
        #
        # Idempotent: CREATE INDEX IF NOT EXISTS — no-op on re-apply.
        """
CREATE INDEX IF NOT EXISTS dna_docs_status_idx
    ON {schema}.dna_documents ((content::jsonb->'spec'->>'status'))
    WHERE content::jsonb ? 'spec'
""",
        """
CREATE INDEX IF NOT EXISTS dna_docs_feature_idx
    ON {schema}.dna_documents ((content::jsonb->'spec'->>'feature'))
    WHERE content::jsonb ? 'spec'
""",
        """
CREATE INDEX IF NOT EXISTS dna_docs_updated_at_idx
    ON {schema}.dna_documents ((content::jsonb->'spec'->>'updated_at'))
    WHERE content::jsonb ? 'spec'
""",
        """
CREATE INDEX IF NOT EXISTS dna_docs_spec_gin_idx
    ON {schema}.dna_documents USING gin ((content::jsonb->'spec'))
    WHERE content::jsonb ? 'spec'
""",
    ],
    7: [
        # s-edge-table-materializer (2026-05-12) — cross-doc citation
        # graph materialized in a sidecar table. Populated by an
        # observer in app.py write-hook that parses spec for slugs
        # (s-/f-/e-/spec-/plan-/cycle-/rem-/dream-/forget-/verdict-)
        # and upserts edges. Dropped freely without losing doc data
        # (same design as dna_doc_embeddings sidecar).
        """
CREATE TABLE IF NOT EXISTS {schema}.dna_edges (
    scope        TEXT NOT NULL,
    from_kind    TEXT NOT NULL,
    from_name    TEXT NOT NULL,
    to_kind      TEXT NOT NULL,
    to_name      TEXT NOT NULL,
    edge_type    TEXT NOT NULL DEFAULT 'spec-ref',
    source_field TEXT,
    tenant       TEXT NOT NULL DEFAULT '',
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, from_kind, from_name, to_kind, to_name, edge_type, tenant)
)
""",
        """
CREATE INDEX IF NOT EXISTS dna_edges_from_lookup
    ON {schema}.dna_edges (scope, from_kind, from_name, tenant)
""",
        """
CREATE INDEX IF NOT EXISTS dna_edges_to_lookup
    ON {schema}.dna_edges (scope, to_kind, to_name, tenant)
""",
    ],
    9: [
        # F2 fix (found by test_postgres_source_count's bundle-guard test,
        # 2026-06-10): da74b845 (binary bundle entries, 2026-05-25) added
        # all the code reading/writing ``content_binary`` but never a
        # migration — the dev DB got the column by hand, so EVERY fresh
        # schema bootstrap broke on the first bundle-entry read/write
        # (UndefinedColumnError in _load_view / save_document /
        # fetch_bundle_entry). Idempotent: IF NOT EXISTS no-ops on DBs
        # already patched manually (e.g. dev public).
        """
ALTER TABLE {schema}.dna_bundle_entries
    ADD COLUMN IF NOT EXISTS content_binary BYTEA
""",
    ],
}


SQLITE_MIGRATIONS: dict[int, str] = {
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
