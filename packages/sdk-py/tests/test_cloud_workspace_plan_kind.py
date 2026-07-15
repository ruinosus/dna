"""s-ws-plan-rename — WorkspacePlan Kind (workspace→Tier assignment) +
kernel.workspace_plan().

Covers the billing→enforcement bridge (ADR "Model B" — billing keys on the
WORKSPACE, not an identity/Azure org), shipped as the `cloud` extension:

1. The ``cloud`` extension registers WorkspacePlan from its descriptor
   (``kinds/workspace-plan.kind.yaml`` — record plane, GLOBAL, generated-convention
   alias ``cloud-workspace-plan``).
2. ``kernel.workspace_plan`` resolves a WorkspacePlan from ``_lib`` by
   ``spec.workspace_id``, returning the RAW DICT row whose ``spec`` carries the
   ``tier_id`` — proving the assignment comes from the DOC (which dna-cloud
   writes), never a literal.
3. An unknown workspace → None (the guard falls back to the Free floor).
4. Zero-migration back-compat: the founding workspace's id == the founder's old
   Azure ``tid``, so an assignment keyed on that same string resolves unchanged
   (mirrors the F1/F2 seed — no data move, no rewrite).

TS twin: tests/cloud-extension.test.ts.
"""
from __future__ import annotations

import pytest

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.extensions.cloud import CloudExtension
from dna.kernel import Kernel
from dna.kernel.protocols import TenantScope


def _workspace_plan(workspace_id: str, *, tier_id: str, source: str = "stripe",
                    status: str = "active") -> dict:
    """Build a WorkspacePlan doc. The assignment lives HERE (the doc), which
    dna-cloud's Stripe webhook writes — never in code."""
    return {
        "apiVersion": "github.com/ruinosus/dna/cloud/v1",
        "kind": "WorkspacePlan",
        "metadata": {"name": workspace_id},
        "spec": {
            "workspace_id": workspace_id,
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
    # WorkspacePlans live in the _lib scope (workspace-plans/<workspace_id>.yaml)
    # — kernel.workspace_plan queries _lib directly regardless of caller scope.
    await k.write_document(
        "_lib", "WorkspacePlan", "acme",
        _workspace_plan("acme", tier_id="pro"),
    )
    return k


# ---------------------------------------------------------------------------
# 1. Kind registration (descriptor)
# ---------------------------------------------------------------------------

def test_workspace_plan_kind_registered_from_descriptor():
    k = Kernel()
    k.load(CloudExtension())
    kp = k.kind_port_for("WorkspacePlan")
    assert kp is not None
    assert kp.alias == "cloud-workspace-plan"
    assert kp.plane == "record"
    # GLOBAL — a shared base registry, no per-tenant override.
    assert kp.scope == TenantScope.GLOBAL
    assert kp.storage.container == "workspace-plans"
    assert getattr(kp, "__declarative__", False) is True


def test_cloud_registers_both_tier_and_workspace_plan():
    """The cloud extension registers BOTH Tier and WorkspacePlan from its
    descriptors — and still never registers ``Plan`` (the SDLC Kind). The old
    ``TenantPlan`` name is gone (renamed to WorkspacePlan, ADR "Model B")."""
    k = Kernel()
    k.load(CloudExtension())
    assert k.kind_port_for("Tier") is not None
    assert k.kind_port_for("WorkspacePlan") is not None
    assert k.kind_port_for("TenantPlan") is None
    assert k.kind_port_for("Plan") is None


# ---------------------------------------------------------------------------
# 2. Resolution — the assignment comes from the DOC
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workspace_plan_resolves_from_doc(tmp_path):
    k = await _kernel(tmp_path)

    plan = await k.workspace_plan("acme")
    assert plan is not None
    spec = plan.get("spec") or {}
    assert spec["tier_id"] == "pro"
    assert spec["workspace_id"] == "acme"
    assert spec["source"] == "stripe"


@pytest.mark.asyncio
async def test_workspace_plan_unknown_workspace_returns_none(tmp_path):
    k = await _kernel(tmp_path)
    assert await k.workspace_plan("globex") is None


# ---------------------------------------------------------------------------
# 3. No-redeploy — rewrite the assignment, re-read, new tier (data, not code)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workspace_plan_assignment_is_data_not_code(tmp_path):
    k = await _kernel(tmp_path)
    assert (await k.workspace_plan("acme"))["spec"]["tier_id"] == "pro"
    # dna-cloud's Stripe webhook downgrades acme to free on cancel — a data
    # edit, no redeploy.
    await k.write_document(
        "_lib", "WorkspacePlan", "acme",
        _workspace_plan("acme", tier_id="free", status="canceled"),
    )
    assert (await k.workspace_plan("acme"))["spec"]["tier_id"] == "free"


# ---------------------------------------------------------------------------
# 4. Zero-migration back-compat — workspace #1 id == founder's old Azure tid
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_founder_workspace_plan_zero_migration(tmp_path):
    """The founding workspace's id equals the founder's pre-Model-B Azure ``tid``
    (``c5b891f7``). A WorkspacePlan keyed on that SAME string resolves unchanged —
    exactly the value the quota guard now passes (F2 resolves the tenancy
    dimension to this workspace_id). No data move, no rewrite (mirrors F1/F2)."""
    k = Kernel()
    k.load(CloudExtension())
    src = FilesystemWritableSource(str(tmp_path / ".dna"))
    k.source(src)
    src.attach_kernel(k)
    founder_ws = "c5b891f7"  # workspace #1 id == the founder's old tid.
    await k.write_document(
        "_lib", "WorkspacePlan", founder_ws,
        _workspace_plan(founder_ws, tier_id="enterprise"),
    )
    plan = await k.workspace_plan(founder_ws)
    assert plan is not None
    assert plan["spec"]["tier_id"] == "enterprise"
    assert plan["spec"]["workspace_id"] == founder_ws
