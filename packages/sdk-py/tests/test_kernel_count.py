"""Tests for Kernel.count() — public aggregation surface (F2 D2) — and the
``scopes=`` cross-scope param on BOTH ``kernel.count`` and ``kernel.query``
(spec F2.4).

Mirrors the test_kernel_query.py harness: mock source capturing kwargs.
Records are per-scope — count has NO ``origin`` param (inheritance/origin
does not apply; spec D5 says derived views build on top in code).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dna.kernel import Kernel


def _make_kernel_with_count(results=None, tenant_binding=None):
    """Build a Kernel with a mock source.count returning per-scope results."""
    results = results if results is not None else {}
    default = {"total": 2, "groups": None}

    async def _fake_count(scope, kind, **kwargs):
        _fake_count.calls.append((scope, kind, dict(kwargs)))
        return dict(results.get(scope, default))
    _fake_count.calls = []

    src = MagicMock()
    src.count = _fake_count

    k = Kernel()
    if tenant_binding:
        k.tenant = tenant_binding
    k._source = src  # type: ignore[assignment]
    return k, _fake_count


# ---------------------------------------------------------------------------
# Delegation + tenant binding (mirror of kernel.query's contract)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kernel_count_delegates_to_source():
    k, fake = _make_kernel_with_count({
        "scope-x": {"total": 2, "groups": [{"key": "todo", "count": 2}]},
    })
    res = await k.count(
        "scope-x", "Story",
        filter={"status": "todo"}, group_by="spec.status",
    )
    assert res == {"total": 2, "groups": [{"key": "todo", "count": 2}]}
    assert len(fake.calls) == 1
    scope, kind, kwargs = fake.calls[0]
    assert (scope, kind) == ("scope-x", "Story")
    assert kwargs["filter"] == {"status": "todo"}
    assert kwargs["group_by"] == "spec.status"


@pytest.mark.asyncio
async def test_kernel_count_uses_explicit_tenant_kwarg():
    k, fake = _make_kernel_with_count()
    await k.count("x", "Story", tenant="acme")
    assert fake.calls[0][2]["tenant"] == "acme"


@pytest.mark.asyncio
async def test_kernel_count_uses_kernel_tenant_binding():
    """When Kernel.tenant is set and tenant kwarg is None, the binding wins."""
    k, fake = _make_kernel_with_count(tenant_binding="globex")
    await k.count("x", "Story")
    assert fake.calls[0][2]["tenant"] == "globex"


@pytest.mark.asyncio
async def test_kernel_count_explicit_tenant_overrides_binding():
    k, fake = _make_kernel_with_count(tenant_binding="globex")
    await k.count("x", "Story", tenant="acme")
    assert fake.calls[0][2]["tenant"] == "acme"


@pytest.mark.asyncio
async def test_kernel_count_no_tenant_when_neither_set():
    k, fake = _make_kernel_with_count()
    await k.count("x", "Story")
    assert fake.calls[0][2]["tenant"] is None


@pytest.mark.asyncio
async def test_kernel_count_assertion_when_no_source():
    k = Kernel()
    with pytest.raises(AssertionError, match="No source registered"):
        await k.count("x", "Story")


@pytest.mark.asyncio
async def test_kernel_count_has_no_origin_param():
    """Records are per-scope: count deliberately has NO origin/inheritance
    dimension (spec D5)."""
    k, _fake = _make_kernel_with_count()
    with pytest.raises(TypeError):
        await k.count("x", "Story", origin="local")


# ---------------------------------------------------------------------------
# Cross-scope: scopes= → 1 source.count per scope, totals SUMMED, groups
# MERGED by key (re-sorted count DESC, key ASC None-last)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kernel_count_scopes_sums_totals_and_merges_groups():
    results = {
        "a": {"total": 3, "groups": [
            {"key": "todo", "count": 2}, {"key": "done", "count": 1},
        ]},
        "b": {"total": 4, "groups": [
            {"key": "done", "count": 3}, {"key": None, "count": 1},
        ]},
    }
    k, fake = _make_kernel_with_count(results)
    res = await k.count("a", "Story", group_by="spec.status", scopes=["a", "b"])
    assert [c[0] for c in fake.calls] == ["a", "b"]
    assert res["total"] == 7
    assert res["groups"] == [
        {"key": "done", "count": 4},   # 1 + 3 — re-sorted to the front
        {"key": "todo", "count": 2},
        {"key": None, "count": 1},
    ]


@pytest.mark.asyncio
async def test_kernel_count_scopes_group_merge_none_last_on_tie():
    results = {
        "a": {"total": 1, "groups": [{"key": None, "count": 1}]},
        "b": {"total": 1, "groups": [{"key": "done", "count": 1}]},
    }
    k, _fake = _make_kernel_with_count(results)
    res = await k.count("a", "Story", group_by="spec.status", scopes=["a", "b"])
    assert res["groups"] == [
        {"key": "done", "count": 1},
        {"key": None, "count": 1},
    ]


@pytest.mark.asyncio
async def test_kernel_count_scopes_wins_over_positional_scope():
    """scopes= is mutually exclusive with a diverging positional scope —
    scopes wins; the positional scope is never queried."""
    k, fake = _make_kernel_with_count()
    res = await k.count("ignored-scope", "Story", scopes=["a", "b"])
    assert [c[0] for c in fake.calls] == ["a", "b"]
    assert "ignored-scope" not in [c[0] for c in fake.calls]
    assert res["total"] == 4  # 2 + 2


@pytest.mark.asyncio
async def test_kernel_count_scopes_no_group_by_keeps_groups_none():
    k, _fake = _make_kernel_with_count()
    res = await k.count("a", "Story", scopes=["a", "b"])
    assert res == {"total": 4, "groups": None}


# ---------------------------------------------------------------------------
# scopes= on kernel.query (spec F2.4) — local-only per-scope queries,
# CONCAT without dedup; scopes wins over positional scope
# ---------------------------------------------------------------------------

def _make_kernel_with_query(rows_by_scope, tenant_binding=None):
    async def _fake_query(scope, kind, **kwargs):
        _fake_query.calls.append((scope, kind, dict(kwargs)))
        for r in rows_by_scope.get(scope, []):
            yield r
    _fake_query.calls = []

    src = MagicMock()
    src.query = _fake_query

    k = Kernel()
    # Register the SDLC Kinds so Story is classified non-inheritable
    # (same rationale as test_kernel_query.py's harness).
    from dna.extensions.sdlc import SdlcExtension
    k.load(SdlcExtension())
    if tenant_binding:
        k.tenant = tenant_binding
    k._source = src  # type: ignore[assignment]
    return k, _fake_query


def _row(name, status="todo"):
    return {"kind": "Story", "metadata": {"name": name}, "spec": {"status": status}}


@pytest.mark.asyncio
async def test_kernel_query_scopes_concat_without_dedup():
    """Records from distinct scopes are distinct docs — same name in two
    scopes yields BOTH rows (no dedup), in scope order."""
    rows_by_scope = {
        "a": [_row("s-1"), _row("dup")],
        "b": [_row("dup"), _row("s-9")],
    }
    k, fake = _make_kernel_with_query(rows_by_scope)
    out = [r async for r in k.query("a", "Story", scopes=["a", "b"])]
    names = [r["metadata"]["name"] for r in out]
    assert names == ["s-1", "dup", "dup", "s-9"]
    assert [c[0] for c in fake.calls] == ["a", "b"]


@pytest.mark.asyncio
async def test_kernel_query_scopes_wins_over_positional_scope():
    rows_by_scope = {"a": [_row("s-1")], "b": [_row("s-2")], "x": [_row("nope")]}
    k, fake = _make_kernel_with_query(rows_by_scope)
    out = [r async for r in k.query("x", "Story", scopes=["a", "b"])]
    assert [r["metadata"]["name"] for r in out] == ["s-1", "s-2"]
    assert "x" not in [c[0] for c in fake.calls]


@pytest.mark.asyncio
async def test_kernel_query_scopes_passes_kwargs_and_tenant_binding():
    rows_by_scope = {"a": [_row("s-1")], "b": []}
    k, fake = _make_kernel_with_query(rows_by_scope, tenant_binding="globex")
    [_ async for _ in k.query(
        "a", "Story",
        filter={"status": "todo"}, projection=["name"], limit=5,
        scopes=["a", "b"],
    )]
    for _scope, _kind, kwargs in fake.calls:
        assert kwargs["filter"] == {"status": "todo"}
        assert kwargs["projection"] == ["name"]
        assert kwargs["limit"] == 5
        assert kwargs["tenant"] == "globex"
