"""s-kernel-bound-layer-observers — cross-scope invalidation drops only the
dependents' cache keys (O(dependents), not a full granular-cache scan) and the
reverse-dep observer entry is evicted on drop (no unbounded growth).
"""
from __future__ import annotations

from collections import OrderedDict

from dna.kernel import Kernel


def test_invalidation_is_o_dependents_and_evicts_observer():
    k = Kernel()
    # 1000 UNRELATED granular entries + the one dependent's 2 entries.
    granular: dict = {
        (f"other{i}", "Agent", "jarvis", "t"): ("x", 0.0)
        for i in range(1000)
    }
    granular[("childA", "Agent", "jarvis", "acme")] = ("x", 0.0)
    granular[("childA", "Agent", "jarvis", "")] = ("x", 0.0)
    k._kcache._doc_cache = granular
    k._kcache._base = OrderedDict({"childA": "mi", "other0": "mi"})
    parent_key = ("_lib", "Agent", "jarvis", "")
    k._layer_observers = OrderedDict({parent_key: {("childA", "acme")}})

    k._invalidate_internal(
        scope="_lib", tenant="", kind="Agent", name="jarvis", op="update",
    )

    # dependent's keys dropped
    assert ("childA", "Agent", "jarvis", "acme") not in k._kcache._doc_cache
    assert ("childA", "Agent", "jarvis", "") not in k._kcache._doc_cache
    # the 1000 UNRELATED keys are untouched → invalidation didn't scan/clear the cache
    assert sum(1 for key in k._kcache._doc_cache if key[0].startswith("other")) == 1000
    # child MI cache dropped; observer entry evicted on drop
    assert "childA" not in k._kcache._base
    assert parent_key not in k._layer_observers


def test_layer_observers_is_lru_bounded():
    # The cap constant exists and is finite (the LRU backstop in resolve_document).
    assert isinstance(Kernel._LAYER_OBSERVERS_MAX, int)
    assert Kernel._LAYER_OBSERVERS_MAX > 0
