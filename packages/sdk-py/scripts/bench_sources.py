"""Micro-benchmark: SqlAlchemySource vs the raw SQL adapters.

Ported from the i-216 spike bench (s-sqlalchemy-source-production).
Reproducible method (no magic): for each (impl, dialect) pair,

  1. save_document × N   (insert version + auto-publish + eventbus)  [write]
  2. load_all × R        (full scope view)                           [read]
  3. query × Q           (pushdown: numeric gt + order_by + limit)

Times are wall-clock via ``time.perf_counter`` on a single process; each
suite runs against a FRESH store (temp sqlite file / throwaway pg schema).

Honesty notes (differences vs the spike-era bench):
  - The production SqlAlchemySource now matches the raw PG write path
    feature-for-feature on pg (outbox + versions_seq + pg_notify +
    auto-publish per save; a second event on publish) — the write
    numbers ARE apples-to-apples now.
  - BOTH PostgresSource and SqlAlchemySource memoize load_all per
    (scope, tenant); the raw SqliteSource does not. Read numbers compare
    cached vs cached for the pg pair, cached vs uncached for sqlite.

Run:

    cd packages/sdk-py
    .venv/bin/python scripts/bench_sources.py                # sqlite only
    DATABASE_URL=postgresql://user:pass@host/db \
        .venv/bin/python scripts/bench_sources.py            # + postgres
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
import uuid

N_DOCS = 150
R_LOADS = 20
Q_QUERIES = 100


def _doc(i: int) -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
        "kind": "Story",
        "metadata": {"name": f"s-bench-{i:04d}"},
        "spec": {
            "title": f"bench story {i}",
            "priority": i,
            "status": "todo" if i % 3 else "done",
            "body": "x" * 512,
        },
    }


async def _bench(label: str, source) -> dict:
    scope = "bench-scope"
    t0 = time.perf_counter()
    for i in range(N_DOCS):
        raw = _doc(i)
        await source.save_document(scope, "Story", raw["metadata"]["name"], raw)
        await source.publish(scope, "Story", raw["metadata"]["name"])
    t_save = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(R_LOADS):
        docs = await source.load_all(scope, None)
        assert len(docs) == N_DOCS
    t_load = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(Q_QUERIES):
        rows = [r async for r in source.query(
            scope, "Story",
            filter={"priority": {"gt": N_DOCS // 2}},
            order_by=["-priority"], limit=10,
        )]
        assert len(rows) == 10
    t_query = time.perf_counter() - t0

    return {
        "impl": label,
        "save+publish x%d (ms)" % N_DOCS: round(t_save * 1000, 1),
        "load_all x%d (ms)" % R_LOADS: round(t_load * 1000, 1),
        "query x%d (ms)" % Q_QUERIES: round(t_query * 1000, 1),
        "save avg (ms/doc)": round(t_save * 1000 / N_DOCS, 2),
        "load_all avg (ms)": round(t_load * 1000 / R_LOADS, 2),
        "query avg (ms)": round(t_query * 1000 / Q_QUERIES, 2),
    }


async def bench_sqlite_raw() -> dict:
    from dna.adapters.sqlite.source import SqliteSource
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    src = SqliteSource(db_path=tmp)
    await src.connect()
    try:
        return await _bench("SqliteSource (raw aiosqlite)", src)
    finally:
        await src.close()
        os.unlink(tmp)


async def bench_sqlite_sa() -> dict:
    from dna.adapters.sqlalchemy_ import SqlAlchemySource
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    src = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp}")
    await src.connect()
    try:
        return await _bench("SqlAlchemySource[sqlite]", src)
    finally:
        await src.close()
        os.unlink(tmp)


async def bench_pg_raw(dsn: str) -> dict:
    import asyncpg
    from dna.adapters.postgres import PostgresSource
    schema = f"dna_bench_{uuid.uuid4().hex[:10]}"
    conn = await asyncpg.connect(dsn)
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.close()
    pool = await asyncpg.create_pool(dsn)
    src = PostgresSource(pool, schema=schema)
    await src.init()
    try:
        return await _bench("PostgresSource (raw asyncpg)", src)
    finally:
        await src.close()
        c = await asyncpg.connect(dsn)
        await c.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        await c.close()


async def bench_pg_sa(dsn: str) -> dict:
    import asyncpg
    from dna.adapters.sqlalchemy_ import SqlAlchemySource
    schema = f"dna_bench_{uuid.uuid4().hex[:10]}"
    conn = await asyncpg.connect(dsn)
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.close()
    src = SqlAlchemySource(
        dsn.replace("postgresql://", "postgresql+asyncpg://", 1), schema=schema,
    )
    await src.connect()
    try:
        return await _bench("SqlAlchemySource[postgres]", src)
    finally:
        await src.close()
        c = await asyncpg.connect(dsn)
        await c.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        await c.close()


def _print(rows: list[dict]) -> None:
    if not rows:
        return
    keys = list(rows[0].keys())
    widths = [max(len(str(r.get(k, ""))) for r in [dict.fromkeys(keys, k)] + rows)
              for k in keys]
    print(" | ".join(k.ljust(w) for k, w in zip(keys, widths)))
    print("-|-".join("-" * w for w in widths))
    for r in rows:
        print(" | ".join(str(r.get(k, "")).ljust(w) for k, w in zip(keys, widths)))


async def main() -> None:
    rows = [await bench_sqlite_raw(), await bench_sqlite_sa()]
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        rows.append(await bench_pg_raw(dsn))
        rows.append(await bench_pg_sa(dsn))
    else:
        print("(DATABASE_URL unset — postgres pair skipped)\n")
    _print(rows)


if __name__ == "__main__":
    asyncio.run(main())
