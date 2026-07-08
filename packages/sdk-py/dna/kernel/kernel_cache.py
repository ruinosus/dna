"""KernelCache — the kernel's three-tier read cache, extracted from the Kernel
god-object (s-kernel-decompose-god-object).

Behavior-preserving extraction: the TTL / single-flight / LRU logic is moved
**verbatim** from ``Kernel``; the kernel now owns one ``KernelCache`` and
delegates to it. The source/reader coupling stays in the kernel — on a miss the
cache invokes a ``load_fn``/``build_fn`` closure supplied by the caller, so this
is a pure caching *mechanism*, testable in isolation.

Three tiers (same keys, TTLs and bounds the kernel used inline):
  • **base** — per-scope base ``ManifestInstance`` (sync; insertion-order LRU,
    no TTL; key = ``scope``). Tenant-independent by design (the *base* MI is
    pre-overlay), so it is safely shared across ``with_tenant`` shallow copies.
  • **granular_list** — ``(scope, kind, tenant)`` → ``[(kind, name)]``
    (async; TTL + single-flight).
  • **granular_doc** — ``(scope, kind, name, tenant)`` → raw dict
    (async; TTL + single-flight + LRU by expiry).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

# Defaults mirror the kernel's historical class constants (i-036 bounds).
_BASE_INSTANCE_MAX = 64
_GRANULAR_LIST_TTL = 30.0
_GRANULAR_DOC_TTL = 60.0
_GRANULAR_DOC_MAX = 2000


class KernelCache:
    """The kernel's read-side cache. One instance per Kernel; shared across
    ``with_tenant`` copies (granular keys carry the tenant; the base tier is
    pre-tenant)."""

    def __init__(
        self,
        *,
        base_max: int = _BASE_INSTANCE_MAX,
        list_ttl: float = _GRANULAR_LIST_TTL,
        doc_ttl: float = _GRANULAR_DOC_TTL,
        doc_max: int = _GRANULAR_DOC_MAX,
    ) -> None:
        self._base: dict[str, Any] = {}
        self._list_cache: dict[tuple, tuple] = {}
        self._list_locks: dict[tuple, asyncio.Lock] = {}
        self._doc_cache: dict[tuple, tuple] = {}
        self._doc_locks: dict[tuple, asyncio.Lock] = {}
        self._base_max = base_max
        self._list_ttl = list_ttl
        self._doc_ttl = doc_ttl
        self._doc_max = doc_max

    # ─── base instance (sync, insertion-order LRU) ───────────────────────
    def base_store(self, scope: str, mi: Any) -> None:
        """Insert/refresh a base MI at the MRU end; evict LRU over the bound."""
        c = self._base
        c.pop(scope, None)
        c[scope] = mi
        while len(c) > self._base_max:
            del c[next(iter(c))]  # drop LRU (oldest insertion)

    def base_touch(self, scope: str) -> None:
        """Mark ``scope`` most-recently-used on a hit so a hot scope survives."""
        c = self._base
        if scope in c:
            c[scope] = c.pop(scope)

    def base_get(self, scope: str) -> Any | None:
        """Return the cached base MI (touching it) or None on a miss."""
        c = self._base
        if scope in c:
            self.base_touch(scope)
            return c[scope]
        return None

    def base_drop(self, scope: str) -> None:
        self._base.pop(scope, None)

    # ─── granular list (async, TTL + single-flight) ─────────────────────
    async def list_cached(
        self, key: tuple, load_fn: Callable[[tuple], Awaitable[Any]],
    ) -> Any:
        cache, locks = self._list_cache, self._list_locks
        entry = cache.get(key)
        if entry is not None:
            value, expires_at = entry
            if time.monotonic() < expires_at:
                return value
        lock = locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            locks[key] = lock
        async with lock:
            entry = cache.get(key)
            if entry is not None:
                value, expires_at = entry
                if time.monotonic() < expires_at:
                    return value
            value = await load_fn(key)
            cache[key] = (value, time.monotonic() + self._list_ttl)
            return value

    # ─── granular doc (async, TTL + single-flight + LRU) ─────────────────
    async def doc_cached(
        self, key: tuple, load_fn: Callable[[tuple], Awaitable[Any]],
    ) -> Any:
        cache, locks = self._doc_cache, self._doc_locks
        entry = cache.get(key)
        if entry is not None:
            value, expires_at = entry
            if time.monotonic() < expires_at:
                return value
        lock = locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            locks[key] = lock
        async with lock:
            entry = cache.get(key)
            if entry is not None:
                value, expires_at = entry
                if time.monotonic() < expires_at:
                    return value
            value = await load_fn(key)
            # LRU eviction when cache exceeds max — drop oldest 10% by expiry.
            if len(cache) >= self._doc_max:
                oldest = sorted(cache.items(), key=lambda kv: kv[1][1])[: self._doc_max // 10]
                for k, _v in oldest:
                    cache.pop(k, None)
            cache[key] = (value, time.monotonic() + self._doc_ttl)
            return value

    def doc_drop_key(self, key: tuple) -> None:
        """Drop a single granular-doc entry (cross-scope observer path)."""
        self._doc_cache.pop(key, None)

    def invalidate_granular(
        self, scope: str, kind: str | None = None, name: str | None = None,
    ) -> None:
        """Drop entries from the granular caches affected by a write.

        Scope-wide (kind=None) drops all list+doc entries for the scope.
        Kind-scoped (name=None) drops list entries matching kind + doc entries
        matching scope+kind. Doc-scoped drops only that key.
        """
        list_cache, doc_cache = self._list_cache, self._doc_cache
        if kind is None:
            drop_keys = [k for k in list_cache if k[0] == scope]
        else:
            drop_keys = [
                k for k in list_cache
                if k[0] == scope and (k[1] == "" or k[1] == kind)
            ]
        for k in drop_keys:
            list_cache.pop(k, None)
        if kind is None:
            drop_keys = [k for k in doc_cache if k[0] == scope]
        elif name is None:
            drop_keys = [k for k in doc_cache if k[0] == scope and k[1] == kind]
        else:
            drop_keys = [
                k for k in doc_cache
                if k[0] == scope and k[1] == kind and k[2] == name
            ]
        for k in drop_keys:
            doc_cache.pop(k, None)
