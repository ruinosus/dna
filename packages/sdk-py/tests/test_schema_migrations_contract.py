"""s-dna-migration-contract — the unified schema-migration contract.

Three layers, mirroring the delivery:

1. **Helper unit tests** — ``dna.adapters._migrations.run_migrations``
   encodes the algorithm both SQL adapters share: ascending numeric order,
   applied-set skip, control-table bootstrap first, list-of-applied return,
   forward-only tolerance for a store newer than the binary.

2. **Old-DB → new-code compat (the inegociável)** — a DB created by a
   VERBATIM replica of the pre-helper inline loop (the "old code") must
   re-boot CLEAN on the refactored adapters: same control table name +
   shape, zero migrations re-applied, and a partially-migrated old DB
   gets exactly the missing tail. SQLite always; Postgres under
   ``requires_postgres``.

3. The idempotent re-boot case itself ships in the public conformance kit
   (``schema_migrations_idempotent`` — see test_source_conformance_kit.py);
   here we only cover what the kit can't (legacy-DB fixtures, control-table
   introspection).
"""
from __future__ import annotations

import os
import sqlite3
import uuid

import aiosqlite
import pytest

from dna.adapters._migrations import run_migrations

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# 1. Helper unit tests (no real DB — recording fakes)
# ---------------------------------------------------------------------------


class _Recorder:
    """Callable trio over an in-memory 'control table' (a set of ints)."""

    def __init__(self, already_applied: set[int] | None = None) -> None:
        self.control: set[int] | None = (
            set(already_applied) if already_applied is not None else None
        )
        self.events: list[tuple[str, object]] = []

    async def ensure_control_table(self) -> None:
        self.events.append(("ensure", None))
        if self.control is None:
            self.control = set()

    async def fetch_applied(self) -> list[int]:
        self.events.append(("fetch", None))
        assert self.control is not None, "ensure_control_table must run first"
        return sorted(self.control)

    async def apply_version(self, version: int, payload: object) -> None:
        self.events.append(("apply", (version, payload)))
        assert self.control is not None
        self.control.add(version)

    def kwargs(self) -> dict:
        return dict(
            ensure_control_table=self.ensure_control_table,
            fetch_applied=self.fetch_applied,
            apply_version=self.apply_version,
        )


async def test_helper_applies_in_ascending_order_and_returns_applied():
    rec = _Recorder()
    migrations = {3: "c", 1: "a", 2: "b"}  # deliberately unsorted keys
    out = await run_migrations(migrations, **rec.kwargs())
    assert out == [1, 2, 3]
    applies = [ev for ev in rec.events if ev[0] == "apply"]
    assert applies == [("apply", (1, "a")), ("apply", (2, "b")), ("apply", (3, "c"))]
    # bootstrap-first contract: ensure precedes fetch precedes any apply
    assert [e[0] for e in rec.events[:2]] == ["ensure", "fetch"]


async def test_helper_skips_applied_versions_and_is_idempotent():
    rec = _Recorder(already_applied={1, 2})
    out = await run_migrations({1: "a", 2: "b", 3: "c"}, **rec.kwargs())
    assert out == [3]
    # second run: nothing pending → [] and zero apply calls
    rec.events.clear()
    out2 = await run_migrations({1: "a", 2: "b", 3: "c"}, **rec.kwargs())
    assert out2 == []
    assert not [ev for ev in rec.events if ev[0] == "apply"]


async def test_helper_tolerates_store_newer_than_binary(caplog):
    """Forward-only tolerance: control table knows v4 but the binary only
    ships 1-3 → no crash, nothing re-applied, loud warning."""
    rec = _Recorder(already_applied={1, 2, 3, 4})
    with caplog.at_level("WARNING", logger="dna.adapters._migrations"):
        out = await run_migrations({1: "a", 2: "b", 3: "c"}, **rec.kwargs())
    assert out == []
    assert any("unknown to this code" in r.message for r in caplog.records)


async def test_helper_rejects_non_positive_or_non_int_versions():
    rec = _Recorder()
    with pytest.raises(ValueError, match="positive ints"):
        await run_migrations({0: "zero"}, **rec.kwargs())
    with pytest.raises(ValueError, match="positive ints"):
        await run_migrations({"1": "str-key"}, **rec.kwargs())  # type: ignore[dict-item]


async def test_helper_failure_keeps_prior_versions_and_stops():
    """A failing migration aborts the run; already-applied versions stay
    recorded so the next boot retries only from the failure point."""
    rec = _Recorder()

    async def apply_version(version: int, payload: object) -> None:
        if version == 2:
            raise RuntimeError("boom")
        await rec.apply_version(version, payload)

    kwargs = rec.kwargs() | {"apply_version": apply_version}
    with pytest.raises(RuntimeError, match="boom"):
        await run_migrations({1: "a", 2: "b", 3: "c"}, **kwargs)
    assert rec.control == {1}
    # next boot: v1 skipped, v2 retried (now passing), v3 applied
    out = await run_migrations({1: "a", 2: "b", 3: "c"}, **rec.kwargs())
    assert out == [2, 3]


# ---------------------------------------------------------------------------
# 2a. SQLite — old-code DB re-boots clean on the new code
# ---------------------------------------------------------------------------


async def _legacy_sqlite_migrate(db_path: str, migrations: dict[int, str]) -> None:
    """VERBATIM replica of the retired raw sqlite adapter's pre-refactor
    inline migration loop (the 'old code') — used to build DB fixtures the
    way every existing SQLite DB in the wild was built."""
    conn = await aiosqlite.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        await conn.commit()
        cursor = await conn.execute("SELECT version FROM schema_migrations")
        rows = await cursor.fetchall()
        applied = {row["version"] for row in rows}
        for version in sorted(migrations):
            if version in applied:
                continue
            await conn.executescript(migrations[version])
            await conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, "2026-01-01T00:00:00+00:00"),
            )
            await conn.commit()
    finally:
        await conn.close()


async def _sqlite_control_rows(db_path: str) -> list[int]:
    conn = await aiosqlite.connect(db_path)
    try:
        cursor = await conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        )
        return [row[0] for row in await cursor.fetchall()]
    finally:
        await conn.close()


async def test_sqlite_old_db_reboots_clean_on_new_code(tmp_path):
    from dna.adapters.sqlalchemy_ import SqlAlchemySource
    from dna.adapters.sqlalchemy_.migrations import SQLITE_MIGRATIONS as MIGRATIONS

    db = str(tmp_path / "legacy-full.db")
    await _legacy_sqlite_migrate(db, MIGRATIONS)

    src = SqlAlchemySource(f"sqlite+aiosqlite:///{db}")
    await src.connect()  # must not raise nor re-apply anything
    try:
        assert await src.run_schema_migrations() == []
        # control table: exact historical name + shape, one row per version
        conn = await aiosqlite.connect(db)
        try:
            conn.row_factory = sqlite3.Row
            cursor = await conn.execute("PRAGMA table_info(schema_migrations)")
            cols = [row["name"] for row in await cursor.fetchall()]
        finally:
            await conn.close()
        assert cols == ["version", "applied_at"]
        assert await _sqlite_control_rows(db) == sorted(MIGRATIONS)
        # and the schema is actually usable by the new code
        raw = {
            "apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Story",
            "metadata": {"name": "s-compat"}, "spec": {"title": "compat"},
        }
        await src.save_document("compat", "Story", "s-compat", raw)
        await src.publish("compat", "Story", "s-compat")
        docs = await src.load_all("compat")
        assert [d["metadata"]["name"] for d in docs] == ["s-compat"]
    finally:
        await src.close()


async def test_sqlite_partially_migrated_old_db_gets_only_the_tail(tmp_path):
    from dna.adapters.sqlalchemy_ import SqlAlchemySource
    from dna.adapters.sqlalchemy_.migrations import SQLITE_MIGRATIONS as MIGRATIONS

    versions = sorted(MIGRATIONS)
    head, tail = versions[:4], versions[4:]
    db = str(tmp_path / "legacy-partial.db")
    await _legacy_sqlite_migrate(db, {v: MIGRATIONS[v] for v in head})
    assert await _sqlite_control_rows(db) == head

    src = SqlAlchemySource(f"sqlite+aiosqlite:///{db}")
    await src.connect()  # boot applies the missing tail
    try:
        assert await _sqlite_control_rows(db) == versions
        assert await src.run_schema_migrations() == []
    finally:
        await src.close()


async def test_sqlite_fresh_db_boot_applies_all_then_noop(tmp_path):
    from dna.adapters.sqlalchemy_ import SqlAlchemySource
    from dna.adapters.sqlalchemy_.migrations import SQLITE_MIGRATIONS as MIGRATIONS

    db = str(tmp_path / "fresh.db")
    src = SqlAlchemySource(f"sqlite+aiosqlite:///{db}")
    await src.connect()
    try:
        assert await _sqlite_control_rows(db) == sorted(MIGRATIONS)
        assert await src.run_schema_migrations() == []
    finally:
        await src.close()


# ---------------------------------------------------------------------------
# 2b. Postgres — old-code schema re-boots clean on the new code
# ---------------------------------------------------------------------------


def _pg_dsn() -> str:
    return (
        os.environ.get("DATABASE_URL")
        or os.environ.get("DNA_PG_TEST_URL")
        or os.environ.get("DNA_PG_TEST_DSN")
        or ""
    )


async def _legacy_pg_migrate(
    dsn: str, schema: str, migrations: dict[int, list[str]],
) -> None:
    """VERBATIM replica of the retired raw PG adapter's pre-refactor
    migration loop (the 'old code'), minus the pool plumbing."""
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {schema}.dna_schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
        """)
        rows = await conn.fetch(f"SELECT version FROM {schema}.dna_schema_migrations")
        applied = {row["version"] for row in rows}
        for version, statements in sorted(migrations.items()):
            if version in applied:
                continue
            async with conn.transaction():
                for stmt in statements:
                    await conn.execute(stmt.format(schema=schema))
                await conn.execute(
                    f"INSERT INTO {schema}.dna_schema_migrations "
                    "(version, applied_at) VALUES ($1, $2)",
                    version, "2026-01-01T00:00:00+00:00",
                )
    finally:
        await conn.close()


@pytest.mark.requires_postgres
@pytest.mark.parametrize("partial", [False, True], ids=["full-old-db", "partial-old-db"])
async def test_postgres_old_schema_reboots_clean_on_new_code(partial):
    import asyncpg
    from dna.adapters.sqlalchemy_ import SqlAlchemySource
    from dna.adapters.sqlalchemy_.migrations import PG_MIGRATIONS as _MIGRATIONS

    dsn = _pg_dsn()
    schema = f"dna_mig_compat_{uuid.uuid4().hex[:12]}"
    versions = sorted(_MIGRATIONS)
    legacy_versions = versions[:5] if partial else versions

    conn = await asyncpg.connect(dsn)
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.close()
    pool = None
    try:
        await _legacy_pg_migrate(
            dsn, schema, {v: _MIGRATIONS[v] for v in legacy_versions},
        )

        sa_url = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
        src = SqlAlchemySource(sa_url, schema=schema)
        await src.connect()  # must not raise; applies only what's missing
        try:
            assert await src.run_schema_migrations() == []
        finally:
            await src.close()

        pool = await asyncpg.create_pool(dsn)

        async with pool.acquire() as c:
            rows = await c.fetch(
                f"SELECT version FROM {schema}.dna_schema_migrations ORDER BY version"
            )
            recorded = [r["version"] for r in rows]
            cols = await c.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = $1 AND table_name = 'dna_schema_migrations' "
                "ORDER BY ordinal_position",
                schema,
            )
        assert recorded == versions
        assert [r["column_name"] for r in cols] == ["version", "applied_at"]
    finally:
        import contextlib
        with contextlib.suppress(Exception):
            c = await asyncpg.connect(dsn)
            await c.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            await c.close()
        if pool is not None:
            with contextlib.suppress(Exception):
                await pool.close()
