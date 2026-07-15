"""f-ws-kinds F1 — the Workspace + WorkspaceMembership Kinds (ADR "Model B").

Two GLOBAL record Kinds shipped as byte-identical Py↔TS descriptors inside the
``tenant`` extension (F3 — record Kinds are data, not classes):

  - Workspace (``tenant-workspace``) — the DNA tenancy root. Its opaque,
    immutable ``workspace_id`` IS the physical ``tenant`` column value on every
    row it owns.
  - WorkspaceMembership (``tenant-workspace-membership``) — the identity→workspace
    boundary (verified oid + email + tid → workspace + role + status).

These are the platform-level Kinds the ADR calls the missing ``TenantMembership``
— distinct from the class-based ``TenantMembership`` (Model-A user↔Tenant link)
and the portfolio ``Membership`` (intra-workspace RBAC), which stay untouched.

TS twin: tests/tenant-workspace-kinds.test.ts.
"""
from __future__ import annotations

import pytest

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.extensions.tenant import TenantExtension
from dna.kernel import Kernel
from dna.kernel.protocols import TenantScope


def _kernel() -> Kernel:
    k = Kernel()
    k.load(TenantExtension())
    return k


# ---------------------------------------------------------------------------
# 1. Registration (descriptor)
# ---------------------------------------------------------------------------

def test_workspace_kind_registered_from_descriptor():
    kp = _kernel().kind_port_for("Workspace")
    assert kp is not None
    assert kp.alias == "tenant-workspace"
    assert kp.plane == "record"
    # GLOBAL — the tenancy boundary lives above any single workspace.
    assert kp.scope == TenantScope.GLOBAL
    assert kp.storage.container == "workspaces"
    # It's a builtin descriptor (data), not a hand-typed class port.
    assert getattr(kp, "__declarative__", False) is True
    assert getattr(kp, "__builtin_descriptor__", False) is True


def test_workspace_membership_kind_registered_from_descriptor():
    kp = _kernel().kind_port_for("WorkspaceMembership")
    assert kp is not None
    assert kp.alias == "tenant-workspace-membership"
    assert kp.plane == "record"
    assert kp.scope == TenantScope.GLOBAL
    assert kp.storage.container == "workspace-memberships"
    assert getattr(kp, "__declarative__", False) is True


def test_tenant_ext_still_registers_the_legacy_class_kinds():
    """F1 ADDS the two workspace Kinds — it must NOT drop the pre-existing
    class-based Tenant / TenantMembership Kinds (Model-A, still live)."""
    k = _kernel()
    assert k.kind_port_for("Tenant") is not None
    assert k.kind_port_for("TenantMembership") is not None
    # And the two new ones coexist alongside them.
    assert k.kind_port_for("Workspace") is not None
    assert k.kind_port_for("WorkspaceMembership") is not None
    # The two membership Kinds are distinct aliases (no collision).
    assert k.kind_port_for("TenantMembership").alias == "tenant-membership"
    assert k.kind_port_for("WorkspaceMembership").alias == "tenant-workspace-membership"


# ---------------------------------------------------------------------------
# 2. Schema contract — Workspace
# ---------------------------------------------------------------------------

def test_workspace_schema_required_and_opaque_id():
    sch = _kernel().kind_port_for("Workspace").schema()
    assert sch["required"] == ["workspace_id", "name", "created_by", "created_at"]
    props = sch["properties"]
    assert props["workspace_id"]["type"] == "string"
    # plan_ref is nullable (Free floor = null).
    assert props["plan_ref"]["type"] == ["string", "null"]
    # closed schema — no stray fields on the tenancy root.
    assert sch["additionalProperties"] is False


# ---------------------------------------------------------------------------
# 3. Schema contract — WorkspaceMembership (the boundary)
# ---------------------------------------------------------------------------

def test_workspace_membership_schema_enums_and_nullable_oid():
    sch = _kernel().kind_port_for("WorkspaceMembership").schema()
    assert sch["required"] == ["workspace_id", "identity_email", "role", "status"]
    props = sch["properties"]
    assert props["role"]["enum"] == ["owner", "admin", "member", "guest"]
    assert props["status"]["enum"] == ["pending", "active"]
    assert props["status"].get("default") == "pending"
    # oid is BOUND on accept — nullable while pending (email is the handle).
    assert props["identity_oid"]["type"] == ["string", "null"]
    assert props["identity_tid"]["type"] == ["string", "null"]
    assert sch["additionalProperties"] is False


# ---------------------------------------------------------------------------
# 4. Round-trip through the kernel funnel (write + read a valid doc)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workspace_docs_write_and_read_back(tmp_path):
    k = _kernel()
    src = FilesystemWritableSource(str(tmp_path / ".dna"))
    k.source(src)
    src.attach_kernel(k)

    ws = {
        "apiVersion": "github.com/ruinosus/dna/tenant/v1",
        "kind": "Workspace",
        "metadata": {"name": "ws-abc123"},
        "spec": {
            "workspace_id": "ws-abc123",
            "name": "Barnabé Labs",
            "created_by": "founder@example.com",
            "created_at": "2026-07-15T00:00:00+00:00",
        },
    }
    await k.write_document("_lib", "Workspace", "ws-abc123", ws)

    mem = {
        "apiVersion": "github.com/ruinosus/dna/tenant/v1",
        "kind": "WorkspaceMembership",
        "metadata": {"name": "ws-abc123--founder"},
        "spec": {
            "workspace_id": "ws-abc123",
            "identity_email": "founder@example.com",
            "identity_oid": None,
            "role": "owner",
            "status": "active",
        },
    }
    await k.write_document("_lib", "WorkspaceMembership", "ws-abc123--founder", mem)

    got_ws = await k.get_document("_lib", "Workspace", "ws-abc123")
    assert got_ws is not None
    assert (got_ws.spec if hasattr(got_ws, "spec") else got_ws["spec"])["name"] == "Barnabé Labs"

    got_mem = await k.get_document("_lib", "WorkspaceMembership", "ws-abc123--founder")
    assert got_mem is not None
    spec = got_mem.spec if hasattr(got_mem, "spec") else got_mem["spec"]
    assert spec["role"] == "owner"
    assert spec["status"] == "active"
