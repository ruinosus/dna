import { describe, it, expect } from "bun:test";
import { AgentSkillsExtension } from "../../src/extensions/agentskills";
import { Kernel } from "../../src/kernel/index";
import type { KindPort } from "../../src/kernel/protocols";

function getSkillPort(): KindPort {
  const k = new Kernel();
  k.load(new AgentSkillsExtension());
  // Reach into the kernel's registered kinds to grab the SkillKind instance.
  // We can't construct it directly because the class is not exported.
  const kinds = (k as unknown as { _kinds: Map<string, KindPort> })._kinds;
  for (const kp of kinds.values()) {
    if (kp.kind === "Skill") return kp;
  }
  throw new Error("SkillKind not registered");
}

describe("SkillKind.preview", () => {
  it("returns a single markdown block when instruction is set", async () => {
    const kp = getSkillPort();
    const blocks = kp.preview!({
      kind: "Skill",
      name: "feedback-tone",
      apiVersion: "agentskills.io/v1",
      spec: { instruction: "# Feedback tone\n\nbe kind and direct." },
      metadata: { name: "feedback-tone" },
    } as never);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].kind).toBe("markdown");
    expect(blocks[0].title).toBe("SKILL.md");
    expect(blocks[0].body).toContain("be kind");
  });

  it("returns an empty block when instruction is missing", async () => {
    const kp = getSkillPort();
    const blocks = kp.preview!({
      kind: "Skill",
      name: "blank",
      apiVersion: "agentskills.io/v1",
      spec: {},
      metadata: { name: "blank" },
    } as never);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].kind).toBe("empty");
  });
});
