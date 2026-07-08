import { describe, test, expect } from "bun:test";
import { FilesystemBundleHandle } from "../src/kernel/bundle-handle.js";
import { mkdirSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { AgentSkillsExtension, SkillWriter } from "../src/extensions/agentskills.js";
import { Kernel } from "../src/kernel/index.js";
import type { ReaderPort } from "../src/kernel/protocols.js";

function getSkillReader(): ReaderPort {
  // SkillReader is not exported; grab it out of the kernel after loading
  // AgentSkillsExtension. The reader for SKILL.md is the only one registered
  // by this extension, so matching by detect(SKILL.md bundle path) is stable.
  const k = new Kernel();
  k.load(new AgentSkillsExtension());
  const readers = (k as unknown as { _readers: ReaderPort[] })._readers;
  const probe = mkdtempSync(join(tmpdir(), "skill-probe-"));
  try {
    writeFileSync(join(probe, "SKILL.md"), "---\nname: probe\n---\nbody");
    for (const r of readers) {
      if (r.detect?.(new FilesystemBundleHandle(probe))) return r;
    }
    throw new Error("SkillReader not found in kernel._readers");
  } finally {
    rmSync(probe, { recursive: true, force: true });
  }
}

describe("SkillReader round-trip", () => {
  test("preserves extra metadata fields (tags, priority, owner)", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "skill-rt-"));
    try {
      const bundle = join(tmp, "my-skill");
      mkdirSync(bundle);
      writeFileSync(
        join(bundle, "SKILL.md"),
        [
          "---",
          "name: my-skill",
          "description: demo",
          "tags:",
          "  - one",
          "  - two",
          "priority: 7",
          "owner: alice",
          "---",
          "skill body",
        ].join("\n"),
      );

      const reader = getSkillReader();
      const raw = reader.read(new FilesystemBundleHandle(bundle)) as {
        metadata: Record<string, unknown>;
        spec: Record<string, unknown>;
      };

      expect(raw.metadata.name).toBe("my-skill");
      expect(raw.metadata.description).toBe("demo");
      expect(raw.metadata.tags).toEqual(["one", "two"]);
      expect(raw.metadata.priority).toBe(7);
      expect(raw.metadata.owner).toBe("alice");

      // Round-trip via SkillWriter.serialize — writer already preserves
      // extras (since 39663a2); reader must now do the same.
      const writer = new SkillWriter({} as never);
      const files = writer.serialize(raw as unknown as Record<string, unknown>);
      const skillMd = files.find(f => f.relativePath === "SKILL.md")!;
      expect(skillMd).toBeDefined();

      const dest = join(tmp, "dest");
      mkdirSync(dest);
      writeFileSync(join(dest, "SKILL.md"), skillMd.content);
      const raw2 = reader.read(new FilesystemBundleHandle(dest)) as { metadata: Record<string, unknown> };
      expect(raw2.metadata.tags).toEqual(["one", "two"]);
      expect(raw2.metadata.priority).toBe(7);
      expect(raw2.metadata.owner).toBe("alice");
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });
});
