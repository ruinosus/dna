// s-delegation-declarative — Agent.spec.delegation_target_for.
//
// TS twin of packages/sdk-py/tests/test_delegation_target_for_schema.py:
// the declarative delegation-target opt-in block that replaced the
// hardcoded DELEGATION_CATALOG in dna_shared delegation_tools.
import { describe, expect, test } from "bun:test";

import { AgentSpecSchema } from "../src/kernel/models.js";

describe("AgentSpec.delegation_target_for", () => {
  test("absent field parses to undefined", () => {
    const spec = AgentSpecSchema.parse({ instruction: "hi" });
    expect(spec.delegation_target_for).toBeUndefined();
  });

  test("full block round-trips", () => {
    const spec = AgentSpecSchema.parse({
      delegation_target_for: {
        agents: ["jarvis"],
        format: "slug",
        typical_seconds: 10,
        use_when: "elaborate HTML",
        purpose: "Generate elaborate HTML mockups",
      },
    });
    expect(spec.delegation_target_for).toEqual({
      agents: ["jarvis"],
      format: "slug",
      typical_seconds: 10,
      use_when: "elaborate HTML",
      purpose: "Generate elaborate HTML mockups",
    });
  });

  test("defaults — format falls back to text, agents to []", () => {
    const spec = AgentSpecSchema.parse({ delegation_target_for: {} });
    expect(spec.delegation_target_for?.format).toBe("text");
    expect(spec.delegation_target_for?.agents).toEqual([]);
    expect(spec.delegation_target_for?.typical_seconds).toBeUndefined();
  });

  test("invalid format is rejected", () => {
    const res = AgentSpecSchema.safeParse({
      delegation_target_for: { agents: ["jarvis"], format: "xml" },
    });
    expect(res.success).toBe(false);
  });
});
