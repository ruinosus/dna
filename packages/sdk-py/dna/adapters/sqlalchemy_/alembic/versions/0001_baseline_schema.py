"""baseline schema (i-038) — frozen equivalent of the retired numbered payloads

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-20

This is the ONE revision that replaces the whole retired ladder:
``PG_MIGRATIONS`` 1..10 and ``SQLITE_MIGRATIONS`` 1..8 (the hand-rolled
``adapters/_migrations.py`` runner). It reproduces their **final** state,
not their history — the intermediate steps (add-column-then-swap-PK,
create-then-drop ``dna_edges``, the v8 ``bundle_entries`` rebuild) were
only ever needed to move an existing database forward, and there is no
database left that needs them: the ladder had no external consumers and
the one production database was truncated before the cutover, so every
DB either starts empty here or is stamped at this revision (see
``source.py::_baseline_legacy_db``).

**Why raw DDL instead of ``op.create_table``:** this revision's job is to
be byte-equivalent to what the payloads produced. Emitting the payloads'
own DDL makes that equivalence auditable by reading, and immune to
SQLAlchemy's DDL-compiler rendering choices drifting between versions. A
revision is a frozen historical fact; it must not re-render from the
model. (The *model* is compared against the database separately — that is
what ``tests/test_schema_autogenerate_guard.py`` is for.)

**Why one revision with a dialect branch** rather than two trees or
branch labels: the two dialects' schemas are disjoint (different table
names, different primary keys, different tables entirely) but a given
database is only ever ONE dialect. Branch labels would produce two heads
and ``upgrade head`` would be ambiguous; two trees would duplicate the
env plumbing. One linear tree whose revisions branch internally keeps
``upgrade head`` unambiguous and mirrors ``source.py::_build_tables``,
which already branches on the same ``_is_pg`` flag.
"""
from __future__ import annotations

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Postgres — final state of PG_MIGRATIONS 1..10.
# ``{schema}`` is interpolated from the migration context (see env.py); the
# identifier is validated at SqlAlchemySource construction (trusted config).
# ---------------------------------------------------------------------------
PG_DDL: list[str] = [
    # --- v1 -----------------------------------------------------------
    """
CREATE TABLE IF NOT EXISTS {schema}.dna_documents (
    scope      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL,
    content    TEXT NOT NULL,
    version    INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    tenant     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (scope, kind, name, tenant)
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
    created_at TEXT NOT NULL,
    tenant     TEXT NOT NULL DEFAULT '',
    semver     TEXT
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
    # --- v2 + v3 + v9 (bundle_entries, tenant in PK, content_binary) ---
    """
CREATE TABLE IF NOT EXISTS {schema}.dna_bundle_entries (
    scope          TEXT NOT NULL,
    kind           TEXT NOT NULL,
    name           TEXT NOT NULL,
    entry_path     TEXT NOT NULL,
    content        TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    tenant         TEXT NOT NULL DEFAULT '',
    content_binary BYTEA,
    PRIMARY KEY (scope, kind, name, entry_path, tenant)
)
""",
    """
CREATE INDEX IF NOT EXISTS dna_bundle_entries_scope_kind_idx
    ON {schema}.dna_bundle_entries (scope, kind)
""",
    # --- v3 tenant indexes --------------------------------------------
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
    # --- v4 semver + v6 Genome rename (v4's Module index never created) -
    """
CREATE UNIQUE INDEX IF NOT EXISTS dna_versions_semver_unique
    ON {schema}.dna_versions (scope, kind, name, tenant, semver)
    WHERE semver IS NOT NULL
""",
    """
CREATE INDEX IF NOT EXISTS dna_versions_package_lookup
    ON {schema}.dna_versions (kind, scope, tenant, semver)
    WHERE kind = 'Genome' AND semver IS NOT NULL
""",
    # --- v5 eventbus ---------------------------------------------------
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
    # --- v8 hot-field expression indices -------------------------------
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
    # v7 created dna_edges and v10 dropped it again — the net effect is
    # nothing, so the baseline creates nothing. (i-039 documents why the
    # table was dead scaffolding: nothing ever inserted a row.)
]


# ---------------------------------------------------------------------------
# SQLite — final state of SQLITE_MIGRATIONS 1..8.
# ---------------------------------------------------------------------------
SQLITE_DDL: list[str] = [
    # --- v1 (tenant added by v4, nullable — NOT in the PK, i-092) ------
    """
CREATE TABLE IF NOT EXISTS documents (
    scope      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL,
    content    TEXT NOT NULL,
    version    INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    tenant     TEXT,
    PRIMARY KEY (scope, kind, name)
)
""",
    # AUTOINCREMENT (not bare INTEGER PRIMARY KEY) — the payload used it,
    # and it is observable: it creates sqlite_sequence and stops rowid reuse.
    """
CREATE TABLE IF NOT EXISTS versions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    scope      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL,
    content    TEXT NOT NULL,
    version    INTEGER NOT NULL,
    is_draft   INTEGER NOT NULL DEFAULT 1,
    author     TEXT,
    created_at TEXT NOT NULL,
    tenant     TEXT,
    semver     TEXT
)
""",
    # --- v2 ------------------------------------------------------------
    """
CREATE TABLE IF NOT EXISTS layer_documents (
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
    # --- v3 + v8 (tenant NOT NULL DEFAULT '' and IN the PK) ------------
    """
CREATE TABLE IF NOT EXISTS bundle_entries (
    scope       TEXT NOT NULL,
    kind        TEXT NOT NULL,
    name        TEXT NOT NULL,
    entry_path  TEXT NOT NULL,
    content     TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    tenant      TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (scope, kind, name, entry_path, tenant)
)
""",
    """
CREATE INDEX IF NOT EXISTS bundle_entries_scope_kind_idx
    ON bundle_entries (scope, kind)
""",
    """
CREATE INDEX IF NOT EXISTS bundle_entries_tenant_idx
    ON bundle_entries (tenant, scope, kind)
""",
    # --- v4 ------------------------------------------------------------
    """
CREATE INDEX IF NOT EXISTS documents_tenant_idx
    ON documents (tenant, scope, kind, name)
""",
    # --- v5 + v6 (v5's Module index was replaced by v6's Genome one) ---
    """
CREATE UNIQUE INDEX IF NOT EXISTS versions_semver_unique
    ON versions (scope, kind, name, tenant, semver)
    WHERE semver IS NOT NULL
""",
    """
CREATE INDEX IF NOT EXISTS versions_package_lookup
    ON versions (kind, scope, tenant, semver)
    WHERE kind = 'Genome' AND semver IS NOT NULL
""",
    # --- v7 expression indices -----------------------------------------
    """
CREATE INDEX IF NOT EXISTS docs_status_idx
    ON documents (scope, kind, json_extract(content, '$.spec.status'))
""",
    """
CREATE INDEX IF NOT EXISTS docs_feature_idx
    ON documents (scope, kind, json_extract(content, '$.spec.feature'))
""",
    """
CREATE INDEX IF NOT EXISTS docs_updated_at_idx
    ON documents (scope, kind, json_extract(content, '$.spec.updated_at'))
""",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        schema = op.get_context().version_table_schema or "public"
        for stmt in PG_DDL:
            op.execute(stmt.format(schema=schema))
    else:
        for stmt in SQLITE_DDL:
            op.execute(stmt)


def downgrade() -> None:
    # Forward-only, as the retired contract was (docs/PORT-CONTRACT.md
    # § "Schema migrations"): recovery is backup/re-seed, not downgrade.
    raise NotImplementedError("DNA schema migrations are forward-only")
