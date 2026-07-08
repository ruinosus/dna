import { quickInstance, createKernelWithBuiltins } from "../src/bootstrap";
import { FilesystemBundleHandle } from "../src/kernel/bundle-handle.js";
import { describe, test, expect } from "bun:test";
import type { SerializedDocument } from "../src/kernel/protocols.js";
import { GenericBundleWriter, GenericBundleReader } from "../src/kernel/generic-rw.js";
import { SD } from "../src/kernel/protocols.js";
import { AgentWriter } from "../src/extensions/helix.js";
import { Kernel } from "../src/kernel/index.js";
import { join } from "node:path";

const BASE_DIR = join(import.meta.dir, "..", "..", "..", "scopes", "open-swe", ".dna");

describe("write path types", () => {
  test("SerializedDocument has files array", async () => {
    const doc: SerializedDocument = {
      files: [{ relativePath: "skills/x/SKILL.md", content: "hello" }],
    };
    expect(doc.files).toHaveLength(1);
  });
});

describe("GenericBundleWriter.serialize", () => {
  test("text body produces single marker file", async () => {
    const sd = SD.bundle("things", "THING.md");
    const writer = new GenericBundleWriter(sd, "Thing");
    const files = writer.serialize!({
      kind: "Thing",
      metadata: { name: "my-thing", description: "test" },
      spec: { instruction: "Do the thing.", custom: "value" },
    });
    expect(files).toHaveLength(1);
    expect(files[0].relativePath).toBe("THING.md");
    expect(files[0].content).toContain("name: my-thing");
    expect(files[0].content).toContain("Do the thing.");
    expect(files[0].content).toContain("custom: value");
  });

  test("list body produces markdown list", async () => {
    const sd = SD.bundle("guards", "GUARD.md", "list", "rules");
    const writer = new GenericBundleWriter(sd, "Guard");
    const files = writer.serialize!({
      kind: "Guard",
      metadata: { name: "safety" },
      spec: { rules: ["No harm", "Be safe"], severity: "error" },
    });
    expect(files).toHaveLength(1);
    expect(files[0].content).toContain("- No harm");
    expect(files[0].content).toContain("- Be safe");
    expect(files[0].content).toContain("severity: error");
  });

  test("roundtrip text: serialize then read", async () => {
    const sd = SD.bundle("things", "THING.md");
    const writer = new GenericBundleWriter(sd, "Thing");
    const reader = new GenericBundleReader(sd, "test.io/v1", "Thing");

    const raw = {
      kind: "Thing",
      metadata: { name: "rt", description: "roundtrip" },
      spec: { instruction: "Hello.", extra: "val" },
    };
    const files = writer.serialize!(raw);

    // Write to temp dir and read back
    const fs = require("node:fs");
    const path = require("node:path");
    const os = require("node:os");
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "rt-"));
    const docDir = path.join(tmp, "rt");
    fs.mkdirSync(docDir, { recursive: true });
    for (const f of files) {
      const fp = path.join(docDir, f.relativePath);
      fs.mkdirSync(path.dirname(fp), { recursive: true });
      fs.writeFileSync(fp, f.content);
    }

    const result = reader.read(new FilesystemBundleHandle(docDir));
    expect((result.metadata as any).name).toBe("rt");
    expect((result.spec as any).instruction).toBe("Hello.");
    expect((result.spec as any).extra).toBe("val");
    fs.rmSync(tmp, { recursive: true });
  });

  test("roundtrip list: serialize then read", async () => {
    const sd = SD.bundle("guards", "GUARD.md", "list", "rules");
    const writer = new GenericBundleWriter(sd, "Guard");
    const reader = new GenericBundleReader(sd, "guard.io/v1", "Guard");

    const raw = {
      kind: "Guard",
      metadata: { name: "safety" },
      spec: { rules: ["A", "B", "C"], severity: "warn" },
    };
    const files = writer.serialize!(raw);

    const fs = require("node:fs");
    const path = require("node:path");
    const os = require("node:os");
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "rt-"));
    const docDir = path.join(tmp, "safety");
    fs.mkdirSync(docDir, { recursive: true });
    for (const f of files) {
      fs.writeFileSync(path.join(docDir, f.relativePath), f.content);
    }

    const result = reader.read(new FilesystemBundleHandle(docDir));
    expect((result.spec as any).rules).toEqual(["A", "B", "C"]);
    expect((result.spec as any).severity).toBe("warn");
    fs.rmSync(tmp, { recursive: true });
  });
});

describe("AgentWriter.serialize", () => {
  test("produces AGENT.md + sub-directory files", async () => {
    const writer = new AgentWriter();
    const files = writer.serialize!({
      kind: "Agent",
      metadata: { name: "bot", description: "A bot" },
      spec: {
        instruction: "Do things.",
        model: "gpt-4",
        skills: ["a", "b"],
        scripts: { "build.sh": "#!/bin/bash\necho hi" },
        root_files: { "README.md": "# Bot" },
      },
    });
    const paths = files.map(f => f.relativePath);
    expect(paths).toContain("AGENT.md");
    expect(paths).toContain("scripts/build.sh");
    expect(paths).toContain("README.md");
    const agentMd = files.find(f => f.relativePath === "AGENT.md")!;
    expect(agentMd.content).toContain("name: bot");
    expect(agentMd.content).toContain("Do things.");
  });
});

describe("SoulWriter.serialize", () => {
  test("produces SOUL.md + companion files", async () => {
    const { SoulWriter } = await import("../src/extensions/soulspec.js");
    const writer = new SoulWriter();
    const files = writer.serialize({
      kind: "Soul",
      metadata: { name: "my-soul" },
      spec: {
        soul_content: "# My Soul",
        style_content: "# Style",
        soul_json: { values: ["kindness"] },
      },
    });
    const paths = files.map(f => f.relativePath);
    expect(paths).toContain("SOUL.md");
    expect(paths).toContain("STYLE.md");
    expect(paths).toContain("soul.json");
    expect(paths).not.toContain("IDENTITY.md");
    expect(paths).not.toContain("HEARTBEAT.md");
  });
});

describe("SkillWriter.serialize", () => {
  test("produces SKILL.md + sub-directory files", async () => {
    const { SkillWriter } = await import("../src/extensions/agentskills.js");
    const writer = new SkillWriter();
    const files = writer.serialize({
      kind: "Skill",
      metadata: { name: "my-skill", description: "A skill" },
      spec: {
        instruction: "Do this.",
        scripts: { "run.sh": "#!/bin/bash" },
        references: { "guide.md": "# Guide" },
      },
    });
    const paths = files.map(f => f.relativePath);
    expect(paths).toContain("SKILL.md");
    expect(paths).toContain("scripts/run.sh");
    expect(paths).toContain("references/guide.md");
  });
});

describe("Kernel.serializeDocument", () => {
  test("serializes Agent with agents/ prefix", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const sweAgent = (mi.documents.find((d) => d.kind === "Agent" && d.name === "swe-agent") ?? null);
    expect(sweAgent).not.toBeNull();
    const k = (mi as any)._kernel as Kernel;
    const result = k.serializeDocument("open-swe", "Agent", "swe-agent", sweAgent!.raw);
    expect(result.files.length).toBeGreaterThan(0);
    expect(result.files[0].relativePath).toStartWith("agents/swe-agent/");
    expect(result.files[0].relativePath).toContain("AGENT.md");
  });

  test("serializes Genome at root", async () => {
    // Phase 16 — Genome replaces Module. Marker file is now Genome.yaml.
    const mi = await quickInstance("open-swe", BASE_DIR);
    const root = mi.root;
    expect(root).not.toBeNull();
    const k = (mi as any)._kernel as Kernel;
    const result = k.serializeDocument("open-swe", "Genome", root!.name, root!.raw);
    expect(result.files[0].relativePath).toBe("Genome.yaml");
  });

  test("serializes Skill with skills/ prefix", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const skills = mi.documents.filter((d) => d.kind === "Skill");
    if (skills.length === 0) return; // skip if no skills
    const skill = skills[0];
    const k = (mi as any)._kernel as Kernel;
    const result = k.serializeDocument("open-swe", "Skill", skill.name, skill.raw);
    expect(result.files[0].relativePath).toStartWith(`skills/${skill.name}/`);
  });

  test("serializes Soul with souls/ prefix + companions", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const souls = mi.documents.filter((d) => d.kind === "Soul");
    if (souls.length === 0) return;
    const soul = souls[0];
    const k = (mi as any)._kernel as Kernel;
    const result = k.serializeDocument("open-swe", "Soul", soul.name, soul.raw);
    expect(result.files[0].relativePath).toStartWith(`souls/${soul.name}/`);
    expect(result.files[0].relativePath).toContain("SOUL.md");
  });
});

describe("Kernel.writeDocument", () => {
  test("delegates to port.saveDocument", async () => {
    const calls: Array<{ scope: string; kind: string; name: string; raw: Record<string, unknown> }> = [];
    const ws = {
      saveDocument: async (
        scope: string, kind: string, name: string, raw: Record<string, unknown>,
      ) => {
        calls.push({ scope, kind, name, raw });
        return "v1";
      },
      deleteDocument: async () => {},
      loadAll: () => [],
      loadBootstrapDocs: async () => [],
      resolveRef: () => "",
      loadLayer: () => [],
      supportsReaders: false,
    };

    const mi = await quickInstance("open-swe", BASE_DIR);
    const k = (mi as any)._kernel as Kernel;
    k.writableSource(ws as any);

    const sweAgent = (mi.documents.find((d) => d.kind === "Agent" && d.name === "swe-agent") ?? null);
    const version = await k.writeDocument("open-swe", "Agent", "swe-agent", sweAgent!.raw);

    expect(version).toBe("v1");
    expect(calls).toHaveLength(1);
    expect(calls[0].scope).toBe("open-swe");
    expect(calls[0].kind).toBe("Agent");
    expect(calls[0].name).toBe("swe-agent");
  });
});

describe("Kernel.writeDocument delegation", () => {
  test("writeDocument delegates to saveDocument and returns its version", async () => {
    const calls: Array<Record<string, unknown>> = [];
    const ws = {
      saveDocument: async (
        scope: string, kind: string, name: string, raw: Record<string, unknown>,
      ) => {
        calls.push({ method: "saveDocument", scope, kind, name, raw });
        return "stub-v1";
      },
      deleteDocument: async () => {},
      loadAll: () => [],
      loadBootstrapDocs: async () => [],
      resolveRef: () => "",
      loadLayer: () => [],
      supportsReaders: false,
    };
    const k = new Kernel();
    const { HelixExtension } = await import("../src/extensions/helix.js");
    k.load(new HelixExtension());
    k.writableSource(ws as any);

    const version = await k.writeDocument("m", "Agent", "alice", {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Agent",
      metadata: { name: "alice" },
      spec: { instruction: "x" },
    });
    expect(version).toBe("stub-v1");
    expect(calls).toHaveLength(1);
    expect(calls[0].kind).toBe("Agent");
  });
});

describe("Kernel.deleteDocument delegation", () => {
  test("deleteDocument delegates to port.deleteDocument", async () => {
    const calls: Array<{ scope: string; kind: string; name: string }> = [];
    const ws = {
      saveDocument: async () => "1",
      deleteDocument: async (scope: string, kind: string, name: string) => {
        calls.push({ scope, kind, name });
      },
      loadAll: () => [],
      loadBootstrapDocs: async () => [],
      resolveRef: () => "",
      loadLayer: () => [],
      supportsReaders: false,
    };
    const k = new Kernel();
    k.writableSource(ws as any);
    await k.deleteDocument("m", "Agent", "alice");
    expect(calls).toEqual([{ scope: "m", kind: "Agent", name: "alice" }]);
  });

  test("deleteDocument emits post_delete (not post_save)", async () => {
    const ws = {
      saveDocument: async () => "1",
      deleteDocument: async () => {},
      loadAll: () => [],
      loadBootstrapDocs: async () => [],
      resolveRef: () => "",
      loadLayer: () => [],
      supportsReaders: false,
    };
    const k = new Kernel();
    k.writableSource(ws as any);

    const saveEvents: any[] = [];
    const deleteEvents: any[] = [];
    k.on("post_save", (ctx) => saveEvents.push(ctx));
    k.on("post_delete", (ctx) => deleteEvents.push(ctx));

    await k.deleteDocument("m", "Agent", "alice");

    expect(saveEvents).toHaveLength(0);
    expect(deleteEvents).toHaveLength(1);
    expect(deleteEvents[0].scope).toBe("m");
    expect(deleteEvents[0].kind).toBe("Agent");
    expect(deleteEvents[0].name).toBe("alice");
  });
});
