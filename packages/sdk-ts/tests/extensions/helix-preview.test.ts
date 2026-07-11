import { describe, it, expect } from "bun:test";
import { HelixExtension } from "../../src/extensions/helix";
import { Kernel } from "../../src/kernel/index";
import type { KindPort } from "../../src/kernel/protocols";

function getPort(kindName: string): KindPort {
  const k = new Kernel();
  k.load(new HelixExtension());
  const kinds = (k as unknown as { _kinds: Map<string, KindPort> })._kinds;
  for (const kp of kinds.values()) {
    if (kp.kind === kindName) return kp;
  }
  throw new Error(`${kindName} not registered`);
}

const fakeDoc = (kind: string, name: string, spec: Record<string, unknown>) =>
  ({ kind, name, apiVersion: "test/v1", spec, metadata: { name } }) as never;

describe("AgentKind.preview", () => {
  it("renders the raw template (mustache placeholders intact) + metadata fields", async () => {
    const blocks = getPort("Agent").preview!(
      fakeDoc("Agent", "coach", {
        instruction: "{{soul_content}}\n\nyou are coach",
        model: "gpt-4o-mini",
        soul: "wise",
        skills: ["concise", "kind"],
      }),
    );
    expect(blocks).toHaveLength(2);
    expect(blocks[0].kind).toBe("markdown");
    expect(blocks[0].body).toContain("{{soul_content}}");
    expect(blocks[1].kind).toBe("fields");
    const metaLabels = (blocks[1].fields ?? []).map((f) => f.label);
    expect(metaLabels).toContain("model");
    expect(metaLabels).toContain("soul");
    expect(metaLabels).toContain("skills");
  });

  it("returns empty when no instruction or metadata", async () => {
    const blocks = getPort("Agent").preview!(
      fakeDoc("Agent", "blank", {}),
    );
    expect(blocks[0].kind).toBe("empty");
  });
});

describe("Tool.preview (record-plane descriptor)", () => {
  // Tool migrated from a hand-written ToolKind class to a record-plane
  // descriptor (helix/kinds/tool.kind.yaml, s-tool-kind-descriptor); its
  // preview is now the generic schema-driven DeclarativeKindPort.preview —
  // scalar props render as a leading "fields" block, object props
  // (input_schema) as their own JSON code block.
  it("renders scalar fields + input_schema as a code block", async () => {
    const blocks = getPort("Tool").preview!(
      fakeDoc("Tool", "slack-send", {
        type: "http",
        endpoint: "https://slack.com/api/chat.postMessage",
        method: "POST",
        input_schema: { type: "object", required: ["channel"] },
        read_only: false,
      }),
    );
    expect(blocks[0].kind).toBe("fields");
    const labels = (blocks[0].fields ?? []).map((f) => f.label);
    expect(labels).toContain("type");
    expect(labels).toContain("endpoint");
    const codeTitles = blocks.filter((b) => b.kind === "code").map((b) => b.title);
    expect(codeTitles).toContain("input_schema");
  });
});

describe("ActorKind.preview", () => {
  it("renders role + goals + pain_points as fields", async () => {
    const blocks = getPort("Actor").preview!(
      fakeDoc("Actor", "customer", {
        role: "End user",
        actor_type: "human",
        goals: ["resolve issue quickly", "feel heard"],
        pain_points: ["long wait times"],
      }),
    );
    expect(blocks[0].kind).toBe("fields");
    const labels = (blocks[0].fields ?? []).map((f) => f.label);
    expect(labels).toContain("role");
    expect(labels).toContain("goals");
    expect(labels).toContain("pain_points");
  });
});

describe("UseCaseKind.preview", () => {
  it("renders primary_actor + main_flow + success_criteria", async () => {
    const blocks = getPort("UseCase").preview!(
      fakeDoc("UseCase", "onboard", {
        primary_actor: "customer",
        main_flow: ["sign up", "verify email", "select plan"],
        success_criteria: ["account active", "plan billed"],
      }),
    );
    expect(blocks[0].kind).toBe("fields");
    const fields = blocks[0].fields ?? [];
    const flow = fields.find((f) => f.label === "main_flow");
    expect(flow?.value).toContain("1. sign up");
  });
});

// Phase 16 — ``ModuleKind.preview`` test deleted. ModuleKind class is
// gone. Equivalent ``GenomeKind.preview`` coverage lives in
// tests/package-layerpolicy-kinds.test.ts. The legacy assertion
// expected ``"agents"`` in the labels but GenomeSpec dropped the
// bill-of-materials inventory arrays.
