import { describe, test, expect } from "bun:test";
import { FilesystemBundleHandle } from "../src/kernel/bundle-handle.js";
import { mkdirSync, writeFileSync, readFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { SoulSpecExtension, SoulWriter } from "../src/extensions/soulspec.js";
import { Kernel } from "../src/kernel/index.js";
import { nodeFS } from "../src/kernel/fs.js";
import type { ReaderPort } from "../src/kernel/protocols.js";

function getSoulReader(): ReaderPort {
  // SoulReader is not exported; grab it out of the kernel after loading
  // SoulSpecExtension. The reader for SOUL.md is the only one registered
  // by this extension, so matching by detect(SOUL.md bundle path) is stable.
  const k = new Kernel();
  k.load(new SoulSpecExtension());
  const readers = (k as unknown as { _readers: ReaderPort[] })._readers;
  const probe = mkdtempSync(join(tmpdir(), "soul-probe-"));
  try {
    writeFileSync(join(probe, "SOUL.md"), "probe body");
    for (const r of readers) {
      if (r.detect?.(new FilesystemBundleHandle(probe))) return r;
    }
    throw new Error("SoulReader not found in kernel._readers");
  } finally {
    rmSync(probe, { recursive: true, force: true });
  }
}

describe("SoulReader + SoulWriter round-trip", () => {
  test("preserves extra frontmatter metadata (specVersion, tags, owner)", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "soul-rt-"));
    try {
      const bundle = join(tmp, "my-soul");
      mkdirSync(bundle);
      writeFileSync(
        join(bundle, "SOUL.md"),
        [
          "---",
          "name: my-soul",
          'specVersion: "2.0"',
          "tags:",
          "  - reflective",
          "  - warm",
          "owner: team-talent",
          "---",
          "soul body text",
        ].join("\n"),
      );
      writeFileSync(join(bundle, "IDENTITY.md"), "I am an identity");
      writeFileSync(join(bundle, "HEARTBEAT.md"), "heartbeat");

      const reader = getSoulReader();
      const raw = reader.read(new FilesystemBundleHandle(bundle)) as {
        metadata: Record<string, unknown>;
        spec: Record<string, unknown>;
      };

      expect(raw.metadata.name).toBe("my-soul");
      expect(raw.metadata.specVersion).toBe("2.0");
      expect(raw.metadata.tags).toEqual(["reflective", "warm"]);
      expect(raw.metadata.owner).toBe("team-talent");

      // Body should NOT include the frontmatter
      const body = raw.spec.soul_content as string;
      expect(body).toContain("soul body text");
      expect(body.split("\n")[0]).not.toBe("---");

      // Round-trip via SoulWriter
      const dest = join(tmp, "dest");
      const writer = new SoulWriter(nodeFS);
      writer.write(new FilesystemBundleHandle(dest), raw as unknown as Record<string, unknown>);

      const writtenSoul = readFileSync(join(dest, "SOUL.md"), "utf-8");
      expect(writtenSoul.startsWith("---\n")).toBe(true);

      const raw2 = reader.read(new FilesystemBundleHandle(dest)) as {
        metadata: Record<string, unknown>;
        spec: Record<string, unknown>;
      };
      expect(raw2.metadata.specVersion).toBe("2.0");
      expect(raw2.metadata.tags).toEqual(["reflective", "warm"]);
      expect(raw2.metadata.owner).toBe("team-talent");
      expect(raw2.spec.soul_content).toContain("soul body text");
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  test("byte-compat: no frontmatter written when metadata only has name", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "soul-plain-"));
    try {
      const dest = join(tmp, "brad");
      const raw = {
        apiVersion: "soulspec.org/v1",
        kind: "Soul",
        metadata: { name: "brad" },
        spec: { soul_content: "I am Brad" },
      };
      new SoulWriter(nodeFS).write(new FilesystemBundleHandle(dest), raw);
      const written = readFileSync(join(dest, "SOUL.md"), "utf-8");
      // Plain body, no frontmatter — preserves fixture byte-compat
      expect(written).toBe("I am Brad");
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });
});
