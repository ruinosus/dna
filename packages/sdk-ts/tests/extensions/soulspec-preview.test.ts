import { describe, it, expect } from "bun:test";
import { SoulSpecExtension } from "../../src/extensions/soulspec";
import { Kernel } from "../../src/kernel/index";
import type { KindPort } from "../../src/kernel/protocols";

function getSoulPort(): KindPort {
  const k = new Kernel();
  k.load(new SoulSpecExtension());
  const kinds = (k as unknown as { _kinds: Map<string, KindPort> })._kinds;
  for (const kp of kinds.values()) {
    if (kp.kind === "Soul") return kp;
  }
  throw new Error("SoulKind not registered");
}

const fakeDoc = (spec: Record<string, unknown>) => ({
  kind: "Soul",
  name: "brad",
  apiVersion: "soulspec.org/v1",
  spec,
  metadata: { name: "brad" },
}) as never;

describe("SoulKind.preview", () => {
  it("stacks SOUL.md + STYLE.md + soul.json + AGENTS.md when all present", async () => {
    const kp = getSoulPort();
    const blocks = kp.preview!(
      fakeDoc({
        soul_content: "I am brad",
        style_content: "concise",
        soul_json: { specVersion: "0.4", name: "brad" },
        agents_content: "## Workflow",
      }),
    );
    expect(blocks).toHaveLength(4);
    expect(blocks[0].title).toBe("SOUL.md");
    expect(blocks[1].title).toBe("STYLE.md");
    expect(blocks[2].title).toBe("soul.json");
    expect(blocks[2].kind).toBe("code");
    expect(blocks[2].language).toBe("json");
    expect(blocks[3].title).toContain("AGENTS.md");
  });

  it("only emits the blocks that have content", async () => {
    const kp = getSoulPort();
    const blocks = kp.preview!(fakeDoc({ soul_content: "just a soul" }));
    expect(blocks).toHaveLength(1);
    expect(blocks[0].title).toBe("SOUL.md");
  });

  it("returns empty block when soul has no content at all", async () => {
    const kp = getSoulPort();
    const blocks = kp.preview!(fakeDoc({}));
    expect(blocks).toHaveLength(1);
    expect(blocks[0].kind).toBe("empty");
  });
});
