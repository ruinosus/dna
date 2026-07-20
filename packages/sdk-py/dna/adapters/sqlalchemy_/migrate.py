"""Driving Alembic from inside the library (i-038).

``SqlAlchemySource.connect()`` applies the schema automatically, and that
behavior is deliberately UNCHANGED by the move to Alembic: this is a
library that owns tables in its consumer's database (dna-cloud boots four
containers against one Postgres and expects the schema to be there). A
"run alembic upgrade yourself" cutover would have broken those consumers
silently, which is exactly the failure mode this issue exists to end.

What changed is the machinery underneath: instead of a hand-rolled runner
over numbered DDL payloads, the revisions are Alembic revisions, applied
through Alembic's own ``upgrade`` command over the source's live
connection. Two properties come free and neither existed before:

* **Revision checksums.** Alembic identifies a revision by id and refuses
  a database whose recorded revision isn't in the script directory.
* **``autogenerate``.** The table model in ``schema.py`` can be diffed
  against a real database — see ``tests/test_schema_autogenerate_guard.py``.

Control table: this adopts Alembic's standard ``alembic_version`` and
retires the historical names (sqlite ``schema_migrations``, postgres
``{schema}.dna_schema_migrations``). Databases carrying the old table are
detected and STAMPED at the baseline revision rather than re-migrated —
see ``baseline_legacy_database``.
"""
from __future__ import annotations

import logging
from pathlib import Path

import sqlalchemy as sa

logger = logging.getLogger(__name__)

#: The revision that reproduces the final state of the retired ladder.
BASELINE_REVISION = "0001_baseline"

#: Last version of the retired numbered ladder, per dialect. A legacy
#: database at exactly this version is schema-identical to
#: ``BASELINE_REVISION`` and can be stamped instead of re-migrated.
LEGACY_HEAD = {"postgresql": 10, "sqlite": 8}

_SCRIPT_LOCATION = Path(__file__).parent / "alembic"


def build_config(schema: str | None = None, *, connection=None):
    """An Alembic ``Config`` bound to the packaged script directory.

    No ini file is read: the wheel ships the revisions, not a config the
    consumer would have to place on disk.
    """
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(_SCRIPT_LOCATION))
    cfg.attributes["dna_schema"] = schema
    if connection is not None:
        cfg.attributes["connection"] = connection
    return cfg


def _legacy_control_table(dialect: str, schema: str | None) -> str:
    if dialect == "postgresql":
        return f"{schema or 'public'}.dna_schema_migrations"
    return "schema_migrations"


def _revisions_between(cfg, start: str | None, end: str | None) -> list[str]:
    """Revision ids walked going from ``start`` to ``end`` (exclusive of start)."""
    from alembic.script import ScriptDirectory

    if start == end:
        return []
    script = ScriptDirectory.from_config(cfg)
    walked = [
        rev.revision
        for rev in script.iterate_revisions(end or "base", start or "base")
    ]
    return list(reversed(walked))


def baseline_legacy_database(conn: sa.Connection, schema: str | None) -> bool:
    """Stamp a pre-Alembic database at the baseline instead of migrating it.

    A database built by the retired numbered ladder already HAS the
    baseline schema — re-running the baseline DDL would at best be a
    no-op and at worst (SQLite, whose payloads rebuilt tables) destructive.
    So: if the legacy control table is present and records the full
    ladder, write ``alembic_version = BASELINE_REVISION`` and drop the
    legacy table.

    A PARTIALLY migrated legacy database is refused loudly rather than
    guessed at. There is no supported path from "half of the old ladder"
    to Alembic: the old runner is gone, so this code cannot finish the
    ladder, and stamping would claim a schema the database does not have.
    The operator's move is to migrate on the previous SDK release first.

    Returns:
        True if the database was stamped (caller should skip ``upgrade``).
    """
    dialect = conn.dialect.name
    insp = sa.inspect(conn)

    legacy_name = "dna_schema_migrations" if dialect == "postgresql" \
        else "schema_migrations"
    if not insp.has_table(legacy_name, schema=schema):
        return False

    # Already cut over (both tables present) — alembic_version wins and the
    # legacy leftover is dropped below.
    qualified = _legacy_control_table(dialect, schema)
    already = insp.has_table("alembic_version", schema=schema)

    if not already:
        max_version = conn.execute(
            sa.text(f"SELECT max(version) FROM {qualified}")
        ).scalar()
        expected = LEGACY_HEAD[dialect]
        if max_version is None:
            # Control table exists but empty: nothing was ever applied, so
            # there is no schema to preserve. Let the normal upgrade run.
            logger.info(
                "Legacy control table %s is empty — dropping it and applying "
                "the Alembic baseline normally.", qualified,
            )
        elif int(max_version) != expected:
            raise RuntimeError(
                f"Cannot adopt Alembic on this database: {qualified} records "
                f"schema version {max_version}, but the retired ladder's final "
                f"version for {dialect} was {expected}. This database is "
                f"{'behind' if int(max_version) < expected else 'ahead of'} the "
                "baseline, and the old migration runner has been removed, so "
                "this code cannot reconcile it. Bring the database to version "
                f"{expected} using dna-sdk <= 0.20.0, then upgrade again."
            )
        else:
            logger.info(
                "Database is at the final pre-Alembic schema version (%s) — "
                "stamping %s and retiring %s.",
                max_version, BASELINE_REVISION, qualified,
            )
            version_table = "alembic_version"
            if schema:
                version_table = f"{schema}.{version_table}"
            conn.execute(sa.text(
                f"CREATE TABLE IF NOT EXISTS {version_table} "
                "(version_num VARCHAR(32) NOT NULL, "
                "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
            ))
            conn.execute(
                sa.text(f"INSERT INTO {version_table} (version_num) VALUES (:v)"),
                {"v": BASELINE_REVISION},
            )
            already = True

    conn.execute(sa.text(f"DROP TABLE IF EXISTS {qualified}"))
    return already


def upgrade_sync(conn: sa.Connection, schema: str | None) -> list[str]:
    """Bring ``conn``'s database to head. Returns the revisions applied.

    Runs inside ``Connection.run_sync`` from the async source — Alembic's
    command layer is synchronous.
    """
    from alembic import command
    from alembic.migration import MigrationContext

    baseline_legacy_database(conn, schema)

    cfg = build_config(schema, connection=conn)
    before = MigrationContext.configure(
        conn, opts={"version_table_schema": schema}
    ).get_current_revision()
    command.upgrade(cfg, "head")
    after = MigrationContext.configure(
        conn, opts={"version_table_schema": schema}
    ).get_current_revision()
    applied = _revisions_between(cfg, before, after)
    if applied:
        logger.info("Applied schema revision(s): %s", ", ".join(applied))
    return applied
