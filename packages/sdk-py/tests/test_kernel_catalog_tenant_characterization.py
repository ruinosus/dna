"""CHARACTERIZATION — pins current behavior for kernel decomposition Fases 2-5;
if this breaks during an extraction, the extraction changed observable behavior.

Block 4 of the kernel-decomposition spec (2026-07-08-kernel-decomposition-design)
= the Catalog-tier cache (``_catalog_scopes`` / ``_compute_catalog_scopes`` /
``_invalidate_catalog_cache``, → ``CatalogCache`` in Fase 5) AND the
``with_tenant`` shallow-copy that decides, per collaborator, "shared vs
per-copy" (spec Risk §3.3 / #3 — extracting CatalogCache/WritePipeline requires
getting this boundary exactly right or cache leaks between tenants).

Already covered elsewhere (referenced, NOT duplicated):
  - ``test_catalog_scopes_kernel``   → TTL cache hit, per-tenant isolation,
                                       write-Genome invalidation, fail-soft [].
  - ``test_kernel_tenant_phase1``    → tenant binding / slug validation / copy
                                       leaves original unchanged.

Genuine GAPS this suite closes:
  1. The exact SHARED-vs-PER-COPY attribute contract of ``with_tenant`` — which
     objects are shared by identity and which are re-instantiated pointing at
     the copy. NO test pins this today; Fase 5 mutates it.
  2. ``_catalog_cache`` is the SAME dict object across tenant views (shared
     state), so a cache entry written via one view is visible via the other —
     the property that makes per-tenant KEYS (not per-copy dicts) the isolation
     boundary.
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel


# Attributes that ``with_tenant`` must SHARE by identity (shallow copy, not
# re-created): global state + wiring that is not tenant-scoped.
_SHARED_BY_IDENTITY = [
    "_kindreg",   # registered-Kind map is global
    "_toolreg",   # tool registry is global
    "_kcache",    # read cache — granular keys carry the tenant, base is pre-tenant
    "_catalog_cache",  # keyed by tenant → safe to share the dict
    "hooks",      # hook registry is global
    "_readers",
    "_writers",
]

# Collaborators that ``with_tenant`` RE-INSTANTIATES so their back-ref points at
# the copy (they read per-kernel instance state like tenant / batch depth).
_PER_COPY_COLLABORATORS = [
    "_sync",
    "_layerpol",
    "_bundleio",
    "_composition",
    "_invctl",
    "_builder",
    "_query",
]


# ── 1. with_tenant shared-vs-per-copy identity contract ───────────────────

def test_with_tenant_shares_global_state_by_identity():
    k = Kernel()
    child = k.with_tenant("acme")
    for attr in _SHARED_BY_IDENTITY:
        assert getattr(child, attr) is getattr(k, attr), (
            f"with_tenant must SHARE {attr} by identity (global state); "
            f"a per-copy would break cache coherence / registration."
        )


def test_with_tenant_reinstantiates_stateful_collaborators_pointing_at_copy():
    k = Kernel()
    child = k.with_tenant("acme")
    for attr in _PER_COPY_COLLABORATORS:
        orig = getattr(k, attr)
        copy = getattr(child, attr)
        assert copy is not orig, (
            f"with_tenant must RE-INSTANTIATE {attr} (it reads per-kernel "
            f"instance state) — sharing it would read the wrong tenant."
        )
        # back-ref points at the COPY, not the original
        assert copy._k is child
        assert orig._k is k


def test_with_tenant_binds_tenant_and_leaves_original_unbound():
    k = Kernel()
    child = k.with_tenant("acme")
    assert child.tenant == "acme"
    assert k.tenant is None  # original untouched


def test_with_tenant_none_unbinds():
    k = Kernel(tenant="acme")
    unbound = k.with_tenant(None)
    assert unbound.tenant is None
    assert k.tenant == "acme"


# ── 2. Catalog cache is shared state keyed by tenant ──────────────────────

def test_catalog_cache_is_shared_dict_across_tenant_views():
    """The catalog cache dict is the SAME object in both views — so writing an
    entry via one view is observable via the other. This is WHY isolation is by
    tenant KEY, not by per-copy dict (spec Risk #3)."""
    k = Kernel()
    child = k.with_tenant("acme")
    assert child._catalog_cache is k._catalog_cache

    # seed via the parent view; visible through the child view.
    k._catalog_cache["acme"] = (123.0, [("pkg-a", None)])
    assert child._catalog_cache.get("acme") == (123.0, [("pkg-a", None)])


def test_invalidate_catalog_cache_all_vs_single_tenant():
    """No-arg drops EVERY tenant (a Genome write changes the mandatory set for
    all); a tenant arg drops only that key and leaves the others."""
    k = Kernel()
    k._catalog_cache["acme"] = (1.0, [("a", None)])
    k._catalog_cache["innovec"] = (1.0, [("b", None)])

    k._invalidate_catalog_cache("acme")
    assert "acme" not in k._catalog_cache
    assert "innovec" in k._catalog_cache  # other tenant untouched

    k._invalidate_catalog_cache()  # no arg → clear all
    assert k._catalog_cache == {}


def test_catalog_invalidation_via_shared_dict_is_seen_by_all_views():
    """Because the dict is shared, an invalidation triggered through any view
    (e.g. a Genome write on the parent) is seen by the child view too."""
    k = Kernel()
    child = k.with_tenant("acme")
    k._catalog_cache["acme"] = (1.0, [("a", None)])

    child._invalidate_catalog_cache("acme")  # invalidate via the child view
    assert "acme" not in k._catalog_cache    # parent sees the drop


@pytest.mark.asyncio
async def test_catalog_scopes_fail_soft_caches_empty_for_ttl():
    """A source that blows up during the catalog scan yields [] AND caches the
    empty result for the TTL (fail-soft, spec §3.5). Pinned so an extraction
    keeps the cache-the-failure semantics."""
    k = Kernel()

    class _Boom:
        def list_scopes(self):
            raise RuntimeError("boom")

    k._source = _Boom()  # type: ignore[assignment]
    out = await k._catalog_scopes("acme")
    assert out == []
    # empty result is cached (not re-attempted within TTL)
    assert "acme" in k._catalog_cache
    assert k._catalog_cache["acme"][1] == []
