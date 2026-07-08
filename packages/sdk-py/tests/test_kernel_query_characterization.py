"""CHARACTERIZATION — pins current behavior for kernel decomposition Fases 2-5;
if this breaks during an extraction, the extraction changed observable behavior.

Block 2 of the kernel-decomposition spec (2026-07-08-kernel-decomposition-design)
= the read/resolve surface (``query`` / ``count`` / ``resolve_document`` /
``composition_summary`` / ``personalize_document``). Most logic already lives in
the ``composition_resolver`` / ``query_engine`` collaborators; Fase 5 moves
``composition_summary`` in and keeps the kernel facade thin. This suite pins the
OBSERVABLE resolution behavior at the kernel surface so those moves are provable.

Already covered elsewhere (referenced, NOT duplicated):
  - ``test_composition_v2_resolver``    → pure merge fns, depth walk, cycle,
                                          tenant-overlay-wins, provenance serialize.
  - ``test_resolve_document_catalog``   → catalog splice precedence + provenance.
  - ``test_composition_summary_installed`` → installed count arithmetic.
  - ``test_kernel_query`` / ``test_kernel_count`` → source push-down + tenant stamp.
  - ``test_composition_resolver_collab``→ collaborator wiring + rule defaults.

Genuine GAPS this suite closes:
  1. ``ResolvedDocument.contributions_by_field`` — the field-level provenance
     (``spec.X ← scope``) is POPULATED by the resolver but asserted by NO test
     at the ``kernel.resolve_document`` surface. Pinned here end-to-end.
  2. A single cohesive golden that crosses inheritance + tenant overlay +
     field-level merge in one resolve, so a reorder of the merge pipeline breaks
     loudly.
"""
from __future__ import annotations

from typing import Any

import pytest

from dna.kernel import Kernel


# ── MockSource (mirrors test_resolve_document_catalog / test_composition_v2) ──

class _MockSource:
    def __init__(self) -> None:
        self.docs: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        self.layer_policies: dict[str, list[dict[str, Any]]] = {}

    async def load_one(self, scope, kind, name, *, readers=None, tenant=None):
        return self.docs.get((scope, kind, name, tenant or ""))

    async def query(self, scope, kind, *, filter=None, projection=None,
                    limit=None, offset=None, order_by=None, tenant=None):
        if kind == "LayerPolicy":
            for d in self.layer_policies.get(scope, []):
                yield d
        return

    async def load_bootstrap_docs(self, scope, **kw):
        return []

    async def load_all(self, scope, readers=None, **kw):
        return []


def _pkg(scope: str, parent: str | None = None) -> dict[str, Any]:
    return {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
            "metadata": {"name": scope},
            "spec": {"owner_tenant": "acme", "parent_scope": parent}}


def _doc(scope: str, kind: str, name: str, spec: dict) -> dict[str, Any]:
    return {"apiVersion": "github.com/ruinosus/dna/test/v1", "kind": kind,
            "metadata": {"name": name}, "spec": spec}


def _layer_policy(scope: str, kind: str, *, merge: str) -> dict[str, Any]:
    return {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "LayerPolicy",
            "metadata": {"name": f"{scope}-lp"},
            "spec": {"composition_rules": {kind: {
                "scope_inheritance": "enabled",
                "merge_strategy": merge,
                "tenant_overlay": "field_level",
            }}}}


def _kernel(src: _MockSource, *, catalog=()) -> Kernel:
    k = Kernel()
    k._source = src  # type: ignore[assignment]

    async def _cat(tenant, *, exclude=None):
        ex = exclude or set()
        return [(s, t) for (s, t) in catalog if s not in ex]
    k._catalog_scopes = _cat  # type: ignore[assignment]
    return k


# ── 1. override_full inheritance: local wins whole, else inherited whole ──

@pytest.mark.asyncio
async def test_override_full_local_wins_and_flags_not_inherited():
    src = _MockSource()
    src.docs[("child", "Genome", "child", "")] = _pkg("child")  # → _lib
    src.docs[("child", "Widget", "w", "")] = _doc("child", "Widget", "w", {"from": "local"})
    src.docs[("_lib", "Widget", "w", "")] = _doc("_lib", "Widget", "w", {"from": "base"})
    k = _kernel(src)

    res = await k.resolve_document("child", "Widget", "w")
    assert res.doc["spec"]["from"] == "local"
    assert res.is_inherited is False
    assert res.provenance.effective_layer.scope == "child"
    # override_full → no per-field provenance
    assert res.contributions_by_field == {}


@pytest.mark.asyncio
async def test_override_full_inherited_whole_when_no_local():
    src = _MockSource()
    src.docs[("child", "Genome", "child", "")] = _pkg("child")
    src.docs[("_lib", "Widget", "w", "")] = _doc("_lib", "Widget", "w", {"from": "base"})
    k = _kernel(src)

    res = await k.resolve_document("child", "Widget", "w")
    assert res.doc["spec"]["from"] == "base"
    assert res.is_inherited is True
    assert res.provenance.effective_layer.scope == "_lib"


# ── 2. field-level merge: THE gap — contributions_by_field surfaced ───────

@pytest.mark.asyncio
async def test_field_level_merge_surfaces_contributions_by_field():
    """With a LayerPolicy declaring merge_strategy=field_level, resolve_document
    deep-merges specs across the inheritance chain AND reports which layer
    contributed each field via ResolvedDocument.contributions_by_field. No
    existing test asserts this at the kernel surface."""
    src = _MockSource()
    src.docs[("child", "Genome", "child", "")] = _pkg("child")  # → _lib
    src.layer_policies["child"] = [_layer_policy("child", "Widget", merge="field_level")]
    # child overrides ONLY `color`; `size` falls through from _lib.
    src.docs[("child", "Widget", "w", "")] = _doc("child", "Widget", "w", {"color": "blue"})
    src.docs[("_lib", "Widget", "w", "")] = _doc(
        "_lib", "Widget", "w", {"color": "red", "size": "large"},
    )
    k = _kernel(src)

    res = await k.resolve_document("child", "Widget", "w")
    assert res.doc["spec"] == {"color": "blue", "size": "large"}
    # per-field provenance: local field ← child, inherited field ← _lib
    assert res.contributions_by_field == {
        "spec.color": "child",
        "spec.size": "_lib",
    }
    # highest-priority contributing layer owns the envelope
    assert res.provenance.effective_layer.scope == "child"


# ── 3. tenant overlay crosses with field-level in one resolve ─────────────

@pytest.mark.asyncio
async def test_tenant_overlay_field_level_merge_end_to_end():
    """The full crossing: tenant overlay (field_level) over base, with base
    filling the uncovered field. Pins the whole merge pipeline order."""
    src = _MockSource()
    src.docs[("child", "Genome", "child", "")] = _pkg("child")
    src.layer_policies["child"] = [_layer_policy("child", "Widget", merge="field_level")]
    # base (tenant=None) has both fields; acme overlay covers only `color`.
    src.docs[("child", "Widget", "w", "")] = _doc(
        "child", "Widget", "w", {"color": "base-red", "size": "M"},
    )
    src.docs[("child", "Widget", "w", "acme")] = _doc(
        "child", "Widget", "w", {"color": "acme-blue"},
    )
    k = _kernel(src)

    res = await k.resolve_document("child", "Widget", "w", tenant="acme")
    assert res.doc["spec"]["color"] == "acme-blue"   # overlay wins the field
    assert res.doc["spec"]["size"] == "M"            # base fills the rest
    assert res.contributions_by_field["spec.color"] == "child"
    assert res.provenance.effective_layer.tenant == "acme"


# ── 4. composition_summary golden (parent_chain + per-Kind counts) ────────

def _summary_kernel(scope_rows, *, catalog):
    from unittest.mock import MagicMock

    async def _fake_query(scope, kind, *, tenant=None, **kw):
        rows = scope_rows.get((scope, tenant))
        if rows is None:
            rows = scope_rows.get(scope, [])
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
        return list(catalog)
    k._catalog_scopes = _cat  # type: ignore[assignment]
    return k


@pytest.mark.asyncio
async def test_composition_summary_parent_chain_and_counts():
    def row(name):
        return {"kind": "Agent", "metadata": {"name": name}, "spec": {}}

    k = _summary_kernel(
        {"proj": [row("local-a")], "_lib": [row("inherited-b")]},
        catalog=[],
    )
    summary = await k.composition_summary("proj")

    assert summary["scope"] == "proj"
    assert summary["parent_chain"] == [k._INHERIT_PARENT_SCOPE]
    ua = summary["resources"]["Agent"]
    assert ua == {"local": 1, "inherited": 1, "installed": 0, "total": 2}
    # Kinds with zero across all origins are omitted entirely.
    assert "LottieAsset" not in summary["resources"]


@pytest.mark.asyncio
async def test_composition_summary_fail_soft_on_broken_kind():
    """A source that raises for one Kind drops it from the summary (fail-soft)
    instead of crashing the whole aggregate."""
    from unittest.mock import MagicMock

    async def _boom_query(scope, kind, *, tenant=None, **kw):
        raise RuntimeError("boom")
        yield  # pragma: no cover — makes this an async generator

    src = MagicMock()
    src.query = _boom_query
    k = Kernel()
    k._source = src  # type: ignore[assignment]

    async def _chain(scope, tenant):
        return [(scope, None)]
    k._composition.compute_resolution_chain = _chain  # type: ignore[assignment]

    async def _cat(tenant, *, exclude=None):
        return []
    k._catalog_scopes = _cat  # type: ignore[assignment]

    summary = await k.composition_summary("proj")
    assert summary["scope"] == "proj"
    assert summary["resources"] == {}  # every Kind failed soft → dropped
