"""Regression test for R1-fix — PostgresSource.load_all is 2 queries, not N+1.

The bug: pre-2026-05-14 load_all did 1 SELECT for docs + 1 SELECT per doc for
bundle_entries. With ~75 docs/scope × 20 scopes = 1500 round-trips on cold mi.
Combined with the 11-hook cascade, every user write triggered 5000+ queries.

Fix: load_all + load_layer call _load_view which issues exactly 2 SELECTs
(docs + all bundle_entries for the scope/tenant) and joins in Python.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_mock_pool(doc_rows, entry_rows):
    """Build an asyncpg-pool-shaped mock that returns the given rowsets in
    order across two consecutive `conn.fetch` calls.

    Mirrors the `_acquire_safe()` path (source.py:149-166): it does
    `conn = await self._pool.acquire()` then `await self._pool.release(conn)`
    — i.e. acquire/release are awaited coroutines, NOT an async context
    manager. So both must be AsyncMocks (the old cm-with-__aenter__ shape
    fed the new path a MagicMock to `await`)."""
    conn = MagicMock()
    conn.fetch = AsyncMock(side_effect=[doc_rows, entry_rows])
    pool = MagicMock()
    pool.acquire = AsyncMock(return_value=conn)
    pool.release = AsyncMock(return_value=None)
    return pool, conn


@pytest.mark.asyncio
async def test_load_all_issues_exactly_two_queries():
    from dna.adapters.postgres.source import PostgresSource

    doc_rows = [
        {"kind": "Story", "name": "s-a", "content": '{"kind":"Story","metadata":{"name":"s-a"},"spec":{}}'},
        {"kind": "Story", "name": "s-b", "content": '{"kind":"Story","metadata":{"name":"s-b"},"spec":{}}'},
        {"kind": "Feature", "name": "f-1", "content": '{"kind":"Feature","metadata":{"name":"f-1"},"spec":{}}'},
    ]
    # Bundle entries deliberately mix kinds so the grouping logic is exercised.
    # `content_binary` is selected by _load_view_uncached (source.py:322-327);
    # None = text entry (the `content` column carries the payload).
    entry_rows = [
        {"kind": "Story", "name": "s-a", "entry_path": "DOC.md", "content": "body-a", "content_binary": None},
        {"kind": "Feature", "name": "f-1", "entry_path": "FEATURE.md", "content": "body-f", "content_binary": None},
    ]
    pool, conn = _make_mock_pool(doc_rows, entry_rows)

    src = PostgresSource.__new__(PostgresSource)
    # __init__ is bypassed; manually seed the composition-aware view cache
    # added in 5ca23c6c so load_all's _load_view path has somewhere to read.
    src._view_cache = {}
    src._view_locks = {}
    src._view_invalidation_wired = False
    src._pool = pool
    src._schema = "public"
    src._readers = []
    src._ensure_migrated = AsyncMock(return_value=None)

    result = await src.load_all("scope-x")

    assert conn.fetch.call_count == 2, (
        f"R1 regression: expected exactly 2 queries, got {conn.fetch.call_count}. "
        f"N+1 returned (load_all would scale with doc count)."
    )

    # First call = docs; second = entries.
    docs_call = conn.fetch.call_args_list[0]
    entries_call = conn.fetch.call_args_list[1]
    assert "dna_documents" in docs_call.args[0]
    assert "dna_bundle_entries" in entries_call.args[0]

    # Without readers, fallback to parsed JSON content.
    assert len(result) == 3


@pytest.mark.asyncio
async def test_load_view_query_count_is_constant():
    """Doubling the doc count must NOT double the query count.
    Direct evidence the N+1 is gone."""
    from dna.adapters.postgres.source import PostgresSource

    for n_docs in (5, 50, 500):
        docs = [
            {"kind": "Story", "name": f"s-{i}",
             "content": f'{{"kind":"Story","metadata":{{"name":"s-{i}"}},"spec":{{}}}}'}
            for i in range(n_docs)
        ]
        pool, conn = _make_mock_pool(docs, [])
        src = PostgresSource.__new__(PostgresSource)
        # __init__ is bypassed; manually seed the composition-aware view cache
        # added in 5ca23c6c so load_all's _load_view path has somewhere to read.
        src._view_cache = {}
        src._view_locks = {}
        src._view_invalidation_wired = False
        src._pool = pool
        src._schema = "public"
        src._readers = []
        src._ensure_migrated = AsyncMock(return_value=None)

        await src.load_all("scope-x")
        assert conn.fetch.call_count == 2, (
            f"R1 regression at n={n_docs}: query count = {conn.fetch.call_count}, expected 2"
        )


@pytest.mark.asyncio
async def test_load_layer_tenant_also_uses_two_queries():
    """load_layer with layer_id='tenant' must reuse _load_view (2 queries)."""
    from dna.adapters.postgres.source import PostgresSource

    docs = [
        {"kind": "Agent", "name": "agent-1",
         "content": '{"kind":"Agent","metadata":{"name":"agent-1"},"spec":{}}'},
    ]
    pool, conn = _make_mock_pool(docs, [])
    src = PostgresSource.__new__(PostgresSource)
    # __init__ is bypassed; manually seed the composition-aware view cache
    # added in 5ca23c6c so load_all's _load_view path has somewhere to read.
    src._view_cache = {}
    src._view_locks = {}
    src._view_invalidation_wired = False
    src._pool = pool
    src._schema = "public"
    src._readers = []
    src._ensure_migrated = AsyncMock(return_value=None)

    await src.load_layer("scope-x", "tenant", "acme")
    assert conn.fetch.call_count == 2

    # tenant column must be passed = 'acme' in both queries
    docs_call_args = conn.fetch.call_args_list[0].args
    entries_call_args = conn.fetch.call_args_list[1].args
    assert "acme" in docs_call_args
    assert "acme" in entries_call_args


@pytest.mark.asyncio
async def test_bundle_entries_are_routed_to_correct_doc():
    """Group-by-key correctness: a bundle entry for (Story, s-a) must end up
    on s-a's handle, not on s-b's."""
    from dna.adapters.postgres.source import PostgresSource

    docs = [
        {"kind": "Story", "name": "s-a",
         "content": '{"kind":"Story","metadata":{"name":"s-a"},"spec":{}}'},
        {"kind": "Story", "name": "s-b",
         "content": '{"kind":"Story","metadata":{"name":"s-b"},"spec":{}}'},
    ]
    # `content_binary` is selected by _load_view_uncached (source.py:322-327);
    # None = text entry (payload lives in `content`).
    entries = [
        {"kind": "Story", "name": "s-a", "entry_path": "STORY.md", "content": "alpha", "content_binary": None},
        {"kind": "Story", "name": "s-b", "entry_path": "STORY.md", "content": "beta", "content_binary": None},
    ]
    pool, _conn = _make_mock_pool(docs, entries)
    src = PostgresSource.__new__(PostgresSource)
    # __init__ is bypassed; manually seed the composition-aware view cache
    # added in 5ca23c6c so load_all's _load_view path has somewhere to read.
    src._view_cache = {}
    src._view_locks = {}
    src._view_invalidation_wired = False
    src._pool = pool
    src._schema = "public"

    # Reader that captures which (name, content) it sees so we can verify
    # routing.
    seen: list[tuple[str, str]] = []

    class _CaptureReader:
        def detect(self, handle):
            return True

        def read(self, handle):
            # DictBundleHandle exposes iter_entries() — read the first one.
            entries = list(handle.iter_entries(recursive=True))
            payload = handle.read_text(entries[0]) if entries else ""
            seen.append((handle.name, payload))
            return {"kind": "Story", "metadata": {"name": handle.name},
                    "spec": {"_capture": payload}}

    src._readers = [_CaptureReader()]
    src._ensure_migrated = AsyncMock(return_value=None)

    result = await src.load_all("scope-x")

    assert len(result) == 2
    names_to_payloads = {r["metadata"]["name"]: r["spec"]["_capture"] for r in result}
    assert names_to_payloads == {"s-a": "alpha", "s-b": "beta"}
    assert set(seen) == {("s-a", "alpha"), ("s-b", "beta")}
