/**
 * s-port-missing-ts-extensions (slice: audit) — the TS AuditExtension is a
 * faithful twin of the Python one: registers AuditLog + UserRoleAssignment as
 * TENANTED, YAML, dict-model Kinds with the same schemas.
 */
import { describe, expect, test } from "bun:test";
import { createKernelWithBuiltins } from "../src/bootstrap.js";

function kindByAlias(alias: string) {
  const k = createKernelWithBuiltins() as unknown as {
    _kinds: Map<string, { alias: string; kind: string; apiVersion: string; storage?: { pattern?: string; container?: string }; schema(): unknown; parse(r: Record<string, unknown>): unknown }>;
  };
  return [...k._kinds.values()].find((x) => x.alias === alias);
}

describe("AuditExtension — AuditLog + UserRoleAssignment Kinds", () => {
  test("AuditLog registers with the right identity + YAML storage", () => {
    const kp = kindByAlias("audit-auditlog");
    expect(kp).toBeDefined();
    expect(kp!.kind).toBe("AuditLog");
    expect(kp!.apiVersion).toBe("github.com/ruinosus/dna/audit/v1");
    expect(kp!.storage?.pattern).toBe("yaml");
    expect(kp!.storage?.container).toBe("audit-log");
  });

  test("UserRoleAssignment registers with the right identity + YAML storage", () => {
    const kp = kindByAlias("audit-userroleassignment");
    expect(kp).toBeDefined();
    expect(kp!.kind).toBe("UserRoleAssignment");
    expect(kp!.storage?.container).toBe("user-roles");
  });

  test("AuditLog schema requires the core compliance fields", () => {
    const schema = kindByAlias("audit-auditlog")!.schema() as { required: string[]; properties: Record<string, unknown> };
    expect(schema.required).toEqual(["actor", "roles", "operation", "outcome", "captured_at"]);
    expect(schema.properties.outcome).toBeDefined();
  });

  test("dict-model parse returns the raw spec untouched (valid doc)", () => {
    const kp = kindByAlias("audit-auditlog")!;
    // AuditLog now validates on parse (s-typed-models-for-dict-kinds) — the
    // sample carries the required compliance fields; parse validates + returns raw.
    const raw = {
      apiVersion: "github.com/ruinosus/dna/audit/v1", kind: "AuditLog", metadata: { name: "x" },
      spec: {
        actor: "a", roles: ["compliance"], operation: "GET /x",
        outcome: "success", captured_at: "2026-06-07T00:00:00Z",
      },
    };
    expect(kp.parse(raw)).toEqual(raw);
  });

  test("AuditLog rejects a spec missing required fields (validate_on_parse)", () => {
    const kp = kindByAlias("audit-auditlog")!;
    expect(() => kp.parse({ spec: { actor: "a" } })).toThrow(/validation failed/);
  });
});
