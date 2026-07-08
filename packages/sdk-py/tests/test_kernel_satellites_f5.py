"""FakeKernelSlice guard for the Fase-5 satellites (``s-kernel-decomp-f5-satellites``).

The four read-only leaf collaborators extracted in Fase 5 — RegistryAccessor,
SearchEngine, CatalogCache, SourceFacade — each declare a NARROW ``*Host``
Protocol (``dna.kernel.collaborator_ports``). This test proves the
narrowing is real, not cosmetic: each is instantiated with a ``SimpleNamespace``
slice exposing ONLY its ``*Host`` surface — a slice, NOT a ``Kernel`` — and its
main path is exercised. Reach for a member outside the contract and the slice
raises ``AttributeError``.

Also pins the CatalogCache shared-dict invariant AT THE COLLABORATOR level
(complements ``test_kernel_catalog_tenant_characterization`` which pins it at the
kernel level): the collaborator holds NO cache — it reads/writes the dict handed
in via the host, so the kernel-owned shared dict stays the single isolation
boundary (spec Risk #3).
"""
from __future__ import annotations

import types

import pytest

from dna.kernel import Kernel
from dna.kernel.catalog_cache import CatalogCache
from dna.kernel.collaborator_ports import (
    CatalogCacheHost,
    RegistryAccessorHost,
    SearchEngineHost,
    SourceFacadeHost,
)
from dna.kernel.registry_accessor import RegistryAccessor
from dna.kernel.search_engine import SearchEngine
from dna.kernel.source_facade import SourceFacade

_GOD_MEMBER = "hooks"


def _slice(**members) -> types.SimpleNamespace:
    ns = types.SimpleNamespace(**members)
    assert not hasattr(ns, _GOD_MEMBER), "slice leaked a god-object member"
    return ns


def _agen(rows):
    async def _q(*_a, **_k):
        for r in rows:
            yield r
    return _q


# ── RegistryAccessor ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_registry_accessor_runs_on_narrow_fake():
    rows = [{"metadata": {"name": "gpt-x"}, "spec": {"model_id": "gpt-x", "aliases": ["gx"]}}]
    fake = _slice(query=_agen(rows))
    ra = RegistryAccessor(fake)  # type: ignore[arg-type]
    assert (await ra.model_profile("gpt-x"))["spec"]["model_id"] == "gpt-x"
    assert (await ra.model_profile("gx"))["spec"]["model_id"] == "gpt-x"  # alias
    assert await ra.model_profile("nope") is None
    assert isinstance(fake, RegistryAccessorHost)


@pytest.mark.asyncio
async def test_registry_accessor_fail_soft_on_query_error():
    async def _boom(*_a, **_k):
        raise RuntimeError("boom")
        yield  # pragma: no cover — make it a generator
    fake = _slice(query=_boom)
    ra = RegistryAccessor(fake)  # type: ignore[arg-type]
    assert await ra.model_profile("x") is None  # degrades, never raises


# ── SearchEngine ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_engine_lexical_fallback_on_narrow_fake():
    rows = [{"metadata": {"name": "doc1"}, "spec": {"text": "hello world"}}]
    fake = _slice(
        tenant=None, _search_provider=None, _search_provider_warned=False,
        query=_agen(rows),
    )
    se = SearchEngine(fake)  # type: ignore[arg-type]
    out = await se.search("myscope", "hello", kind="Doc")
    assert out["degraded"] is True
    assert out["hits"] and out["hits"][0]["name"] == "doc1"
    assert isinstance(fake, SearchEngineHost)


@pytest.mark.asyncio
async def test_search_engine_provider_path_resets_damper():
    class _Prov:
        async def search(self, **_k):
            return [{"name": "semantic"}]
    fake = _slice(
        tenant=None, _search_provider=_Prov(), _search_provider_warned=True,
        query=_agen([]),
    )
    se = SearchEngine(fake)  # type: ignore[arg-type]
    out = await se.search("s", "q", kind="Doc")
    assert out == {"hits": [{"name": "semantic"}], "degraded": False}
    assert fake._search_provider_warned is False  # damper reset via the host


# ── CatalogCache (the shared-dict-at-collaborator-level invariant) ─────────

@pytest.mark.asyncio
async def test_catalog_cache_reads_and_writes_the_host_owned_dict():
    """The collaborator holds NO cache — the dict is owned by the host. A miss
    computes + writes it back into the host dict (spec Risk #3)."""
    shared: dict = {}
    fake = _slice(
        _INHERIT_PARENT_SCOPE="_lib",
        _GRANULAR_DOC_TTL=60.0,
        _catalog_cache=shared,
        query=_agen([]),
        list_scopes_async=_scope_list([]),
        source_metadata=lambda: {},
    )
    cc = CatalogCache(fake)  # type: ignore[arg-type]
    out = await cc.catalog_scopes("acme")
    assert out == []
    # the empty compute was written back into the HOST dict, not a private one.
    assert "acme" in shared and shared["acme"][1] == []
    assert isinstance(fake, CatalogCacheHost)


def test_catalog_cache_invalidate_mutates_host_dict_in_place():
    shared = {"acme": (1.0, []), "innovec": (1.0, [])}
    fake = _slice(
        _INHERIT_PARENT_SCOPE="_lib", _GRANULAR_DOC_TTL=60.0,
        _catalog_cache=shared, query=_agen([]),
        list_scopes_async=_scope_list([]), source_metadata=lambda: {},
    )
    cc = CatalogCache(fake)  # type: ignore[arg-type]
    cc.invalidate("acme")
    assert "acme" not in shared and "innovec" in shared  # same dict, mutated
    cc.invalidate()  # no arg → clear all
    assert shared == {}


# ── SourceFacade ──────────────────────────────────────────────────────────

def test_source_facade_runs_on_narrow_fake():
    src = types.SimpleNamespace(base_dir="/tmp/x", _dsn=None)
    fake = _slice(_source=src)
    sf = SourceFacade(fake)  # type: ignore[arg-type]
    assert sf.source_type == "SimpleNamespace"
    assert sf.source_metadata() == {"type": "SimpleNamespace", "base_dir": "/tmp/x"}
    assert isinstance(fake, SourceFacadeHost)


def test_source_facade_empty_when_no_source():
    fake = _slice(_source=None)
    sf = SourceFacade(fake)  # type: ignore[arg-type]
    assert sf.source_type == ""
    assert sf.source_metadata() == {}


# ── a real Kernel structurally satisfies every satellite host ─────────────

@pytest.mark.parametrize(
    "host",
    [RegistryAccessorHost, SearchEngineHost, CatalogCacheHost, SourceFacadeHost],
)
def test_kernel_satisfies_satellite_host(host):
    k = Kernel.auto()
    assert isinstance(k, host), f"Kernel must structurally satisfy {host.__name__}"


def _scope_list(scopes):
    async def _f():
        return scopes
    return _f
