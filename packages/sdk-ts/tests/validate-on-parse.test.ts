/**
 * s-typed-models-for-dict-kinds — KindBase.validateOnParse (ajv). 1:1 with the
 * Python twin: when a Kind opts in, parse() validates spec vs schema() and
 * throws a clear error on a malformed doc; AuditLog (the runtime-artifact with a
 * TS twin) opts in.
 */
import { describe, expect, test } from "bun:test";
import { KindBase } from "../src/kernel/kind_base.js";
import { SD } from "../src/kernel/protocols.js";
import { createKernelWithBuiltins } from "../src/bootstrap.js";

class ValidatedKind extends KindBase {
  readonly apiVersion = "x/v1";
  readonly kind = "Validated";
  readonly alias = "x-validated";
  readonly storage = SD.yaml("validateds");
  readonly validateOnParse = true;
  schema() {
    return {
      type: "object",
      required: ["name"],
      properties: { name: { type: "string" }, n: { type: ["number", "null"] } },
    };
  }
}

class UncheckedKind extends KindBase {
  readonly apiVersion = "x/v1";
  readonly kind = "Unchecked";
  readonly alias = "x-unchecked";
  readonly storage = SD.yaml("uncheckeds");
  schema() { return { type: "object", required: ["name"], properties: {} }; }
}

describe("validateOnParse", () => {
  test("valid spec parses; nullable field accepted (flat + enveloped)", () => {
    const k = new ValidatedKind();
    expect(k.parse({ name: "ok", n: null })).toBeDefined();
    expect(k.parse({ name: "ok", n: 3 })).toBeDefined();
    // enveloped shape also accepted (validates raw.spec)
    expect(k.parse({ apiVersion: "x/v1", kind: "Validated", spec: { name: "ok" } })).toBeDefined();
  });

  test("invalid spec throws a clear error", () => {
    const k = new ValidatedKind();
    expect(() => k.parse({})).toThrow(/Validated.*validation failed/);
    expect(() => k.parse({ name: 1 })).toThrow(/validation failed/);
  });

  test("opt-out Kind does NOT validate (returns raw)", () => {
    const k = new UncheckedKind();
    expect(k.parse({})).toBeDefined(); // no throw despite missing required
  });

  test("AuditLog (descriptor — expr batch A) validates on parse", () => {
    // AuditLog migrated to a descriptor (kinds/audit-log.kind.yaml); the
    // synthesized port validates against the declared schema rather than
    // carrying a validateOnParse flag — assert the BEHAVIOR (the class set
    // validate_on_parse=true; the descriptor preserves it via schema validation).
    const k = createKernelWithBuiltins() as unknown as {
      _kinds: Map<string, { kind: string; parse(r: Record<string, unknown>): unknown }>;
    };
    const audit = [...k._kinds.values()].find((x) => x.kind === "AuditLog");
    expect(audit).toBeDefined();
    // valid spec → accepted; missing required field → throws.
    expect(audit!.parse({
      apiVersion: "github.com/ruinosus/dna/audit/v1", kind: "AuditLog", metadata: { name: "x" },
      spec: {
        actor: "a", roles: ["compliance"], operation: "GET /x",
        outcome: "success", captured_at: "2026-06-07T00:00:00Z",
      },
    })).toBeDefined();
    expect(() => audit!.parse({ spec: { actor: "a" } })).toThrow(/validation failed/);
  });
});
