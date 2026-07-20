"""Pre-Alembic databases adopt Alembic without re-running DDL (i-038).

The cutover has to handle databases that already exist. dna-cloud's
production Postgres carries the retired ``dna_schema_migrations`` control
table and the full v1..10 schema; a developer's SQLite file carries
``schema_migrations`` at v8. Neither should have the baseline DDL replayed
against it — at best a no-op, at worst destructive (the SQLite payloads
rebuilt tables).

So ``migrate.baseline_legacy_database`` STAMPS them: writes
``alembic_version = 0001_baseline`` and drops the retired control table.
And a database at a PARTIAL ladder version is refused loudly, because the
old runner is gone and stamping would claim a schema the database does not
have.
"""
from __future__ import annotations

import pytest

sa = pytest.importorskip("sqlalchemy")
pytest.importorskip("alembic")

from dna.adapters.sqlalchemy_.migrate import BASELINE_REVISION, LEGACY_HEAD

pytestmark = pytest.mark.asyncio


def _legacy_sqlite_control(conn, version: int | None) -> None:
    """Recreate the retired SQLite control table at ``version``."""
    conn.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    if version is not None:
        for v in range(1, version + 1):
            conn.exec_driver_sql(
                f"INSERT INTO schema_migrations (version, applied_at) "
                f"VALUES ({v}, '2026-01-01')"
            )


def _head_revision() -> str:
    """The ladder's current head.

    Read from the script directory rather than pinned to
    ``BASELINE_REVISION``: the baseline stopped being the head the moment a
    second revision landed, and a stamped database is expected to come
    FORWARD to head, not to sit at the baseline forever."""
    from alembic.script import ScriptDirectory

    from dna.adapters.sqlalchemy_.migrate import build_config

    return ScriptDirectory.from_config(build_config(None)).get_current_head()


async def _stamped_state(db) -> tuple[list[str], bool]:
    """(alembic_version rows, legacy table still present)."""
    eng = sa.create_engine(f"sqlite:///{db}")
    with eng.connect() as c:
        rows = [r[0] for r in c.exec_driver_sql(
            "SELECT version_num FROM alembic_version")]
        legacy = bool(list(c.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='schema_migrations'")))
    eng.dispose()
    return rows, legacy


async def test_fully_migrated_legacy_sqlite_db_is_stamped_not_remigrated(tmp_path):
    """A v8 database gets stamped; no baseline DDL runs, legacy table goes."""
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    db = tmp_path / "legacy.db"
    # Build the real pre-Alembic schema by running the baseline, then swap
    # the control table for the retired one at its final version. That is
    # byte-for-byte the state a v1..8 database is in (proven equivalent in
    # the i-038 schema comparison).
    src = SqlAlchemySource(f"sqlite+aiosqlite:///{db}")
    await src.connect()
    await src.close()

    eng = sa.create_engine(f"sqlite:///{db}")
    with eng.begin() as c:
        c.exec_driver_sql("DROP TABLE alembic_version")
        _legacy_sqlite_control(c, LEGACY_HEAD["sqlite"])
    eng.dispose()

    src = SqlAlchemySource(f"sqlite+aiosqlite:///{db}")
    applied = await src.run_schema_migrations()
    await src.close()

    assert BASELINE_REVISION not in applied, (
        "a fully-migrated legacy database must be STAMPED at the baseline, not "
        f"have the baseline DDL replayed against it — got {applied!r}"
    )
    rows, legacy_present = await _stamped_state(db)
    # Stamped at the baseline, then carried forward to head like any other
    # database — the post-baseline revisions are real work this DB still needs.
    assert rows == [_head_revision()]
    assert not legacy_present, "retired control table should have been dropped"


async def test_partially_migrated_legacy_db_is_refused_loudly(tmp_path):
    """Half a ladder is not something this code may guess at."""
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    db = tmp_path / "partial.db"
    eng = sa.create_engine(f"sqlite:///{db}")
    with eng.begin() as c:
        _legacy_sqlite_control(c, 5)  # ladder head is 8
    eng.dispose()

    src = SqlAlchemySource(f"sqlite+aiosqlite:///{db}")
    with pytest.raises(RuntimeError, match="records schema version 5"):
        await src.run_schema_migrations()
    await src.close()


async def test_empty_legacy_control_table_falls_through_to_normal_bootstrap(tmp_path):
    """Control table present but nothing applied == a fresh database."""
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    db = tmp_path / "empty.db"
    eng = sa.create_engine(f"sqlite:///{db}")
    with eng.begin() as c:
        _legacy_sqlite_control(c, None)
    eng.dispose()

    src = SqlAlchemySource(f"sqlite+aiosqlite:///{db}")
    applied = await src.run_schema_migrations()
    # A fresh bootstrap runs the whole ladder, baseline first.
    assert applied[0] == BASELINE_REVISION
    assert applied[-1] == _head_revision()
    assert await src.run_schema_migrations() == []
    await src.close()

    rows, legacy_present = await _stamped_state(db)
    assert rows == [_head_revision()]
    assert not legacy_present


async def test_stamped_database_then_boots_idempotently(tmp_path):
    """After the stamp, ordinary boots are no-ops — the whole point."""
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    db = tmp_path / "reboot.db"
    src = SqlAlchemySource(f"sqlite+aiosqlite:///{db}")
    await src.connect()
    await src.close()

    eng = sa.create_engine(f"sqlite:///{db}")
    with eng.begin() as c:
        c.exec_driver_sql("DROP TABLE alembic_version")
        _legacy_sqlite_control(c, LEGACY_HEAD["sqlite"])
    eng.dispose()

    # First boot after the stamp: adopt Alembic and come forward to head
    # (without replaying the baseline).
    src = SqlAlchemySource(f"sqlite+aiosqlite:///{db}")
    first = await src.run_schema_migrations()
    await src.close()
    assert BASELINE_REVISION not in first

    # Every boot after that is a no-op — the whole point.
    for _ in range(3):
        src = SqlAlchemySource(f"sqlite+aiosqlite:///{db}")
        assert await src.run_schema_migrations() == []
        await src.close()
