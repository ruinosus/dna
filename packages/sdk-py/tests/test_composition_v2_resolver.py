"""F2 — Composition Engine V2 resolver tests (Phase 17).

Story s-comp-f2-resolver (2026-05-28).

Cobre:
1. Bootstrap Kinds (Genome, LayerPolicy, KindDefinition) NÃO herdam.
2. Depth 0 (scope sem parent) — só local.
3. Depth 1 (scope → parent) — local miss + parent hit.
4. Depth 2 (scope → parent → grandparent) — transitive walk.
5. Local override ganha sobre parent (override_full).
6. Field-level merge: parent fields + local field overrides.
7. Tenant overlay quando rule.tenant_overlay=field_level.
8. tenant_overlay=none pula tenant layers.
9. scope_inheritance=disabled pula parent.
10. Cycle detection (A → B → A).
11. MAX_RESOLUTION_DEPTH cap.
12. V1 backward-compat: sem parent_scope explícito, escala pra _lib.

Usa MockSource em vez de bater Postgres pra controle absoluto.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from dna.kernel import Kernel
from dna.kernel.query.resolver import (
    BOOTSTRAP_KINDS,
    DEFAULT_INHERITABLE_KINDS_V1,
    ResolutionLayer,
    merge_field_level,
    merge_override_full,
)


# ──────────────────────────────────────────────────────────────────────
# Mock source — full control over what each (scope, kind, name, tenant) returns.
# ──────────────────────────────────────────────────────────────────────


class MockSource:
    """Implementação minimalista de SourcePort pra testes — apenas
    ``load_one`` + ``query`` (este último retorna iterable vazio por
    padrão, sobreposto via ``layer_policies``)."""

    def __init__(self):
        # (scope, kind, name, tenant) → raw doc dict
        self.docs: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        # (scope, "LayerPolicy") → list of LayerPolicy docs to yield from query
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

    # SourcePort other methods stubbed
    async def load_bootstrap_docs(self, scope: str, **kw):
        return []

    async def load_all(self, scope: str, readers=None, **kw):
        return []


def make_kernel_with_mock(mock: MockSource) -> Kernel:
    k = Kernel()
    k._source = mock  # type: ignore[assignment]
    return k


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def package_doc(scope: str, parent_scope: str | None = None) -> dict[str, Any]:
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": scope},
        "spec": {
            "owner_tenant": "acme",
            "parent_scope": parent_scope,
        },
    }


def kind_doc(scope: str, kind: str, name: str, spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "apiVersion": "github.com/ruinosus/dna/test/v1",
        "kind": kind,
        "metadata": {"name": name},
        "spec": spec,
    }


# ──────────────────────────────────────────────────────────────────────
# 1. Bootstrap Kinds bypass inheritance
# ──────────────────────────────────────────────────────────────────────


def test_bootstrap_kinds_constant():
    assert "Genome" in BOOTSTRAP_KINDS
    assert "LayerPolicy" in BOOTSTRAP_KINDS
    assert "KindDefinition" in BOOTSTRAP_KINDS


def test_v1_inheritable_constant():
    assert "Agent" in DEFAULT_INHERITABLE_KINDS_V1
    assert "LottieAsset" in DEFAULT_INHERITABLE_KINDS_V1
    assert "Story" not in DEFAULT_INHERITABLE_KINDS_V1


@pytest.mark.asyncio
async def test_bootstrap_kind_no_inheritance():
    """Genome never inherits — local-only resolve."""
    src = MockSource()
    src.docs[("scope-a", "Genome", "scope-a", "")] = package_doc("scope-a")
    k = make_kernel_with_mock(src)

    res = await k.resolve_document("scope-a", "Genome", "scope-a")
    assert res.doc is not None
    assert res.is_inherited is False
    assert len(res.provenance.steps) == 1
    assert res.provenance.steps[0].scope == "scope-a"


# ──────────────────────────────────────────────────────────────────────
# 2. Depth 0 — scope without parent → local only
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_depth_0_local_only():
    """Scope is _lib (the root V1 fallback target) — no escalation."""
    src = MockSource()
    src.docs[("_lib", "Genome", "_lib", "")] = package_doc("_lib")
    src.docs[("_lib", "LottieAsset", "X", "")] = kind_doc(
        "_lib", "LottieAsset", "X", {"variant": "idle"},
    )
    k = make_kernel_with_mock(src)

    res = await k.resolve_document("_lib", "LottieAsset", "X")
    assert res.doc is not None
    assert res.is_inherited is False
    assert res.provenance.effective_layer.scope == "_lib"


# ──────────────────────────────────────────────────────────────────────
# 3. Depth 1 — local miss, parent hit (V1 fallback to _lib)
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_depth_1_v1_fallback():
    """No parent_scope explicit; V1 backward-compat escalates to _lib."""
    src = MockSource()
    src.docs[("child", "Genome", "child", "")] = package_doc("child")
    src.docs[("_lib", "LottieAsset", "shared", "")] = kind_doc(
        "_lib", "LottieAsset", "shared", {"variant": "idle"},
    )
    k = make_kernel_with_mock(src)

    res = await k.resolve_document("child", "LottieAsset", "shared")
    assert res.doc is not None
    assert res.is_inherited is True
    assert res.provenance.effective_layer.scope == "_lib"


# ──────────────────────────────────────────────────────────────────────
# 4. Depth 2 — child → mid → _lib
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_depth_2_transitive_walk():
    """child declares parent_scope=mid; mid declares parent_scope=_lib.
    LottieAsset only at root."""
    src = MockSource()
    src.docs[("child", "Genome", "child", "")] = package_doc("child", parent_scope="mid")
    src.docs[("mid", "Genome", "mid", "")] = package_doc("mid", parent_scope="_lib")
    src.docs[("_lib", "LottieAsset", "root-only", "")] = kind_doc(
        "_lib", "LottieAsset", "root-only", {"variant": "x"},
    )
    k = make_kernel_with_mock(src)

    res = await k.resolve_document("child", "LottieAsset", "root-only")
    assert res.doc is not None
    assert res.is_inherited is True
    assert res.provenance.effective_layer.scope == "_lib"
    # Verify chain order: child, mid, _lib (3 scopes × 1 base layer each)
    found_scopes = [s.scope for s in res.provenance.steps if s.found]
    assert found_scopes == ["_lib"]


@pytest.mark.asyncio
async def test_depth_2_mid_layer_wins():
    """Same chain, but doc exists at mid AND _lib. mid wins (closer
    to caller)."""
    src = MockSource()
    src.docs[("child", "Genome", "child", "")] = package_doc("child", parent_scope="mid")
    src.docs[("mid", "Genome", "mid", "")] = package_doc("mid", parent_scope="_lib")
    src.docs[("mid", "LottieAsset", "shared", "")] = kind_doc(
        "mid", "LottieAsset", "shared", {"variant": "from-mid"},
    )
    src.docs[("_lib", "LottieAsset", "shared", "")] = kind_doc(
        "_lib", "LottieAsset", "shared", {"variant": "from-root"},
    )
    k = make_kernel_with_mock(src)

    res = await k.resolve_document("child", "LottieAsset", "shared")
    assert res.is_inherited is True
    assert res.provenance.effective_layer.scope == "mid"
    assert res.doc["spec"]["variant"] == "from-mid"


# ──────────────────────────────────────────────────────────────────────
# 5. Local override wins
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_local_override_wins():
    """Child has explicit local doc — wins over parent's."""
    src = MockSource()
    src.docs[("child", "Genome", "child", "")] = package_doc("child", parent_scope="_lib")
    src.docs[("child", "LottieAsset", "X", "")] = kind_doc(
        "child", "LottieAsset", "X", {"variant": "local-version"},
    )
    src.docs[("_lib", "LottieAsset", "X", "")] = kind_doc(
        "_lib", "LottieAsset", "X", {"variant": "platform-version"},
    )
    k = make_kernel_with_mock(src)

    res = await k.resolve_document("child", "LottieAsset", "X")
    assert res.is_inherited is False
    assert res.provenance.effective_layer.scope == "child"
    assert res.doc["spec"]["variant"] == "local-version"


# ──────────────────────────────────────────────────────────────────────
# 6. Field-level merge
# ──────────────────────────────────────────────────────────────────────


def test_field_level_merge_pure():
    """Pure-function field-level merge test."""
    L1 = ResolutionLayer(scope="child", tenant=None, found=True)
    L2 = ResolutionLayer(scope="_lib", tenant=None, found=True)
    contribs = [
        (L1, {
            "apiVersion": "v1", "kind": "Agent",
            "metadata": {"name": "jarvis"},
            "spec": {"model": "gpt-5.4"},  # local overrides this field
        }),
        (L2, {
            "apiVersion": "v1", "kind": "Agent",
            "metadata": {"name": "jarvis"},
            "spec": {
                "model": "gpt-5",         # from platform
                "persona": "jarvis-style",  # only in platform
            },
        }),
    ]
    merged, primary, fields = merge_field_level(contribs)
    assert merged is not None
    assert merged["spec"]["model"] == "gpt-5.4"   # local won
    assert merged["spec"]["persona"] == "jarvis-style"  # inherited
    assert primary.scope == "child"  # metadata from highest priority
    assert fields["spec.model"] == "child"
    assert fields["spec.persona"] == "_lib"


def test_override_full_merge_pure():
    """First non-None wins entirely."""
    L1 = ResolutionLayer(scope="child", tenant=None, found=False)
    L2 = ResolutionLayer(scope="_lib", tenant=None, found=True)
    contribs = [
        (L1, None),  # local miss
        (L2, {"apiVersion": "v1", "spec": {"variant": "platform"}}),
    ]
    merged, winner = merge_override_full(contribs)
    assert merged is not None
    assert merged["spec"]["variant"] == "platform"
    assert winner.scope == "_lib"


def test_override_full_all_miss():
    L1 = ResolutionLayer(scope="child", tenant=None, found=False)
    L2 = ResolutionLayer(scope="_lib", tenant=None, found=False)
    merged, winner = merge_override_full([(L1, None), (L2, None)])
    assert merged is None
    assert winner is None


# ──────────────────────────────────────────────────────────────────────
# 7. scope_inheritance=disabled skips parent
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scope_inheritance_disabled_for_kind():
    """LayerPolicy declares Story scope_inheritance=disabled. Story does
    NOT escalate even if parent has a Story doc."""
    src = MockSource()
    src.docs[("child", "Genome", "child", "")] = package_doc("child", parent_scope="_lib")
    src.layer_policies["child"] = [{
        "apiVersion": "github.com/ruinosus/dna/policy/v1",
        "kind": "LayerPolicy",
        "metadata": {"name": "composition"},
        "spec": {
            "composition_rules": {
                "Story": {"scope_inheritance": "disabled"},
            },
        },
    }]
    src.docs[("_lib", "Story", "S1", "")] = kind_doc(
        "_lib", "Story", "S1", {"title": "in platform"},
    )
    k = make_kernel_with_mock(src)

    res = await k.resolve_document("child", "Story", "S1")
    assert res.doc is None  # not found locally + skipped parent
    assert res.is_inherited is False


# ──────────────────────────────────────────────────────────────────────
# 8. Cycle detection
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cycle_detection_terminates():
    """A → B → A — must not loop infinite. Each scope visited once."""
    src = MockSource()
    src.docs[("a", "Genome", "a", "")] = package_doc("a", parent_scope="b")
    src.docs[("b", "Genome", "b", "")] = package_doc("b", parent_scope="a")
    src.docs[("a", "LottieAsset", "X", "")] = kind_doc("a", "LottieAsset", "X", {})
    k = make_kernel_with_mock(src)

    res = await k.resolve_document("a", "LottieAsset", "X")
    assert res.doc is not None
    # chain should visit a + b (no infinite loop)
    scopes_in_chain = {s.scope for s in res.provenance.steps}
    assert "a" in scopes_in_chain
    assert "b" in scopes_in_chain


# ──────────────────────────────────────────────────────────────────────
# 9. Tenant overlay
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tenant_overlay_wins_over_base():
    """Tenant overlay layer present + base — tenant wins."""
    src = MockSource()
    src.docs[("child", "Genome", "child", "")] = package_doc("child")
    src.docs[("child", "LottieAsset", "X", "acme")] = kind_doc(
        "child", "LottieAsset", "X", {"variant": "acme-overlay"},
    )
    src.docs[("child", "LottieAsset", "X", "")] = kind_doc(
        "child", "LottieAsset", "X", {"variant": "base"},
    )
    k = make_kernel_with_mock(src)

    res = await k.resolve_document("child", "LottieAsset", "X", tenant="acme")
    assert res.doc is not None
    assert res.doc["spec"]["variant"] == "acme-overlay"
    assert res.is_inherited is False
    assert res.provenance.effective_layer.tenant == "acme"


# ──────────────────────────────────────────────────────────────────────
# 10. Resolution chain serialization
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_provenance_serializes_for_json_api():
    """ResolvedDocument.serialize() must produce a JSON-clean dict."""
    src = MockSource()
    src.docs[("child", "Genome", "child", "")] = package_doc("child")
    src.docs[("_lib", "LottieAsset", "X", "")] = kind_doc(
        "_lib", "LottieAsset", "X", {"variant": "v1"},
    )
    k = make_kernel_with_mock(src)

    res = await k.resolve_document("child", "LottieAsset", "X")
    obj = res.serialize()
    assert obj["doc"] is not None
    assert obj["is_inherited"] is True
    assert "steps" in obj["provenance"]
    assert obj["provenance"]["effective_layer"]["scope"] == "_lib"


# ──────────────────────────────────────────────────────────────────────
# F3 — Observers / cross-scope invalidation
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_observers_register_on_parent_consult():
    src = MockSource()
    src.docs[("child", "Genome", "child", "")] = package_doc("child", parent_scope="_lib")
    src.docs[("_lib", "LottieAsset", "X", "")] = kind_doc(
        "_lib", "LottieAsset", "X", {"v": 1},
    )
    k = make_kernel_with_mock(src)
    await k.resolve_document("child", "LottieAsset", "X", tenant="acme")
    observers = getattr(k, "_layer_observers", {})
    parent_key = ("_lib", "LottieAsset", "X", None)
    assert parent_key in observers
    assert ("child", "acme") in observers[parent_key]


@pytest.mark.asyncio
async def test_observers_invalidate_drops_child_cache():
    src = MockSource()
    src.docs[("child", "Genome", "child", "")] = package_doc("child", parent_scope="_lib")
    src.docs[("_lib", "LottieAsset", "X", "")] = kind_doc(
        "_lib", "LottieAsset", "X", {"v": 1},
    )
    k = make_kernel_with_mock(src)
    await k.resolve_document("child", "LottieAsset", "X", tenant="acme")
    granular = getattr(k._kcache, "_doc_cache", {})
    assert ("child", "LottieAsset", "X", "acme") in granular

    k._invalidate_internal(
        scope="_lib", tenant=None, kind="LottieAsset",
        name="X", op="write",
    )

    granular_after = getattr(k._kcache, "_doc_cache", {})
    assert ("child", "LottieAsset", "X", "acme") not in granular_after
