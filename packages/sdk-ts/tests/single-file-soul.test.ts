/**
 * s-dx-single-file-soul — a Soul is authorable as a single SOUL.md.
 *
 * Twin of packages/sdk-py/tests/test_single_file_soul.py.
 *
 * DNA reads SOUL.md directly, so a Soul needs no soul.json manifest — a single
 * file is a first-class convenience. This suite LOCKS that contract and proves
 * the 2-file soulspec form is not regressed (soul.json preserved when present).
 */
import { describe, test, expect } from "bun:test";
import { FilesystemBundleHandle } from "../src/kernel/bundle-handle.js";
import { mkdirSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { SoulSpecExtension, SoulWriter } from "../src/extensions/soulspec.js";
import { Kernel } from "../src/kernel/index.js";
import { quickInstance } from "../src/bootstrap.js";
import { nodeFS } from "../src/kernel/fs.js";
import type { ReaderPort } from "../src/kernel/protocols.js";

function getSoulReader(): ReaderPort {
  const k = new Kernel();
  k.load(new SoulSpecExtension());
  const readers = (k as unknown as { _readers: ReaderPort[] })._readers;
  const probe = mkdtempSync(join(tmpdir(), "soul-probe-"));
  try {
    writeFileSync(join(probe, "SOUL.md"), "probe body");
    for (const r of readers) {
      if (r.detect?.(new FilesystemBundleHandle(probe))) return r;
    }
    throw new Error("SoulReader not found");
  } finally {
    rmSync(probe, { recursive: true, force: true });
  }
}

function emit(raw: Record<string, unknown>): Set<string> {
  return new Set(new SoulWriter(nodeFS).serialize(raw).map((f) => f.relativePath));
}

describe("s-dx-single-file-soul", () => {
  test("single SOUL.md, no frontmatter, no soul.json reads with inferred name", () => {
    const tmp = mkdtempSync(join(tmpdir(), "sfs-"));
    try {
      const bundle = join(tmp, "persona");
      mkdirSync(bundle);
      writeFileSync(join(bundle, "SOUL.md"), "# Persona\n\nCalm and precise.");
      const raw = getSoulReader().read(new FilesystemBundleHandle(bundle)) as {
        metadata: Record<string, unknown>;
        spec: Record<string, unknown>;
      };
      expect(raw.metadata.name).toBe("persona");
      expect(raw.spec.soul_content as string).toContain("Calm and precise.");
      expect(raw.spec.soul_json).toBeUndefined();
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  test("write path stays single-file — no phantom soul.json", () => {
    const tmp = mkdtempSync(join(tmpdir(), "sfs-w-"));
    try {
      const bundle = join(tmp, "p");
      mkdirSync(bundle);
      writeFileSync(join(bundle, "SOUL.md"), "# P\n\nBody.");
      const raw = getSoulReader().read(new FilesystemBundleHandle(bundle)) as Record<string, unknown>;
      expect(emit(raw)).toEqual(new Set(["SOUL.md"]));
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  test("2-file soulspec form is preserved (soul.json re-emitted)", () => {
    const tmp = mkdtempSync(join(tmpdir(), "sfs-2-"));
    try {
      const bundle = join(tmp, "brad");
      mkdirSync(bundle);
      writeFileSync(join(bundle, "SOUL.md"), "# Brad\n\nA persona.");
      writeFileSync(join(bundle, "soul.json"), JSON.stringify({ specVersion: "0.4", name: "brad" }));
      const raw = getSoulReader().read(new FilesystemBundleHandle(bundle)) as {
        spec: Record<string, unknown>;
      };
      expect((raw.spec.soul_json as Record<string, unknown>).specVersion).toBe("0.4");
      expect(emit(raw as Record<string, unknown>)).toEqual(new Set(["SOUL.md", "soul.json"]));
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  test("single-file soul composes into an agent prompt", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "sfs-c-"));
    try {
      const scope = "sfs";
      const root = join(tmp, scope);
      mkdirSync(join(root, "agents", "a1"), { recursive: true });
      mkdirSync(join(root, "souls", "s1"), { recursive: true });
      writeFileSync(
        join(root, "Genome.yaml"),
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\nmetadata:\n  name: sfs\nspec:\n  default_agent: a1\n",
      );
      writeFileSync(join(root, "agents", "a1", "AGENT.md"), "---\nname: a1\nsoul: s1\n---\n# A1\n\nDo the thing.");
      writeFileSync(join(root, "souls", "s1", "SOUL.md"), "# S1\n\nWarm and precise voice.");
      const mi = await quickInstance(scope, tmp);
      const prompt = await mi.buildPrompt({ agent: "a1" });
      expect(prompt).toContain("Warm and precise voice.");
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });
});
