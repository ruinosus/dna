"""instance edges — the DERIVED reference graph, with a producer this time

Revision ID: 0006_document_edges
Revises: 0005_approval_trail
Create Date: 2026-08-06

``dna_edges`` existed once before. Migration 7 created it (12/05/2026), nothing
ever inserted a row, and migration 10 dropped it (i-039). The dead DDL even
described the producer it lacked — *"an observer in ``app.py`` write-hook that
parses spec for slugs"* — against a file that never existed in this repo. The
lesson taken from that was not "no edge table"; it was **never create the table
without the producer**, which is why this revision ships in the same commit as
``resolve_declared_edges`` and the ``edges=`` write kwarg, and why the test
suite fails if the table exists and the write path does not fill it.

**Both dialects, unlike 0002/0004/0005.** Those are control-plane tables and a
single-process self-host does not have the question they answer. This one is
instance data derived from instance data: a SQLite self-host asks "what points
at this?" exactly as a hosted Postgres does, and the traversal is one recursive
CTE in standard SQL that runs unchanged on both.

**What the shape fixes relative to the dead DDL** (details in ``schema.py``):
``source_field`` and ``ordinal`` are IN the primary key (the dead one left the
field out, so two fields pointing at one target collided and the graph lost the
"by which field" a relations view renders); ``to_kind`` is NULLABLE because a
dangling reference is a row worth keeping, not a row worth hiding; ``to_scope``
is separate because a reference can resolve in a PARENT scope; ``from_version``
records which version of the instance the edges were derived from, so drift is
detectable on the paths that are not atomic (backfill, an adapter without the
kwarg).

**No foreign keys.** A Kind is not a table, and ``to_name`` deliberately may
name an instance that does not exist — that case is the one the table is most
useful for.

⚠️ **The legacy bridge still drops the old table, and the ORDER matters.**
``migrate.py::_LEGACY_BRIDGES`` carries ``("postgresql", 9) → DROP TABLE
dna_edges`` with ``must_be_empty=("dna_edges",)``. ``upgrade_sync`` runs
``baseline_legacy_database`` FIRST and only then ``command.upgrade``, so a v9
database drops the empty dead table, is stamped at the baseline, and then this
revision creates the new one. That sequence is proven by
``tests/test_graph_edges_legacy_migration.py`` rather than assumed — reverse it
and the bridge would refuse a table our own producer had just filled.

Raw DDL rather than ``op.create_table`` follows 0001_baseline: a revision is a
frozen historical fact and must not re-render from the model.
"""
from __future__ import annotations

from alembic import op

revision = "0006_document_edges"
down_revision = "0005_approval_trail"
branch_labels = None
depends_on = None


PG_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.dna_edges (
    scope            TEXT        NOT NULL,
    tenant           TEXT        NOT NULL DEFAULT '',
    from_api_version TEXT        NOT NULL DEFAULT '',
    from_kind        TEXT        NOT NULL,
    from_name        TEXT        NOT NULL,
    source_field     TEXT        NOT NULL,
    ordinal          INTEGER     NOT NULL DEFAULT 0,
    to_scope         TEXT,
    to_kind          TEXT,
    to_name          TEXT        NOT NULL,
    declared_to      TEXT        NOT NULL DEFAULT '',
    from_version     INTEGER     NOT NULL DEFAULT 0,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, tenant, from_api_version, from_kind, from_name,
                 source_field, ordinal)
)
"""

PG_DDL_IDX_OUT = """
CREATE INDEX IF NOT EXISTS dna_edges_out_idx
    ON {schema}.dna_edges (scope, tenant, from_kind, from_name)
"""

# The one that carries the product question. "What does this point at" is
# already served by the primary-key prefix; "what points AT this" has no other
# index that could serve it, and without this line the recursive traversal
# scans the table on every inbound hop.
PG_DDL_IDX_IN = """
CREATE INDEX IF NOT EXISTS dna_edges_in_idx
    ON {schema}.dna_edges (scope, tenant, to_kind, to_name)
"""

SQLITE_DDL: list[str] = [
    """
CREATE TABLE IF NOT EXISTS edges (
    scope            TEXT    NOT NULL,
    tenant           TEXT    NOT NULL DEFAULT '',
    from_api_version TEXT    NOT NULL DEFAULT '',
    from_kind        TEXT    NOT NULL,
    from_name        TEXT    NOT NULL,
    source_field     TEXT    NOT NULL,
    ordinal          INTEGER NOT NULL DEFAULT 0,
    to_scope         TEXT,
    to_kind          TEXT,
    to_name          TEXT    NOT NULL,
    declared_to      TEXT    NOT NULL DEFAULT '',
    from_version     INTEGER NOT NULL DEFAULT 0,
    updated_at       TEXT    NOT NULL,
    PRIMARY KEY (scope, tenant, from_api_version, from_kind, from_name,
                 source_field, ordinal)
)
""",
    """
CREATE INDEX IF NOT EXISTS edges_out_idx
    ON edges (scope, tenant, from_kind, from_name)
""",
    """
CREATE INDEX IF NOT EXISTS edges_in_idx
    ON edges (scope, tenant, to_kind, to_name)
""",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        schema = op.get_context().version_table_schema or "public"
        op.execute(PG_DDL.format(schema=schema))
        op.execute(PG_DDL_IDX_OUT.format(schema=schema))
        op.execute(PG_DDL_IDX_IN.format(schema=schema))
    else:
        for stmt in SQLITE_DDL:
            op.execute(stmt)


def downgrade() -> None:
    # Forward-only, as the baseline is (docs/PORT-CONTRACT.md § "Schema
    # migrations"): recovery is backup/re-seed, not downgrade.
    raise NotImplementedError("DNA schema migrations are forward-only")
