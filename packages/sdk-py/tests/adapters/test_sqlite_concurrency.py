"""SqliteSource concurrency + cancellation safety (s-sqlite-single-connection).

The old single shared aiosqlite connection serialized every caller and could
leave a cursor mid-flight when a coroutine was cancelled, corrupting the next
caller. Now each operation acquires its own connection (closed in finally), so
concurrent ops don't interfere and a cancelled op can't poison the source.
"""
from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio

from dna.adapters.sqlite.source import SqliteSource


@pytest_asyncio.fixture
async def src(tmp_path):
    s = SqliteSource(str(tmp_path / "concurrency.db"))
    await s.connect()
    yield s
    await s.close()


async def _seed(src: SqliteSource, n: int) -> None:
    async with src._acquire() as conn:
        for i in range(n):
            doc = {"kind": "Story", "metadata": {"name": f"s-{i}"}, "spec": {}}
            await conn.execute(
                "INSERT OR REPLACE INTO documents "
                "(scope, kind, name, content, version, updated_at, tenant) "
                "VALUES (?, ?, ?, ?, 1, '2026-01-01', NULL)",
                ("s", "Story", f"s-{i}", json.dumps(doc)),
            )
        await conn.commit()


async def _all(src, scope, kind):
    """Materialize the query async-generator into a list."""
    return [d async for d in src.query(scope, kind)]


@pytest.mark.asyncio
async def test_concurrent_queries_all_return_correct_rows(src):
    await _seed(src, 20)
    # 30 queries fired concurrently — each on its own connection.
    results = await asyncio.gather(*[_all(src, "s", "Story") for _ in range(30)])
    assert all(len(r) == 20 for r in results)


@pytest.mark.asyncio
async def test_concurrent_writes_and_reads_dont_corrupt(src):
    async def writer(i: int) -> None:
        async with src._acquire() as conn:
            doc = {"kind": "Story", "metadata": {"name": f"w-{i}"}, "spec": {}}
            await conn.execute(
                "INSERT OR REPLACE INTO documents "
                "(scope, kind, name, content, version, updated_at, tenant) "
                "VALUES (?, ?, ?, ?, 1, '2026-01-01', NULL)",
                ("s", "Story", f"w-{i}", json.dumps(doc)),
            )
            await conn.commit()

    await asyncio.gather(*[writer(i) for i in range(25)])
    rows = await _all(src, "s", "Story")
    assert len(rows) == 25


@pytest.mark.asyncio
async def test_early_break_query_does_not_leak_connection_threads(src):
    """An abandoned ``query()`` generator must not leak aiosqlite's worker thread.

    ``query()`` is an async-generator; the common ``mi.one()`` pattern advances it
    to the first row and stops (``async for d in query(...): return d``). The old
    code held the per-op connection open *across* the ``yield``, so a suspended
    generator kept an open connection — and aiosqlite's worker thread is
    ``daemon=False``. Enough of these accumulate (a fixture/closure holding a
    reference defeats refcount cleanup) and at interpreter exit Python blocks
    joining the non-daemon threads against a dead event loop — the process hangs
    forever. This is exactly what stalled CI shard 3 for 17min *after* the suite
    reported "456 passed in 21s". The fix materializes rows then closes the
    connection BEFORE yielding, so an early break can't strand a connection.

    The discriminator is the COUNT: the old buggy code leaks one worker thread
    per suspended generator (~20 here); the fix leaks ~0. We assert well below
    20 (not exactly 0) and poll briefly first, because a thread that was just
    ``await conn.close()``d is joined but can linger one tick in
    ``threading.enumerate()`` under CI load — asserting ==0 instantly was flaky
    and reddened the python-sdk lane (i-104).
    """
    import asyncio
    import threading

    await _seed(src, 5)

    def worker_threads() -> int:
        return len(
            [t for t in threading.enumerate() if "connection_worker" in t.name]
        )

    # Let _seed's just-closed connection thread be reaped before the baseline.
    await asyncio.sleep(0.1)
    base = worker_threads()
    held = []  # hold refs so refcount GC can't mask the leak (mimics CI fixtures)
    for _ in range(20):
        gen = src.query("s", "Story")
        held.append(gen)
        first = await gen.__anext__()  # advance to the first yield
        assert first["metadata"]["name"].startswith("s-")

    # Fixed code closes each connection BEFORE the yield → 20 held generators add
    # ~0 worker threads. Poll briefly so a just-closed thread can be reaped, then
    # assert FAR below the ~20 the buggy code would strand.
    leaked = worker_threads() - base
    for _ in range(40):  # up to ~2s
        if leaked < 5:
            break
        await asyncio.sleep(0.05)
        leaked = worker_threads() - base
    assert leaked < 5, (
        f"{leaked} leaked aiosqlite worker threads across 20 held query() "
        f"generators (the old buggy code strands ~20) — a generator is holding "
        f"its (non-daemon) connection open across `yield`, which hangs the "
        f"interpreter at exit"
    )

    for gen in held:
        await gen.aclose()


@pytest.mark.asyncio
async def test_cancelled_op_leaves_source_usable(src):
    await _seed(src, 5)
    # Cancel a query task; the per-op connection cleans up in finally, so the
    # source must still serve subsequent callers (no poisoned shared connection).
    task = asyncio.create_task(_all(src, "s", "Story"))
    await asyncio.sleep(0)  # let it start
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    rows = await _all(src, "s", "Story")
    assert len(rows) == 5
