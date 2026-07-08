import { describe, expect, test } from "bun:test";
import { createKernelWithBuiltins } from "../src/bootstrap.js";

describe("Kind interface: schema() and dependencies()", () => {
  const k = createKernelWithBuiltins();

  function findKind(name: string) {
    for (const kp of k._kinds.values()) {
      if (kp.kind === name) return kp;
    }
    return null;
  }

  test("Agent has schema() returning JSON Schema with properties", async () => {
    const kp = findKind("Agent")!;
    expect(kp).toBeTruthy();
    const s = kp.schema!();
    expect(s).toBeTruthy();
    expect(s!.type).toBe("object");
    expect(s!.properties).toBeTruthy();
    const props = s!.properties as Record<string, any>;
    expect(props.instruction).toBeTruthy();
    expect(props.skills).toBeTruthy();
  });

  test("Agent has dependencies() returning dep map", async () => {
    const kp = findKind("Agent")!;
    const deps = kp.dependencies!();
    expect(deps).toBeTruthy();
    expect(deps!.soul).toBe("soulspec-soul");
    expect(deps!.skills).toBe("agentskills-skill");
  });

  test("Genome has no inventory dep_filters", async () => {
    // Phase 16 — bill-of-materials arrays (agents, skills, ...) dropped
    // from GenomeSpec. dep_filters returns null. Composition validation
    // walks scanner-discovered docs directly.
    const kp = findKind("Genome")!;
    expect(kp.dependencies!()).toBeNull();
  });

  test("Skill has schema()", async () => {
    const kp = findKind("Skill")!;
    const s = kp.schema!();
    expect(s).toBeTruthy();
    expect(s!.type).toBe("object");
    const props = s!.properties as Record<string, any>;
    expect(props.instruction).toBeTruthy();
  });

  test("Soul has schema()", async () => {
    const kp = findKind("Soul")!;
    const s = kp.schema!();
    expect(s).toBeTruthy();
  });

  test("Guardrail has schema()", async () => {
    const kp = findKind("Guardrail")!;
    const s = kp.schema!();
    expect(s).toBeTruthy();
    const props = s!.properties as Record<string, any>;
    expect(props.rules).toBeTruthy();
  });

  test("dependencies() delegates to depFilters() for all kinds", async () => {
    for (const kp of k._kinds.values()) {
      if (kp.dependencies) {
        expect(kp.dependencies()).toEqual(kp.depFilters());
      }
    }
  });
});
