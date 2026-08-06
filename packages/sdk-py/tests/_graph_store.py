"""Shared store fixture for the derived-graph tests — BOTH dialects.

The whole argument for a recursive CTE over a graph extension is that the query
is standard SQL and runs unchanged on Postgres and SQLite. An argument like that
is worth exactly as much as the test that exercises both, so these modules
parametrize over the two rather than trusting SQLite and hoping.

Postgres runs when ``DATABASE_URL`` is set (the same gate the adapter
conformance matrix uses) and is skipped otherwise, so a laptop without a
database still runs the SQLite half instead of silently running nothing.

Three things only Postgres can falsify, which is why the second half matters:
``jsonb_exists`` (the backfill's GIN-served key-existence predicate, which has
no SQLite equivalent), the ``||`` concatenation and ``CASE`` inside a recursive
CTE, and the fact that ``documents`` there keys on ``tenant`` — so two tenants
really can hold the same document name (i-092 makes that impossible on SQLite).
"""
from __future__ import annotations

import os
import tempfile
from typing import Any

import pytest


DIALECTS = ("sqlite", "postgres")


async def build_store(dialect: str, tag: str) -> tuple[Any, Any]:
    """``(source, cleanup)`` for one dialect. ``tag`` namespaces the PG schema."""
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    if dialect == "sqlite":
        fd, path = tempfile.mkstemp(prefix=f"dna-{tag}-", suffix=".db")
        os.close(fd)
        src = SqlAlchemySource(f"sqlite+aiosqlite:///{path}")
        await src.connect()

        async def cleanup() -> None:
            await src.close()
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass

        return src, cleanup

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("DATABASE_URL not set — skipping the Postgres dialect")
    if "+asyncpg" not in dsn:
        dsn = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    schema = f"dna_{tag}_{os.getpid()}"

    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine

    setup = create_async_engine(dsn)
    async with setup.begin() as conn:
        await conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await conn.execute(sa.text(f"CREATE SCHEMA {schema}"))
    await setup.dispose()

    src = SqlAlchemySource(dsn, schema=schema)
    await src.connect()

    async def cleanup() -> None:
        await src.close()
        teardown = create_async_engine(dsn)
        async with teardown.begin() as conn:
            await conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await teardown.dispose()

    return src, cleanup
