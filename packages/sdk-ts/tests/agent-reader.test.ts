/**
 * AgentReader + AgentWriter tests.
 */

import { describe, test, expect } from "bun:test";
import { FilesystemBundleHandle } from "../src/kernel/bundle-handle.js";
import { mkdtempSync, writeFileSync, mkdirSync, readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

import { AgentReader, AgentWriter } from "../src/extensions/helix.js";

function makeTmpDir(): string {
  return mkdtempSync(join(tmpdir(), "agent-test-"));
}

// ---------------------------------------------------------------------------
// AgentReader
// ---------------------------------------------------------------------------

describe("AgentReader", () => {
  const reader = new AgentReader();

  test("detect returns true when AGENT.md exists", async () => {
    const dir = makeTmpDir();
    writeFileSync(join(dir, "AGENT.md"), "---\nname: test\n---\nHello");
    expect(reader.detect(new FilesystemBundleHandle(dir))).toBe(true);
  });

  test("detect returns false when AGENT.md is missing", async () => {
    const dir = makeTmpDir();
    expect(reader.detect(new FilesystemBundleHandle(dir))).toBe(false);
  });

  test("read parses frontmatter and body", async () => {
    const dir = makeTmpDir();
    const content = [
      "---",
      "name: my-agent",
      "description: A test agent",
      "model: gpt-4",
      "soul: mysoul",
      "skills:",
      "  - skill-a",
      "  - skill-b",
      "---",
      "",
      "You are a helpful assistant.",
    ].join("\n");
    writeFileSync(join(dir, "AGENT.md"), content);

    const result = reader.read(new FilesystemBundleHandle(dir));

    expect(result.apiVersion).toBe("github.com/ruinosus/dna/v1");
    expect(result.kind).toBe("Agent");
    expect((result.metadata as any).name).toBe("my-agent");
    expect((result.metadata as any).description).toBe("A test agent");
    expect((result.spec as any).model).toBe("gpt-4");
    expect((result.spec as any).soul).toBe("mysoul");
    expect((result.spec as any).skills).toEqual(["skill-a", "skill-b"]);
    expect((result.spec as any).instruction).toBe("You are a helpful assistant.");
  });

  test("read extracts all spec fields", async () => {
    const dir = makeTmpDir();
    const content = [
      "---",
      "name: full-agent",
      "description: Full spec",
      "labels:",
      "  env: prod",
      "objective: Help users",
      "type: assistant",
      "tags:",
      "  - tag1",
      "  - tag2",
      "tools:",
      "  - tool-x",
      "team_members:",
      "  - agent-y",
      "promptTemplate: custom-template",
      "---",
      "",
      "Instruction body.",
    ].join("\n");
    writeFileSync(join(dir, "AGENT.md"), content);

    const result = reader.read(new FilesystemBundleHandle(dir));
    const meta = result.metadata as any;
    const spec = result.spec as any;

    expect(meta.labels).toEqual({ env: "prod" });
    expect(spec.objective).toBe("Help users");
    expect(spec.type).toBe("assistant");
    expect(spec.tags).toEqual(["tag1", "tag2"]);
    expect(spec.tools).toEqual(["tool-x"]);
    expect(spec.team_members).toEqual(["agent-y"]);
    expect(spec.promptTemplate).toBe("custom-template");
  });

  test("read falls back to directory name when name is missing", async () => {
    const dir = makeTmpDir();
    const agentDir = join(dir, "fallback-agent");
    mkdirSync(agentDir);
    writeFileSync(join(agentDir, "AGENT.md"), "---\ndescription: no name\n---\nBody");

    const result = reader.read(new FilesystemBundleHandle(agentDir));
    expect((result.metadata as any).name).toBe("fallback-agent");
  });

  test("read collects references subdir", async () => {
    const dir = makeTmpDir();
    writeFileSync(join(dir, "AGENT.md"), "---\nname: ref-agent\n---\nBody");
    const refDir = join(dir, "references");
    mkdirSync(refDir);
    writeFileSync(join(refDir, "guide.md"), "# Guide\nSome content");

    const result = reader.read(new FilesystemBundleHandle(dir));
    const spec = result.spec as any;
    expect(spec.references).toEqual({ "guide.md": "# Guide\nSome content" });
  });
});

// ---------------------------------------------------------------------------
// AgentWriter
// ---------------------------------------------------------------------------

describe("AgentWriter", () => {
  const writer = new AgentWriter();
  const reader = new AgentReader();

  test("canWrite returns true for Agent", async () => {
    expect(writer.canWrite({ kind: "Agent" })).toBe(true);
  });

  test("canWrite returns false for other kinds", async () => {
    expect(writer.canWrite({ kind: "Skill" })).toBe(false);
    expect(writer.canWrite({ kind: "Genome" })).toBe(false);
    expect(writer.canWrite({})).toBe(false);
  });

  test("write creates AGENT.md", async () => {
    const dir = join(makeTmpDir(), "out-agent");
    const raw = {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Agent",
      metadata: { name: "written-agent", description: "desc" },
      spec: { instruction: "Do stuff", model: "gpt-4" },
    };
    writer.write(new FilesystemBundleHandle(dir), raw);

    expect(existsSync(join(dir, "AGENT.md"))).toBe(true);
    const content = readFileSync(join(dir, "AGENT.md"), "utf-8");
    expect(content).toContain("name: written-agent");
    expect(content).toContain("Do stuff");
  });

  test("round-trip write then read", async () => {
    const dir = join(makeTmpDir(), "roundtrip-agent");
    const raw = {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Agent",
      metadata: { name: "rt-agent", description: "round-trip" },
      spec: {
        instruction: "Be helpful.",
        model: "claude-3",
        soul: "default-soul",
        skills: ["skill-1", "skill-2"],
        references: { "ref.md": "Reference content" },
      },
    };
    writer.write(new FilesystemBundleHandle(dir), raw);
    const result = reader.read(new FilesystemBundleHandle(dir));

    expect((result.metadata as any).name).toBe("rt-agent");
    expect((result.metadata as any).description).toBe("round-trip");
    expect((result.spec as any).instruction).toBe("Be helpful.");
    expect((result.spec as any).model).toBe("claude-3");
    expect((result.spec as any).soul).toBe("default-soul");
    expect((result.spec as any).skills).toEqual(["skill-1", "skill-2"]);
    expect((result.spec as any).references).toEqual({ "ref.md": "Reference content" });
  });
});
