"""The guard that would have caught ``content_binary`` (i-038).

Before Alembic, the schema was defined TWICE — as DDL payloads and as
``sa.Table`` objects — and nothing compared them. On 2026-05-25 commit
da74b845 added every line of code that reads and writes
``dna_bundle_entries.content_binary`` but no migration creating the
column. The dev database was patched by hand, so nobody noticed; every
FRESH bootstrap was broken for two weeks, until a bundle-guard test
finally failed on 2026-06-10 and the column was backfilled as migration
v9.

This test closes that hole. It boots a database from the Alembic
revisions and asks Alembic's own ``compare_metadata`` whether the live
schema still matches ``dna.adapters.sqlalchemy_.schema.build_metadata`` —
the model ``SqlAlchemySource`` binds to. A column added to the model
without a revision (or a revision without the model) is a FAILURE here,
at development time, instead of a broken bootstrap in production.

Scope of the comparison is deliberately bounded — see
``schema.UNMANAGED_INDEXES`` and ``alembic/env.py``: partial/expression
indexes can't be round-tripped by SQLAlchemy reflection and are excluded
by name, and server defaults are not compared. Tables, columns, types and
nullability ARE compared, which is the class of drift that actually bit.
"""
from __future__ import annotations

import os
import uuid

import pytest

sa = pytest.importorskip("sqlalchemy")
pytest.importorskip("alembic")


def _diff(sync_conn, schema):
    """Model-vs-database diff, filtered exactly as env.py filters it."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from dna.adapters.sqlalchemy_.schema import (
        build_metadata, compare_type, include_object, make_include_name,
    )

    is_pg = sync_conn.dialect.name == "postgresql"
    tables = build_metadata(is_pg=is_pg, schema=schema)
    ctx = MigrationContext.configure(
        sync_conn,
        opts={
            "include_object": include_object,
            "include_name": make_include_name(schema),
            "compare_type": compare_type,
            "compare_server_default": False,
            "version_table_schema": schema,
            "include_schemas": bool(schema),
            "target_metadata": tables.metadata,
        },
    )
    return compare_metadata(ctx, tables.metadata)


# ---------------------------------------------------------------------------
# SQLite — always runs.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sqlite_model_matches_migrated_database(tmp_path):
    """A database built by the revisions matches the model, exactly."""
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    db = tmp_path / "guard.db"
    src = SqlAlchemySource(f"sqlite+aiosqlite:///{db}")
    await src.connect()
    async with src._engine.connect() as conn:
        diffs = await conn.run_sync(lambda c: _diff(c, None))
    await src.close()

    assert diffs == [], (
        "The SQLite table model and the migrated schema disagree. Either a "
        "column/table was changed in adapters/sqlalchemy_/schema.py without a "
        "matching Alembic revision, or a revision changed the database without "
        "the model. Diff:\n  " + "\n  ".join(repr(d) for d in diffs)
    )


@pytest.mark.asyncio
async def test_guard_detects_a_column_added_without_a_revision(tmp_path, monkeypatch):
    """The guard FAILS on exactly the ``content_binary`` mistake.

    Adds a column to the model only — no revision — and asserts the diff is
    non-empty and names that column. A guard never seen failing is not a
    guard.
    """
    import dna.adapters.sqlalchemy_.schema as schema_mod
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    db = tmp_path / "drift.db"
    src = SqlAlchemySource(f"sqlite+aiosqlite:///{db}")
    await src.connect()  # database built from the revisions, WITHOUT the column

    real_build = schema_mod.build_metadata

    def build_with_undeclared_column(*, is_pg, schema=None):
        tables = real_build(is_pg=is_pg, schema=schema)
        tables.documents.append_column(
            sa.Column("undeclared_column", sa.Text, nullable=True)
        )
        return tables

    monkeypatch.setattr(schema_mod, "build_metadata", build_with_undeclared_column)

    async with src._engine.connect() as conn:
        diffs = await conn.run_sync(lambda c: _diff(c, None))
    await src.close()

    assert diffs, "guard did not notice a column that exists only in the model"
    rendered = repr(diffs)
    assert "add_column" in rendered and "undeclared_column" in rendered, rendered


# ---------------------------------------------------------------------------
# Postgres — needs a real server (marker + DATABASE_URL, see conftest.py).
# ---------------------------------------------------------------------------


def _dsn() -> str:
    return (
        os.environ.get("DATABASE_URL")
        or os.environ.get("DNA_PG_TEST_URL")
        or os.environ.get("DNA_PG_TEST_DSN")
        or ""
    )


@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_postgres_model_matches_migrated_database():
    import asyncpg

    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    dsn = _dsn()
    schema = f"dna_guard_{uuid.uuid4().hex[:12]}"
    conn = await asyncpg.connect(dsn)
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.close()

    src = SqlAlchemySource(
        dsn.replace("postgresql://", "postgresql+asyncpg://", 1), schema=schema
    )
    try:
        await src.connect()
        async with src._engine.connect() as c:
            diffs = await c.run_sync(lambda sc: _diff(sc, schema))
        assert diffs == [], (
            "The Postgres table model and the migrated schema disagree. Diff:\n  "
            + "\n  ".join(repr(d) for d in diffs)
        )
    finally:
        await src.close()
        c = await asyncpg.connect(dsn)
        await c.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        await c.close()
