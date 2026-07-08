import { describe, it, expect } from "bun:test";
import { AgentsMdExtension } from "../../src/extensions/agentsmd";
import { Kernel } from "../../src/kernel/index";
import type { KindPort } from "../../src/kernel/protocols";

function getPort(): KindPort {
  const k = new Kernel();
  k.load(new AgentsMdExtension());
  const kinds = (k as unknown as { _kinds: Map<string, KindPort> })._kinds;
  for (const kp of kinds.values()) {
    if (kp.kind === "AgentDefinition") return kp;
  }
  throw new Error("AgentDefinitionKind not registered");
}

describe("AgentDefinitionKind.preview", () => {
  it("returns a markdown block when content is set", async () => {
    const blocks = getPort().preview!({
      kind: "AgentDefinition",
      name: "main",
      apiVersion: "agents.md/v1",
      spec: { content: "# Coder\n\nDoes the work." },
      metadata: { name: "main" },
    } as never);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].kind).toBe("markdown");
    expect(blocks[0].title).toBe("AGENTS.md");
    expect(blocks[0].body).toContain("Coder");
  });

  it("returns empty block when content missing", async () => {
    const blocks = getPort().preview!({
      kind: "AgentDefinition",
      name: "blank",
      apiVersion: "agents.md/v1",
      spec: {},
      metadata: { name: "blank" },
    } as never);
    expect(blocks[0].kind).toBe("empty");
  });
});
