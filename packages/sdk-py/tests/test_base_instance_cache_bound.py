"""Tests for the bounded base-instance cache (i-036).

The base MI cache was an unbounded dict keyed by scope — it grew without limit
as more scopes were accessed (the residual leak vector left by i-012). It now
has an LRU max-entries bound: oldest scope evicted over the bound, and a
cache-hit touches the entry so a hot scope survives.

s-kernel-decompose-god-object: the cache mechanism moved from Kernel into the
``KernelCache`` collaborator, so these mechanism tests now exercise it directly.
"""
from __future__ import annotations

from dna.kernel.boot.cache import KernelCache


def test_evicts_oldest_over_max() -> None:
    maxn = 8
    kc = KernelCache(base_max=maxn)
    for i in range(maxn + 5):
        kc.base_store(f"s{i}", object())
    assert len(kc._base) == maxn               # bounded
    assert "s0" not in kc._base                # oldest evicted
    assert f"s{maxn + 4}" in kc._base          # newest kept


def test_touch_keeps_hot_scope() -> None:
    maxn = 8
    kc = KernelCache(base_max=maxn)
    for i in range(maxn):
        kc.base_store(f"s{i}", object())
    kc.base_touch("s0")                         # hot scope accessed
    kc.base_store("snew", object())             # forces one eviction
    assert "s0" in kc._base                     # survived (touched)
    assert "s1" not in kc._base                 # evicted instead


def test_base_get_touches_on_hit() -> None:
    maxn = 8
    kc = KernelCache(base_max=maxn)
    for i in range(maxn):
        kc.base_store(f"s{i}", object())
    assert kc.base_get("s0") is not None        # hit touches s0 → MRU
    kc.base_store("snew", object())             # evicts the now-LRU (s1)
    assert "s0" in kc._base
    assert "s1" not in kc._base


def test_store_is_idempotent_on_same_scope() -> None:
    kc = KernelCache()
    a, b = object(), object()
    kc.base_store("x", a)
    kc.base_store("x", b)
    assert len(kc._base) == 1
    assert kc._base["x"] is b                   # latest value wins


def test_base_drop_removes_scope() -> None:
    kc = KernelCache()
    kc.base_store("x", object())
    kc.base_drop("x")
    assert "x" not in kc._base
    kc.base_drop("x")                            # idempotent — no raise
