import { quickInstance, createKernelWithBuiltins } from "../src/bootstrap";
/**
 * v3 Integration tests — real open-swe fixture loaded via await quickInstance().
 */

import { describe, test, expect } from "bun:test";
import path from "node:path";
import { Kernel } from "../src/kernel/index.js";

// examples/ lives at repo root (v2/dna-sdk/examples/), not inside typescript/
const BASE_DIR = path.resolve(import.meta.dir, "../../../scopes/open-swe/.dna");

describe("v3 integration — open-swe fixture", () => {
  test("quick loads all kinds", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    expect(mi.root).not.toBeNull();
    expect(mi.root!.kind).toBe("Genome");
    expect(mi.root!.name).toBe("open-swe");
    expect(mi.documents.filter((d) => d.kind === "Skill").length).toBeGreaterThan(0);
    expect(mi.documents.filter((d) => d.kind === "Agent").length).toBeGreaterThan(0);
  });

  test("loads skills via SkillReader", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const skills = mi.documents.filter((d) => d.kind === "Skill");
    const names = skills.map((s) => s.name).sort();
    expect(names).toContain("pr-review");
    expect(names).toContain("branch-naming");
    expect(names).toContain("debug-prod");
  });

  test("loads souls via SoulReader", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const souls = mi.documents.filter((d) => d.kind === "Soul");
    expect(souls.length).toBeGreaterThan(0);
    expect(souls[0].name).toBe("swe-soul");
    // Verify soul_content was read
    const spec = souls[0].spec;
    expect(typeof spec.soul_content).toBe("string");
    expect((spec.soul_content as string).length).toBeGreaterThan(10);
  });

  test("loads agents from YAML", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const agents = mi.documents.filter((d) => d.kind === "Agent");
    const names = agents.map((a) => a.name).sort();
    expect(names).toContain("swe-agent");
    expect(names).toContain("reviewer-agent");
  });

  test("listKinds returns present kinds", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const kinds = mi.listKinds();
    // Phase 16 — examples migrated from Module to Genome as the
    // scope-root identity Kind.
    expect(kinds).toContain("Genome");
    expect(kinds).toContain("Skill");
    expect(kinds).toContain("Agent");
    expect(kinds).toContain("Soul");
  });

  test("defaultAgent returns swe-agent", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const agent = mi.defaultAgent();
    expect(agent).not.toBeNull();
    expect(agent!.name).toBe("swe-agent");
  });

  test("buildPrompt renders instruction content", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const agent = mi.defaultAgent();
    expect(agent).not.toBeNull();
    const prompt = await mi.buildPrompt({ agent: agent!.name });
    expect(prompt.length).toBeGreaterThan(50);
  });

  test("compositionResult validates refs", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const cr = mi.compositionResult;
    // swe-agent declares soul: swe-soul and skills: [pr-review, branch-naming, debug-prod]
    expect(cr.resolved.length).toBeGreaterThan(0);
  });

  test("generateLock produces SHA256 entries", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const lock = mi.generateLock();
    expect(lock.documents.length).toBeGreaterThan(0);
    for (const entry of lock.documents) {
      expect(entry.sha256).toMatch(/^[0-9a-f]{64}$/);
    }
  });

  test("get returns summary for all kinds", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const all = mi.get();
    expect(all.length).toBeGreaterThan(0);
    expect(all[0]).toHaveProperty("kind");
    expect(all[0]).toHaveProperty("name");
  });

  test("one returns specific document", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const skill = (mi.documents.find((d) => d.kind === "Skill" && d.name === "pr-review") ?? null);
    expect(skill).not.toBeNull();
    expect(skill!.kind).toBe("Skill");
    expect(skill!.apiVersion).toBe("agentskills.io/v1");
  });

  test("describe returns formatted output", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const desc = mi.describe("Genome", "open-swe");
    expect(desc).toContain("Name:");
    expect(desc).toContain("open-swe");
  });

  test("summary includes all kinds with counts", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const s = mi.summary();
    expect(s).toContain("Scope: open-swe");
    expect(s).toContain("Genome:");
    expect(s).toContain("Skill:");
  });

  test("skill has instruction from SKILL.md body", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const skill = (mi.documents.find((d) => d.kind === "Skill" && d.name === "pr-review") ?? null);
    expect(skill).not.toBeNull();
    const spec = skill!.spec;
    expect(typeof spec.instruction).toBe("string");
    expect((spec.instruction as string).length).toBeGreaterThan(0);
  });

  test("skill has references subdirectory loaded", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const skill = (mi.documents.find((d) => d.kind === "Skill" && d.name === "pr-review") ?? null);
    expect(skill).not.toBeNull();
    const spec = skill!.spec;
    // pr-review has a references/ subdirectory
    expect(spec.references).toBeDefined();
    expect(typeof spec.references).toBe("object");
  });

  test("auto creates kernel with extensions", async () => {
    const k = createKernelWithBuiltins();
    expect(k._kinds.size).toBeGreaterThan(0);
    // Should have Module, Agent, Actor, Skill, Soul, AgentDefinition
    expect(k._kinds.has("github.com/ruinosus/dna/v1\0Genome")).toBe(true);
    expect(k._kinds.has("agentskills.io/v1\0Skill")).toBe(true);
    expect(k._kinds.has("soulspec.org/v1\0Soul")).toBe(true);
    expect(k._kinds.has("agents.md/v1\0AgentDefinition")).toBe(true);
  });

  test("auto kernel can be used with manual source/cache", async () => {
    const k = createKernelWithBuiltins();
    // Import adapters at top level
    const { FilesystemSource } = require("../src/adapters/filesystem/source.js") as typeof import("../src/adapters/filesystem/source.js");
    const { FilesystemCache } = require("../src/adapters/filesystem/cache.js") as typeof import("../src/adapters/filesystem/cache.js");
    k.source(new FilesystemSource(BASE_DIR));
    k.cache(new FilesystemCache(BASE_DIR));
    const mi = await k.instance("open-swe");
    expect(mi.root).not.toBeNull();
  });
});
