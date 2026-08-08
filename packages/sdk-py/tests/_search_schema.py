"""A disposable Postgres schema, brought to the migration head — for the
pgvector search tests.

Before ``s-indice-por-dimensao`` these tests only had to ``CREATE SCHEMA``: the
search provider applied its own numbered ladder on first use, so the store
built itself. It no longer does, and that is the point (``CLAUDE.md``:
*"Data-access code never runs DDL."*). The schema is now owned by the alembic
ladder, so the tests have to do what a real boot does —
``SqlAlchemySource.run_schema_migrations()`` — before a provider can read
anything.

That is a heavier setup than ``CREATE SCHEMA``, and honestly so: it exercises
the SAME path dna-cloud's containers run in their boot ``CMD``. A store that
works in a test only because the test hand-built its tables is a store nobody
has proven boots.
"""
from __future__ import annotations

import os
import uuid
from typing import Awaitable, Callable

import pytest


def dsn() -> str:
    """The Postgres DSN, from any of the three env names the suite honours
    (the ``requires_postgres`` marker gates on the same set)."""
    for key in ("DATABASE_URL", "DNA_PG_TEST_URL", "DNA_PG_TEST_DSN"):
        value = os.environ.get(key)
        if value:
            return value
    raise RuntimeError("no Postgres DSN set")  # pragma: no cover — marker guards


def _async_url(raw: str) -> str:
    return raw.replace("postgresql://", "postgresql+asyncpg://", 1)


async def migrated_schema(
    prefix: str,
) -> tuple[str, str, Callable[[], Awaitable[None]]]:
    """Create ``<prefix>_<uuid>``, migrate it to head, return
    ``(dsn, schema, cleanup)``.

    Cleanup drops the schema CASCADE, so a case never leaks state into the next
    one — the isolation the old per-case ``CREATE SCHEMA`` already gave.
    """
    import asyncpg

    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    raw = dsn()
    schema = f"{prefix}_{uuid.uuid4().hex[:12]}"

    admin = await asyncpg.connect(raw)
    try:
        await admin.execute(f"CREATE SCHEMA {schema}")
    finally:
        await admin.close()

    source = SqlAlchemySource(_async_url(raw), schema=schema)
    try:
        await source.run_schema_migrations()
    finally:
        await source.close()

    async def cleanup() -> None:
        conn = await asyncpg.connect(raw)
        try:
            await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        finally:
            await conn.close()

    return raw, schema, cleanup


async def bare_schema(prefix: str) -> tuple[str, str, Callable[[], Awaitable[None]]]:
    """The same, WITHOUT migrating — a schema at revision zero.

    Used to prove the provider refuses instead of creating: the store must
    fail loud and name the revision, and the schema must be exactly as empty
    afterwards as it was before.
    """
    import asyncpg

    raw = dsn()
    schema = f"{prefix}_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(raw)
    try:
        await admin.execute(f"CREATE SCHEMA {schema}")
    finally:
        await admin.close()

    async def cleanup() -> None:
        conn = await asyncpg.connect(raw)
        try:
            await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        finally:
            await conn.close()

    return raw, schema, cleanup


async def table_names(raw_dsn: str, schema: str) -> set[str]:
    """Every table in ``schema``, straight from the catalog."""
    import asyncpg

    conn = await asyncpg.connect(raw_dsn)
    try:
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = $1", schema
        )
    finally:
        await conn.close()
    return {r["tablename"] for r in rows}


__all__ = ["dsn", "migrated_schema", "bare_schema", "table_names", "pytest"]
