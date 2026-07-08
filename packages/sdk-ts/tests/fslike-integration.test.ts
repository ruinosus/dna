import { describe, test, expect } from "bun:test";
import { FilesystemBundleHandle } from "../src/kernel/bundle-handle.js";
import yaml from "js-yaml";
import { Kernel, HelixExtension, AgentSkillsExtension, SoulSpecExtension, AgentsMdExtension, GuardrailExtension, createMemoryFS } from "../src/index";
import type { FSLike, SourcePort, CachePort } from "../src/index";

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
      // Collect YAML docs
      for (const entry of fs.readDir(scopeDir)) {
        const full = `${scopeDir}/${entry}`;
        if (fs.isFile(full) && (entry.endsWith(".yaml") || entry.endsWith(".yml"))) {
          const content = yaml.load(fs.readFile(full)) as Record<string, unknown>;
          if (content && typeof content === "object" && "kind" in content) docs.push(content);
        }
      }
      // Use readers for bundle dirs
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

describe("FSLike integration — full kernel with in-memory FS", () => {
  test("loads skill, soul, agent, guardrail from memory", async () => {
    const fs = createMemoryFS({
      ".dna/demo/manifest.yaml": [
        "apiVersion: github.com/ruinosus/dna/v1",
        "kind: Genome",
        "metadata:",
        "  name: demo",
        "spec:",
        "  default_agent: swe",
      ].join("\n"),
      ".dna/demo/agents/swe/AGENT.md": [
        "---",
        "name: swe",
        "description: SWE agent",
        "model: gpt-4o",
        "soul: swe-soul",
        "skills:",
        "  - code-review",
        "guardrails:",
        "  - safe-output",
        "---",
        "",
        "You are a software engineer.",
      ].join("\n"),
      ".dna/demo/skills/code-review/SKILL.md": [
        "---",
        "name: code-review",
        "description: Reviews code",
        "---",
        "",
        "Review the code carefully.",
      ].join("\n"),
      ".dna/demo/souls/swe-soul/SOUL.md": "# SWE Soul\n\nYou think like an engineer.",
      ".dna/demo/guardrails/safe-output/GUARDRAIL.md": [
        "---",
        "name: safe-output",
        "severity: error",
        "---",
        "",
        "- Never output secrets",
        "- Never output PII",
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

    const mi = await k.instance("demo");

    expect(mi.documents.length).toBeGreaterThanOrEqual(4);
    expect(mi.root?.name).toBe("demo");

    const agent = (mi.documents.find((d) => d.kind === "Agent" && d.name === "swe") ?? null);
    expect(agent).not.toBeNull();
    expect(agent!.spec.instruction).toContain("software engineer");
    expect(agent!.spec.model).toBe("gpt-4o");

    const skill = (mi.documents.find((d) => d.kind === "Skill" && d.name === "code-review") ?? null);
    expect(skill).not.toBeNull();
    expect(skill!.spec.instruction).toContain("Review the code");

    const soul = (mi.documents.find((d) => d.kind === "Soul" && d.name === "swe-soul") ?? null);
    expect(soul).not.toBeNull();
    expect(soul!.spec.soul_content).toContain("engineer");

    const guardrail = (mi.documents.find((d) => d.kind === "Guardrail" && d.name === "safe-output") ?? null);
    expect(guardrail).not.toBeNull();
    expect(guardrail!.spec.rules).toContain("Never output secrets");
  });

  test("buildPrompt works with in-memory FS", async () => {
    const fs = createMemoryFS({
      ".dna/test/manifest.yaml": [
        "apiVersion: github.com/ruinosus/dna/v1",
        "kind: Genome",
        "metadata:",
        "  name: test",
        "spec:",
        "  default_agent: bot",
      ].join("\n"),
      ".dna/test/agents/bot/AGENT.md": [
        "---",
        "name: bot",
        "soul: bot-soul",
        "---",
        "",
        "You are helpful.",
      ].join("\n"),
      ".dna/test/souls/bot-soul/SOUL.md": "Be kind and concise.",
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

    const mi = await k.instance("test");
    const prompt = await mi.buildPrompt();
    expect(prompt).toContain("You are helpful");
    expect(prompt).toContain("Be kind and concise");
  });
});
