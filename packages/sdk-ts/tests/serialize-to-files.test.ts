import { describe, test, expect } from "bun:test";
import { Kernel } from "../src/kernel/index.js";
import { serializeRawToFiles } from "../src/kernel/serialize-to-files.js";
import { HelixExtension } from "../src/extensions/helix.js";
import { AgentSkillsExtension } from "../src/extensions/agentskills.js";

function loadedKernel(exts: Array<{ new (): any }>): Kernel {
  const k = new Kernel();
  for (const E of exts) k.load(new E());
  return k;
}

describe("serializeRawToFiles", () => {
  test("Agent bundle: AGENT.md with frontmatter + instruction body", async () => {
    const k = loadedKernel([HelixExtension]);
    const raw = {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Agent",
      metadata: { name: "alice" },
      spec: { instruction: "Be helpful" },
    };
    const files = serializeRawToFiles(raw, k);
    expect(files.length).toBeGreaterThanOrEqual(1);
    const agentMd = files.find((f) => f.relativePath.endsWith("AGENT.md"));
    expect(agentMd).toBeDefined();
    expect(agentMd!.content).toContain("name: alice");
    expect(agentMd!.content).toContain("Be helpful");
  });

  test("Skill bundle: SKILL.md with instruction body", async () => {
    const k = loadedKernel([AgentSkillsExtension]);
    const raw = {
      apiVersion: "agentskills.io/v1",
      kind: "Skill",
      metadata: { name: "demo" },
      spec: { instruction: "do x" },
    };
    const files = serializeRawToFiles(raw, k);
    const skillMd = files.find((f) => f.relativePath.endsWith("SKILL.md"));
    expect(skillMd).toBeDefined();
    expect(skillMd!.content).toContain("do x");
  });

  test("unknown kind throws with helpful message", async () => {
    const k = new Kernel();
    expect(() =>
      serializeRawToFiles(
        {
          apiVersion: "x/v1",
          kind: "NoSuchKind",
          metadata: { name: "x" },
          spec: {},
        },
        k,
      ),
    ).toThrow(/Unknown kind: NoSuchKind/);
  });
});
