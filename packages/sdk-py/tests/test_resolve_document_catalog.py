"""Phase 3b ch4 (i-112) — ``resolve_document`` injects the Catalog tier.

The single-doc resolver (the one ``build_prompt`` rides on) splices the
tenant's Catalog scopes into the resolution chain IMMEDIATELY AFTER the local
scope's entries and BEFORE the first parent → precedence ``Local > Catalog >
Base``. The positional ``merge_field_level`` (first contributor = primary) is
preserved.

Back-compat is SACRED: with no Catalog packages installed the chain — and thus
the merged doc + provenance — is byte-identical to today.
"""
from __future__ import annotations

import logging
from typing import Any

import pytest

from dna.kernel import Kernel


# ──────────────────────────────────────────────────────────────────────
# Mock source — full control over what each (scope, kind, name, tenant) returns.
# Mirrors test_composition_v2_resolver.py::MockSource so the chain walk
# (compute_resolution_chain → Genome reads) behaves exactly as in prod.
# ──────────────────────────────────────────────────────────────────────


class MockSource:
    def __init__(self):
        self.docs: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        self.layer_policies: dict[str, list[dict[str, Any]]] = {}

    async def load_one(
        self, scope: str, kind: str, name: str, *,
        readers=None, tenant: str | None = None,
    ) -> dict[str, Any] | None:
        return self.docs.get((scope, kind, name, tenant or ""))

    async def query(
        self, scope: str, kind: str, *,
        filter=None, projection=None, limit=None, offset=None,
        order_by=None, tenant: str | None = None,
    ):
        if kind == "LayerPolicy":
            for d in self.layer_policies.get(scope, []):
                yield d
        return

    async def load_bootstrap_docs(self, scope: str, **kw):
        return []

    async def load_all(self, scope: str, readers=None, **kw):
        return []


def make_kernel(mock: MockSource, *, catalog_scopes) -> Kernel:
    """Kernel over the mock source, with ``_catalog_scopes`` stubbed.

    ``catalog_scopes`` is the FULL (un-excluded) list; the stub honors the
    ``exclude`` kwarg the resolver passes (the scope being resolved), exactly
    like the real helper.
    """
    k = Kernel()
    k._source = mock  # type: ignore[assignment]

    async def _cat(tenant, *, exclude=None):
        ex = exclude or set()
        return [(s, t) for (s, t) in catalog_scopes if s not in ex]

    k._catalog_scopes = _cat  # type: ignore[assignment]
    return k


def package_doc(scope: str, parent_scope: str | None = None) -> dict[str, Any]:
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": scope},
        "spec": {"owner_tenant": "acme", "parent_scope": parent_scope},
    }


def kind_doc(scope: str, kind: str, name: str, spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "apiVersion": "github.com/ruinosus/dna/test/v1",
        "kind": kind,
        "metadata": {"name": name},
        "spec": spec,
    }


# ──────────────────────────────────────────────────────────────────────
# 1. Local wins over Catalog (and base)
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_local_wins_over_catalog_and_base():
    src = MockSource()
    src.docs[("proj", "Genome", "proj", "")] = package_doc("proj")  # → _lib
    src.docs[("proj", "Soul", "x", "")] = kind_doc("proj", "Soul", "x", {"from": "local"})
    src.docs[("pkg-a", "Soul", "x", "")] = kind_doc("pkg-a", "Soul", "x", {"from": "catalog"})
    src.docs[("_lib", "Soul", "x", "")] = kind_doc("_lib", "Soul", "x", {"from": "base"})
    k = make_kernel(src, catalog_scopes=[("pkg-a", None)])

    res = await k.resolve_document("proj", "Soul", "x")
    assert res.doc is not None
    assert res.doc["spec"]["from"] == "local"
    assert res.is_inherited is False
    assert res.provenance.effective_layer.scope == "proj"


# ──────────────────────────────────────────────────────────────────────
# 2. Catalog wins over Base when absent locally
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_catalog_wins_over_base_when_no_local():
    src = MockSource()
    src.docs[("proj", "Genome", "proj", "")] = package_doc("proj")
    src.docs[("pkg-a", "Soul", "x", "")] = kind_doc("pkg-a", "Soul", "x", {"from": "catalog"})
    src.docs[("_lib", "Soul", "x", "")] = kind_doc("_lib", "Soul", "x", {"from": "base"})
    k = make_kernel(src, catalog_scopes=[("pkg-a", None)])

    res = await k.resolve_document("proj", "Soul", "x")
    assert res.doc is not None
    assert res.doc["spec"]["from"] == "catalog"
    assert res.is_inherited is True  # primary scope (pkg-a) != requesting scope
    assert res.provenance.effective_layer.scope == "pkg-a"


@pytest.mark.asyncio
async def test_catalog_inserted_between_local_and_parent_in_provenance():
    """Provenance step order proves the splice position: proj, then pkg-a,
    then _lib."""
    src = MockSource()
    src.docs[("proj", "Genome", "proj", "")] = package_doc("proj")
    src.docs[("pkg-a", "Soul", "x", "")] = kind_doc("pkg-a", "Soul", "x", {"from": "catalog"})
    k = make_kernel(src, catalog_scopes=[("pkg-a", None)])

    res = await k.resolve_document("proj", "Soul", "x")
    scopes = [s.scope for s in res.provenance.steps]
    assert scopes.index("proj") < scopes.index("pkg-a") < scopes.index("_lib")


# ──────────────────────────────────────────────────────────────────────
# 3. Conflict among multiple catalog scopes — first (sorted) wins + log
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_two_catalog_scopes_first_wins_and_logs(caplog):
    src = MockSource()
    src.docs[("proj", "Genome", "proj", "")] = package_doc("proj")
    src.docs[("pkg-a", "Soul", "x", "")] = kind_doc("pkg-a", "Soul", "x", {"from": "pkg-a"})
    src.docs[("pkg-b", "Soul", "x", "")] = kind_doc("pkg-b", "Soul", "x", {"from": "pkg-b"})
    # _catalog_scopes is already deterministically sorted: pkg-a before pkg-b.
    k = make_kernel(src, catalog_scopes=[("pkg-a", None), ("pkg-b", None)])

    with caplog.at_level(logging.INFO):
        res = await k.resolve_document("proj", "Soul", "x")
    assert res.doc["spec"]["from"] == "pkg-a"  # first sorted catalog scope wins
    assert res.provenance.effective_layer.scope == "pkg-a"
    # ≥2 catalog layers contributed the same (kind,name) → an INFO surface.
    assert any(
        "catalog" in rec.message.lower() and "x" in rec.message
        for rec in caplog.records
    ), f"expected a catalog-conflict INFO log; got {[r.message for r in caplog.records]}"


# ──────────────────────────────────────────────────────────────────────
# 4. Back-compat — no catalog installed → chain identical to today
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_catalog_identical_to_today():
    """With an empty catalog the merged doc + provenance match the pre-ch4
    path exactly (only local + parent layers, nothing spliced)."""
    src = MockSource()
    src.docs[("child", "Genome", "child", "")] = package_doc("child", parent_scope="_lib")
    src.docs[("_lib", "Soul", "shared", "")] = kind_doc(
        "_lib", "Soul", "shared", {"from": "platform"},
    )
    k = make_kernel(src, catalog_scopes=[])

    res = await k.resolve_document("child", "Soul", "shared")
    assert res.doc is not None
    assert res.doc["spec"]["from"] == "platform"
    assert res.is_inherited is True
    # No catalog scope ⇒ the only scopes in the chain are child + _lib.
    scopes = {s.scope for s in res.provenance.steps}
    assert scopes == {"child", "_lib"}


# ──────────────────────────────────────────────────────────────────────
# 5. Bootstrap / disabled Kind — catalog NOT injected
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bootstrap_kind_no_catalog_injection():
    """Genome is a BOOTSTRAP Kind → local-only, catalog never consulted."""
    src = MockSource()
    src.docs[("proj", "Genome", "proj", "")] = package_doc("proj")
    # A Genome doc in a catalog scope must NOT bleed in.
    src.docs[("pkg-a", "Genome", "proj", "")] = package_doc("pkg-a")
    k = make_kernel(src, catalog_scopes=[("pkg-a", None)])

    res = await k.resolve_document("proj", "Genome", "proj")
    assert res.doc is not None
    assert len(res.provenance.steps) == 1  # local-only, no catalog/parent
    assert res.provenance.steps[0].scope == "proj"


@pytest.mark.asyncio
async def test_disabled_kind_no_catalog_injection():
    """A LayerPolicy disabling inheritance for a Kind → catalog NOT spliced
    (stays local-only, as today)."""
    src = MockSource()
    src.docs[("proj", "Genome", "proj", "")] = package_doc("proj", parent_scope="_lib")
    src.layer_policies["proj"] = [{
        "apiVersion": "github.com/ruinosus/dna/policy/v1",
        "kind": "LayerPolicy",
        "metadata": {"name": "composition"},
        "spec": {"composition_rules": {"Story": {"scope_inheritance": "disabled"}}},
    }]
    src.docs[("pkg-a", "Story", "S1", "")] = kind_doc("pkg-a", "Story", "S1", {"from": "catalog"})
    src.docs[("_lib", "Story", "S1", "")] = kind_doc("_lib", "Story", "S1", {"from": "base"})
    k = make_kernel(src, catalog_scopes=[("pkg-a", None)])

    res = await k.resolve_document("proj", "Story", "S1")
    # disabled ⇒ neither catalog nor parent consulted → not found locally.
    assert res.doc is None
    assert res.is_inherited is False
    scopes = {s.scope for s in res.provenance.steps}
    assert scopes == {"proj"}


# ──────────────────────────────────────────────────────────────────────
# 6. Catalog layers registered as observers (cross-scope invalidation)
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_catalog_layer_registers_observer():
    src = MockSource()
    src.docs[("proj", "Genome", "proj", "")] = package_doc("proj")
    src.docs[("pkg-a", "Soul", "x", "")] = kind_doc("pkg-a", "Soul", "x", {"from": "catalog"})
    k = make_kernel(src, catalog_scopes=[("pkg-a", None)])

    await k.resolve_document("proj", "Soul", "x", tenant="acme")
    observers = getattr(k, "_layer_observers", {})
    cat_key = ("pkg-a", "Soul", "x", None)
    assert cat_key in observers
    assert ("proj", "acme") in observers[cat_key]


# ──────────────────────────────────────────────────────────────────────
# 7. Tenant isolation — _catalog_scopes is the gate
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tenant_isolation_empty_catalog():
    """A tenant with no catalog installs sees only local + base — the catalog
    scope of another tenant does not leak in."""
    src = MockSource()
    src.docs[("proj", "Genome", "proj", "")] = package_doc("proj")
    src.docs[("pkg-a", "Soul", "x", "")] = kind_doc("pkg-a", "Soul", "x", {"from": "catalog"})
    src.docs[("_lib", "Soul", "x", "")] = kind_doc("_lib", "Soul", "x", {"from": "base"})
    # innovec: empty catalog
    k = make_kernel(src, catalog_scopes=[])

    res = await k.resolve_document("proj", "Soul", "x", tenant="innovec")
    assert res.doc["spec"]["from"] == "base"  # catalog never consulted
    assert res.provenance.effective_layer.scope == "_lib"
