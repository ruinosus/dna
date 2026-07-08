import { describe, expect, test } from "bun:test";
import { FilesystemBundleHandle } from "../src/kernel/bundle-handle.js";
import yaml from "js-yaml";
import { Kernel } from "../src/kernel/index.js";
import { HelixExtension } from "../src/extensions/helix.js";
import { AgentSkillsExtension } from "../src/extensions/agentskills.js";
import { SoulSpecExtension } from "../src/extensions/soulspec.js";
import { AgentsMdExtension } from "../src/extensions/agentsmd.js";
import { GuardrailExtension } from "../src/extensions/guardrails.js";
import { HookExtension } from "../src/extensions/hooks.js";
import { SafetyPolicyExtension } from "../src/extensions/safety.js";
import { createMemoryFS } from "../src/kernel/fs.js";
import type { FSLike, SourcePort, CachePort } from "../src/index.js";

// ---------------------------------------------------------------------------
// In-memory source/cache helpers (same pattern as hooks-kind.test.ts)
// ---------------------------------------------------------------------------

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
  return { has: () => false, store: () => {}, loadKey: () => [], loadAll: () => [] };
}

function buildKernel(fs: FSLike): Kernel {
  const k = new Kernel();
  k.source(createMemSource(fs, ".dna"));
  k.cache(createMemCache());
  k.fs(fs);
  k.load(new HelixExtension(fs));
  k.load(new AgentSkillsExtension(fs));
  k.load(new SoulSpecExtension(fs));
  k.load(new AgentsMdExtension(fs));
  k.load(new GuardrailExtension(fs));
  k.load(new HookExtension(fs));
  k.load(new SafetyPolicyExtension(fs));
  return k;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SafetyPolicy input enforcement", () => {
  test("masks CPF in prompt context", async () => {
    const fs = createMemoryFS({
      ".dna/test/manifest.yaml": [
        "apiVersion: github.com/ruinosus/dna/v1",
        "kind: Genome",
        "metadata:",
        "  name: test",
        "spec:",
        "  default_agent: agent-1",
      ].join("\n"),
      ".dna/test/agents/agent-1/AGENT.md": [
        "---",
        "name: agent-1",
        "---",
        "",
        "User CPF is {{user_cpf}}",
      ].join("\n"),
      ".dna/test/safety/pii-br/SAFETYPOLICY.md": [
        "---",
        "name: pii-br",
        "scope: input",
        "action: mask",
        "severity: error",
        "---",
        "",
        "- type: pii",
        "  entities:",
        "    - cpf",
        "    - email",
      ].join("\n"),
    });

    const k = buildKernel(fs);
    const mi = await k.instance("test");
    mi.applyHooks();

    const prompt = await mi.prompt.build({ context: { user_cpf: "529.982.247-25" } });
    expect(prompt).not.toContain("529.982.247-25");
  });

  test("masks email in prompt context", async () => {
    const fs = createMemoryFS({
      ".dna/test/manifest.yaml": [
        "apiVersion: github.com/ruinosus/dna/v1",
        "kind: Genome",
        "metadata:",
        "  name: test",
        "spec:",
        "  default_agent: agent-1",
      ].join("\n"),
      ".dna/test/agents/agent-1/AGENT.md": [
        "---",
        "name: agent-1",
        "---",
        "",
        "Contact: {{email}}",
      ].join("\n"),
      ".dna/test/safety/pii-br/SAFETYPOLICY.md": [
        "---",
        "name: pii-br",
        "scope: both",
        "action: mask",
        "severity: error",
        "---",
        "",
        "- type: pii",
        "  entities:",
        "    - email",
      ].join("\n"),
    });

    const k = buildKernel(fs);
    const mi = await k.instance("test");
    mi.applyHooks();

    const prompt = await mi.prompt.build({ context: { email: "joao@example.com" } });
    expect(prompt).not.toContain("joao@example.com");
    expect(prompt).toContain("***@");
  });

  test("output-only scope does not mask input", async () => {
    const fs = createMemoryFS({
      ".dna/test/manifest.yaml": [
        "apiVersion: github.com/ruinosus/dna/v1",
        "kind: Genome",
        "metadata:",
        "  name: test",
        "spec:",
        "  default_agent: agent-1",
      ].join("\n"),
      ".dna/test/agents/agent-1/AGENT.md": [
        "---",
        "name: agent-1",
        "---",
        "",
        "CPF: {{cpf}}",
      ].join("\n"),
      ".dna/test/safety/output-only/SAFETYPOLICY.md": [
        "---",
        "name: output-only",
        "scope: output",
        "action: mask",
        "severity: error",
        "---",
        "",
        "- type: pii",
        "  entities:",
        "    - cpf",
      ].join("\n"),
    });

    const k = buildKernel(fs);
    const mi = await k.instance("test");
    mi.applyHooks();

    const prompt = await mi.prompt.build({ context: { cpf: "529.982.247-25" } });
    expect(prompt).toContain("529.982.247-25");
  });

  test("SafetyPolicy documents appear in all()", async () => {
    const fs = createMemoryFS({
      ".dna/test/manifest.yaml": [
        "apiVersion: github.com/ruinosus/dna/v1",
        "kind: Genome",
        "metadata:",
        "  name: test",
        "spec: {}",
      ].join("\n"),
      ".dna/test/safety/pii-br/SAFETYPOLICY.md": [
        "---",
        "name: pii-br",
        "scope: both",
        "action: mask",
        "severity: error",
        "---",
        "",
        "- type: pii",
        "  entities:",
        "    - cpf",
      ].join("\n"),
    });

    const k = buildKernel(fs);
    const mi = await k.instance("test");

    const policies = mi.documents.filter((d) => d.kind === "SafetyPolicy");
    expect(policies.length).toBe(1);
    expect(policies[0].name).toBe("pii-br");
    expect((policies[0].spec as any).scope).toBe("both");
    expect((policies[0].spec as any).action).toBe("mask");
  });
});
