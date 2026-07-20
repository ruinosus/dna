"""The SqlAlchemySource table model — ONE definition of the schema.

Before i-038 the schema existed twice: as DDL payloads (``migrations.py``)
and as ``sa.Table`` objects built inline in ``source.py``, with nothing
checking that they agreed. They drifted for two weeks (``content_binary``
was added to the code but never to a migration, so every fresh bootstrap
broke — see the retired PG migration v9).

Now there is one model, here, and it is the ``target_metadata`` Alembic
autogenerates against. ``tests/test_schema_autogenerate_guard.py`` boots a
database from the Alembic revisions and asserts the model and the database
agree; a column added here without a revision (or vice versa) fails that
test instead of shipping.

Because the model is now compared against a real database, the columns
carry their real constraints (``nullable``, ``primary_key``,
``server_default``) rather than the loose bare-``Column`` shorthand the
inline version used — a model that lies about nullability cannot be a
drift detector.

[dialect] The two dialects' schemas are genuinely disjoint — different
table names (``dna_``-prefixed vs bare), different primary keys
(``documents`` includes ``tenant`` on pg, not on sqlite — i-092), and pg
has two tables sqlite does not (the Phase 15.1 eventbus). ``build_metadata``
branches on ``is_pg`` exactly as the retired ``_build_tables`` did.
"""
from __future__ import annotations

from dataclasses import dataclass

import sqlalchemy as sa

# Indexes deliberately NOT represented in the model, and therefore excluded
# from autogenerate comparison (see ``alembic/env.py::include_object``).
#
# Every one of these is a partial and/or expression index. SQLAlchemy cannot
# round-trip them: reflection on SQLite outright skips expression indexes
# ("SAWarning: Skipped unsupported reflection of expression-based index"), and
# on Postgres it returns them as opaque ``_textual_index_element`` objects that
# never compare equal to a model-side definition. Left in the comparison they
# would report a phantom "remove_index" on every single run, and a guard that
# always fails is a guard nobody reads.
#
# The tradeoff is explicit and narrow: these index names are pinned here, so
# autogenerate stays silent about THESE indexes only. A NEW index — or any
# table/column drift, which is the ``content_binary`` failure mode this guard
# exists to catch — is still reported.
UNMANAGED_INDEXES: frozenset[str] = frozenset({
    # Postgres — hot-field expression indices, partial on `content ? 'spec'`.
    "dna_docs_status_idx",
    "dna_docs_feature_idx",
    "dna_docs_updated_at_idx",
    "dna_docs_spec_gin_idx",
    # Postgres — partial indexes on `semver IS NOT NULL` / `kind = 'Genome'`.
    "dna_versions_semver_unique",
    "dna_versions_package_lookup",
    # SQLite — json_extract expression indices.
    "docs_status_idx",
    "docs_feature_idx",
    "docs_updated_at_idx",
    # SQLite — the same two partial indexes.
    "versions_semver_unique",
    "versions_package_lookup",
})


#: Tables inside the DNA database that the Source model does NOT own, and
#: which autogenerate must therefore not propose dropping.
FOREIGN_TABLES: frozenset[str] = frozenset({
    # Retired control tables (kept excluded so a database mid-cutover does
    # not look like it has a stray table).
    "schema_migrations", "dna_schema_migrations",
    # The search stores own their own schema through a separate provider
    # (adapters/search/*), whose DDL is parametrized by embedding width and
    # so cannot live in a static revision — see that module.
    "dna_search_migrations", "dna_search_docs", "dna_search_meta",
    "search_docs", "search_vec", "search_fts", "search_meta",
    # AUTOINCREMENT bookkeeping, owned by SQLite itself.
    "sqlite_sequence",
    # Alembic's own control table. Alembic filters it out of its own
    # schema automatically, but not when reflecting a named schema.
    "alembic_version",
})


def make_include_name(schema: str | None):
    """Restrict reflection to the ONE schema this Source owns.

    [dialect] Postgres only. ``include_schemas`` has to be on so the named
    DNA schema is reflected at all, but with it on Alembic reflects EVERY
    schema in the database and reports every table it finds elsewhere as a
    table to drop. A DNA schema shares its database with other things —
    dna-cloud's Postgres hosts several — so an unrestricted autogenerate
    would cheerfully propose dropping tables that belong to someone else.
    This admits the target schema and nothing else.
    """

    def include_name(name, type_, parent_names) -> bool:
        if type_ == "schema":
            return name == schema
        return True

    return include_name


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Filter what autogenerate is allowed to have an opinion about.

    Lives here rather than in ``alembic/env.py`` because the guard test
    must apply the SAME filter, and ``env.py`` executes Alembic context
    setup at import time (Alembic loads it by path, not as a module).
    """
    if type_ == "index" and name in UNMANAGED_INDEXES:
        return False
    if type_ == "table" and name in FOREIGN_TABLES:
        return False
    return True


def compare_type(context_, inspected_column, metadata_column,
                 inspected_type, metadata_type):
    """Alembic's default type comparison, minus one known false positive.

    [dialect] SQLite has no native BOOLEAN — ``is_draft`` is stored as
    INTEGER 0/1 (the retired payload said ``INTEGER NOT NULL DEFAULT 1``).
    The model says ``sa.Boolean`` because that is what the code means and
    how it queries (``is_draft.is_(True)``). Reflection returns INTEGER, so
    the default comparator would report a type change on every run.
    Suppress exactly that pair, on SQLite only.

    Returns ``None`` to defer to Alembic's default comparison.
    """
    if context_.dialect.name != "postgresql":
        if isinstance(metadata_type, sa.Boolean) and isinstance(
            inspected_type, sa.Integer
        ):
            return False
    return None


@dataclass(frozen=True)
class Tables:
    """The tables ``SqlAlchemySource`` binds to, plus their shared MetaData."""

    metadata: sa.MetaData
    documents: sa.Table
    versions: sa.Table
    bundle_entries: sa.Table
    layer_documents: sa.Table
    # [dialect] pg-only (Phase 15.1 eventbus); None on sqlite.
    outbox: sa.Table | None
    versions_seq: sa.Table | None
    # [dialect] pg-only CONTROL-PLANE table. Not bound by SqlAlchemySource --
    # nothing in the document path reads or writes it. It lives in this model
    # anyway because the model is what autogenerate compares against: a table
    # created by a revision but absent here would be reported as a table to
    # DROP on every run (see FOREIGN_TABLES for the other way out, taken by
    # the search stores, whose DDL cannot live in a static revision). Written
    # by the MCP metering store (``dna_cli._mcp_quota.PostgresQuotaStore``).
    quota_counters: sa.Table | None = None


def build_metadata(*, is_pg: bool, schema: str | None = None) -> Tables:
    """Build the table model for one dialect.

    Args:
        is_pg: Postgres if True, SQLite otherwise. Selects table names,
            primary keys, column nullability and which tables exist.
        schema: Postgres schema namespace; must be None on SQLite.
    """
    md = sa.MetaData(schema=schema)
    # [dialect] pg tables are dna_-prefixed; sqlite's are bare.
    p = "dna_" if is_pg else ""

    # [dialect] tenant: pg is NOT NULL DEFAULT '' and part of the documents
    # PK; sqlite left it nullable and outside the PK (i-092 lives here).
    doc_tenant = (
        sa.Column("tenant", sa.Text, nullable=False,
                  server_default=sa.text("''"), primary_key=True)
        if is_pg else
        sa.Column("tenant", sa.Text, nullable=True)
    )
    documents = sa.Table(
        f"{p}documents", md,
        sa.Column("scope", sa.Text, primary_key=True, nullable=False),
        sa.Column("kind", sa.Text, primary_key=True, nullable=False),
        sa.Column("name", sa.Text, primary_key=True, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False,
                  server_default=sa.text("1")),
        sa.Column("updated_at", sa.Text, nullable=False),
        doc_tenant,
        sa.Index(f"{p}documents_tenant_idx", "tenant", "scope", "kind", "name"),
    )

    versions = sa.Table(
        f"{p}versions", md,
        # [dialect] pg's SERIAL is NOT NULL; sqlite's INTEGER PRIMARY KEY is
        # the rowid alias, which accepts NULL on insert (that is HOW you ask
        # for an autoassigned id) and reflects as nullable. Stating that
        # here rather than suppressing the diff keeps the model honest --
        # the flag affects comparison only, never emitted DDL, because the
        # revisions carry their own frozen DDL.
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True,
                  nullable=not is_pg),
        sa.Column("scope", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        # [dialect] pg stores a real BOOLEAN; sqlite stores INTEGER 0/1.
        # The model says Boolean on both -- the source code compares with
        # ``is_(True)`` -- and env.py's compare_type suppresses the sqlite
        # affinity false-positive rather than the model lying about intent.
        sa.Column("is_draft", sa.Boolean, nullable=False,
                  server_default=sa.text("true" if is_pg else "1")),
        sa.Column("author", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column(
            "tenant", sa.Text,
            nullable=not is_pg,
            server_default=sa.text("''") if is_pg else None,
        ),
        sa.Column("semver", sa.Text, nullable=True),
        # [dialect] sqlite used INTEGER PRIMARY KEY AUTOINCREMENT, which is
        # observably different from a bare rowid alias (it creates
        # sqlite_sequence and stops rowid reuse).
        sqlite_autoincrement=not is_pg,
    )
    if is_pg:
        versions.append_constraint(
            sa.Index(f"{p}versions_tenant_idx", "tenant", "scope", "kind", "name")
        )

    bundle_cols: list[sa.Column] = [
        sa.Column("scope", sa.Text, primary_key=True, nullable=False),
        sa.Column("kind", sa.Text, primary_key=True, nullable=False),
        sa.Column("name", sa.Text, primary_key=True, nullable=False),
        sa.Column("entry_path", sa.Text, primary_key=True, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.Column("tenant", sa.Text, primary_key=True, nullable=False,
                  server_default=sa.text("''")),
    ]
    if is_pg:
        # [dialect] only pg has the BYTEA column; sqlite stores bytes in
        # `content` via type affinity. THIS is the column whose absence from
        # the migrations went unnoticed for two weeks.
        bundle_cols.append(sa.Column("content_binary", sa.LargeBinary, nullable=True))
    bundle_entries = sa.Table(
        f"{p}bundle_entries", md, *bundle_cols,
        sa.Index(f"{p}bundle_entries_scope_kind_idx", "scope", "kind"),
        sa.Index(f"{p}bundle_entries_tenant_idx", "tenant", "scope", "kind"),
    )

    layer_documents = sa.Table(
        f"{p}layer_documents", md,
        sa.Column("scope", sa.Text, primary_key=True, nullable=False),
        sa.Column("layer_id", sa.Text, primary_key=True, nullable=False),
        sa.Column("layer_value", sa.Text, primary_key=True, nullable=False),
        sa.Column("kind", sa.Text, primary_key=True, nullable=False),
        sa.Column("name", sa.Text, primary_key=True, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
    )

    outbox = versions_seq = quota_counters = None
    if is_pg:
        # [dialect] the DNA Cloud metering counter — the DURABLE half of the
        # MCP quota meter (``dna_cli._mcp_quota``). Postgres-only on purpose:
        # its whole reason to exist is to be correct across RESTARTS and
        # across N REPLICAS, which a single-file SQLite self-host does not
        # have and does not need (that deployment keeps the in-process
        # counter). One row per (day, tenant, tier); the counter is advanced
        # with INSERT ... ON CONFLICT DO UPDATE SET calls = calls + 1, never
        # read-modify-write, so concurrent replicas cannot lose an increment.
        #
        # `day` is a DATE in UTC, written by the store (not a server default)
        # so the bucket boundary is the store's clock, not the database
        # server's timezone.
        #
        # The PK (day, tenant, tier) is also the read path's index: the daily
        # billing rollup filters `day = <today> AND tenant = <t>`, and both
        # are equality predicates on a leading prefix of the PK, so no
        # secondary index is warranted.
        quota_counters = sa.Table(
            f"{p}quota_counters", md,
            sa.Column("day", sa.Date, primary_key=True, nullable=False),
            sa.Column("tenant", sa.Text, primary_key=True, nullable=False),
            sa.Column("tier", sa.Text, primary_key=True, nullable=False),
            sa.Column("calls", sa.BigInteger, nullable=False,
                      server_default=sa.text("0")),
        )
        # [dialect] the Phase 15.1 eventbus is Postgres infrastructure
        # (outbox + LISTEN/NOTIFY); sqlite has no cross-process bus.
        outbox = sa.Table(
            f"{p}outbox", md,
            sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.Column("scope", sa.Text, nullable=False),
            sa.Column("tenant", sa.Text, nullable=False,
                      server_default=sa.text("''")),
            sa.Column("kind", sa.Text, nullable=False),
            sa.Column("name", sa.Text, nullable=False),
            sa.Column("op", sa.Text, nullable=False),
            sa.Column("doc_version", sa.Integer, nullable=False),
            sa.Column("actor", sa.Text, nullable=True),
            sa.Column("cause", sa.Text, nullable=True),
            sa.Index(f"{p}outbox_scope_id_idx", "scope", "tenant", "id"),
            sa.Index(f"{p}outbox_occurred_at_idx", "occurred_at"),
        )
        versions_seq = sa.Table(
            f"{p}versions_seq", md,
            sa.Column("scope", sa.Text, primary_key=True, nullable=False),
            sa.Column("tenant", sa.Text, primary_key=True, nullable=False,
                      server_default=sa.text("''")),
            sa.Column("last_id", sa.BigInteger, nullable=False),
            sa.Column("last_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
        )

    return Tables(
        metadata=md, documents=documents, versions=versions,
        bundle_entries=bundle_entries, layer_documents=layer_documents,
        outbox=outbox, versions_seq=versions_seq,
        quota_counters=quota_counters,
    )
