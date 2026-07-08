/**
 * Phase A + B tests — per-kind docs attribute + DOCS.md loader.
 */
import { describe, test, expect } from "bun:test";
import { mkdtempSync, writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { Kernel } from "../src/kernel/index.js";
import { HelixExtension } from "../src/extensions/helix.js";
import { AgentSkillsExtension } from "../src/extensions/agentskills.js";
import { SoulSpecExtension } from "../src/extensions/soulspec.js";
import { AgentsMdExtension } from "../src/extensions/agentsmd.js";
import { GuardrailExtension } from "../src/extensions/guardrails.js";
import { KindDefinitionExtension } from "../src/extensions/kinddef.js";

function _kernelWithAll(): Kernel {
  const k = new Kernel();
  k.load(new HelixExtension());
  k.load(new AgentSkillsExtension());
  k.load(new SoulSpecExtension());
  k.load(new AgentsMdExtension());
  k.load(new GuardrailExtension());
  k.load(new KindDefinitionExtension());
  return k;
}

describe("Phase A — docs attribute present on every built-in kind", () => {
  const expected = [
    "Genome",
    "Agent",
    "Actor",
    "UseCase",
    "Skill",
    "Soul",
    "AgentDefinition",
    "Guardrail",
    "KindDefinition",
  ];

  for (const kindName of expected) {
    test(`${kindName} exposes a non-empty docs attribute`, () => {
      const k = _kernelWithAll();
      const info = k.describeKind(kindName);
      expect(info).not.toBeNull();
      expect(typeof info!.docs).toBe("string");
      expect((info!.docs as string).length).toBeGreaterThan(20);
    });
  }
});

describe("Phase B — DOCS.md loader precedence", () => {
  test("describeKind returns prose from DOCS-<Kind>.md override", async () => {
    // Phase 16 — GenomeKind ships its own ``docs`` attribute; the TS
    // kernel uses that directly. Pin it to the inline string instead
    // of the (Py-only) DOCS-<Kind>.md loader output.
    const k = _kernelWithAll();
    const info = k.describeKind("Genome");
    expect(info).not.toBeNull();
    expect(info!.docs).toContain("scope-root identity");
  });

  test("single-kind extension picks up DOCS.md override", async () => {
    const k = _kernelWithAll();
    const info = k.describeKind("Soul");
    // DOCS.md for soulspec mentions soulspec.org
    expect(info!.docs).toContain("soulspec.org");
  });

  test("describeKind returns null for unknown kind", async () => {
    const k = _kernelWithAll();
    expect(k.describeKind("Nonexistent")).toBeNull();
  });
});
