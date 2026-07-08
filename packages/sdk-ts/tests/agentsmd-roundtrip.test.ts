import { describe, test, expect } from "bun:test";
import { FilesystemBundleHandle } from "../src/kernel/bundle-handle.js";
import { mkdirSync, writeFileSync, readFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { AgentsMdExtension, AgentDefinitionWriter } from "../src/extensions/agentsmd.js";
import { Kernel } from "../src/kernel/index.js";
import { nodeFS } from "../src/kernel/fs.js";
import type { ReaderPort } from "../src/kernel/protocols.js";

function getAgentsMdReader(): ReaderPort {
  // AgentDefinitionReader is not exported; grab it out of the kernel after
  // loading AgentsMdExtension. Match by detect() on a probe bundle that
  // contains an AGENTS.md but NOT a SOUL.md (so the soul reader ignores it).
  const k = new Kernel();
  k.load(new AgentsMdExtension());
  const readers = (k as unknown as { _readers: ReaderPort[] })._readers;
  const probe = mkdtempSync(join(tmpdir(), "agentsmd-probe-"));
  try {
    writeFileSync(join(probe, "AGENTS.md"), "probe body");
    for (const r of readers) {
      if (r.detect?.(new FilesystemBundleHandle(probe))) return r;
    }
    throw new Error("AgentDefinitionReader not found in kernel._readers");
  } finally {
    rmSync(probe, { recursive: true, force: true });
  }
}

describe("AgentDefinitionReader + AgentDefinitionWriter round-trip", () => {
  test("preserves extra frontmatter metadata (version, tags, owner)", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "agentsmd-rt-"));
    try {
      const bundle = join(tmp, "my-agent");
      mkdirSync(bundle);
      writeFileSync(
        join(bundle, "AGENTS.md"),
        [
          "---",
          "name: my-agent",
          'version: "1.2"',
          "tags:",
          "  - spec-driven",
          "  - internal",
          "owner: alice",
          "---",
          "agent body text",
        ].join("\n"),
      );

      const reader = getAgentsMdReader();
      const raw = reader.read(new FilesystemBundleHandle(bundle)) as {
        metadata: Record<string, unknown>;
        spec: Record<string, unknown>;
      };

      expect(raw.metadata.name).toBe("my-agent");
      expect(raw.metadata.version).toBe("1.2");
      expect(raw.metadata.tags).toEqual(["spec-driven", "internal"]);
      expect(raw.metadata.owner).toBe("alice");

      // Body preserved, WITHOUT frontmatter header
      const body = raw.spec.content as string;
      expect(body).toContain("agent body text");
      expect(body.split("\n")[0]).not.toBe("---");

      // Round-trip via AgentDefinitionWriter
      const dest = join(tmp, "dest");
      const writer = new AgentDefinitionWriter(nodeFS);
      writer.write(new FilesystemBundleHandle(dest), raw as unknown as Record<string, unknown>);

      const written = readFileSync(join(dest, "AGENTS.md"), "utf-8");
      expect(written.startsWith("---\n")).toBe(true);

      const raw2 = reader.read(new FilesystemBundleHandle(dest)) as {
        metadata: Record<string, unknown>;
        spec: Record<string, unknown>;
      };
      expect(raw2.metadata.version).toBe("1.2");
      expect(raw2.metadata.tags).toEqual(["spec-driven", "internal"]);
      expect(raw2.metadata.owner).toBe("alice");
      expect(raw2.spec.content).toContain("agent body text");
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  test("byte-compat: no frontmatter written when metadata only has name", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "agentsmd-plain-"));
    try {
      const dest = join(tmp, "plain");
      const raw = {
        apiVersion: "agents.md/v1",
        kind: "AgentDefinition",
        metadata: { name: "plain" },
        spec: { content: "just the body" },
      };
      new AgentDefinitionWriter(nodeFS).write(new FilesystemBundleHandle(dest), raw);
      const written = readFileSync(join(dest, "AGENTS.md"), "utf-8");
      expect(written).toBe("just the body");
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });
});
