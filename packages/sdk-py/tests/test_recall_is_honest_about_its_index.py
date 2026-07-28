"""Item 1 — a failed index refresh must not produce a confident result.

``recall_impl`` wrapped ``backfill_index`` in ``except Exception: pass`` while
``degraded`` / ``semantic`` came from the search itself. A provider-backed search
therefore reported a clean, non-degraded, semantic result that could NOT contain
the Engram written a moment earlier — the one failure mode a memory system must
never render as success. The class is small; the consequence is that "I have no
memory of that" and "I could not look" become indistinguishable.
"""
from __future__ import annotations

import pytest

from dna.application.live import LiveDna
from dna.application.runtime import recall_impl


class _Kernel:
    def __init__(self):
        self.searched: list[str] = []

    def kinds_with_trait(self, trait):
        return frozenset({"Engram"}) if trait == "memory.recallable" else frozenset()

    async def search(self, scope, query, *, kind=None, k=5, tenant=None):
        self.searched.append(kind)
        return {"hits": [], "degraded": False, "semantic": True}

    def with_tenant(self, tenant, **kw):
        return self

    async def query(self, scope, kind, **kw):
        return
        yield  # pragma: no cover — an empty async generator


class _KernelWithOneUnindexedMemory(_Kernel):
    """A kernel whose scope holds a memory the index has never seen — so the
    refresh has real work to do and MUST reach the provider."""

    def __init__(self, provider):
        super().__init__()
        self._search_provider = provider  # what dna.memory._provider() reads

    async def query(self, scope, kind, **kw):
        yield {"kind": kind, "metadata": {"name": "m1"},
               "spec": {"summary": "the memory written a moment ago"}}


class _UnreachableProvider:
    """A provider whose store cannot be reached — i-091's shape: the pool could
    not be opened because the DSN's ``ssl`` param reached Postgres as a server
    setting."""

    async def index(self, records):
        raise ConnectionError('parameter "ssl" cannot be changed now')


def _live(kernel, provider):
    return LiveDna(base_scope="sc", kernel=kernel, provider=provider)


@pytest.mark.asyncio
async def test_a_failed_refresh_marks_the_result_degraded(monkeypatch):
    async def _boom(*a, **kw):
        raise RuntimeError("sqlite-vec store is locked")

    monkeypatch.setattr("dna.memory.backfill_index", _boom, raising=False)
    import dna.memory as memory_pkg

    monkeypatch.setattr(memory_pkg, "backfill_index", _boom, raising=False)

    res = await recall_impl(_live(_Kernel(), provider=object()), "anything")
    assert res["index_refreshed"] is False
    assert res["degraded"] is True, (
        "a result the caller's last write cannot be in is a degraded result"
    )
    assert "sqlite-vec store is locked" in res["index_error"]


@pytest.mark.asyncio
async def test_a_successful_refresh_says_so_and_leaves_degraded_alone(monkeypatch):
    calls: list[tuple] = []

    async def _ok(kernel, scope, *, kinds=None, tenant=None):
        calls.append((scope, tuple(kinds or ()), tenant))
        return 0

    import dna.memory as memory_pkg

    monkeypatch.setattr(memory_pkg, "backfill_index", _ok, raising=False)

    res = await recall_impl(_live(_Kernel(), provider=object()), "anything")
    assert res["index_refreshed"] is True
    assert res["degraded"] is False
    assert "index_error" not in res
    # The refresh covers the trait-derived recallable set, not a literal list.
    assert calls == [("sc", ("Engram",), None)]


@pytest.mark.asyncio
async def test_no_provider_is_not_a_failed_refresh():
    """Lexical-only is a mode, not an error: there is no index to refresh, so
    the result is not claiming to be read-your-writes in the first place."""
    res = await recall_impl(_live(_Kernel(), provider=None), "anything")
    assert res["index_refreshed"] is False
    assert "index_error" not in res


@pytest.mark.asyncio
async def test_the_result_reports_the_scope_it_actually_read():
    """Item 5: ``recall(personal=True, scope="x")`` drops ``scope``. The drop is
    deliberate — every personal write lands at base_scope — but it used to be
    invisible, so a caller who passed a scope had no way to learn it was ignored
    short of reading the resolver."""
    live = _live(_Kernel(), provider=None)
    res = await recall_impl(
        live, "anything", "some-workspace-scope", 5,
        memory_scope="personal", oid="user-1",
    )
    assert res["scope"] == "sc", "personal memory reads its one home"
    plain = await recall_impl(live, "anything", "some-other-scope")
    assert plain["scope"] == "some-other-scope"


@pytest.mark.asyncio
async def test_a_refresh_that_cannot_reach_its_store_is_reported_not_swallowed():
    """i-091 — the honest degradation, pinned through the REAL ``backfill_index``.

    The other cases here monkeypatch the refresh; this one does not, so the pin
    covers the whole path: ``backfill_index`` must not absorb a provider error
    into a ``0 records`` success, and ``recall_impl`` must not report a result
    the caller's last write cannot be in as clean. i-091 fixed the *cause* of
    one such failure (an ``ssl=`` DSN param handed to asyncpg as a server
    setting); the reporting of any remaining one may not be traded for a green
    path along the way.
    """
    prov = _UnreachableProvider()
    live = _live(_KernelWithOneUnindexedMemory(prov), provider=prov)

    res = await recall_impl(live, "anything")

    assert res["index_refreshed"] is False
    assert res["degraded"] is True
    assert 'parameter "ssl" cannot be changed now' in res["index_error"]
