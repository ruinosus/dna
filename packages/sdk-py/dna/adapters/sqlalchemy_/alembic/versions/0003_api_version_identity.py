"""api_version joins the row key — a Kind's identity is (apiVersion, kind)

Revision ID: 0003_api_version
Revises: 0002_quota_counters
Create Date: 2026-07-26

The registry keys a Kind on ``(api_version, kind)``, and tenant-authored
Kinds depend on it: two workspaces may each declare a ``Deal`` under their
own namespace — that is what namespacing the apiVersion is FOR. The tables
this revision changes keyed rows on ``(scope, kind, name)`` alone, so those
two Kinds were indistinguishable to the adapter: the second save OVERWROTE
the first, and ``delete_document``'s ``api_version`` argument had nowhere to
go. This revision gives it somewhere.

**The backfill reads the row, not a registry.** Every ``documents`` /
``versions`` row stores the whole document as JSON in ``content``, and a DNA
document carries its own ``apiVersion``. So the value is not inferred from a
Kind-name → apiVersion table (which is exactly the map that cannot answer
when two Kinds share a name, and which no migration process can be trusted
to hold in full — a retired Kind, or one from an extension the migrating
process never imported, is simply absent from it). It is read from the row
being migrated. Nothing is guessed.

Two consequences worth stating, because they are what make this safe:

* **The new key is a strict superset of the old one**, so the widening can
  never merge two rows and never splits one. Row counts are preserved by
  construction, and that is asserted below rather than assumed.
* **A row whose document declares no apiVersion is recorded as ``''``** —
  which is a fact about the row ("this document states none"), not a guess at
  a Kind. ``''`` is never treated as an apiVersion by the adapter; an
  unpinned read matches it exactly as it always did.

**Where it can still be undecidable, it FAILS.** If a row declares no
apiVersion AND its ``(scope, kind)`` is observed under more than one
apiVersion elsewhere, then that row genuinely belongs to one of two Kinds and
this code cannot say which. That is the corruption this whole change exists
to prevent, so it is refused — with the full list — instead of resolved by
picking. See :func:`_refuse_undecidable_rows`.

**Bundle entries** hold file bytes, not documents, so they have no apiVersion
of their own; they inherit it from the document they belong to (the
``documents`` row, else the newest ``versions`` row for the same key). An
ORPHANED entry — one whose document is already gone — keeps ``''``: there is
nothing left to inherit from, and no read reaches it without a document.

Raw DDL rather than ``op.create_table``, following 0001/0002: a revision is a
frozen historical fact and must not re-render from the model. The model is
compared against the database separately by
``tests/test_schema_autogenerate_guard.py``.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_api_version"
down_revision = "0002_quota_counters"
branch_labels = None
depends_on = None

#: The tables whose row key gains ``api_version``.
_TABLES = ("documents", "versions", "bundle_entries")


def _qualify(schema: str | None, prefix: str, table: str) -> str:
    base = f"{prefix}{table}"
    return f"{schema}.{base}" if schema else base


# ---------------------------------------------------------------------------
# Postgres — the PK is a named constraint, so it is swapped in place.
# ---------------------------------------------------------------------------

PG_REKEY: list[str] = [
    # documents: (scope, kind, name, tenant) → + api_version
    "ALTER TABLE {documents} DROP CONSTRAINT {documents_pkey}",
    "ALTER TABLE {documents} ADD PRIMARY KEY "
    "(scope, kind, api_version, name, tenant)",
    "DROP INDEX IF EXISTS {schema}.dna_documents_tenant_idx",
    "CREATE INDEX dna_documents_tenant_idx ON {documents} "
    "(tenant, scope, kind, api_version, name)",
    # versions: no business PK (id is a surrogate) — the indexes carry it.
    "DROP INDEX IF EXISTS {schema}.dna_versions_tenant_idx",
    "CREATE INDEX dna_versions_tenant_idx ON {versions} "
    "(tenant, scope, kind, api_version, name)",
    # The semver UNIQUENESS index is an identity constraint: two Kinds sharing
    # a name must be able to publish the same semver independently.
    "DROP INDEX IF EXISTS {schema}.dna_versions_semver_unique",
    "CREATE UNIQUE INDEX dna_versions_semver_unique ON {versions} "
    "(scope, kind, api_version, name, tenant, semver) WHERE semver IS NOT NULL",
    # bundle_entries: (scope, kind, name, entry_path, tenant) → + api_version
    "ALTER TABLE {bundle_entries} DROP CONSTRAINT {bundle_entries_pkey}",
    "ALTER TABLE {bundle_entries} ADD PRIMARY KEY "
    "(scope, kind, api_version, name, entry_path, tenant)",
    "DROP INDEX IF EXISTS {schema}.dna_bundle_entries_scope_kind_idx",
    "CREATE INDEX dna_bundle_entries_scope_kind_idx ON {bundle_entries} "
    "(scope, kind, api_version)",
    "DROP INDEX IF EXISTS {schema}.dna_bundle_entries_tenant_idx",
    "CREATE INDEX dna_bundle_entries_tenant_idx ON {bundle_entries} "
    "(tenant, scope, kind, api_version)",
]


# ---------------------------------------------------------------------------
# SQLite — a PRIMARY KEY cannot be altered, so the two keyed tables are
# rebuilt: create → copy → drop → rename → recreate indexes. ``versions`` is
# NOT rebuilt (its PK is the ``id`` rowid alias, and rebuilding it would
# needlessly disturb AUTOINCREMENT/sqlite_sequence); only its indexes change.
#
# Column ORDER is preserved with api_version appended last, matching what
# ``ALTER TABLE ... ADD COLUMN`` did on Postgres, so the two dialects' physical
# layouts stay comparable. The PK states the logical order.
# ---------------------------------------------------------------------------

SQLITE_REKEY: list[str] = [
    """
CREATE TABLE documents_rekeyed (
    scope       TEXT NOT NULL,
    kind        TEXT NOT NULL,
    name        TEXT NOT NULL,
    content     TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    updated_at  TEXT NOT NULL,
    tenant      TEXT,
    api_version TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (scope, kind, api_version, name)
)
""",
    """
INSERT INTO documents_rekeyed
    (scope, kind, name, content, version, updated_at, tenant, api_version)
SELECT scope, kind, name, content, version, updated_at, tenant, api_version
  FROM documents
""",
    "DROP TABLE documents",
    "ALTER TABLE documents_rekeyed RENAME TO documents",
    # DROP TABLE took the indexes with it — restate every one of them.
    "CREATE INDEX documents_tenant_idx ON documents "
    "(tenant, scope, kind, api_version, name)",
    "CREATE INDEX docs_status_idx ON documents "
    "(scope, kind, json_extract(content, '$.spec.status'))",
    "CREATE INDEX docs_feature_idx ON documents "
    "(scope, kind, json_extract(content, '$.spec.feature'))",
    "CREATE INDEX docs_updated_at_idx ON documents "
    "(scope, kind, json_extract(content, '$.spec.updated_at'))",
    # versions — indexes only.
    "DROP INDEX IF EXISTS versions_semver_unique",
    "CREATE UNIQUE INDEX versions_semver_unique ON versions "
    "(scope, kind, api_version, name, tenant, semver) WHERE semver IS NOT NULL",
    """
CREATE TABLE bundle_entries_rekeyed (
    scope       TEXT NOT NULL,
    kind        TEXT NOT NULL,
    name        TEXT NOT NULL,
    entry_path  TEXT NOT NULL,
    content     TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    tenant      TEXT NOT NULL DEFAULT '',
    api_version TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (scope, kind, api_version, name, entry_path, tenant)
)
""",
    """
INSERT INTO bundle_entries_rekeyed
    (scope, kind, name, entry_path, content, updated_at, tenant, api_version)
SELECT scope, kind, name, entry_path, content, updated_at, tenant, api_version
  FROM bundle_entries
""",
    "DROP TABLE bundle_entries",
    "ALTER TABLE bundle_entries_rekeyed RENAME TO bundle_entries",
    "CREATE INDEX bundle_entries_scope_kind_idx ON bundle_entries "
    "(scope, kind, api_version)",
    "CREATE INDEX bundle_entries_tenant_idx ON bundle_entries "
    "(tenant, scope, kind, api_version)",
]


# ---------------------------------------------------------------------------
# backfill + refusal
# ---------------------------------------------------------------------------


def _api_version_expr(is_pg: bool) -> str:
    """The row's OWN declared apiVersion, read out of ``content``."""
    # [dialect] pg's content column is TEXT → explicit ::jsonb cast, then ->>
    # for the text value. SQLite has json_extract, which returns the native
    # JSON type (TEXT here) with no cast dance.
    return "content::jsonb->>'apiVersion'" if is_pg \
        else "json_extract(content, '$.apiVersion')"


def _refuse_undecidable_rows(conn, tables: dict[str, str], is_pg: bool) -> None:
    """Raise if any row's Kind is genuinely undecidable.

    A row is undecidable when it declares no apiVersion of its own AND its
    ``(scope, kind)`` is observed under MORE THAN ONE apiVersion in the same
    database. Then the row belongs to one of several Kinds and nothing here can
    say which — picking would bake exactly the corruption this change exists to
    prevent into a column that is about to become part of an identity.

    A ``(scope, kind)`` with zero or one observed apiVersion is NOT decided by
    that observation either: the row keeps ``''``, recording what its document
    actually says (nothing) rather than borrowing a neighbour's answer.
    """
    # Every apiVersion observed per (scope, kind), from both document tables.
    observed: dict[tuple[str, str], set[str]] = {}
    for table in ("documents", "versions"):
        rows = conn.execute(sa.text(
            f"SELECT DISTINCT scope, kind, api_version FROM {tables[table]} "
            "WHERE api_version <> ''"
        )).all()
        for scope, kind, api_version in rows:
            observed.setdefault((scope, kind), set()).add(api_version)

    ambiguous = {k for k, v in observed.items() if len(v) > 1}
    if not ambiguous:
        return

    offenders: list[str] = []
    for table in _TABLES:
        rows = conn.execute(sa.text(
            f"SELECT scope, kind, name, COALESCE(tenant, '') FROM {tables[table]} "
            "WHERE api_version = ''"
        )).all()
        for scope, kind, name, tenant in rows:
            if (scope, kind) not in ambiguous:
                continue
            candidates = ", ".join(sorted(observed[(scope, kind)]))
            offenders.append(
                f"  {tables[table]}: scope={scope!r} kind={kind!r} name={name!r} "
                f"tenant={tenant!r} — candidates: {candidates}"
            )

    if not offenders:
        return

    example = (
        f"  UPDATE {tables['documents']} SET content = jsonb_set("
        "content::jsonb, '{apiVersion}', '\"<the-one-it-is>\"')::text\n"
        "   WHERE scope = ... AND kind = ... AND name = ...;"
        if is_pg else
        f"  UPDATE {tables['documents']} SET content = json_set("
        "content, '$.apiVersion', '<the-one-it-is>')\n"
        "   WHERE scope = ... AND kind = ... AND name = ...;"
    )
    raise RuntimeError(
        "Cannot add api_version to the row key: "
        f"{len(offenders)} row(s) declare no apiVersion of their own while "
        "their Kind name is used by more than one apiVersion in this database. "
        "Which Kind each row belongs to is not knowable from the row, and "
        "guessing would make the ambiguity permanent — the guess would be "
        "written into a column that is part of the identity from here on.\n"
        "\n" + "\n".join(offenders) + "\n"
        "\n"
        "Recovery: decide each row by hand and record the decision in the "
        "document itself BEFORE re-running — the backfill reads apiVersion out "
        "of content, so fixing the document is what fixes the row:\n"
        f"{example}\n"
        "If a row is disposable, delete it instead. Nothing has been changed: "
        "this runs inside the migration's transaction."
    )


def _assert_no_rows_lost(conn, tables: dict[str, str], before: dict[str, int]) -> None:
    """The widening must preserve every row. Asserted, not assumed."""
    for table in _TABLES:
        after = conn.execute(
            sa.text(f"SELECT count(*) FROM {tables[table]}")
        ).scalar_one()
        if after != before[table]:
            raise RuntimeError(
                f"Refusing to complete: {tables[table]} held {before[table]} "
                f"row(s) before the api_version rekey and {after} after. The "
                "new key is a strict superset of the old one, so this is "
                "impossible unless the rekey itself is wrong — the migration "
                "is aborted with the transaction intact."
            )


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    schema = op.get_context().version_table_schema or "public" if is_pg else None
    prefix = "dna_" if is_pg else ""
    tables = {t: _qualify(schema, prefix, t) for t in _TABLES}

    before = {
        t: bind.execute(sa.text(f"SELECT count(*) FROM {tables[t]}")).scalar_one()
        for t in _TABLES
    }

    # 1. The column. NOT NULL DEFAULT '' rather than nullable-then-tighten:
    #    both dialects add it without a table rewrite, and '' is the value the
    #    column keeps for a document that declares no apiVersion anyway — one
    #    meaning for the empty string, in the transient state and the final one.
    for t in _TABLES:
        op.execute(f"ALTER TABLE {tables[t]} ADD COLUMN api_version TEXT "
                   "NOT NULL DEFAULT ''")

    # 2. Backfill the document tables from the document each row already holds.
    expr = _api_version_expr(is_pg)
    for t in ("documents", "versions"):
        op.execute(
            f"UPDATE {tables[t]} SET api_version = {expr} "
            f"WHERE COALESCE({expr}, '') <> ''"
        )

    # 3. Bundle entries hold file bytes, not documents — they inherit from the
    #    document they belong to. Correlated subqueries rather than UPDATE ...
    #    FROM: one statement that both dialects accept. The tenant sentinel
    #    differs between the tables (documents may store NULL on sqlite, bundle
    #    entries always store ''), hence COALESCE on the document side.
    be, docs, vers = tables["bundle_entries"], tables["documents"], tables["versions"]
    own = f"{prefix}bundle_entries"
    doc_match = (
        f"d.scope = {own}.scope AND d.kind = {own}.kind AND d.name = {own}.name "
        f"AND COALESCE(d.tenant, '') = {own}.tenant AND d.api_version <> ''"
    )
    op.execute(
        f"UPDATE {be} SET api_version = "
        f"(SELECT d.api_version FROM {docs} d WHERE {doc_match}) "
        f"WHERE api_version = '' "
        f"AND EXISTS (SELECT 1 FROM {docs} d WHERE {doc_match})"
    )
    ver_match = (
        f"v.scope = {own}.scope AND v.kind = {own}.kind AND v.name = {own}.name "
        f"AND COALESCE(v.tenant, '') = {own}.tenant AND v.api_version <> ''"
    )
    op.execute(
        f"UPDATE {be} SET api_version = "
        f"(SELECT v.api_version FROM {vers} v WHERE {ver_match} "
        " ORDER BY v.version DESC LIMIT 1) "
        f"WHERE api_version = '' "
        f"AND EXISTS (SELECT 1 FROM {vers} v WHERE {ver_match})"
    )

    # 4. Refuse rather than resolve where the row's Kind is undecidable.
    _refuse_undecidable_rows(bind, tables, is_pg)

    # 5. Rekey.
    if is_pg:
        names = {
            "schema": schema,
            "documents_pkey": _pg_pk_name(bind, schema, "dna_documents"),
            "bundle_entries_pkey": _pg_pk_name(bind, schema, "dna_bundle_entries"),
            **tables,
        }
        for stmt in PG_REKEY:
            op.execute(stmt.format(**names))
    else:
        for stmt in SQLITE_REKEY:
            op.execute(stmt)

    _assert_no_rows_lost(bind, tables, before)


def _pg_pk_name(conn, schema: str | None, table: str) -> str:
    """The PRIMARY KEY constraint's real name, looked up rather than assumed.

    ``CREATE TABLE ... PRIMARY KEY`` names it ``<table>_pkey``, but a database
    restored from a dump or created by an older tool may carry another name,
    and ``DROP CONSTRAINT`` on the wrong name is a failed migration on someone
    else's production database.
    """
    name = conn.execute(sa.text(
        "SELECT c.conname FROM pg_constraint c "
        "JOIN pg_class t ON t.oid = c.conrelid "
        "JOIN pg_namespace n ON n.oid = t.relnamespace "
        "WHERE c.contype = 'p' AND t.relname = :t AND n.nspname = :s"
    ), {"t": table, "s": schema or "public"}).scalar()
    if not name:
        raise RuntimeError(
            f"{schema or 'public'}.{table} has no PRIMARY KEY constraint — this "
            "database does not have the shape revision 0001_baseline built, so "
            "the api_version rekey will not be applied on a guess."
        )
    return f'"{name}"'


def downgrade() -> None:
    # Forward-only, as the baseline is (docs/PORT-CONTRACT.md § "Schema
    # migrations"): recovery is backup/re-seed, not downgrade.
    raise NotImplementedError("DNA schema migrations are forward-only")
