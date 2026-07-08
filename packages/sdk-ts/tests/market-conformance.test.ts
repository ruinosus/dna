/**
 * Market-fidelity conformance — REAL market artifacts, no adaptation (F3).
 *
 * TS twin of packages/sdk-py/tests/test_market_conformance.py — see that
 * file's docstring for the thesis, the subjects (31 real marketplace Skills,
 * openai/codex AGENTS.md, real soulspec bundles) and the DOCUMENTED
 * NORMALIZATIONS N1–N4. Provenance: tests/market-fixtures/NOTICE.md.
 */
import { describe, test, expect } from "bun:test";
import { readFileSync } from "node:fs";
import { mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";
import yaml from "js-yaml";

import { createKernelWithBuiltins } from "../src/bootstrap";
import { FilesystemSource, FilesystemCache } from "../src/adapters/filesystem";
import { FilesystemBundleHandle } from "../src/kernel/bundle-handle";
import { SkillReader, SkillWriter } from "../src/extensions/agentskills";
import { nodeFS } from "../src/kernel/fs";

const REPO_ROOT = resolve(import.meta.dir, "../../..");
const MARKET_BASE = join(REPO_ROOT, "scopes/market-integration/.dna");
const FIXTURE_BASE = join(REPO_ROOT, "tests/market-fixtures/.dna");

// N1 shrink-only ratchet — twin of SKILL_FM_STYLE_ALLOWLIST (py).
const SKILL_FM_STYLE_ALLOWLIST = new Set([
  "brainstorming", "claude-api", "docx", "pptx", "xlsx",
]);

async function instance(base: string, scope: string) {
  const k = createKernelWithBuiltins();
  k.source(new FilesystemSource(base));
  k.cache(new FilesystemCache(base));
  const mi = await k.instance(scope);
  return { k, mi };
}

function emittedFiles(k: any, scope: string, doc: any): Record<string, string> {
  const payload = k.serializeDocument(scope, doc.kind, doc.name, doc.raw);
  const out: Record<string, string> = {};
  for (const f of payload.files) out[f.relativePath] = f.content;
  return out;
}

function splitFrontmatter(text: string): [Record<string, unknown>, string] {
  const m = text.match(/^---\n([\s\S]*?)---\n?([\s\S]*)$/);
  expect(m).toBeTruthy();
  return [(yaml.load(m![1]) ?? {}) as Record<string, unknown>, m![2]];
}

describe("real marketplace Skills (agentskills.io/v1)", () => {
  test("scan finds the real skills, typed, owner namespace untouched", async () => {
    const { mi } = await instance(MARKET_BASE, "market-demo");
    const skills = mi.documents.filter((d) => d.kind === "Skill");
    const names = new Set(skills.map((s: any) => s.name));
    expect(skills.length).toBeGreaterThanOrEqual(3);
    for (const n of ["xlsx", "docx", "pdf", "pptx"]) expect(names.has(n)).toBe(true);
    for (const s of skills) {
      expect(s.kind).toBe("Skill");
      expect((s.raw as any).apiVersion).toBe("agentskills.io/v1");
      expect(s.typed).toBeTruthy();
      expect(((s.spec as any).instruction as string).length).toBeGreaterThan(50);
    }
  });

  test("write round-trip is byte-identical (N1 allowlist excepted)", async () => {
    const { k, mi } = await instance(MARKET_BASE, "market-demo");
    const scopeDir = join(MARKET_BASE, "market-demo");
    let identical = 0;
    let fmStyle = 0;
    for (const s of mi.documents.filter((d) => d.kind === "Skill")) {
      const files = emittedFiles(k, "market-demo", s);
      expect(files[`skills/${s.name}/SKILL.md`]).toBeDefined();
      for (const [rel, content] of Object.entries(files)) {
        const disk = readFileSync(join(scopeDir, rel), "utf-8");
        if (disk === content) { identical++; continue; }
        expect(rel).toBe(`skills/${s.name}/SKILL.md`);
        expect(SKILL_FM_STYLE_ALLOWLIST.has(s.name)).toBe(true);
        fmStyle++;
      }
    }
    expect(identical).toBeGreaterThanOrEqual(350);
    expect(fmStyle).toBeLessThanOrEqual(SKILL_FM_STYLE_ALLOWLIST.size);
  });

  test("N1 deviations are confined to frontmatter STYLE", async () => {
    const { k, mi } = await instance(MARKET_BASE, "market-demo");
    const scopeDir = join(MARKET_BASE, "market-demo");
    for (const name of SKILL_FM_STYLE_ALLOWLIST) {
      const doc = (mi.documents.find((d) => d.kind === "Skill" && d.name === name) ?? null)!;
      const emitted = emittedFiles(k, "market-demo", doc)[`skills/${name}/SKILL.md`];
      const disk = readFileSync(join(scopeDir, "skills", name, "SKILL.md"), "utf-8");
      const [fmE, bodyE] = splitFrontmatter(emitted);
      const [fmD, bodyD] = splitFrontmatter(disk);
      expect(fmE).toEqual(fmD);
      expect(bodyE).toBe(bodyD);
    }
  });

  test("round-trip is idempotent (write → read → write fixpoint)", async () => {
    const { mi } = await instance(MARKET_BASE, "market-demo");
    const reader = new SkillReader(nodeFS);
    const writer = new SkillWriter(nodeFS);
    const subjects = [...SKILL_FM_STYLE_ALLOWLIST, "algorithmic-art"];
    for (const name of subjects) {
      const doc = (mi.documents.find((d) => d.kind === "Skill" && d.name === name) ?? null)!;
      const files1: Record<string, string> = {};
      for (const f of writer.serialize(doc.raw as Record<string, unknown>)) {
        files1[f.relativePath] = f.content ?? "";
      }
      const bundleDir = join(tmpdir(), `dna-conformance-${process.pid}`, name);
      for (const [rel, content] of Object.entries(files1)) {
        const p = join(bundleDir, rel);
        mkdirSync(dirname(p), { recursive: true });
        writeFileSync(p, content);
      }
      const raw2 = reader.read(new FilesystemBundleHandle(bundleDir));
      const files2: Record<string, string> = {};
      for (const f of writer.serialize(raw2)) files2[f.relativePath] = f.content ?? "";
      expect(files2).toEqual(files1);
    }
  });
});

describe("real AGENTS.md — openai/codex (agents.md/v1)", () => {
  test("scope-root AGENTS.md scans, types, and round-trips byte-identical", async () => {
    const { k, mi } = await instance(FIXTURE_BASE, "market-conformance");
    const doc = (mi.documents.find((d) => d.kind === "AgentDefinition" && d.name === "market-conformance") ?? null);
    expect(doc).toBeTruthy();
    expect((doc!.raw as any).apiVersion).toBe("agents.md/v1");
    expect(doc!.typed).toBeTruthy();
    expect((doc!.spec as any).content as string).toContain("codex-rs");
    const emitted = emittedFiles(k, "market-conformance", doc)["AGENTS.md"];
    const disk = readFileSync(join(FIXTURE_BASE, "market-conformance/AGENTS.md"), "utf-8");
    expect(emitted).toBe(disk);
  });

  test("market-demo scope-root AGENTS.md round-trips too", async () => {
    const { k, mi } = await instance(MARKET_BASE, "market-demo");
    const doc = (mi.documents.find((d) => d.kind === "AgentDefinition" && d.name === "market-demo") ?? null);
    expect(doc).toBeTruthy();
    const emitted = emittedFiles(k, "market-demo", doc)["AGENTS.md"];
    const disk = readFileSync(join(MARKET_BASE, "market-demo/AGENTS.md"), "utf-8");
    expect(emitted).toBe(disk);
  });
});

describe("real Souls — soulspec.org/v1", () => {
  test("starter bundle (standard owner's templates) scans typed", async () => {
    // NOTE: the TYPED SoulSpec view is canonical (soul/style/agents/
    // soul_json) — identity_content/heartbeat_content travel on doc.raw
    // only (soulspec canonical refactor). The write path is raw-based.
    const { mi } = await instance(FIXTURE_BASE, "market-conformance");
    const soul = (mi.documents.find((d) => d.kind === "Soul" && d.name === "starter") ?? null);
    expect(soul).toBeTruthy();
    expect((soul!.raw as any).apiVersion).toBe("soulspec.org/v1");
    expect(soul!.typed).toBeTruthy();
    const base = join(FIXTURE_BASE, "market-conformance/souls/starter");
    const rawSpec = ((soul!.raw as any).spec ?? {}) as Record<string, string>;
    expect(rawSpec.identity_content).toBe(readFileSync(join(base, "IDENTITY.md"), "utf-8"));
    expect(rawSpec.heartbeat_content).toBe(readFileSync(join(base, "HEARTBEAT.md"), "utf-8"));
  });

  test("IDENTITY.md + HEARTBEAT.md round-trip byte-identical", async () => {
    const { k, mi } = await instance(FIXTURE_BASE, "market-conformance");
    const soul = (mi.documents.find((d) => d.kind === "Soul" && d.name === "starter") ?? null)!;
    const files = emittedFiles(k, "market-conformance", soul);
    const base = join(FIXTURE_BASE, "market-conformance/souls/starter");
    for (const fname of ["IDENTITY.md", "HEARTBEAT.md"]) {
      expect(files[`souls/starter/${fname}`]).toBe(readFileSync(join(base, fname), "utf-8"));
    }
  });

  test("SOUL.md normalization is confined (N1 + N2 + N4)", async () => {
    const { k, mi } = await instance(FIXTURE_BASE, "market-conformance");
    const soul = (mi.documents.find((d) => d.kind === "Soul" && d.name === "starter") ?? null)!;
    const emitted = emittedFiles(k, "market-conformance", soul)["souls/starter/SOUL.md"];
    const disk = readFileSync(
      join(FIXTURE_BASE, "market-conformance/souls/starter/SOUL.md"), "utf-8");
    const [fmE, bodyE] = splitFrontmatter(emitted);
    const [fmD, bodyD] = splitFrontmatter(disk);
    expect(fmE).toEqual({ ...fmD, name: "starter" }); // N2
    expect(bodyE).toBe(bodyD.replace(/^\n+/, "")); // N4
  });

  test("brad (real community persona) round-trips byte-identical", async () => {
    const { k, mi } = await instance(MARKET_BASE, "market-demo");
    const soul = (mi.documents.find((d) => d.kind === "Soul" && d.name === "brad") ?? null)!;
    const files = emittedFiles(k, "market-demo", soul);
    const base = join(MARKET_BASE, "market-demo/souls/brad");
    for (const fname of ["SOUL.md", "STYLE.md", "AGENTS.md"]) {
      expect(files[`souls/brad/${fname}`]).toBe(readFileSync(join(base, fname), "utf-8"));
    }
  });

  test("soul.json canonical re-emit (N3): content-equal, unicode kept", async () => {
    const { k, mi } = await instance(MARKET_BASE, "market-demo");
    const soul = (mi.documents.find((d) => d.kind === "Soul" && d.name === "brad") ?? null)!;
    const emitted = emittedFiles(k, "market-demo", soul)["souls/brad/soul.json"];
    const disk = readFileSync(join(MARKET_BASE, "market-demo/souls/brad/soul.json"), "utf-8");
    expect(JSON.parse(emitted)).toEqual(JSON.parse(disk));
    expect(emitted.includes("\\u")).toBe(false);
    expect(emitted).toBe(JSON.stringify(JSON.parse(disk), null, 2));
  });
});

describe("composition", () => {
  test("buildPrompt flattens the real SOUL.md", async () => {
    const { mi } = await instance(FIXTURE_BASE, "market-conformance");
    const prompt = await mi.buildPrompt({ agent: "conductor" });
    expect(prompt).toContain("You're not a chatbot");
    expect(prompt).toContain("conductor agent");
  });

  test("agents.md is a FULL prompt target — its prose renders", async () => {
    const { mi } = await instance(FIXTURE_BASE, "market-conformance");
    const prompt = await mi.buildPrompt({ agent: "market-conformance" });
    expect(prompt).toContain("codex-rs");
  });
});
