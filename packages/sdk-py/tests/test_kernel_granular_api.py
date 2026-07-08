"""Tests for kernel.list_documents + kernel.get_document — L2.

Story s-kernel-granular-api (f-source-granular-access).

Covers:
- Granular methods delegate to SourcePort granular when available
- LRU + TTL cache works
- Single-flight: 2 concurrent requests share 1 SourcePort call
- Write invalidates the correct cache scope (doc → kind-list → scope-list)
- Fallback path when SourcePort doesn't have granular methods
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, AsyncMock

import pytest

from dna.kernel import Kernel


def _make_kernel_with_mock_source(refs=None, doc_loader=None):
    """Build a Kernel with a mock SourcePort that records calls."""
    src = MagicMock()
    src.list_doc_refs = AsyncMock(
        return_value=refs if refs is not None else [("Story", "s-a")],
    )
    src.load_one = AsyncMock(
        side_effect=doc_loader if doc_loader else (
            lambda scope, kind, name, **_: {
                "kind": kind, "metadata": {"name": name}, "spec": {}}
        ),
    )
    src.load_all = AsyncMock(return_value=[])

    k = Kernel()
    k.source(src)
    return k, src


class TestListDocuments:
    @pytest.mark.asyncio
    async def test_delegates_to_source_list_doc_refs(self):
        k, src = _make_kernel_with_mock_source(
            refs=[("Story", "s-1"), ("Feature", "f-1")],
        )
        result = await k.list_documents("scope-x")
        assert result == [("Story", "s-1"), ("Feature", "f-1")]
        src.list_doc_refs.assert_called_once_with(
            "scope-x", kind=None, tenant=None,
        )

    @pytest.mark.asyncio
    async def test_filter_by_kind(self):
        k, src = _make_kernel_with_mock_source(
            refs=[("Story", "s-1")],
        )
        await k.list_documents("scope-x", kind="Story")
        src.list_doc_refs.assert_called_once_with(
            "scope-x", kind="Story", tenant=None,
        )

    @pytest.mark.asyncio
    async def test_cache_hit_skips_source(self):
        k, src = _make_kernel_with_mock_source(
            refs=[("Story", "s-1")],
        )
        await k.list_documents("scope-x")
        await k.list_documents("scope-x")
        # 1 call only — second was cache hit
        assert src.list_doc_refs.call_count == 1

    @pytest.mark.asyncio
    async def test_single_flight_concurrent_requests(self):
        """2 concurrent requests on cold cache → 1 SourcePort call."""
        call_count = {"n": 0}

        async def slow_list(*a, **kw):
            call_count["n"] += 1
            await asyncio.sleep(0.05)
            return [("Story", "s-1")]

        src = MagicMock()
        src.list_doc_refs = slow_list

        k = Kernel()
        k.source(src)

        results = await asyncio.gather(
            k.list_documents("scope-y"),
            k.list_documents("scope-y"),
            k.list_documents("scope-y"),
        )
        assert all(r == [("Story", "s-1")] for r in results)
        assert call_count["n"] == 1, (
            f"single-flight failed: {call_count['n']} source calls for 3 concurrent requests"
        )

    @pytest.mark.asyncio
    async def test_fallback_when_source_lacks_granular(self):
        """SourcePort without list_doc_refs falls back to load_all + filter."""
        src = MagicMock(spec=["load_all"])
        src.load_all = AsyncMock(return_value=[
            {"kind": "Story", "metadata": {"name": "s-old"}},
            {"kind": "Feature", "metadata": {"name": "f-old"}},
        ])

        k = Kernel()
        k.source(src)
        result = await k.list_documents("scope-z")
        assert ("Story", "s-old") in result
        assert ("Feature", "f-old") in result


class TestGetDocument:
    @pytest.mark.asyncio
    async def test_delegates_to_source_load_one(self):
        k, src = _make_kernel_with_mock_source()
        doc = await k.get_document("scope-x", "Story", "s-1")
        assert doc is not None
        assert doc["kind"] == "Story"
        src.load_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_source(self):
        k, src = _make_kernel_with_mock_source()
        await k.get_document("scope-x", "Story", "s-1")
        await k.get_document("scope-x", "Story", "s-1")
        assert src.load_one.call_count == 1

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self):
        async def loader(scope, kind, name, **_):
            return None
        k, _src = _make_kernel_with_mock_source(doc_loader=loader)
        result = await k.get_document("scope-x", "Story", "missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_fallback_when_source_lacks_granular(self):
        src = MagicMock(spec=["load_all"])
        src.load_all = AsyncMock(return_value=[
            {"kind": "Story", "metadata": {"name": "s-1"}, "spec": {"x": 1}},
        ])
        k = Kernel()
        k.source(src)
        doc = await k.get_document("scope-x", "Story", "s-1")
        assert doc is not None
        assert doc["spec"]["x"] == 1


class TestInvalidation:
    @pytest.mark.asyncio
    async def test_doc_specific_invalidate(self):
        """write_document invalidates the exact (scope, kind, name) key
        in doc cache + drops list cache entries for that kind."""
        k, src = _make_kernel_with_mock_source()
        await k.list_documents("scope-x")
        await k.get_document("scope-x", "Story", "s-1")
        assert src.list_doc_refs.call_count == 1
        assert src.load_one.call_count == 1

        # Simulate a write: only this doc + the list should invalidate
        k._invalidate_granular_cache("scope-x", kind="Story", name="s-1")

        # Doc fetch should hit source again
        await k.get_document("scope-x", "Story", "s-1")
        assert src.load_one.call_count == 2
        # List should also refetch (kind affects list)
        await k.list_documents("scope-x")
        assert src.list_doc_refs.call_count == 2

    @pytest.mark.asyncio
    async def test_scope_wide_invalidate(self):
        """Invalidate without kind drops everything for the scope."""
        k, src = _make_kernel_with_mock_source()
        await k.list_documents("scope-x")
        await k.list_documents("scope-y")  # different scope unaffected
        await k.get_document("scope-x", "Story", "s-1")

        k._invalidate_granular_cache("scope-x")  # scope-wide

        # scope-x doc cache cleared
        await k.get_document("scope-x", "Story", "s-1")
        assert src.load_one.call_count == 2
        # scope-x list cache cleared
        await k.list_documents("scope-x")
        assert src.list_doc_refs.call_count == 3  # 2 sx + 1 sy
        # scope-y list cache still hot
        await k.list_documents("scope-y")
        assert src.list_doc_refs.call_count == 3
