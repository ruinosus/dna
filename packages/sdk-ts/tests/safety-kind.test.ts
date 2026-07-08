import { describe, expect, test } from "bun:test";
import { createKernelWithBuiltins } from "../src/bootstrap.js";
import { SafetyPolicySpecSchema } from "../src/kernel/models.js";

describe("SafetyPolicy Kind", () => {
  test("registered", async () => {
    const k = createKernelWithBuiltins();
    let found = false;
    for (const kp of k._kinds.values()) {
      if (kp.kind === "SafetyPolicy") {
        found = true;
        break;
      }
    }
    expect(found).toBe(true);
  });

  test("alias and metadata", async () => {
    const k = createKernelWithBuiltins();
    for (const kp of k._kinds.values()) {
      if (kp.kind === "SafetyPolicy") {
        expect(kp.alias).toBe("helix-safety-policy");
        expect(kp.isRoot).toBe(false);
        expect(kp.isPromptTarget).toBe(false);
        expect(kp.apiVersion).toBe("github.com/ruinosus/dna/v1");
        return;
      }
    }
    throw new Error("SafetyPolicy kind not found");
  });

  test("graphStyle is red", async () => {
    const k = createKernelWithBuiltins();
    for (const kp of k._kinds.values()) {
      if (kp.kind === "SafetyPolicy") {
        expect(kp.graphStyle?.fill).toBe("#DC2626");
        expect(kp.graphStyle?.stroke).toBe("#B91C1C");
        return;
      }
    }
  });

  test("schema returns JSON Schema", async () => {
    const k = createKernelWithBuiltins();
    for (const kp of k._kinds.values()) {
      if (kp.kind === "SafetyPolicy") {
        const schema = kp.schema?.();
        expect(schema).toBeTruthy();
        expect((schema as any).type).toBe("object");
        expect((schema as any).properties.scope).toBeTruthy();
        expect((schema as any).properties.action).toBeTruthy();
        expect((schema as any).properties.rules).toBeTruthy();
        return;
      }
    }
  });
});

describe("SafetyPolicySpecSchema — Phase 7 ml-privacy fields", () => {
  test("ml-privacy-filter engine fields round-trip", async () => {
    const parsed = SafetyPolicySpecSchema.parse({
      engine: "ml-privacy-filter",
      threshold: 0.85,
      categories: ["private_email", "private_phone"],
      budget_ms: 1000,
    });
    expect(parsed.engine).toBe("ml-privacy-filter");
    expect(parsed.threshold).toBe(0.85);
    expect(parsed.categories).toEqual(["private_email", "private_phone"]);
    expect(parsed.budget_ms).toBe(1000);
  });

  test("backward-compat — defaults preserve presidio", async () => {
    const parsed = SafetyPolicySpecSchema.parse({});
    expect(parsed.engine).toBe("presidio");
    expect(parsed.severity).toBe("error");
    expect(parsed.threshold).toBe(0.8);
    expect(parsed.categories).toBeNull();
    expect(parsed.mask_char).toBe("[REDACTED]");
  });
});
