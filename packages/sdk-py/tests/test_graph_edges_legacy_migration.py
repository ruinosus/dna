"""The name trap: a legacy bridge still DROPS ``dna_edges``, and order decides.

``migrate.py::_LEGACY_BRIDGES`` carries ``("postgresql", 9) → DROP TABLE
dna_edges``, guarded by ``must_be_empty=("dna_edges",)``. That bridge was
written when the table was dead scaffolding nothing had ever inserted into.
It is no longer dead: revision ``0006`` recreates it and the write path fills
it.

The sequence still works — ``upgrade_sync`` runs the legacy bridge FIRST, and
only then Alembic — so a v9 database drops the empty OLD table, is stamped at
the baseline, and then 0006 creates the NEW one. But "still works" is a claim
about ORDER, and order is exactly the kind of thing that is assumed rather than
checked until the day it flips. Reverse those two calls and the bridge meets a
table our own producer has just populated, and refuses to migrate at all.

So both halves are pinned here: the ordering (always), and the real v9 → head
walk (whenever a Postgres is available, since the bridge is Postgres-only by
construction).
"""
from __future__ import annotations

import os

import pytest
import sqlalchemy as sa

from dna.adapters.sqlalchemy_ import migrate as migrate_mod


class TestTheOrderIsProven:
    def test_the_legacy_bridge_runs_before_alembic(self, monkeypatch, tmp_path):
        """⚠️ The load-bearing order.

        The bridge drops the OLD ``dna_edges`` on the way to the baseline;
        revision 0006 creates the NEW one. Bridge first, Alembic second. If
        this ever flips, a v9 database upgrading through a build that already
        has the producer would find rows in a table the bridge insists must be
        empty — and refuse, loudly, at boot.
        """
        calls: list[str] = []

        def _fake_baseline(conn, schema):
            calls.append("bridge")
            return False

        class _FakeCommand:
            @staticmethod
            def upgrade(cfg, rev):
                calls.append("alembic")

        monkeypatch.setattr(
            migrate_mod, "baseline_legacy_database", _fake_baseline,
        )
        from alembic import command as _command

        monkeypatch.setattr(_command, "upgrade", _FakeCommand.upgrade)

        engine = sa.create_engine(f"sqlite:///{tmp_path/'x.db'}")
        with engine.begin() as conn:
            migrate_mod.upgrade_sync(conn, None)
        assert calls == ["bridge", "alembic"], (
            "Alembic ran before the legacy bridge — a v9 database would meet "
            "revision 0006's dna_edges before the bridge that must drop the "
            "old one"
        )

    def test_the_bridge_still_names_the_table_it_drops(self):
        """A guard about a name only works while the name is the same. If the
        bridge is ever rewritten, this test says out loud that the drop and the
        create are talking about the same table."""
        bridge = migrate_mod._LEGACY_BRIDGES[("postgresql", 9)]
        assert bridge.must_be_empty == ("dna_edges",)
        assert any("dna_edges" in stmt for stmt in bridge.statements)


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="the legacy bridge is Postgres-only — set DATABASE_URL to walk it",
)
class TestTheRealWalk:
    """The real v9 → head walk, on a real Postgres.

    Driven through the ASYNC engine + ``run_sync``, exactly as
    ``SqlAlchemySource.connect`` drives Alembic: the SDK ships ``asyncpg`` and
    no sync Postgres driver, so a test that reached for ``psycopg2`` would be
    testing a stack this package does not have.
    """

    @staticmethod
    def _engine():
        from sqlalchemy.ext.asyncio import create_async_engine

        dsn = os.environ["DATABASE_URL"]
        if "+asyncpg" not in dsn:
            dsn = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
        return create_async_engine(dsn)

    @staticmethod
    async def _make_v9_database(engine, schema: str) -> None:
        """A REAL pre-Alembic v9 database, not a two-table caricature.

        Built by applying the baseline revision (which reproduces the final
        state of the retired ladder) and then winding it back to v9: drop
        Alembic's control table, restore the dead ``dna_edges`` that ladder
        version 10 removed, and write the legacy control table claiming 9.
        v10's ONLY change was that DROP, so this is precisely what a consumer
        stopped at the last published release has.

        A hand-rolled two-table fixture would look like it worked and prove
        nothing: revision 0003 backfills ``dna_versions``, so it would fail on
        the fixture's own thinness rather than on anything about edges.
        """
        from alembic import command

        async with engine.begin() as conn:
            await conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            await conn.execute(sa.text(f"CREATE SCHEMA {schema}"))

        def _baseline(sync_conn):
            cfg = migrate_mod.build_config(schema, connection=sync_conn)
            command.upgrade(cfg, migrate_mod.BASELINE_REVISION)

        async with engine.begin() as conn:
            await conn.run_sync(_baseline)

        async with engine.begin() as conn:
            await conn.execute(sa.text(f"DROP TABLE {schema}.alembic_version"))
            await conn.execute(sa.text(
                f"CREATE TABLE {schema}.dna_edges ("
                "scope TEXT, from_kind TEXT, from_name TEXT, to_kind TEXT, "
                "to_name TEXT, edge_type TEXT DEFAULT 'spec-ref', "
                "source_field TEXT, tenant TEXT DEFAULT '', "
                "updated_at TIMESTAMPTZ)"
            ))
            await conn.execute(sa.text(
                f"CREATE TABLE {schema}.dna_schema_migrations "
                "(version INTEGER, applied_at TEXT)"
            ))
            await conn.execute(sa.text(
                f"INSERT INTO {schema}.dna_schema_migrations VALUES (9, 'x')"
            ))

    @pytest.mark.anyio
    async def test_a_v9_database_reaches_head_with_a_usable_edge_table(self):
        """v9 → bridge → baseline → 0006.

        The structural test above pins the ORDER; this pins the OUTCOME: after
        the walk the NEW ``dna_edges`` exists with the NEW shape (``ordinal``
        gives it away — the dead DDL had no such column).
        """
        schema = f"dna_legacy_edges_{os.getpid()}"
        engine = self._engine()
        try:
            await self._make_v9_database(engine, schema)
            async with engine.begin() as conn:
                await conn.run_sync(migrate_mod.upgrade_sync, schema)
            async with engine.connect() as conn:
                cols = {
                    r[0] for r in (await conn.execute(sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = :s AND table_name = 'dna_edges'"
                    ), {"s": schema})).all()
                }
            assert "ordinal" in cols, (
                "the bridge dropped dna_edges and revision 0006 did not "
                "recreate it — or recreated the DEAD shape"
            )
            assert {"source_field", "from_api_version", "to_scope"} <= cols
        finally:
            async with engine.begin() as conn:
                await conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            await engine.dispose()

    @pytest.mark.anyio
    async def test_a_populated_legacy_table_is_refused_not_dropped(self):
        """The bridge's own promise, re-proven now that rows are possible.

        i-039 argued ``dna_edges`` was provably empty because nothing in the
        DNA tree ever wrote to it. That is no longer true of THIS build, and
        ``must_be_empty`` is what keeps a consumer's rows from being dropped by
        an upgrade. It has to refuse, not warn.
        """
        schema = f"dna_legacy_rows_{os.getpid()}"
        engine = self._engine()
        try:
            async with engine.begin() as conn:
                await conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
                await conn.execute(sa.text(f"CREATE SCHEMA {schema}"))
                await conn.execute(sa.text(
                    f"CREATE TABLE {schema}.dna_documents (x TEXT)"
                ))
                await conn.execute(sa.text(f"CREATE TABLE {schema}.dna_edges (x TEXT)"))
                await conn.execute(sa.text(
                    f"INSERT INTO {schema}.dna_edges VALUES ('mine')"
                ))

            def _bridge(sync_conn):
                migrate_mod._bridge_legacy_gap(
                    sync_conn, schema, "postgresql", 9, 10,
                    f"{schema}.dna_schema_migrations",
                )

            async with engine.begin() as conn:
                with pytest.raises(RuntimeError) as exc:
                    await conn.run_sync(_bridge)
            assert "holds 1 row(s)" in str(exc.value)
            assert "destroy that data" in str(exc.value)
        finally:
            async with engine.begin() as conn:
                await conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            await engine.dispose()
