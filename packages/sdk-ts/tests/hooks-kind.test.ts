import { describe, expect, test } from "bun:test";
import { FilesystemBundleHandle } from "../src/kernel/bundle-handle.js";
import yaml from "js-yaml";
import { createKernelWithBuiltins } from "../src/bootstrap.js";
import { Kernel } from "../src/kernel/index.js";
import { HelixExtension } from "../src/extensions/helix.js";
import { AgentSkillsExtension } from "../src/extensions/agentskills.js";
import { SoulSpecExtension } from "../src/extensions/soulspec.js";
import { AgentsMdExtension } from "../src/extensions/agentsmd.js";
import { GuardrailExtension } from "../src/extensions/guardrails.js";
import { HookExtension } from "../src/extensions/hooks.js";
import { createMemoryFS } from "../src/kernel/fs.js";
import type { FSLike, SourcePort, CachePort } from "../src/index.js";

// ---------------------------------------------------------------------------
// In-memory source/cache helpers (same pattern as fslike-integration.test.ts)
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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Hook Kind", () => {
  test("HookExtension registers Hook kind", async () => {
    const k = createKernelWithBuiltins();
    let found = false;
    for (const kp of k._kinds.values()) {
      if (kp.kind === "Hook") { found = true; break; }
    }
    expect(found).toBe(true);
  });

  test("Hook kind has correct metadata", async () => {
    const k = createKernelWithBuiltins();
    const kp = k._kinds.get("github.com/ruinosus/dna/v1\0Hook");
    expect(kp).toBeDefined();
    expect(kp!.alias).toBe("helix-hook");
    expect(kp!.apiVersion).toBe("github.com/ruinosus/dna/v1");
    expect(kp!.isRoot).toBe(false);
    expect(kp!.isPromptTarget).toBe(false);
    expect(kp!.schema!()).toBeTruthy();
    expect(kp!.dependencies!()).toBeNull();
  });

  test("Hook inject_fields middleware modifies prompt context", async () => {
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
        "Hello {{environment}}",
      ].join("\n"),
      ".dna/test/hooks/inject-env/HOOK.md": [
        "---",
        "name: inject-env",
        "target: pre_build_prompt",
        "type: middleware",
        "action: inject_fields",
        "---",
        "",
        "environment: production",
        "team: backend",
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
    k.load(new HookExtension(fs));

    const mi = await k.instance("test");

    // Verify hook document was loaded
    const hooks = mi.all("Hook");
    expect(hooks.length).toBe(1);
    expect(hooks[0].name).toBe("inject-env");

    // Apply hooks and test prompt
    mi.applyHooks();
    const prompt = await mi.prompt.build();
    expect(prompt).toContain("production");
  });

  test("Hook log event fires on post_build_prompt", async () => {
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
        "Hello",
      ].join("\n"),
      ".dna/test/hooks/log-prompts/HOOK.md": [
        "---",
        "name: log-prompts",
        "target: post_build_prompt",
        "type: event",
        "action: log",
        "---",
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
    k.load(new HookExtension(fs));

    const mi = await k.instance("test");

    expect(mi.all("Hook").length).toBe(1);

    // Apply hooks
    mi.applyHooks();

    // Build prompt should not throw (log event fires silently)
    const prompt = await mi.prompt.build();
    expect(prompt.length).toBeGreaterThan(0);
  });

  test("Hook parse applies defaults when spec fields are missing", async () => {
    const k = createKernelWithBuiltins();
    const kp = k._kinds.get("github.com/ruinosus/dna/v1\0Hook")!;

    const raw = {
      apiVersion: "github.com/ruinosus/dna/v1" as const,
      kind: "Hook" as const,
      metadata: { name: "minimal-hook" },
      spec: { target: "pre_build_prompt" },
    };

    const typed = kp.parse(raw) as Record<string, unknown>;
    const spec = typed.spec as Record<string, unknown>;
    expect(spec.target).toBe("pre_build_prompt");
    expect(spec.type).toBe("middleware");
    expect(spec.action).toBe("inject_fields");
    expect(spec.fields).toEqual({});
    expect(spec.body).toBe("");
  });

  test("Hook summary returns target, type, and action", async () => {
    const k = createKernelWithBuiltins();
    const kp = k._kinds.get("github.com/ruinosus/dna/v1\0Hook")!;

    const sum = kp.summary!({
      spec: { target: "pre_build_prompt", type: "middleware", action: "inject_fields" },
    } as never);
    expect(sum).not.toBeNull();
    expect(sum!.target).toBe("pre_build_prompt");
    expect(sum!.type).toBe("middleware");
    expect(sum!.action).toBe("inject_fields");
  });

  test("Hook describe returns formatted string", async () => {
    const k = createKernelWithBuiltins();
    const kp = k._kinds.get("github.com/ruinosus/dna/v1\0Hook")!;

    const desc = kp.describe!({
      name: "my-hook",
      spec: { target: "pre_build_prompt", action: "inject_fields" },
    } as never);
    expect(desc).toContain("my-hook");
    expect(desc).toContain("pre_build_prompt");
    expect(desc).toContain("inject_fields");
  });
});
