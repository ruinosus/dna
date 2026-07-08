import { describe, it, expect } from "bun:test";
import { FilesystemBundleHandle } from "../src/kernel/bundle-handle.js";
import yaml from "js-yaml";
import {
  Kernel,
  HelixExtension,
  AgentSkillsExtension,
  SoulSpecExtension,
  AgentsMdExtension,
  GuardrailExtension,
  createMemoryFS,
} from "../src/index.js";
import type { FSLike, SourcePort, CachePort, ManifestInstance } from "../src/index.js";

function createMemSource(fs: FSLike, baseDir: string): SourcePort {
  return {
    supportsReaders: true,
    async loadBootstrapDocs(scope: string) {
      const m = yaml.load(fs.readFile(`${baseDir}/${scope}/manifest.yaml`)) as Record<string, unknown>;
      return [m];
    },
    loadAll(scope: string, readers: any[] = []) {
      const docs: Record<string, unknown>[] = [];
      const scopeDir = `${baseDir}/${scope}`;
      for (const entry of fs.readDir(scopeDir)) {
        const full = `${scopeDir}/${entry}`;
        if (fs.isFile(full) && (entry.endsWith(".yaml") || entry.endsWith(".yml"))) {
          const content = yaml.load(fs.readFile(full)) as Record<string, unknown>;
          if (content && typeof content === "object" && "kind" in content) docs.push(content);
        }
      }
      for (const entry of fs.readDir(scopeDir)) {
        const full = `${scopeDir}/${entry}`;
        if (!fs.isDirectory(full) || entry === "layers") continue;
        for (const sub of fs.readDir(full)) {
          const subFull = `${full}/${sub}`;
          if (!fs.isDirectory(subFull)) continue;
          for (const reader of readers) {
            try {
              if (reader.detect(new FilesystemBundleHandle(subFull))) {
                const doc = reader.read(new FilesystemBundleHandle(subFull));
                if (doc && "kind" in doc) docs.push(doc);
                break;
              }
            } catch {}
          }
        }
      }
      return docs;
    },
    resolveRef: () => "",
    loadLayer: () => [],
  };
}

function createMemCache(): CachePort {
  return {
    has: () => false,
    store: () => {},
    loadKey: () => [],
    loadAll: () => [],
  };
}

async function buildMinimalMi(): Promise<ManifestInstance> {
  const fs = createMemoryFS({
    ".dna/demo/manifest.yaml": [
      "apiVersion: github.com/ruinosus/dna/v1",
      "kind: Module",
      "metadata:",
      "  name: demo",
      "spec:",
      "  default_agent: foo",
    ].join("\n"),
    ".dna/demo/agents/foo/AGENT.md": [
      "---",
      "name: foo",
      "description: foo agent",
      "model: gpt-4o",
      "soul: my-soul",
      "skills:",
      "  - a",
      "  - b",
      "---",
      "",
      "You are foo.",
    ].join("\n"),
  });

  const k = new Kernel();
  k.source(createMemSource(fs, ".dna"));
  k.cache(createMemCache());
  k.fs(fs);
  k.load(new HelixExtension(fs));
  k.load(new AgentSkillsExtension(fs));
  k.load(new SoulSpecExtension(fs));
  k.load(new AgentsMdExtension(fs));
  k.load(new GuardrailExtension(fs));
  return k.instance("demo");
}

describe("ManifestInstance.readSpec sugar", () => {
  it("reads a spec field by (kind, name, field)", async () => {
    const mi = await buildMinimalMi();
    expect(mi.readSpec("Agent", "foo", "soul")).toBe("my-soul");
    expect(mi.readSpec("Agent", "foo", "missing")).toBeUndefined();
    expect(mi.readSpecStringArray("Agent", "foo", "skills")).toEqual(["a", "b"]);
  });
  it("throws on missing document", async () => {
    const mi = await buildMinimalMi();
    expect(() => mi.readSpec("Agent", "nope", "x")).toThrow(/not found/);
  });
});
