/**
 * explainPrompt — per-section prompt provenance (s-dna-explain-provenance).
 *
 * TS twin of tests/test_explain_provenance.py. Proves: explain returns the
 * composed prompt PLUS a section→provenance map; the prompt is byte-identical
 * to buildPrompt (the byte-equal gate); each section is attributed to its
 * source artifact + hash + layer origin; a tenant overlay that wins a section
 * is flagged overriddenByTenant.
 */
import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import yaml from "js-yaml";

import { createKernelWithBuiltins } from "../src/bootstrap.js";
import { FilesystemSource } from "../src/adapters/filesystem/source.js";
import { FilesystemCache } from "../src/adapters/filesystem/cache.js";

function write(path: string, text: string): void {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, text, "utf-8");
}

function makeScope(root: string): string {
  const base = join(root, ".dna");
  const scope = join(base, "demo");
  write(join(scope, "Genome.yaml"), yaml.dump({
    apiVersion: "github.com/ruinosus/dna/v1",
    kind: "Genome",
    metadata: { name: "demo" },
    spec: { default_agent: "greeter" },
  }));
  write(join(scope, "agents", "greeter.yaml"), yaml.dump({
    apiVersion: "github.com/ruinosus/dna/v1",
    kind: "Agent",
    metadata: { name: "greeter" },
    spec: {
      instruction: "You greet users.",
      soul: "warm",
      skills: ["greeting"],
      guardrails: ["polite"],
    },
  }));
  write(join(scope, "souls", "warm", "SOUL.md"), "# Warm Soul\nBe kind and welcoming.");
  write(join(scope, "skills", "greeting", "SKILL.md"),
    "---\nname: greeting\n---\nBASE greeting procedure: say hello.");
  write(join(scope, "guardrails", "polite", "GUARDRAIL.md"),
    "---\nseverity: warn\nrules:\n  - Never insult the user\n---\n");
  // Tenant overlay: acme overrides the greeting skill.
  write(join(base, "tenants", "acme", "scopes", "demo", "skills", "greeting", "SKILL.md"),
    "---\nname: greeting\n---\nACME greeting procedure: welcome warmly to Acme.");
  return base;
}

function kernelFor(base: string) {
  const k = createKernelWithBuiltins();
  k.source(new FilesystemSource(base));
  k.cache(new FilesystemCache(base));
  return k;
}

describe("explainPrompt — per-section provenance", () => {
  let root: string;
  let base: string;

  beforeEach(() => {
    root = mkdtempSync(join(tmpdir(), "dna-explain-"));
    base = makeScope(root);
  });
  afterEach(() => rmSync(root, { recursive: true, force: true }));

  test("prompt is byte-identical to buildPrompt (byte-equal gate)", async () => {
    const mi = await kernelFor(base).instance("demo");
    const exp = await mi.explainPrompt({ agent: "greeter" });
    expect(exp.prompt).toBe(await mi.buildPrompt({ agent: "greeter" }));
  });

  test("sections cover all composition inputs, not tools/actors", async () => {
    const mi = await kernelFor(base).instance("demo");
    const exp = await mi.explainPrompt({ agent: "greeter" });
    const labels = exp.sections.map((s) => s.section);
    expect(labels).toContain("instruction");
    expect(labels).toContain("soul");
    expect(labels).toContain("skill:greeting");
    expect(labels).toContain("guardrail:polite");
    expect(labels.some((l) => l.startsWith("tool"))).toBe(false);
  });

  test("section carries source, hash, origin", async () => {
    const mi = await kernelFor(base).instance("demo");
    const exp = await mi.explainPrompt({ agent: "greeter" });
    const skill = exp.sections.find((s) => s.section === "skill:greeting")!;
    expect(skill.kind).toBe("Skill");
    expect(skill.source).toBe("skills/greeting/SKILL.md");
    expect(skill.hash).toMatch(/^[0-9a-f]{64}$/);
    expect(skill.origin).toBe("demo");
    expect(skill.overriddenByTenant).toBe(false);
  });

  test("tenant overlay is flagged overriddenByTenant", async () => {
    const k = kernelFor(base);
    // TS applies tenant overlays via explicit layers (no withTenant
    // auto-promotion — a documented Py↔TS instance-API difference).
    const mi = await k.instance("demo", { tenant: "acme" });
    const exp = await mi.explainPrompt({ agent: "greeter", tenant: "acme" });
    // Overlay body composed in; byte-equal gate still holds.
    expect(exp.prompt).toBe(await mi.buildPrompt({ agent: "greeter" }));
    expect(exp.prompt).toContain("ACME greeting procedure");
    expect(exp.prompt).not.toContain("BASE greeting procedure");
    const skill = exp.sections.find((s) => s.section === "skill:greeting")!;
    const soul = exp.sections.find((s) => s.section === "soul")!;
    expect(skill.overriddenByTenant).toBe(true);
    expect(soul.overriddenByTenant).toBe(false);
  });
});
