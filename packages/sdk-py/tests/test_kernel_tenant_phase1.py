"""Phase 1 — Tenant first-class on Kernel.

Validates the new tenant API surface added in `feat/tenant-first-class`:
- `Kernel(tenant=X)` constructor binding (Sanity pattern)
- `Kernel.with_tenant(Y)` per-call override (Stripe Connect pattern)
- KindPort.scope = TENANTED → TenantRequired without tenant
- KindPort.scope = GLOBAL  → TenantNotAllowed with tenant
- Back-compat: layer=("tenant", X) routes to tenant=X with DeprecationWarning
- RESERVED tenant slugs rejected
"""
from __future__ import annotations

import asyncio
import tempfile
import warnings
from pathlib import Path

import pytest

from dna.kernel import Kernel
from dna.kernel.protocols import (
    TenantScope, TenantRequired, TenantNotAllowed, InvalidTenantSlug,
    validate_tenant_slug, RESERVED_TENANT_SLUGS,
)
from dna.extensions.helix import HelixExtension
from dna.adapters.filesystem.writable import FilesystemWritableSource


def _make_kernel(tmp: Path, *, tenant: str | None = None) -> Kernel:
    (tmp / "scope").mkdir(exist_ok=True)
    (tmp / "scope" / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
        "metadata: {name: scope}\nspec: {}\n"
    )
    k = Kernel(tenant=tenant)
    k.load(HelixExtension())
    src = FilesystemWritableSource(str(tmp), writers=list(k._writers), kernel=k)
    k.source(src)
    return k


def test_kernel_constructor_binds_tenant():
    k = Kernel(tenant="acme")
    assert k.tenant == "acme"


def test_kernel_default_tenant_is_none():
    k = Kernel()
    assert k.tenant is None


def test_with_tenant_returns_copy_unchanged_original():
    k = Kernel(tenant="acme")
    other = k.with_tenant("globex")
    assert k.tenant == "acme"
    assert other.tenant == "globex"
    assert k is not other


def test_with_tenant_none_unbinds():
    k = Kernel(tenant="acme")
    other = k.with_tenant(None)
    assert other.tenant is None


def test_reserved_slug_rejected_in_constructor():
    with pytest.raises(InvalidTenantSlug):
        Kernel(tenant="_global")


def test_reserved_slug_rejected_in_with_tenant():
    k = Kernel()
    with pytest.raises(InvalidTenantSlug):
        k.with_tenant("_legacy")


def test_validate_tenant_slug_accepts_uppercase():
    # Phase 1 keeps slug rules permissive for back-compat
    assert validate_tenant_slug("Acme") is None
    assert validate_tenant_slug("T1") is None


def test_validate_tenant_slug_rejects_too_long():
    with pytest.raises(InvalidTenantSlug):
        validate_tenant_slug("a" * 254)


def test_back_compat_layer_tenant_emits_deprecation_warning(tmp_path: Path):
    """layer=('tenant', X) still works but emits DeprecationWarning."""
    k = _make_kernel(tmp_path)
    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "old-style"},
        "spec": {"description": "x", "instruction": "y"},
    }
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        asyncio.run(k.write_document(
            "scope", "Agent", "old-style", raw,
            layer=("tenant", "beta"),
        ))
        deps = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deps) == 1, f"expected 1 DeprecationWarning, got {len(deps)}"
        assert "layer=('tenant', X)" in str(deps[0].message)


def test_back_compat_writes_to_same_layer_path(tmp_path: Path):
    """Old layer=('tenant', X) and new tenant=X produce same file path."""
    k = _make_kernel(tmp_path)
    spec_a = {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
        "metadata": {"name": "a"}, "spec": {"instruction": "x"},
    }
    spec_b = dict(spec_a)
    spec_b["metadata"] = {"name": "b"}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        asyncio.run(k.write_document(
            "scope", "Agent", "a", spec_a, layer=("tenant", "shared"),
        ))
    asyncio.run(k.write_document(
        "scope", "Agent", "b", spec_b, tenant="shared",
    ))

    a_files = list(tmp_path.rglob("*a*"))
    b_files = list(tmp_path.rglob("*b*"))
    a_paths = [str(p.relative_to(tmp_path).parent) for p in a_files if p.name == "a"]
    b_paths = [str(p.relative_to(tmp_path).parent) for p in b_files if p.name == "b"]
    assert a_paths and b_paths
    assert a_paths[0] == b_paths[0], (
        f"layer=('tenant', X) and tenant=X must write to same path, got "
        f"{a_paths[0]!r} vs {b_paths[0]!r}"
    )


def test_explicit_tenanted_kind_requires_tenant(tmp_path: Path):
    """When KindPort declares scope=TENANTED, write without tenant raises."""
    k = _make_kernel(tmp_path)
    # Patch the Agent KindPort to declare TENANTED scope
    kp = k._kind_port_for("Agent")
    kp.scope = TenantScope.TENANTED  # explicit declaration

    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
        "metadata": {"name": "x"}, "spec": {"instruction": "y"},
    }
    with pytest.raises(TenantRequired):
        asyncio.run(k.write_document("scope", "Agent", "x", raw))

    # With tenant bound, write succeeds
    k_bound = k.with_tenant("acme")
    asyncio.run(k_bound.write_document("scope", "Agent", "x", raw))


def test_explicit_global_kind_rejects_tenant(tmp_path: Path):
    """When KindPort declares scope=GLOBAL, write with tenant raises."""
    k = _make_kernel(tmp_path)
    kp = k._kind_port_for("Agent")
    kp.scope = TenantScope.GLOBAL  # explicit declaration

    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
        "metadata": {"name": "x"}, "spec": {"instruction": "y"},
    }
    k_bound = k.with_tenant("acme")
    with pytest.raises(TenantNotAllowed):
        asyncio.run(k_bound.write_document("scope", "Agent", "x", raw))


def test_undeclared_kind_is_permissive(tmp_path: Path):
    """Phase 1: KindPorts without explicit scope behave as before — no enforcement."""
    k = _make_kernel(tmp_path)
    # Don't set kp.scope — should fall through to permissive
    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent",
        "metadata": {"name": "permissive"}, "spec": {"instruction": "x"},
    }
    # Both should succeed
    asyncio.run(k.write_document("scope", "Agent", "permissive", raw))
    asyncio.run(k.with_tenant("acme").write_document(
        "scope", "Agent", "with-tenant", raw,
    ))
