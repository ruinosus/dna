import { describe, it, expect } from "bun:test";
import { KindDefinitionExtension } from "../../src/extensions/kinddef";
import { Kernel } from "../../src/kernel/index";
import type { KindPort } from "../../src/kernel/protocols";

function getPort(): KindPort {
  const k = new Kernel();
  k.load(new KindDefinitionExtension());
  const kinds = (k as unknown as { _kinds: Map<string, KindPort> })._kinds;
  for (const kp of kinds.values()) {
    if (kp.kind === "KindDefinition") return kp;
  }
  throw new Error("KindDefinitionKind not registered");
}

const fakeDoc = (spec: Record<string, unknown>) => ({
  kind: "KindDefinition",
  name: "meeting",
  apiVersion: "github.com/ruinosus/dna/core/v1",
  spec,
  metadata: { name: "meeting" },
}) as never;

describe("KindDefinitionKind.preview", () => {
  it("renders target_kind / alias / schema / storage as fields", async () => {
    const blocks = getPort().preview!(
      fakeDoc({
        target_kind: "Meeting",
        target_api_version: "user.local/v1",
        alias: "user-meeting",
        origin: "user.local",
        is_root: false,
        prompt_target: false,
        flatten_in_context: false,
        schema: {
          type: "object",
          required: ["title"],
          properties: { title: { type: "string" } },
        },
        storage: { type: "yaml", container: "meetings" },
        docs: "Reunião com título e participantes.",
      }),
    );
    expect(blocks).toHaveLength(1);
    expect(blocks[0].kind).toBe("fields");
    const labels = (blocks[0].fields ?? []).map((f) => f.label);
    expect(labels).toContain("target_kind");
    expect(labels).toContain("alias");
    expect(labels).toContain("schema");
    expect(labels).toContain("storage");
    expect(labels).toContain("docs");
  });
});
