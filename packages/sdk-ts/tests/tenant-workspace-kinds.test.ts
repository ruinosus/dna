// f-ws-kinds F1 — the Workspace + WorkspaceMembership Kinds (ADR "Model B").
// TS twin of tests/test_tenant_workspace_kinds.py.
//
// Two GLOBAL record Kinds shipped as byte-identical Py↔TS descriptors inside
// the `tenant` extension (F3 — record Kinds are data, not classes):
//   - Workspace (`tenant-workspace`) — the DNA tenancy root; its opaque,
//     immutable workspace_id IS the physical `tenant` column value.
//   - WorkspaceMembership (`tenant-workspace-membership`) — the
//     identity→workspace boundary (verified oid + email + tid → workspace).
import { describe, it, expect } from "bun:test";
import { Kernel } from "../src/kernel/index.js";
import { TenantScope } from "../src/kernel/protocols.js";
import { TenantExtension } from "../src/extensions/tenant.js";

function kernel(): Kernel {
  const k = new Kernel();
  k.load(new TenantExtension());
  return k;
}

// ---------------------------------------------------------------------------
// Registration (descriptor)
// ---------------------------------------------------------------------------

describe("Workspace Kind (descriptor)", () => {
  it("registers from kinds/workspace.kind.yaml as a GLOBAL record Kind", () => {
    const kp = kernel().kindPortFor("Workspace");
    expect(kp).not.toBeNull();
    expect(kp!.alias).toBe("tenant-workspace");
    expect((kp as any).plane).toBe("record");
    // GLOBAL — the tenancy boundary lives above any single workspace.
    expect((kp as any).scope).toBe(TenantScope.GLOBAL);
    expect(kp!.storage.container).toBe("workspaces");
    expect((kp as any).__declarative__).toBe(true);
    expect((kp as any).__builtin_descriptor__).toBe(true);
  });

  it("required + opaque id + nullable plan_ref", () => {
    const sch = (kernel().kindPortFor("Workspace") as any).schema();
    expect(sch.required).toEqual(["workspace_id", "name", "created_by", "created_at"]);
    expect(sch.properties.workspace_id.type).toBe("string");
    expect(sch.properties.plan_ref.type).toEqual(["string", "null"]);
    expect(sch.additionalProperties).toBe(false);
  });
});

describe("WorkspaceMembership Kind (descriptor)", () => {
  it("registers as a GLOBAL record Kind — the identity→workspace boundary", () => {
    const kp = kernel().kindPortFor("WorkspaceMembership");
    expect(kp).not.toBeNull();
    expect(kp!.alias).toBe("tenant-workspace-membership");
    expect((kp as any).plane).toBe("record");
    expect((kp as any).scope).toBe(TenantScope.GLOBAL);
    expect(kp!.storage.container).toBe("workspace-memberships");
    expect((kp as any).__declarative__).toBe(true);
  });

  it("role/status enums + nullable oid (bound on accept)", () => {
    const sch = (kernel().kindPortFor("WorkspaceMembership") as any).schema();
    expect(sch.required).toEqual(["workspace_id", "identity_email", "role", "status"]);
    expect(sch.properties.role.enum).toEqual(["owner", "admin", "member", "guest"]);
    expect(sch.properties.status.enum).toEqual(["pending", "active"]);
    expect(sch.properties.status.default).toBe("pending");
    expect(sch.properties.identity_oid.type).toEqual(["string", "null"]);
    expect(sch.properties.identity_tid.type).toEqual(["string", "null"]);
    expect(sch.additionalProperties).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Coexistence — F1 ADDS; it must not drop the legacy class Kinds.
// ---------------------------------------------------------------------------

describe("tenant extension coexistence", () => {
  it("keeps the legacy Tenant / TenantMembership class Kinds alongside the new ones", () => {
    const k = kernel();
    expect(k.kindPortFor("Tenant")).not.toBeNull();
    expect(k.kindPortFor("TenantMembership")).not.toBeNull();
    expect(k.kindPortFor("Workspace")).not.toBeNull();
    expect(k.kindPortFor("WorkspaceMembership")).not.toBeNull();
    // Distinct membership aliases — no collision.
    expect(k.kindPortFor("TenantMembership")!.alias).toBe("tenant-membership");
    expect(k.kindPortFor("WorkspaceMembership")!.alias).toBe("tenant-workspace-membership");
  });
});
