"""SPIKE (i-216) — SqlAlchemySource × the public source-conformance kit.

Mirror of ``test_source_conformance_kit.py`` for the SQLAlchemy Core
prototype ONLY (kept separate so the spike doesn't pollute the canonical
adapter matrix). Runs the SAME ~20-case suite twice:

  1. sqlalchemy-sqlite    — aiosqlite engine over a temp-file DB
  2. sqlalchemy-postgres  — asyncpg engine over DATABASE_URL (skips unset),
                            one throwaway schema per factory build

Known, tracked divergences (documented — not silently green):
  - sqlalchemy-sqlite × tenant_overlay_shadows_base → strict xfail. The
    SQLite ``documents`` PK is (scope, kind, name) WITHOUT tenant — the
    exact schema limitation behind i-092 on the raw SqliteSource. The
    prototype binds to the EXISTING schema by design, so it inherits it.

Requires the ``sqlalchemy-spike`` extra; the whole module skips without it.
"""
from __future__ import annotations

import os
import tempfile
import uuid
from typing import Any

import pytest

pytest.importorskip("sqlalchemy", reason="spike extra not installed (sqlalchemy-spike)")

from dna.testing import source_conformance_suite


async def _sqlalchemy_sqlite_factory():
    from dna.adapters.sqlalchemy_ import SqlAlchemySource
    from dna.kernel import Kernel

    fd, tmp = tempfile.mkstemp(prefix="dna-spike-sa-", suffix=".db")
    os.close(fd)
    src = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp}")
    await src.connect()
    Kernel.auto(source=src)

    async def cleanup() -> None:
        await src.close()
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass

    return src, cleanup


async def _sqlalchemy_postgres_factory():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("DATABASE_URL not set — skipping SqlAlchemySource[postgres]")

    import asyncpg
    from dna.adapters.sqlalchemy_ import SqlAlchemySource
    from dna.kernel import Kernel

    schema = f"dna_spike_{uuid.uuid4().hex[:12]}"
    conn = await asyncpg.connect(dsn)
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.close()

    sa_url = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    src = SqlAlchemySource(sa_url, schema=schema)
    await src.connect()
    Kernel.auto(source=src)

    async def cleanup() -> None:
        import contextlib
        with contextlib.suppress(Exception):
            await src.close()
        with contextlib.suppress(Exception):
            c = await asyncpg.connect(dsn)
            await c.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            await c.close()

    return src, cleanup


_FACTORIES: dict[str, Any] = {
    "sqlalchemy-sqlite": _sqlalchemy_sqlite_factory,
    "sqlalchemy-postgres": _sqlalchemy_postgres_factory,
}

_KNOWN = {
    ("sqlalchemy-sqlite", "tenant_overlay_shadows_base"): pytest.mark.xfail(
        reason="i-092 (inherited schema limitation): SQLite documents PK is "
               "(scope, kind, name) without tenant — an overlay publish "
               "clobbers the base row. Same xfail as the raw SqliteSource.",
        strict=True,
    ),
}


def _all_params():
    params = []
    for fid, factory in _FACTORIES.items():
        for case in source_conformance_suite(factory):
            marks = [_KNOWN[k] for k in ((fid, case.name),) if k in _KNOWN]
            params.append(pytest.param(case, id=f"{fid}-{case.name}", marks=marks))
    return params


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _all_params())
async def test_sqlalchemy_spike_conformance(case):
    await case.run()
