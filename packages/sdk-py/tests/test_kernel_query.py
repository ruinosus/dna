"""Tests for Kernel.query() — kernel-level wrapper over SourcePort.query.

Story s-kernel-query-wrapper (Feature f-source-as-query). Mostly thin
delegation tests + tenant binding.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dna.kernel import Kernel


def _make_kernel_with_source(rows=None, tenant_binding=None):
    """Build a Kernel with a mock source.query that yields ``rows``."""
    rows = rows if rows is not None else [
        {"kind": "Story", "metadata": {"name": "s-a"}, "spec": {"status": "todo"}},
        {"kind": "Story", "metadata": {"name": "s-b"}, "spec": {"status": "todo"}},
    ]

    async def _fake_query(scope, kind, **kwargs):
        _fake_query.last_kwargs = kwargs
        _fake_query.last_args = (scope, kind)
        for r in rows:
            yield r
    _fake_query.last_kwargs = {}
    _fake_query.last_args = None

    src = MagicMock()
    src.query = _fake_query

    k = Kernel()
    # Register the SDLC Kinds so the kernel reads Story's scope_inheritable=False
    # classification (s-kernel-kindport-classification-attrs — non-inheritable is
    # now derived from the registered Kind, not a hardcoded name list). Without it
    # Story defaults to inheritable and the query escalates to _lib instead
    # of staying on the requested scope.
    from dna.extensions.sdlc import SdlcExtension
    k.load(SdlcExtension())
    if tenant_binding:
        k.tenant = tenant_binding
    k._source = src  # type: ignore[assignment]
    return k, src, _fake_query


@pytest.mark.asyncio
async def test_kernel_query_delegates_to_source():
    k, _src, fake = _make_kernel_with_source()
    rows = [r async for r in k.query(
        "scope-x", "Story",
        filter={"status": "todo"},
        limit=50,
    )]
    assert len(rows) == 2
    assert fake.last_args == ("scope-x", "Story")
    assert fake.last_kwargs["filter"] == {"status": "todo"}
    assert fake.last_kwargs["limit"] == 50


@pytest.mark.asyncio
async def test_kernel_query_passes_projection_through():
    k, _src, fake = _make_kernel_with_source()
    [_ async for _ in k.query(
        "x", "Story",
        projection=["name", "spec.title"],
    )]
    assert fake.last_kwargs["projection"] == ["name", "spec.title"]


@pytest.mark.asyncio
async def test_kernel_query_passes_order_by_offset():
    k, _src, fake = _make_kernel_with_source()
    [_ async for _ in k.query(
        "x", "Story",
        order_by=["-spec.updated_at"],
        offset=10,
    )]
    assert fake.last_kwargs["order_by"] == ["-spec.updated_at"]
    assert fake.last_kwargs["offset"] == 10


@pytest.mark.asyncio
async def test_kernel_query_uses_explicit_tenant_kwarg():
    k, _src, fake = _make_kernel_with_source()
    [_ async for _ in k.query("x", "Story", tenant="acme")]
    assert fake.last_kwargs["tenant"] == "acme"


@pytest.mark.asyncio
async def test_kernel_query_uses_kernel_tenant_binding():
    """When Kernel.tenant is set and tenant kwarg is None, the binding wins."""
    k, _src, fake = _make_kernel_with_source(tenant_binding="globex")
    [_ async for _ in k.query("x", "Story")]
    assert fake.last_kwargs["tenant"] == "globex"


@pytest.mark.asyncio
async def test_kernel_query_explicit_tenant_overrides_binding():
    """tenant kwarg takes precedence over Kernel.tenant binding (Stripe Connect)."""
    k, _src, fake = _make_kernel_with_source(tenant_binding="globex")
    [_ async for _ in k.query("x", "Story", tenant="acme")]
    assert fake.last_kwargs["tenant"] == "acme"


@pytest.mark.asyncio
async def test_kernel_query_no_tenant_when_neither_set():
    k, _src, fake = _make_kernel_with_source()
    [_ async for _ in k.query("x", "Story")]
    assert fake.last_kwargs["tenant"] is None


@pytest.mark.asyncio
async def test_kernel_query_assertion_when_no_source():
    k = Kernel()
    with pytest.raises(AssertionError, match="No source registered"):
        [_ async for _ in k.query("x", "Story")]


@pytest.mark.asyncio
async def test_kernel_query_yields_all_rows_lazily():
    """Returns AsyncIterator — caller decides materialization."""
    k, _src, _fake = _make_kernel_with_source(rows=[
        {"kind": "Story", "metadata": {"name": f"s-{i}"}, "spec": {}}
        for i in range(100)
    ])
    count = 0
    async for _ in k.query("x", "Story"):
        count += 1
        if count >= 10:
            break  # early exit must work
    assert count == 10
