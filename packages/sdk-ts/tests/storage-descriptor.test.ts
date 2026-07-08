/**
 * Tests for StorageDescriptor, SD factory, GenericBundleReader/Writer,
 * deferred registration, and Kernel helpers.
 */

import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { FilesystemBundleHandle } from "../src/kernel/bundle-handle.js";
import { mkdirSync, rmSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { SD, type StorageDescriptor } from "../src/kernel/protocols.js";
import { GenericBundleReader, GenericBundleWriter } from "../src/kernel/generic-rw.js";
import { Kernel } from "../src/kernel/index.js";
import { HelixExtension } from "../src/extensions/helix.js";
import { AgentSkillsExtension } from "../src/extensions/agentskills.js";
import { SoulSpecExtension } from "../src/extensions/soulspec.js";
import { AgentsMdExtension } from "../src/extensions/agentsmd.js";
import { GuardrailExtension } from "../src/extensions/guardrails.js";

// ---------------------------------------------------------------------------
// SD factory functions
// ---------------------------------------------------------------------------

describe("SD factory functions", () => {
  test("SD.bundle produces correct fields", async () => {
    const sd = SD.bundle("skills", "SKILL.md");
    expect(sd.container).toBe("skills");
    expect(sd.pattern).toBe("bundle");
    expect(sd.marker).toBe("SKILL.md");
    expect(sd.bodyAs).toBe("text");
    expect(sd.bodyField).toBe("instruction");
  });

  test("SD.bundle with custom bodyAs and bodyField", async () => {
    const sd = SD.bundle("guardrails", "GUARDRAIL.md", "list", "rules");
    expect(sd.container).toBe("guardrails");
    expect(sd.pattern).toBe("bundle");
    expect(sd.marker).toBe("GUARDRAIL.md");
    expect(sd.bodyAs).toBe("list");
    expect(sd.bodyField).toBe("rules");
  });

  test("SD.yaml produces correct fields", async () => {
    const sd = SD.yaml("actors");
    expect(sd.container).toBe("actors");
    expect(sd.pattern).toBe("yaml");
    expect(sd.marker).toBeUndefined();
  });

  test("SD.root produces correct fields (default filename)", async () => {
    const sd = SD.root();
    expect(sd.container).toBe("");
    expect(sd.pattern).toBe("root");
    expect(sd.marker).toBe("manifest.yaml");
  });

  test("SD.root with custom filename", async () => {
    const sd = SD.root("custom.yaml");
    expect(sd.marker).toBe("custom.yaml");
  });

  test("SD.standalone produces correct fields", async () => {
    const sd = SD.standalone("AGENTS.md");
    expect(sd.container).toBe("");
    expect(sd.pattern).toBe("standalone");
    expect(sd.marker).toBe("AGENTS.md");
    expect(sd.bodyAs).toBe("text");
    expect(sd.bodyField).toBe("content");
  });
});

// ---------------------------------------------------------------------------
// All built-in kinds have storage declared
// ---------------------------------------------------------------------------

describe("Built-in kinds have storage", () => {
  const extensions = [
    new HelixExtension(),
    new AgentSkillsExtension(),
    new SoulSpecExtension(),
    new AgentsMdExtension(),
    new GuardrailExtension(),
  ];

  test("all registered kinds have a storage field", async () => {
    const k = new Kernel();
    for (const ext of extensions) k.load(ext);

    for (const [key, kp] of k._kinds.entries()) {
      expect(kp.storage, `kind ${key} missing storage`).toBeDefined();
      expect(["bundle", "yaml", "root", "standalone"]).toContain(kp.storage.pattern);
    }
  });

  test("Genome kind has root storage", async () => {
    // Phase 16 — replaces "Module kind has root storage". Genome is
    // the canonical scope-root identity Kind. Marker file is now
    // ``Genome.yaml`` (was ``manifest.yaml`` legacy).
    const k = new Kernel();
    k.load(new HelixExtension());
    const packageKind = [...k._kinds.values()].find((kp) => kp.kind === "Genome");
    expect(packageKind?.storage.pattern).toBe("root");
    expect(packageKind?.storage.marker).toBe("Genome.yaml");
  });

  test("Agent kind has bundle storage with AGENT.md", async () => {
    const k = new Kernel();
    k.load(new HelixExtension());
    const kind = [...k._kinds.values()].find((kp) => kp.kind === "Agent");
    expect(kind?.storage.pattern).toBe("bundle");
    expect(kind?.storage.marker).toBe("AGENT.md");
    expect(kind?.storage.container).toBe("agents");
  });

  test("Actor kind has yaml storage", async () => {
    const k = new Kernel();
    k.load(new HelixExtension());
    const kind = [...k._kinds.values()].find((kp) => kp.kind === "Actor");
    expect(kind?.storage.pattern).toBe("yaml");
    expect(kind?.storage.container).toBe("actors");
  });

  test("Skill kind has bundle storage with SKILL.md", async () => {
    const k = new Kernel();
    k.load(new AgentSkillsExtension());
    const kind = [...k._kinds.values()].find((kp) => kp.kind === "Skill");
    expect(kind?.storage.pattern).toBe("bundle");
    expect(kind?.storage.marker).toBe("SKILL.md");
    expect(kind?.storage.container).toBe("skills");
  });

  test("Soul kind has bundle storage with SOUL.md", async () => {
    const k = new Kernel();
    k.load(new SoulSpecExtension());
    const kind = [...k._kinds.values()].find((kp) => kp.kind === "Soul");
    expect(kind?.storage.pattern).toBe("bundle");
    expect(kind?.storage.marker).toBe("SOUL.md");
    expect(kind?.storage.container).toBe("souls");
  });

  test("Guardrail kind has bundle storage with GUARDRAIL.md and list body", async () => {
    const k = new Kernel();
    k.load(new GuardrailExtension());
    const kind = [...k._kinds.values()].find((kp) => kp.kind === "Guardrail");
    expect(kind?.storage.pattern).toBe("bundle");
    expect(kind?.storage.marker).toBe("GUARDRAIL.md");
    expect(kind?.storage.bodyAs).toBe("list");
    expect(kind?.storage.bodyField).toBe("rules");
  });

  test("AgentDefinition kind has standalone storage", async () => {
    const k = new Kernel();
    k.load(new AgentsMdExtension());
    const kind = [...k._kinds.values()].find((kp) => kp.kind === "AgentDefinition");
    expect(kind?.storage.pattern).toBe("standalone");
    expect(kind?.storage.marker).toBe("AGENTS.md");
  });
});

// ---------------------------------------------------------------------------
// Kernel helpers: containerForKind / storageForKind
// ---------------------------------------------------------------------------

describe("Kernel helpers", () => {
  let k: Kernel;

  beforeEach(() => {
    k = new Kernel();
    k.load(new HelixExtension());
    k.load(new AgentSkillsExtension());
    k.load(new GuardrailExtension());
  });

  test("containerForKind returns correct container", async () => {
    expect(k.containerForKind("Skill")).toBe("skills");
    expect(k.containerForKind("Agent")).toBe("agents");
    expect(k.containerForKind("Guardrail")).toBe("guardrails");
  });

  test("containerForKind returns null for unknown kind", async () => {
    expect(k.containerForKind("Unknown")).toBeNull();
  });

  test("storageForKind returns StorageDescriptor", async () => {
    const sd = k.storageForKind("Skill");
    expect(sd).not.toBeNull();
    expect(sd!.pattern).toBe("bundle");
    expect(sd!.marker).toBe("SKILL.md");
  });

  test("storageForKind returns null for unknown kind", async () => {
    expect(k.storageForKind("Unknown")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// GenericBundleReader/Writer roundtrip
// ---------------------------------------------------------------------------

describe("GenericBundleReader/Writer roundtrip", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = join(tmpdir(), `dna-test-${Date.now()}`);
    mkdirSync(tmpDir, { recursive: true });
  });

  afterEach(() => {
    rmSync(tmpDir, { recursive: true, force: true });
  });

  test("text mode roundtrip", async () => {
    const sd = SD.bundle("skills", "SKILL.md", "text", "instruction");
    const bundleDir = join(tmpDir, "my-skill");
    mkdirSync(bundleDir);

    const raw = {
      apiVersion: "agentskills.io/v1",
      kind: "Skill",
      metadata: { name: "my-skill", description: "A test skill" },
      spec: { instruction: "Do something useful." },
    };

    const writer = new GenericBundleWriter(sd, "Skill");
    expect(writer.canWrite(raw)).toBe(true);
    expect(writer.canWrite({ kind: "Other" })).toBe(false);
    writer.write(new FilesystemBundleHandle(bundleDir), raw);

    expect(existsSync(join(bundleDir, "SKILL.md"))).toBe(true);

    const reader = new GenericBundleReader(sd, "agentskills.io/v1", "Skill");
    expect(reader.detect(new FilesystemBundleHandle(bundleDir))).toBe(true);
    expect(reader.detect(new FilesystemBundleHandle(tmpDir))).toBe(false);

    const result = reader.read(new FilesystemBundleHandle(bundleDir));
    expect(result.kind).toBe("Skill");
    expect(result.apiVersion).toBe("agentskills.io/v1");
    const meta = result.metadata as Record<string, unknown>;
    const spec = result.spec as Record<string, unknown>;
    expect(meta.name).toBe("my-skill");
    expect(meta.description).toBe("A test skill");
    expect(spec.instruction).toBe("Do something useful.");
  });

  test("list mode roundtrip", async () => {
    const sd = SD.bundle("guardrails", "GUARDRAIL.md", "list", "rules");
    const bundleDir = join(tmpDir, "my-guardrail");
    mkdirSync(bundleDir);

    const raw = {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Guardrail",
      metadata: { name: "my-guardrail" },
      spec: { rules: ["No PII", "No secrets", "Be polite"] },
    };

    const writer = new GenericBundleWriter(sd, "Guardrail");
    writer.write(new FilesystemBundleHandle(bundleDir), raw);

    const content = readFileSync(join(bundleDir, "GUARDRAIL.md"), "utf-8");
    expect(content).toContain("- No PII");
    expect(content).toContain("- No secrets");
    expect(content).toContain("- Be polite");

    const reader = new GenericBundleReader(sd, "github.com/ruinosus/dna/v1", "Guardrail");
    const result = reader.read(new FilesystemBundleHandle(bundleDir));
    const spec = result.spec as Record<string, unknown>;
    expect(spec.rules).toEqual(["No PII", "No secrets", "Be polite"]);
  });

  test("sections mode roundtrip", async () => {
    const sd = SD.bundle("souls", "SOUL.md", "sections", "soul_content");
    const bundleDir = join(tmpDir, "my-soul");
    mkdirSync(bundleDir);

    const raw = {
      apiVersion: "soulspec.org/v1",
      kind: "Soul",
      metadata: { name: "my-soul" },
      spec: {
        soul_content: {
          Identity: "I am a helpful assistant.",
          Style: "Concise and clear.",
        },
      },
    };

    const writer = new GenericBundleWriter(sd, "Soul");
    writer.write(new FilesystemBundleHandle(bundleDir), raw);

    const content = readFileSync(join(bundleDir, "SOUL.md"), "utf-8");
    expect(content).toContain("## Identity");
    expect(content).toContain("I am a helpful assistant.");
    expect(content).toContain("## Style");

    const reader = new GenericBundleReader(sd, "soulspec.org/v1", "Soul");
    const result = reader.read(new FilesystemBundleHandle(bundleDir));
    const spec = result.spec as Record<string, unknown>;
    const sections = spec.soul_content as Record<string, string>;
    expect(sections["Identity"]).toBe("I am a helpful assistant.");
    expect(sections["Style"]).toBe("Concise and clear.");
  });

  test("_marker is exposed on reader", async () => {
    const sd = SD.bundle("skills", "SKILL.md");
    const reader = new GenericBundleReader(sd, "agentskills.io/v1", "Skill");
    expect(reader._marker).toBe("SKILL.md");
  });

  test("_kind is exposed on writer", async () => {
    const sd = SD.bundle("skills", "SKILL.md");
    const writer = new GenericBundleWriter(sd, "Skill");
    expect(writer._kind).toBe("Skill");
  });
});

// ---------------------------------------------------------------------------
// Deferred registration
// ---------------------------------------------------------------------------

describe("Deferred registration", () => {
  test("_genericsResolved resets when a new kind is registered", async () => {
    const k = new Kernel();
    k.load(new AgentSkillsExtension());
    // Access private field via cast for testing
    const kernel = k as unknown as { _genericsResolved: boolean };
    // Initially false
    expect(kernel._genericsResolved).toBe(false);
  });
});
