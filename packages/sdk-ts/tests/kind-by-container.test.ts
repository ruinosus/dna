import { describe, expect, test } from "bun:test";
import { Kernel } from "../src/kernel/index.js";
import { HelixExtension } from "../src/extensions/helix.js";
import { AgentSkillsExtension } from "../src/extensions/agentskills.js";

describe("Kernel.kindByContainer", () => {
  test("returns kind for registered container", async () => {
    const k = new Kernel();
    k.load(new HelixExtension());
    k.load(new AgentSkillsExtension());
    expect(k.kindByContainer("agents")).toBe("Agent");
    expect(k.kindByContainer("skills")).toBe("Skill");
  });

  test("returns null for unknown container", async () => {
    const k = new Kernel();
    k.load(new HelixExtension());
    expect(k.kindByContainer("does-not-exist")).toBeNull();
  });

  test("empty container returns null", async () => {
    const k = new Kernel();
    k.load(new HelixExtension());
    expect(k.kindByContainer("")).toBeNull();
  });
});
