import { describe, it, expect } from "bun:test";
import { GuardrailExtension } from "../../src/extensions/guardrails";
import { Kernel } from "../../src/kernel/index";
import type { KindPort } from "../../src/kernel/protocols";

function getGuardrailPort(): KindPort {
  const k = new Kernel();
  k.load(new GuardrailExtension());
  const kinds = (k as unknown as { _kinds: Map<string, KindPort> })._kinds;
  for (const kp of kinds.values()) {
    if (kp.kind === "Guardrail") return kp;
  }
  throw new Error("GuardrailKind not registered");
}

const fakeDoc = (spec: Record<string, unknown>) => ({
  kind: "Guardrail",
  name: "no-pii",
  apiVersion: "github.com/ruinosus/dna/v1",
  spec,
  metadata: { name: "no-pii" },
}) as never;

describe("GuardrailKind.preview", () => {
  it("renders instruction + rules + severity/scope", async () => {
    const kp = getGuardrailPort();
    const blocks = kp.preview!(
      fakeDoc({
        instruction: "Never leak personally identifiable information.",
        rules: ["No emails", "No phone numbers", "No addresses"],
        severity: "hard",
        scope: "both",
      }),
    );
    expect(blocks.length).toBe(3);
    expect(blocks[0].title).toBe("GUARDRAIL.md");
    expect(blocks[1].title).toBe("Rules");
    expect(blocks[1].body).toContain("- No emails");
    expect(blocks[2].kind).toBe("fields");
    expect(blocks[2].fields?.find((f) => f.label === "severity")?.value).toBe("hard");
  });

  it("returns empty block when nothing is set", async () => {
    const kp = getGuardrailPort();
    const blocks = kp.preview!(fakeDoc({}));
    expect(blocks).toHaveLength(1);
    expect(blocks[0].kind).toBe("empty");
  });
});
