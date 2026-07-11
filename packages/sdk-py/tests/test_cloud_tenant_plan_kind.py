"""s-dna-cloud-plan-by-tenant — TenantPlan Kind (tenant→Tier assignment) +
kernel.tenant_plan().

Covers the billing→enforcement bridge shipped as the `cloud` extension:

1. The ``cloud`` extension registers TenantPlan from its descriptor
   (``kinds/tenant-plan.kind.yaml`` — record plane, GLOBAL, generated-convention
   alias ``cloud-tenant-plan``).
2. ``kernel.tenant_plan`` resolves a TenantPlan from ``_lib`` by ``spec.tenant``,
   returning the RAW DICT row whose ``spec`` carries the ``tier_id`` — proving the
   assignment comes from the DOC (which dna-cloud writes), never a literal.
3. An unknown tenant → None (the guard falls back to the Free floor).

TS twin: tests/cloud-extension.test.ts.
"""
from __future__ import annotations

import pytest

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.extensions.cloud import CloudExtension
from dna.kernel import Kernel
from dna.kernel.protocols import TenantScope


def _tenant_plan(tenant: str, *, tier_id: str, source: str = "stripe",
                 status: str = "active") -> dict:
    """Build a TenantPlan doc. The assignment lives HERE (the doc), which
    dna-cloud's Stripe webhook writes — never in code."""
    return {
        "apiVersion": "github.com/ruinosus/dna/cloud/v1",
        "kind": "TenantPlan",
        "metadata": {"name": tenant},
        "spec": {
            "tenant": tenant,
            "tier_id": tier_id,
            "source": source,
            "status": status,
        },
    }


async def _kernel(tmp_path) -> Kernel:
    k = Kernel()
    k.load(CloudExtension())
    src = FilesystemWritableSource(str(tmp_path / ".dna"))
    k.source(src)
    src.attach_kernel(k)
    # TenantPlans live in the _lib scope (tenant-plans/<tenant>.yaml) —
    # kernel.tenant_plan queries _lib directly regardless of caller scope.
    await k.write_document(
        "_lib", "TenantPlan", "acme",
        _tenant_plan("acme", tier_id="pro"),
    )
    return k


# ---------------------------------------------------------------------------
# 1. Kind registration (descriptor)
# ---------------------------------------------------------------------------

def test_tenant_plan_kind_registered_from_descriptor():
    k = Kernel()
    k.load(CloudExtension())
    kp = k.kind_port_for("TenantPlan")
    assert kp is not None
    assert kp.alias == "cloud-tenant-plan"
    assert kp.plane == "record"
    # GLOBAL — a shared base registry, no per-tenant override.
    assert kp.scope == TenantScope.GLOBAL
    assert kp.storage.container == "tenant-plans"
    assert getattr(kp, "__declarative__", False) is True


def test_cloud_registers_both_tier_and_tenant_plan():
    """The cloud extension registers BOTH Tier and TenantPlan from its
    descriptors — and still never registers ``Plan`` (the SDLC Kind)."""
    k = Kernel()
    k.load(CloudExtension())
    assert k.kind_port_for("Tier") is not None
    assert k.kind_port_for("TenantPlan") is not None
    assert k.kind_port_for("Plan") is None


# ---------------------------------------------------------------------------
# 2. Resolution — the assignment comes from the DOC
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tenant_plan_resolves_from_doc(tmp_path):
    k = await _kernel(tmp_path)

    plan = await k.tenant_plan("acme")
    assert plan is not None
    spec = plan.get("spec") or {}
    assert spec["tier_id"] == "pro"
    assert spec["tenant"] == "acme"
    assert spec["source"] == "stripe"


@pytest.mark.asyncio
async def test_tenant_plan_unknown_tenant_returns_none(tmp_path):
    k = await _kernel(tmp_path)
    assert await k.tenant_plan("globex") is None


# ---------------------------------------------------------------------------
# 3. No-redeploy — rewrite the assignment, re-read, new tier (data, not code)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tenant_plan_assignment_is_data_not_code(tmp_path):
    k = await _kernel(tmp_path)
    assert (await k.tenant_plan("acme"))["spec"]["tier_id"] == "pro"
    # dna-cloud's Stripe webhook downgrades acme to free on cancel — a data
    # edit, no redeploy.
    await k.write_document(
        "_lib", "TenantPlan", "acme",
        _tenant_plan("acme", tier_id="free", status="canceled"),
    )
    assert (await k.tenant_plan("acme"))["spec"]["tier_id"] == "free"
