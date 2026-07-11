import { describe, test, expect } from "bun:test";
import { FilesystemBundleHandle } from "../src/kernel/bundle-handle.js";
import { mkdtempSync, rmSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Kernel } from "../src/kernel/index.js";
import { SdlcExtension } from "../src/extensions/sdlc.js";
import type { ReaderPort, WriterPort } from "../src/kernel/protocols.js";

// The HtmlArtifact reader/writer are not exported; grab them out of the kernel
// after loading SdlcExtension (matching the soulspec-roundtrip approach).
async function getRW(): Promise<{ reader: ReaderPort; writer: WriterPort }> {
  const k = new Kernel();
  k.load(new SdlcExtension());
  const readers = (k as unknown as { _readers: ReaderPort[] })._readers;
  const writers = (k as unknown as { _writers: WriterPort[] })._writers;
  const probe = mkdtempSync(join(tmpdir(), "ha-probe-"));
  try {
    const { writeFileSync } = await import("node:fs");
    writeFileSync(join(probe, "ARTIFACT.html"), "<p>probe</p>");
    let reader: ReaderPort | undefined;
    for (const r of readers) {
      if (await r.detect?.(new FilesystemBundleHandle(probe))) { reader = r; break; }
    }
    const writer = writers.find((w) => w.canWrite({ kind: "HtmlArtifact" }));
    if (!reader || !writer) throw new Error("HtmlArtifact reader/writer not found");
    return { reader, writer };
  } finally {
    rmSync(probe, { recursive: true, force: true });
  }
}

const HTML =
  `<!DOCTYPE html>\n` +
  `<html lang="pt-BR">\n` +
  `<head>\n` +
  `  <meta charset="utf-8">\n` +
  `  <title>DNA DX — Agora → Depois</title>\n` +
  `  <style>body { --bg: #f2f0ea; } /* quotes ' and " & < > */</style>\n` +
  `</head>\n` +
  `<body>\n` +
  `  <h1>Agora → Depois</h1>\n` +
  `  <p>Acentuação: configuração, herança, funções.</p>\n` +
  `</body>\n` +
  `</html>\n`;

describe("HtmlArtifact reader + writer round-trip", () => {
  test("ARTIFACT.html is byte-faithful (no frontmatter, no re-escaping)", async () => {
    const { writer } = await getRW();
    const tmp = mkdtempSync(join(tmpdir(), "ha-bf-"));
    try {
      const dest = join(tmp, "ha-x");
      await writer.write(new FilesystemBundleHandle(dest), {
        apiVersion: "github.com/ruinosus/dna/sdlc/v1",
        kind: "HtmlArtifact",
        metadata: { name: "ha-x" },
        spec: { html: HTML },
      });
      const onDisk = readFileSync(join(dest, "ARTIFACT.html"), "utf-8");
      expect(onDisk).toBe(HTML);
      // No companion when there's no metadata.
      expect(existsSync(join(dest, "artifact.json"))).toBe(false);
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  test("html + artifact.json round-trip; description promoted to metadata", async () => {
    const { reader, writer } = await getRW();
    const tmp = mkdtempSync(join(tmpdir(), "ha-rt-"));
    try {
      const aj = {
        title: "DNA DX — Agora → Depois",
        description: "Antes/depois da DX do DNA.",
        source: "design doc do épico e-dna-dx",
        created_at: "2026-07-11T00:00:00+00:00",
      };
      const dest = join(tmp, "ha-e-dna-dx-design");
      await writer.write(new FilesystemBundleHandle(dest), {
        apiVersion: "github.com/ruinosus/dna/sdlc/v1",
        kind: "HtmlArtifact",
        metadata: { name: "ha-e-dna-dx-design" },
        spec: { html: HTML, artifact_json: aj },
      });

      const back = (await reader.read(new FilesystemBundleHandle(dest))) as {
        kind: string;
        metadata: Record<string, unknown>;
        spec: Record<string, unknown>;
      };
      expect(back.kind).toBe("HtmlArtifact");
      expect(back.metadata.name).toBe("ha-e-dna-dx-design");
      expect(back.metadata.description).toBe("Antes/depois da DX do DNA.");
      expect(back.spec.html).toBe(HTML);
      expect(back.spec.artifact_json).toEqual(aj);
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });
});
