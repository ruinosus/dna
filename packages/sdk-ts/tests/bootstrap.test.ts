import { describe, it, expect } from "bun:test";
import { createKernelWithBuiltins } from "../src/bootstrap";

describe("createKernelWithBuiltins", () => {
  it("registers all built-in kinds", async () => {
    const k = createKernelWithBuiltins();
    const registered = Array.from(
      (k as unknown as { _kinds: Map<string, { kind: string }> })._kinds.values(),
    ).map((kp) => kp.kind);
    expect(registered).toContain("Genome");
    expect(registered).toContain("Agent");
    expect(registered).toContain("Skill");
    expect(registered).toContain("Soul");
    expect(registered).toContain("Guardrail");
    expect(registered).toContain("AgentDefinition");
    expect(registered).toContain("KindDefinition");
  });
});
