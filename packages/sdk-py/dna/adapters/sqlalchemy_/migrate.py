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

#: Highest ladder version reachable by installing a PUBLISHED pre-Alembic
#: release, per dialect. This is NOT always ``LEGACY_HEAD``: Postgres
#: migration 10 (i-039, ``DROP TABLE dna_edges``) merged AFTER the v0.20.0
#: tag, and the ladder was retired before the next release shipped — so no
#: published wheel has ever contained it. Telling an operator to "reach
#: version 10 with dna-sdk <= 0.20.0" sends them after a version that does
#: not exist; that bug is what ``_LEGACY_BRIDGES`` and the recovery message
#: below exist to fix.
LEGACY_LAST_PUBLISHED = {"postgresql": 9, "sqlite": 8}

#: The last release that still carries the retired ladder.
LEGACY_LAST_RELEASE = "0.20.0"


class _Bridge:
    """One ladder step this code can still apply on its own.

    The ladder's DDL payloads were DELETED when Alembic replaced them
    (``migrations.py``, -471 lines), so the SDK cannot replay the ladder in
    general. A step earns a bridge only when all three hold:

    * it sits between the last PUBLISHED version and ``LEGACY_HEAD``, so no
      published release can close the gap and the operator is otherwise
      stranded;
    * its DDL is small enough to restate here exactly and is idempotent;
    * its losslessness is CHECKABLE at runtime, not merely asserted.

    ``must_be_empty`` is that last check. i-039 argued ``dna_edges`` is
    provably empty because nothing in the DNA tree ever inserted a row —
    but that was proven against THIS repo, and the database being upgraded
    belongs to a consumer. So the emptiness is re-proven against the actual
    database before the DROP runs, and a non-empty table is refused loudly.
    """

    def __init__(self, to_version, summary, statements, must_be_empty=()):
        self.to_version = to_version
        self.summary = summary
        self.statements = statements
        self.must_be_empty = must_be_empty


#: ``(dialect, from_version)`` → the step that takes the database forward.
_LEGACY_BRIDGES: dict[tuple[str, int], _Bridge] = {
    ("postgresql", 9): _Bridge(
        to_version=10,
        summary="drop dna_edges, dead scaffolding with no producer (i-039)",
        statements=("DROP TABLE IF EXISTS {schema}.dna_edges",),
        must_be_empty=("dna_edges",),
    ),
}

#: Table the ladder creates at version 1 and never drops. If the control
#: table claims a version but this is missing, the control table is lying
#: about the database and no DDL may be applied on its word.
_LADDER_SENTINEL = {"postgresql": "dna_documents", "sqlite": "documents"}

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


def _stranded_message(qualified: str, dialect: str, current: int, expected: int) -> str:
    """Why we refuse a behind-the-baseline database, and what actually works.

    The instruction this replaces named a version that was never published.
    Everything here is checked against what a consumer can really install.
    """
    reachable = LEGACY_LAST_PUBLISHED[dialect]
    lines = [
        f"Cannot adopt Alembic on this database: {qualified} records schema "
        f"version {current}, but the retired ladder's final version for "
        f"{dialect} was {expected}. The ladder's DDL payloads were removed "
        "from the SDK when Alembic replaced them, so this code cannot replay "
        f"versions {current + 1}..{reachable} against your database.",
        "",
        "Recovery:",
        f"  1. Install dna-sdk=={LEGACY_LAST_RELEASE} — the last release that "
        f"still carries the ladder. It reaches version {reachable}.",
        "  2. Connect once with it; it will migrate this database forward.",
        "  3. Upgrade back to this version.",
    ]
    if reachable < expected:
        # The whole point of the bridge: step 3 is not another dead end.
        missing = (
            f"Version {expected}" if reachable + 1 == expected
            else f"Versions {reachable + 1}..{expected}"
        )
        was = "was" if reachable + 1 == expected else "were"
        lines.append(
            f"     {missing} {was} never published in any release — this "
            f"version applies it for you on connect, so reaching {reachable} "
            "in step 1 is enough."
        )
    return "\n".join(lines)


def _ahead_message(qualified: str, dialect: str, current: int, expected: int) -> str:
    """A database ahead of the ladder head is refused, never stamped."""
    return (
        f"Cannot adopt Alembic on this database: {qualified} records schema "
        f"version {current}, which is AHEAD of the retired ladder's final "
        f"version for {dialect} ({expected}). No released dna-sdk ever wrote "
        f"a version above {expected}, so this code does not know what version "
        f"{current} changed and cannot tell whether the schema still matches "
        f"the {BASELINE_REVISION} baseline. Stamping would claim a schema this "
        "database may not have, and there is no downgrade path.\n"
        "\n"
        "Recovery: this database was probably written by a newer or modified "
        "build — run that build instead. Only if those rows are stale (someone "
        "recorded versions by hand) and you have confirmed the schema really "
        f"is the pre-Alembic final state, drop them so the head becomes "
        f"{expected}:\n"
        f"  DELETE FROM {qualified} WHERE version > {expected};"
    )


def _bridge_legacy_gap(
    conn: sa.Connection,
    schema: str | None,
    dialect: str,
    current: int,
    expected: int,
    qualified: str,
) -> int:
    """Walk the known bridges from ``current`` toward ``expected``.

    Returns the version actually reached. Raises rather than applying DDL
    whenever the database does not match what the control table claims.
    """
    if current > expected:
        raise RuntimeError(_ahead_message(qualified, dialect, current, expected))

    if (dialect, current) not in _LEGACY_BRIDGES:
        raise RuntimeError(_stranded_message(qualified, dialect, current, expected))

    # About to run DDL on a consumer's database on the control table's word.
    # Verify the database is really the one the control table describes before
    # trusting it: version 1 created the sentinel and nothing ever dropped it.
    insp = sa.inspect(conn)
    sentinel = _LADDER_SENTINEL[dialect]
    if not insp.has_table(sentinel, schema=schema):
        raise RuntimeError(
            f"Refusing to migrate: {qualified} claims schema version {current}, "
            f"but table {sentinel!r} — created by ladder version 1 and never "
            "dropped — is missing. The control table does not describe this "
            "database, so this code will not apply DDL on its word. Inspect "
            "the database by hand; do not let an unrelated control table drive "
            "a migration."
        )

    while current != expected:
        bridge = _LEGACY_BRIDGES.get((dialect, current))
        if bridge is None:
            raise RuntimeError(_stranded_message(qualified, dialect, current, expected))

        for table in bridge.must_be_empty:
            qualified_table = f"{schema or 'public'}.{table}" \
                if dialect == "postgresql" else table
            if not insp.has_table(table, schema=schema):
                continue  # already gone — the step is a no-op for this table
            rows = conn.execute(
                sa.text(f"SELECT count(*) FROM {qualified_table}")
            ).scalar()
            if rows:
                raise RuntimeError(
                    f"Refusing to apply ladder version {bridge.to_version} "
                    f"({bridge.summary}): {qualified_table} holds {rows} row(s). "
                    "That table was retired as dead scaffolding precisely "
                    "because no DNA code ever wrote to it, so rows here mean "
                    "something outside DNA owns this data. Dropping it would "
                    "destroy that data.\n"
                    "\n"
                    "Recovery: preserve or confirm the rows are disposable, "
                    f"then drop the table yourself and reconnect:\n"
                    f"  DROP TABLE {qualified_table};"
                )

        logger.warning(
            "Database is at legacy schema version %d but the baseline needs "
            "%d, and no published release contains version %d. Applying it "
            "here: %s.", current, expected, bridge.to_version, bridge.summary,
        )
        for stmt in bridge.statements:
            conn.execute(sa.text(stmt.replace("{schema}", schema or "public")))
        conn.execute(
            sa.text(f"INSERT INTO {qualified} (version, applied_at) VALUES "
                    "(:v, :t)"),
            {"v": bridge.to_version, "t": _now()},
        )
        current = bridge.to_version

    return current


def _now() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _stamp_baseline(
    conn: sa.Connection, schema: str | None, qualified: str, version: int,
) -> None:
    """Write ``alembic_version = BASELINE_REVISION`` for a legacy database."""
    logger.info(
        "Database is at the final pre-Alembic schema version (%s) — "
        "stamping %s and retiring %s.",
        version, BASELINE_REVISION, qualified,
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


def baseline_legacy_database(conn: sa.Connection, schema: str | None) -> bool:
    """Stamp a pre-Alembic database at the baseline instead of migrating it.

    A database built by the retired numbered ladder already HAS the
    baseline schema — re-running the baseline DDL would at best be a
    no-op and at worst (SQLite, whose payloads rebuilt tables) destructive.
    So: if the legacy control table is present and records the full
    ladder, write ``alembic_version = BASELINE_REVISION`` and drop the
    legacy table.

    A PARTIALLY migrated legacy database is refused loudly rather than
    guessed at — with ONE exception, which exists because the general rule
    stranded real deployments. Postgres ladder version 10 shipped in no
    release at all (see ``LEGACY_LAST_PUBLISHED``), so every database built
    by the last published SDK sits one step short of the baseline and no
    published SDK can close the gap. ``_LEGACY_BRIDGES`` closes exactly the
    steps that are (a) unreachable from any release, (b) restatable here
    exactly, and (c) provably lossless against the live database. Any other
    gap still raises, now with a recovery path that exists.

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
            # Not automatically fatal any more: a gap the code still knows how
            # to close, and can PROVE is lossless, is closed here. Everything
            # else still raises — with a recovery path that exists.
            _bridge_legacy_gap(
                conn, schema, dialect, int(max_version), expected, qualified,
            )
            _stamp_baseline(conn, schema, qualified, expected)
            already = True
        else:
            _stamp_baseline(conn, schema, qualified, int(max_version))
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
