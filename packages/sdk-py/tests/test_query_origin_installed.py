"""Phase 3b ch2 (i-112) — ``origin=installed`` catalog pass in query_engine.

A catalog pass runs BETWEEN the local and parent passes, sharing one dedup set
→ precedence ``Local > Catalog > Base``. Emission gating:
  - local  emits when origin in {all, local}
  - catalog emits when origin in {all, installed}
  - parent emits when origin in {all, inherited}

Back-compat: ``origin=local`` / ``origin=inherited`` are unchanged.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dna.kernel import Kernel


def _row(name, scope):
    """A queryable doc whose spec marks which scope it came from."""
    return {
        "kind": "Soul",
        "metadata": {"name": name},
        "spec": {"from": scope},
    }


def _make_kernel(scope_to_rows, *, catalog_scopes, tenant_binding=None):
    """Kernel whose mock source routes ``query(scope, kind)`` to
    ``scope_to_rows[(scope, tenant)]`` (falls back to ``scope_to_rows[scope]``),
    and whose ``_catalog_scopes`` is stubbed to ``catalog_scopes``.

    The local scope is ``proj`` (non-base); the base/parent is ``_lib``.
    """

    async def _fake_query(scope, kind, *, tenant=None, **kwargs):
        rows = scope_to_rows.get((scope, tenant))
        if rows is None:
            rows = scope_to_rows.get(scope, [])
        for r in rows:
            if r.get("kind") == kind:
                yield r

    src = MagicMock()
    src.query = _fake_query

    k = Kernel()
    if tenant_binding:
        k.tenant = tenant_binding
    k._source = src  # type: ignore[assignment]

    # Soul is inheritable by default (denylist) → parent pass runs for
    # _lib. Stub the resolution chain to [(proj, None), (_lib, None)].
    async def _chain(scope, tenant):
        return [(scope, None), (k._INHERIT_PARENT_SCOPE, None)]
    k._compute_resolution_chain = _chain  # type: ignore[assignment]

    async def _cat(tenant, *, exclude=None):
        return list(catalog_scopes)
    k._catalog_scopes = _cat  # type: ignore[assignment]
    return k, src


def _names(rows):
    return {r["metadata"]["name"]: r["spec"]["from"] for r in rows}


@pytest.mark.asyncio
async def test_origin_installed_only_catalog():
    k, _ = _make_kernel(
        {
            "proj": [_row("a", "proj")],
            "pkg-a": [_row("b", "pkg-a")],
            "_lib": [_row("c", "_lib")],
        },
        catalog_scopes=[("pkg-a", "acme")],
    )
    rows = [r async for r in k.query("proj", "Soul", origin="installed")]
    assert _names(rows) == {"b": "pkg-a"}


@pytest.mark.asyncio
async def test_origin_local_unchanged():
    k, _ = _make_kernel(
        {
            "proj": [_row("a", "proj")],
            "pkg-a": [_row("b", "pkg-a")],
            "_lib": [_row("c", "_lib")],
        },
        catalog_scopes=[("pkg-a", "acme")],
    )
    rows = [r async for r in k.query("proj", "Soul", origin="local")]
    assert _names(rows) == {"a": "proj"}


@pytest.mark.asyncio
async def test_origin_inherited_unchanged():
    k, _ = _make_kernel(
        {
            "proj": [_row("a", "proj")],
            "pkg-a": [_row("b", "pkg-a")],
            "_lib": [_row("c", "_lib")],
        },
        catalog_scopes=[("pkg-a", "acme")],
    )
    rows = [r async for r in k.query("proj", "Soul", origin="inherited")]
    # ONLY parent docs (catalog is NOT inherited).
    assert _names(rows) == {"c": "_lib"}


@pytest.mark.asyncio
async def test_origin_all_union_local_catalog_inherited():
    k, _ = _make_kernel(
        {
            "proj": [_row("a", "proj")],
            "pkg-a": [_row("b", "pkg-a")],
            "_lib": [_row("c", "_lib")],
        },
        catalog_scopes=[("pkg-a", "acme")],
    )
    rows = [r async for r in k.query("proj", "Soul", origin="all")]
    assert _names(rows) == {"a": "proj", "b": "pkg-a", "c": "_lib"}


@pytest.mark.asyncio
async def test_origin_all_local_wins_over_catalog():
    # name "x" present in BOTH local and catalog → LOCAL doc wins.
    k, _ = _make_kernel(
        {
            "proj": [_row("x", "proj")],
            "pkg-a": [_row("x", "pkg-a")],
            "_lib": [],
        },
        catalog_scopes=[("pkg-a", "acme")],
    )
    rows = [r async for r in k.query("proj", "Soul", origin="all")]
    assert _names(rows) == {"x": "proj"}


@pytest.mark.asyncio
async def test_origin_all_catalog_wins_over_base():
    # name "y" present in catalog AND base (not local) → CATALOG doc wins.
    k, _ = _make_kernel(
        {
            "proj": [],
            "pkg-a": [_row("y", "pkg-a")],
            "_lib": [_row("y", "_lib")],
        },
        catalog_scopes=[("pkg-a", "acme")],
    )
    rows = [r async for r in k.query("proj", "Soul", origin="all")]
    assert _names(rows) == {"y": "pkg-a"}


@pytest.mark.asyncio
async def test_catalog_pass_uses_target_tenant():
    seen = {}

    async def _fake_query(scope, kind, *, tenant=None, **kwargs):
        seen[scope] = tenant
        if scope == "pkg-a":
            yield _row("b", "pkg-a")

    src = MagicMock()
    src.query = _fake_query
    k = Kernel()
    k._source = src  # type: ignore[assignment]

    async def _chain(scope, tenant):
        return [(scope, None)]
    k._compute_resolution_chain = _chain  # type: ignore[assignment]

    async def _cat(tenant, *, exclude=None):
        return [("pkg-a", "acme")]
    k._catalog_scopes = _cat  # type: ignore[assignment]

    [r async for r in k.query("proj", "Soul", origin="installed")]
    assert seen["pkg-a"] == "acme"  # catalog pass queries with target_tenant


@pytest.mark.asyncio
async def test_origin_installed_parent_does_not_run():
    parent_queried = {"hit": False}

    async def _fake_query(scope, kind, *, tenant=None, **kwargs):
        if scope == "_lib":
            parent_queried["hit"] = True
            yield _row("c", "_lib")
        elif scope == "pkg-a":
            yield _row("b", "pkg-a")
        elif scope == "proj":
            yield _row("a", "proj")

    src = MagicMock()
    src.query = _fake_query
    k = Kernel()
    k._source = src  # type: ignore[assignment]

    async def _chain(scope, tenant):
        return [(scope, None), (k._INHERIT_PARENT_SCOPE, None)]
    k._compute_resolution_chain = _chain  # type: ignore[assignment]

    async def _cat(tenant, *, exclude=None):
        return [("pkg-a", "acme")]
    k._catalog_scopes = _cat  # type: ignore[assignment]

    rows = [r async for r in k.query("proj", "Soul", origin="installed")]
    assert _names(rows) == {"b": "pkg-a"}
    assert parent_queried["hit"] is False  # parent pass must NOT run


@pytest.mark.asyncio
async def test_tenant_isolation_via_catalog_scopes():
    # innovec's catalog has NO pkg-a → installed query yields nothing.
    k, _ = _make_kernel(
        {
            "proj": [],
            "pkg-a": [_row("b", "pkg-a")],
            "_lib": [],
        },
        catalog_scopes=[],  # innovec: empty catalog
    )
    rows = [r async for r in k.query("proj", "Soul", origin="installed")]
    assert rows == []
