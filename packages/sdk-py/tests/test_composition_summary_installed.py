"""Phase 3b ch3 (i-112) — composition_summary gains an ``installed`` count.

``resources[kind] = {local, inherited, installed, total}`` where
``total = local + inherited + installed``. Back-compat: a scope with no Catalog
tier → ``installed: 0`` and totals unchanged from today's ``local + inherited``.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dna.kernel import Kernel


def _row(name):
    return {"kind": "Skill", "metadata": {"name": name}, "spec": {}}


def _make_kernel(scope_to_rows, *, catalog_scopes):
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
    k._source = src  # type: ignore[assignment]

    async def _chain(scope, tenant):
        return [(scope, None), (k._INHERIT_PARENT_SCOPE, None)]
    k._compute_resolution_chain = _chain  # type: ignore[assignment]
    k._composition.compute_resolution_chain = _chain  # type: ignore[assignment]

    async def _cat(tenant, *, exclude=None):
        return list(catalog_scopes)
    k._catalog_scopes = _cat  # type: ignore[assignment]
    return k


@pytest.mark.asyncio
async def test_summary_has_installed_count_and_total_sums_three():
    k = _make_kernel(
        {
            "proj": [_row("a")],
            "pkg-a": [_row("b")],
            "_lib": [_row("c")],
        },
        catalog_scopes=[("pkg-a", "acme")],
    )
    summary = await k.composition_summary("proj")
    skill = summary["resources"]["Skill"]
    assert skill == {
        "local": 1, "inherited": 1, "installed": 1, "total": 3,
    }


@pytest.mark.asyncio
async def test_no_catalog_installed_zero_total_unchanged():
    k = _make_kernel(
        {
            "proj": [_row("a")],
            "_lib": [_row("c")],
        },
        catalog_scopes=[],
    )
    summary = await k.composition_summary("proj")
    skill = summary["resources"]["Skill"]
    assert skill == {
        "local": 1, "inherited": 1, "installed": 0, "total": 2,
    }


@pytest.mark.asyncio
async def test_kind_with_only_installed_surfaces():
    k = _make_kernel(
        {
            "proj": [],
            "pkg-a": [_row("b")],
            "_lib": [],
        },
        catalog_scopes=[("pkg-a", "acme")],
    )
    summary = await k.composition_summary("proj")
    skill = summary["resources"]["Skill"]
    assert skill == {
        "local": 0, "inherited": 0, "installed": 1, "total": 1,
    }
