import { describe, expect, test } from "bun:test";
import { deriveFirstLine } from "../src/kernel/_text.js";
import { Kernel } from "../src/kernel/index.js";
import { SoulSpecExtension } from "../src/extensions/soulspec.js";
import { AgentSkillsExtension } from "../src/extensions/agentskills.js";
import { GuardrailExtension } from "../src/extensions/guardrails.js";
import { AgentsMdExtension } from "../src/extensions/agentsmd.js";

describe("deriveFirstLine", () => {
  test("returns null for null/empty", async () => {
    expect(deriveFirstLine(null)).toBeNull();
    expect(deriveFirstLine("")).toBeNull();
    expect(deriveFirstLine("   \n   ")).toBeNull();
  });

  test("strips heading markers", async () => {
    expect(deriveFirstLine("# Title\nbody")).toBe("Title");
    expect(deriveFirstLine("### Sub\nbody")).toBe("Sub");
  });

  test("skips dividers", async () => {
    expect(deriveFirstLine("---\nreal")).toBe("real");
    expect(deriveFirstLine("====\nreal")).toBe("real");
  });

  test("truncates long lines", async () => {
    const text = "x".repeat(200);
    const result = deriveFirstLine(text, 50);
    expect(result).not.toBeNull();
    expect(result!.length).toBe(53);
    expect(result!.endsWith("...")).toBe(true);
  });

  test("preserves short lines", async () => {
    expect(deriveFirstLine("short", 50)).toBe("short");
  });
});

describe("Kernel._fillDerivedDescription", () => {
  test("derives when description missing", async () => {
    const raw: Record<string, unknown> = {
      metadata: { name: "x" },
      spec: { body: "# Hello\nworld" },
    };
    Kernel._fillDerivedDescription(raw, { descriptionFallbackField: "body" });
    expect((raw.metadata as { description: string }).description).toBe("Hello");
  });

  test("preserves authored description", async () => {
    const raw: Record<string, unknown> = {
      metadata: { name: "x", description: "Authored" },
      spec: { body: "# Other" },
    };
    Kernel._fillDerivedDescription(raw, { descriptionFallbackField: "body" });
    expect((raw.metadata as { description: string }).description).toBe("Authored");
  });

  test("no-op when kind has no fallback field", async () => {
    const raw: Record<string, unknown> = {
      metadata: { name: "x" },
      spec: { body: "# Hello" },
    };
    Kernel._fillDerivedDescription(raw, {});
    expect((raw.metadata as { description?: string }).description).toBeUndefined();
  });

  test("no-op when spec field missing", async () => {
    const raw: Record<string, unknown> = {
      metadata: { name: "x" },
      spec: {},
    };
    Kernel._fillDerivedDescription(raw, { descriptionFallbackField: "body" });
    expect((raw.metadata as { description?: string }).description).toBeUndefined();
  });
});

describe("Built-in kinds declare descriptionFallbackField", () => {
  test("Soul → soul_content", async () => {
    const ext = new SoulSpecExtension(undefined as never);
    const k = new Kernel();
    k.load(ext);
    const kp = (k as unknown as { _kinds: Map<string, { descriptionFallbackField?: string }> })._kinds.get(
      "soulspec.org/v1\0Soul",
    );
    expect(kp?.descriptionFallbackField).toBe("soul_content");
  });

  test("Skill → instruction", async () => {
    const ext = new AgentSkillsExtension(undefined as never);
    const k = new Kernel();
    k.load(ext);
    const kp = (k as unknown as { _kinds: Map<string, { descriptionFallbackField?: string }> })._kinds.get(
      "agentskills.io/v1\0Skill",
    );
    expect(kp?.descriptionFallbackField).toBe("instruction");
  });

  test("Guardrail → instruction", async () => {
    const ext = new GuardrailExtension();
    const k = new Kernel();
    k.load(ext);
    const kp = (k as unknown as { _kinds: Map<string, { descriptionFallbackField?: string }> })._kinds.get(
      "github.com/ruinosus/dna/v1\0Guardrail",
    );
    expect(kp?.descriptionFallbackField).toBe("instruction");
  });

  test("AgentDefinition → content", async () => {
    const ext = new AgentsMdExtension(undefined as never);
    const k = new Kernel();
    k.load(ext);
    const kp = (k as unknown as { _kinds: Map<string, { descriptionFallbackField?: string }> })._kinds.get(
      "agents.md/v1\0AgentDefinition",
    );
    expect(kp?.descriptionFallbackField).toBe("content");
  });
});
