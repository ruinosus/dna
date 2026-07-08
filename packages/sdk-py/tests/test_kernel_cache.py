"""Unit tests for the KernelCache collaborator (s-kernel-decompose-god-object).

Exercises the granular tiers' mechanism in isolation — TTL expiry, single-flight
(one load per key under concurrency), LRU bound, and the scope/kind/name
invalidation matrix — independent of any source. (Base-tier mechanism lives in
test_base_instance_cache_bound.py.)
"""
from __future__ import annotations

import asyncio

import pytest

from dna.kernel.kernel_cache import KernelCache


@pytest.mark.asyncio
async def test_list_cached_caches_until_ttl():
    kc = KernelCache(list_ttl=100.0)
    calls = {"n": 0}

    async def load(_key):
        calls["n"] += 1
        return ["v"]

    key = ("scope", "", "")
    assert await kc.list_cached(key, load) == ["v"]
    assert await kc.list_cached(key, load) == ["v"]  # hit — not reloaded
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_doc_cached_single_flight():
    """Concurrent waiters on the same key trigger exactly ONE load."""
    kc = KernelCache()
    calls = {"n": 0}

    async def load(_key):
        calls["n"] += 1
        await asyncio.sleep(0.02)  # hold the lock so others queue
        return {"doc": 1}

    key = ("s", "K", "n", "")
    results = await asyncio.gather(*(kc.doc_cached(key, load) for _ in range(8)))
    assert all(r == {"doc": 1} for r in results)
    assert calls["n"] == 1  # single-flight collapsed the 8 into 1


@pytest.mark.asyncio
async def test_doc_cached_lru_evicts_over_max():
    kc = KernelCache(doc_max=10)

    async def load(key):
        return {"k": key}

    for i in range(25):
        await kc.doc_cached(("s", "K", f"n{i}", ""), load)
    # LRU keeps the cache bounded (drops oldest 10% when at/over max).
    assert len(kc._doc_cache) <= 10


@pytest.mark.asyncio
async def test_invalidate_granular_matrix():
    kc = KernelCache()

    async def load_list(_k):
        return [("K", "x")]

    async def load_doc(_k):
        return {"d": 1}

    # Seed list (scope,kind,tenant) + doc (scope,kind,name,tenant) entries.
    await kc.list_cached(("s", "K", ""), load_list)
    await kc.list_cached(("s", "K2", ""), load_list)
    await kc.doc_cached(("s", "K", "a", ""), load_doc)
    await kc.doc_cached(("s", "K", "b", ""), load_doc)
    await kc.doc_cached(("s", "K2", "c", ""), load_doc)

    # Doc-scoped: only that one key.
    kc.invalidate_granular("s", "K", "a")
    assert ("s", "K", "a", "") not in kc._doc_cache
    assert ("s", "K", "b", "") in kc._doc_cache

    # Kind-scoped (name=None): list entries for the kind + docs of scope+kind.
    kc.invalidate_granular("s", "K")
    assert ("s", "K", "") not in kc._list_cache
    assert ("s", "K2", "") in kc._list_cache          # other kind survives
    assert ("s", "K", "b", "") not in kc._doc_cache
    assert ("s", "K2", "c", "") in kc._doc_cache       # other kind survives

    # Scope-wide (kind=None): everything for the scope.
    kc.invalidate_granular("s")
    assert not any(k[0] == "s" for k in kc._list_cache)
    assert not any(k[0] == "s" for k in kc._doc_cache)
