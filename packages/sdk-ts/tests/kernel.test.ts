import { quickInstance, createKernelWithBuiltins } from "../src/bootstrap";
/**
 * v3 Kernel core tests — protocols, document, hooks, models, lock.
 */

import { describe, expect, test } from "bun:test";

import {
  LayerPolicy,
  type CompositionResult,
  isCompositionValid,
  ResolveError,
  ResolveNotFoundError,
  ResolveAuthError,
  ResolveNetworkError,
  type CacheItem,
  type ResolvedItem,
} from "../src/kernel/protocols.js";

import { Document } from "../src/kernel/document.js";

import { HookRegistry, type HookContext } from "../src/kernel/hooks.js";

import {
  GenomeSchema,
  SkillSchema,
  AgentSchema,
  SoulSchema,
  AgentDefinitionSchema,
  ActorSchema,
  MetadataSchema,
} from "../src/kernel/models.js";

import type { LockEntry, Lockfile } from "../src/kernel/lock.js";

// ---------------------------------------------------------------------------
// LayerPolicy
// ---------------------------------------------------------------------------

describe("LayerPolicy", () => {
  test("has three values", async () => {
    expect(LayerPolicy.OPEN).toBe("open");
    expect(LayerPolicy.RESTRICTED).toBe("restricted");
    expect(LayerPolicy.LOCKED).toBe("locked");
  });
});

// ---------------------------------------------------------------------------
// CompositionResult
// ---------------------------------------------------------------------------

describe("CompositionResult", () => {
  test("valid when no missing refs", async () => {
    const result: CompositionResult = {
      resolved: ["brad.soul=brad"],
      missing: [],
      warnings: [],
      deferred: [],
    };
    expect(isCompositionValid(result)).toBe(true);
  });

  test("invalid when missing refs exist", async () => {
    const result: CompositionResult = {
      resolved: [],
      missing: ["brad.soul=nonexistent"],
      warnings: ["something"],
      deferred: [],
    };
    expect(isCompositionValid(result)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Document
// ---------------------------------------------------------------------------

describe("Document", () => {
  test("fromRaw extracts fields", async () => {
    const raw = {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Genome",
      metadata: { name: "my-mod", description: "test" },
      spec: { owner: "team-a" },
    };
    const doc = Document.fromRaw(raw);

    expect(doc.apiVersion).toBe("github.com/ruinosus/dna/v1");
    expect(doc.kind).toBe("Genome");
    expect(doc.name).toBe("my-mod");
    expect(doc.raw).toBe(raw);
    expect(doc.spec).toEqual({ owner: "team-a" });
    expect(doc.metadata).toEqual({ name: "my-mod", description: "test" });
  });

  test("origin defaults to local", async () => {
    const doc = Document.fromRaw({ apiVersion: "x", kind: "Y", metadata: { name: "z" } });
    expect(doc.origin).toBe("local");
  });

  test("delegates to typed when present", async () => {
    const typed = {
      metadata: { name: "typed-name", version: "1.0" },
      spec: { instruction: "do stuff" },
    };
    const doc = Document.fromRaw(
      { apiVersion: "a", kind: "B", metadata: { name: "raw-name" }, spec: {} },
      typed,
    );

    expect(doc.metadata).toBe(typed.metadata);
    expect(doc.spec).toBe(typed.spec);
  });

  test("falls back to raw when typed has no metadata/spec", async () => {
    const doc = Document.fromRaw(
      { apiVersion: "a", kind: "B", metadata: { name: "raw" }, spec: { x: 1 } },
      "just-a-string", // typed but no .metadata/.spec
    );
    expect(doc.metadata).toEqual({ name: "raw" });
    expect(doc.spec).toEqual({ x: 1 });
  });

  test("toString", async () => {
    const doc = Document.fromRaw({
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Genome",
      metadata: { name: "demo" },
    });
    expect(doc.toString()).toBe("Document(github.com/ruinosus/dna/v1/Genome: demo)");
  });
});

// ---------------------------------------------------------------------------
// HookRegistry
// ---------------------------------------------------------------------------

describe("HookRegistry", () => {
  test("middleware chains context", async () => {
    const reg = new HookRegistry();
    reg.use("pre_build", (ctx: HookContext) => ({ ...ctx, data: { ...ctx.data, step: 1 } }));
    reg.use("pre_build", (ctx: HookContext) => ({ ...ctx, data: { ...ctx.data, step: 2 } }));

    const result = reg.runMiddleware("pre_build", { scope: "test", data: {} });
    expect(result.data.step).toBe(2);
  });

  test("event fires without raising", async () => {
    const reg = new HookRegistry();
    const calls: string[] = [];
    reg.on("post_build", (ctx: HookContext) => { calls.push(ctx.scope); });

    reg.emit("post_build", { scope: "hello", data: {} });
    expect(calls).toEqual(["hello"]);
  });

  test("event error is swallowed", async () => {
    const reg = new HookRegistry();
    reg.on("danger", () => { throw new Error("boom"); });
    reg.on("danger", () => { /* safe */ });

    // Should not throw
    expect(() => reg.emit("danger", { scope: "x", data: {} })).not.toThrow();
  });

  test("has() returns false for empty, true for registered", async () => {
    const reg = new HookRegistry();
    expect(reg.has("nope")).toBe(false);

    reg.use("yes", (ctx: HookContext) => ctx);
    expect(reg.has("yes")).toBe(true);

    reg.on("events", () => {});
    expect(reg.has("events")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Models (Zod schemas)
// ---------------------------------------------------------------------------

describe("GenomeSchema", () => {
  test("parses valid manifest", async () => {
    const result = GenomeSchema.parse({
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Genome",
      metadata: { name: "open-swe" },
      spec: { owner: "platform", default_agent: "swe-agent" },
    });

    expect(result.metadata.name).toBe("open-swe");
    expect(result.spec.owner).toBe("platform");
    expect(result.spec.default_agent).toBe("swe-agent");
    expect(result.spec.tags).toEqual([]);
    expect(result.spec.dependencies).toEqual([]);
  });

  test("defaults empty spec", async () => {
    // Phase 16 — bill-of-materials arrays (agents, layers, custom_kinds)
    // dropped from GenomeSpec. tags + dependencies remain.
    const result = GenomeSchema.parse({
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Genome",
      metadata: { name: "minimal" },
    });
    expect(result.spec.tags).toEqual([]);
    expect(result.spec.dependencies).toEqual([]);
  });

  test("accepts explicit null for nullable spec fields (parity with Python str|None)", async () => {
    // YAML manifests often serialise optional fields as explicit `null`
    // (e.g. `repository:` with no value). The Python model uses
    // `str | None = None`; the Zod schema must accept the same shape via
    // `.nullish()` or the Navigator logs a parse warning at every
    // workspace load. Regression guard for B2.6.
    const result = GenomeSchema.parse({
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Genome",
      metadata: { name: "mod" },
      spec: { repository: null, budget: null },
    });
    expect(result.spec.repository).toBeNull();
    expect(result.spec.budget).toBeNull();
  });
});

describe("SkillSchema", () => {
  test("parses with instruction", async () => {
    const result = SkillSchema.parse({
      apiVersion: "agentskills.io/v1",
      kind: "Skill",
      metadata: { name: "code-review" },
      spec: { instruction: "Review code thoroughly" },
    });
    expect(result.spec.instruction).toBe("Review code thoroughly");
    expect(result.spec.scripts).toEqual({});
  });
});

describe("AgentSchema", () => {
  test("parses soul + skills refs", async () => {
    const result = AgentSchema.parse({
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Agent",
      metadata: { name: "brad" },
      spec: {
        soul: "toolsmith",
        skills: ["code-review", "testing"],
        instruction: "You are brad",
      },
    });
    expect(result.spec.soul).toBe("toolsmith");
    expect(result.spec.skills).toEqual(["code-review", "testing"]);
  });
});

describe("SoulSchema", () => {
  test("parses soul content", async () => {
    const result = SoulSchema.parse({
      apiVersion: "soulspec.org/v1",
      kind: "Soul",
      metadata: { name: "toolsmith" },
      spec: { soul_content: "I am a toolsmith" },
    });
    expect(result.spec.soul_content).toBe("I am a toolsmith");
  });
});

describe("ActorSchema", () => {
  test("parses traits and defaults actorType to human", async () => {
    const result = ActorSchema.parse({
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Actor",
      metadata: { name: "exec" },
      spec: { traits: ["strategic", "concise"], role: "CTO" },
    });
    expect(result.spec.traits).toEqual(["strategic", "concise"]);
    expect(result.spec.role).toBe("CTO");
    expect(result.spec.actorType).toBe("human");
  });

  test("accepts system and time actorType", async () => {
    const sys = ActorSchema.parse({
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Actor",
      metadata: { name: "upstream" },
      spec: { actorType: "system" },
    });
    expect(sys.spec.actorType).toBe("system");

    const cron = ActorSchema.parse({
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Actor",
      metadata: { name: "nightly" },
      spec: { actorType: "time" },
    });
    expect(cron.spec.actorType).toBe("time");
  });
});

describe("AgentDefinitionSchema", () => {
  test("parses content", async () => {
    const result = AgentDefinitionSchema.parse({
      apiVersion: "agents.md/v1",
      kind: "AgentDefinition",
      metadata: { name: "context" },
      spec: { content: "# Agents\nBe helpful." },
    });
    expect(result.spec.content).toBe("# Agents\nBe helpful.");
  });
});

describe("MetadataSchema", () => {
  test("defaults optional fields", async () => {
    const result = MetadataSchema.parse({ name: "test" });
    expect(result.description).toBe("");
    expect(result.version).toBe("");
    expect(result.labels).toEqual({});
  });
});

// ---------------------------------------------------------------------------
// Lock types
// ---------------------------------------------------------------------------

describe("Lock types", () => {
  test("LockEntry interface usage", async () => {
    const entry: LockEntry = {
      name: "open-swe",
      kind: "Genome",
      apiVersion: "github.com/ruinosus/dna/v1",
      origin: "local",
      path: ".dna/open-swe/manifest.yaml",
      sha256: "abc123",
    };
    expect(entry.name).toBe("open-swe");
    expect(entry.sha256).toBe("abc123");
  });

  test("Lockfile interface usage", async () => {
    const lock: Lockfile = {
      scope: "open-swe",
      documents: [],
      lockVersion: 3,
      generatedAt: "2026-03-31T00:00:00Z",
    };
    expect(lock.lockVersion).toBe(3);
    expect(lock.documents).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Error hierarchy
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Kernel
// ---------------------------------------------------------------------------

import { Kernel, ManifestInstance } from "../src/kernel/index.js";
import type { KindPort, SourcePort, CachePort } from "../src/kernel/protocols.js";

function makeKindPort(overrides: Partial<KindPort> & Pick<KindPort, "apiVersion" | "kind" | "alias">): KindPort {
  return {
    origin: "test",
    isRoot: false,
    isPromptTarget: false,
    promptTargetPriority: 0,
    flattenInContext: false,
    storage: { container: "test", pattern: "yaml" },
    depFilters: () => null,
    getDefaultAgentName: () => null,
    getLayerPolicies: () => null,
    parse: (raw) => raw,
    describe: () => null,
    summary: () => null,
    promptTemplate: () => null,
    ...overrides,
  };
}

/** Minimal source+cache for await Kernel.instance() tests. */
function makeStubPorts(manifest: Record<string, unknown>, allDocs: Record<string, unknown>[]) {
  const source: SourcePort = {
    supportsReaders: false,
    loadBootstrapDocs: async () => {
      const out = allDocs.filter((d) =>
        ["KindDefinition", "LayerPolicy", "Genome"].includes((d.kind as string) ?? ""),
      );
      // Surface the manifest doc too (useful when fixture passes Module
      // shape outside of allDocs).
      if (
        manifest
        && typeof manifest === "object"
        && "kind" in manifest
        && !out.includes(manifest)
      ) {
        out.push(manifest);
      }
      return out;
    },
    loadAll: () => allDocs,
    resolveRef: (_s, ref) => ref,
    loadLayer: () => [],
  };
  const cache: CachePort = {
    has: () => false,
    store: () => {},
    loadAll: () => [],
  };
  return { source, cache };
}

describe("v3 Kernel", () => {
  test("registers kinds via kind()", async () => {
    const k = new Kernel();
    const kp = makeKindPort({ apiVersion: "test/v1", kind: "Widget", alias: "test-widget" });
    k.kind(kp);
    expect(k._kinds.size).toBe(1);
    expect(k._kinds.get("test/v1\0Widget")).toBe(kp);
  });

  test("load with extension_error hook catches bad extension", async () => {
    const k = new Kernel();
    const errors: string[] = [];
    k.on("extension_error", (ctx) => {
      errors.push(ctx.data.error as string);
    });
    k.load({
      name: "bad-ext",
      version: "1.0",
      register: () => { throw new Error("boom"); },
    });
    // Should NOT throw
    expect(errors).toEqual(["Error: boom"]);
  });

  test("load without hook re-raises", async () => {
    const k = new Kernel();
    expect(() =>
      k.load({
        name: "bad-ext",
        version: "1.0",
        register: () => { throw new Error("boom"); },
      }),
    ).toThrow("boom");
  });

  test("_parseDoc falls back to raw on parse error", async () => {
    const k = new Kernel();
    k.kind(makeKindPort({
      apiVersion: "test/v1",
      kind: "Bad",
      alias: "test-bad",
      parse: () => { throw new Error("parse fail"); },
    }));
    const doc = k._parseDoc({ apiVersion: "test/v1", kind: "Bad", metadata: { name: "x" }, spec: {} });
    expect(doc.kind).toBe("Bad");
    expect(doc.name).toBe("x");
    expect(doc.typed).toBeNull();
  });

  test("_parseDoc emits parse_error event", async () => {
    const k = new Kernel();
    const errors: string[] = [];
    k.on("parse_error", (ctx) => {
      errors.push(ctx.data.error as string);
    });
    k.kind(makeKindPort({
      apiVersion: "test/v1",
      kind: "Bad",
      alias: "test-bad",
      parse: () => { throw new Error("parse fail"); },
    }));
    k._parseDoc({ apiVersion: "test/v1", kind: "Bad", metadata: { name: "x" }, spec: {} });
    expect(errors.length).toBe(1);
    expect(errors[0]).toContain("parse fail");
  });

  test("instance() creates ManifestInstance with documents", async () => {
    const k = new Kernel();
    const manifest = {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Genome",
      metadata: { name: "test-mod" },
      spec: {},
    };
    const allDocs = [
      manifest,
      { apiVersion: "github.com/ruinosus/dna/v1", kind: "Agent", metadata: { name: "agent-a" }, spec: { instruction: "do stuff" } },
    ];
    const { source, cache } = makeStubPorts(manifest, allDocs);
    k.source(source);
    k.cache(cache);

    const mi = await k.instance("test-mod");
    expect(mi.scope).toBe("test-mod");
    expect(mi.documents.length).toBe(2);
  });

  test("instance() throws without source", async () => {
    const k = new Kernel();
    k.cache({ has: () => false, store: () => {}, loadAll: () => [], loadKey: () => [] });
    await expect(k.instance("x")).rejects.toThrow("No source registered");
  });

  test("instance() throws without cache", async () => {
    const k = new Kernel();
    k.source({
      supportsReaders: false,
      loadBootstrapDocs: async () => [],
      loadAll: async () => [],
      resolveRef: async () => "",
      loadLayer: async () => [],
    });
    await expect(k.instance("x")).rejects.toThrow("No cache registered");
  });

  test("_registerCustomKinds registers dynamic kinds", async () => {
    const k = new Kernel();
    const manifest = {
      spec: {
        custom_kinds: [
          { apiVersion: "myco/v1", kind: "Pipeline", alias: "myco-pipeline" },
        ],
      },
    };
    // @ts-expect-error - accessing private method for testing
    k._registerCustomKinds(manifest);
    expect(k._kinds.has("myco/v1\0Pipeline")).toBe(true);
    const kp = k._kinds.get("myco/v1\0Pipeline")!;
    expect(kp.alias).toBe("myco-pipeline");
    expect(kp.isRoot).toBe(false);
  });

  test("quick() throws on missing scope dir", async () => {
    await expect(quickInstance("nonexistent-scope", "/tmp/no-such-dir")).rejects.toThrow();
  });

  test("auto() returns kernel with extensions loaded", async () => {
    const k = createKernelWithBuiltins();
    expect(k._kinds.size).toBeGreaterThanOrEqual(6);
    expect(k._kinds.has("github.com/ruinosus/dna/v1\0Genome")).toBe(true);
    expect(k._kinds.has("agentskills.io/v1\0Skill")).toBe(true);
    expect(k._kinds.has("soulspec.org/v1\0Soul")).toBe(true);
    expect(k._kinds.has("agents.md/v1\0AgentDefinition")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// ManifestInstance
// ---------------------------------------------------------------------------

describe("v3 ManifestInstance", () => {
  test("all filters by kind", async () => {
    const docs = [
      Document.fromRaw({ apiVersion: "a/v1", kind: "A", metadata: { name: "a1" }, spec: {} }),
      Document.fromRaw({ apiVersion: "b/v1", kind: "B", metadata: { name: "b1" }, spec: {} }),
    ];
    const mi = new ManifestInstance({ scope: "test", documents: docs, kinds: new Map() });
    expect(mi.all("A").length).toBe(1);
    expect(mi.all("B").length).toBe(1);
    expect(mi.all("C").length).toBe(0);
  });

  test("one returns doc or null", async () => {
    const docs = [
      Document.fromRaw({ apiVersion: "a/v1", kind: "A", metadata: { name: "a1" }, spec: {} }),
      Document.fromRaw({ apiVersion: "a/v1", kind: "A", metadata: { name: "a2" }, spec: {} }),
    ];
    const mi = new ManifestInstance({ scope: "test", documents: docs, kinds: new Map() });
    expect(mi.one("A", "a1")?.name).toBe("a1");
    expect(mi.one("A", "a2")?.name).toBe("a2");
    expect(mi.one("A", "a3")).toBeNull();
    expect(mi.one("B", "a1")).toBeNull();
  });

  test("root finds isRoot kind", async () => {
    const kinds = new Map<string, KindPort>();
    kinds.set("github.com/ruinosus/dna/v1\0Genome", makeKindPort({
      apiVersion: "github.com/ruinosus/dna/v1", kind: "Genome", alias: "helix-genome", isRoot: true,
    }));
    const docs = [
      Document.fromRaw({ apiVersion: "github.com/ruinosus/dna/v1", kind: "Genome", metadata: { name: "my-mod" }, spec: {} }),
      Document.fromRaw({ apiVersion: "github.com/ruinosus/dna/v1", kind: "Agent", metadata: { name: "agent-a" }, spec: {} }),
    ];
    const mi = new ManifestInstance({ scope: "test", documents: docs, kinds });
    expect(mi.root?.name).toBe("my-mod");
  });

  test("root returns null when no isRoot kind", async () => {
    const mi = new ManifestInstance({ scope: "test", documents: [], kinds: new Map() });
    expect(mi.root).toBeNull();
  });

  test("compositionResult detects missing refs", async () => {
    const kinds = new Map<string, KindPort>();
    kinds.set("github.com/ruinosus/dna/v1\0Agent", makeKindPort({
      apiVersion: "github.com/ruinosus/dna/v1", kind: "Agent", alias: "helix-agent",
      isPromptTarget: true,
      depFilters: () => ({ skills: "agentskills-skill" }),
    }));
    kinds.set("agentskills.io/v1\0Skill", makeKindPort({
      apiVersion: "agentskills.io/v1", kind: "Skill", alias: "agentskills-skill",
    }));

    const docs = [
      Document.fromRaw({
        apiVersion: "github.com/ruinosus/dna/v1", kind: "Agent",
        metadata: { name: "brad" },
        spec: { skills: ["code-review", "nonexistent"] },
      }),
      Document.fromRaw({
        apiVersion: "agentskills.io/v1", kind: "Skill",
        metadata: { name: "code-review" },
        spec: {},
      }),
    ];
    const mi = new ManifestInstance({ scope: "test", documents: docs, kinds });
    const result = mi.compositionResult;

    expect(result.resolved.length).toBe(1);
    expect(result.resolved[0]).toContain("code-review");
    expect(result.missing.length).toBe(1);
    expect(result.missing[0]).toContain("nonexistent");
    expect(result.missing[0]).toContain("NOT FOUND");
  });

  test("compositionResult resolves valid refs", async () => {
    const kinds = new Map<string, KindPort>();
    kinds.set("github.com/ruinosus/dna/v1\0Agent", makeKindPort({
      apiVersion: "github.com/ruinosus/dna/v1", kind: "Agent", alias: "helix-agent",
      depFilters: () => ({ soul: "soulspec-soul" }),
    }));
    kinds.set("soulspec.org/v1\0Soul", makeKindPort({
      apiVersion: "soulspec.org/v1", kind: "Soul", alias: "soulspec-soul",
    }));

    const docs = [
      Document.fromRaw({
        apiVersion: "github.com/ruinosus/dna/v1", kind: "Agent",
        metadata: { name: "brad" },
        spec: { soul: "toolsmith" },
      }),
      Document.fromRaw({
        apiVersion: "soulspec.org/v1", kind: "Soul",
        metadata: { name: "toolsmith" },
        spec: {},
      }),
    ];
    const mi = new ManifestInstance({ scope: "test", documents: docs, kinds });
    const result = mi.compositionResult;

    expect(result.resolved.length).toBe(1);
    expect(result.missing.length).toBe(0);
  });

  test("listKinds returns sorted unique kinds", async () => {
    const docs = [
      Document.fromRaw({ apiVersion: "a/v1", kind: "B", metadata: { name: "b1" }, spec: {} }),
      Document.fromRaw({ apiVersion: "a/v1", kind: "A", metadata: { name: "a1" }, spec: {} }),
      Document.fromRaw({ apiVersion: "a/v1", kind: "B", metadata: { name: "b2" }, spec: {} }),
    ];
    const mi = new ManifestInstance({ scope: "test", documents: docs, kinds: new Map() });
    expect(mi.listKinds()).toEqual(["A", "B"]);
  });

  test("get returns summary dicts", async () => {
    const docs = [
      Document.fromRaw({ apiVersion: "a/v1", kind: "A", metadata: { name: "a1" }, spec: {} }),
      Document.fromRaw({ apiVersion: "b/v1", kind: "B", metadata: { name: "b1" }, spec: {} }),
    ];
    const mi = new ManifestInstance({ scope: "test", documents: docs, kinds: new Map() });
    const all = mi.get();
    expect(all.length).toBe(2);
    expect(all[0]).toEqual({ kind: "A", name: "a1", apiVersion: "a/v1" });

    const filtered = mi.get("B");
    expect(filtered.length).toBe(1);
    expect(filtered[0].name).toBe("b1");
  });

  test("describe returns formatted string", async () => {
    const docs = [
      Document.fromRaw({
        apiVersion: "a/v1", kind: "A",
        metadata: { name: "a1", description: "A thing" },
        spec: {},
      }),
    ];
    const mi = new ManifestInstance({ scope: "test", documents: docs, kinds: new Map() });
    const desc = mi.describe("A", "a1");
    expect(desc).toContain("Name:       a1");
    expect(desc).toContain("Kind:       A");
    expect(desc).toContain("Description: A thing");
  });

  test("describe returns not found for missing", async () => {
    const mi = new ManifestInstance({ scope: "test", documents: [], kinds: new Map() });
    expect(mi.describe("X", "y")).toBe("X/y not found");
  });

  test("summary includes all kinds", async () => {
    const docs = [
      Document.fromRaw({ apiVersion: "a/v1", kind: "Genome", metadata: { name: "m1" }, spec: {} }),
      Document.fromRaw({ apiVersion: "a/v1", kind: "Skill", metadata: { name: "s1" }, spec: {} }),
    ];
    const mi = new ManifestInstance({ scope: "my-scope", documents: docs, kinds: new Map() });
    const s = mi.summary();
    expect(s).toContain("Scope: my-scope");
    expect(s).toContain("Genome: 1");
    expect(s).toContain("Skill: 1");
  });

  test("buildPrompt returns agent instruction fallback", async () => {
    const kinds = new Map<string, KindPort>();
    kinds.set("github.com/ruinosus/dna/v1\0Agent", makeKindPort({
      apiVersion: "github.com/ruinosus/dna/v1", kind: "Agent", alias: "helix-agent",
      isPromptTarget: true,
    }));
    const docs = [
      Document.fromRaw({
        apiVersion: "github.com/ruinosus/dna/v1", kind: "Agent",
        metadata: { name: "brad" },
        spec: { instruction: "You are Brad, the helpful agent." },
      }),
    ];
    const mi = new ManifestInstance({ scope: "test", documents: docs, kinds });
    const prompt = await mi.buildPrompt({ agent: "brad" });
    expect(prompt).toBe("You are Brad, the helpful agent.");
  });

  test("buildPrompt uses kind template", async () => {
    const kinds = new Map<string, KindPort>();
    kinds.set("github.com/ruinosus/dna/v1\0Agent", makeKindPort({
      apiVersion: "github.com/ruinosus/dna/v1", kind: "Agent", alias: "helix-agent",
      isPromptTarget: true,
      promptTemplate: () => "Agent: {{agent.name}} - {{agent.instruction}}",
    }));
    const docs = [
      Document.fromRaw({
        apiVersion: "github.com/ruinosus/dna/v1", kind: "Agent",
        metadata: { name: "brad" },
        spec: { instruction: "Be helpful" },
      }),
    ];
    const mi = new ManifestInstance({ scope: "test", documents: docs, kinds });
    const prompt = await mi.buildPrompt({ agent: "brad" });
    expect(prompt).toBe("Agent: brad - Be helpful");
  });

  test("buildPrompt uses agent-level template override", async () => {
    const kinds = new Map<string, KindPort>();
    kinds.set("github.com/ruinosus/dna/v1\0Agent", makeKindPort({
      apiVersion: "github.com/ruinosus/dna/v1", kind: "Agent", alias: "helix-agent",
      isPromptTarget: true,
      promptTemplate: () => "KIND TEMPLATE: {{agent.instruction}}",
    }));
    const docs = [
      Document.fromRaw({
        apiVersion: "github.com/ruinosus/dna/v1", kind: "Agent",
        metadata: { name: "brad" },
        spec: { instruction: "Be helpful", promptTemplate: "AGENT TEMPLATE: {{agent.instruction}}" },
      }),
    ];
    const mi = new ManifestInstance({ scope: "test", documents: docs, kinds });
    const prompt = await mi.buildPrompt({ agent: "brad" });
    expect(prompt).toBe("AGENT TEMPLATE: Be helpful");
  });

  test("buildPrompt returns not found for missing agent", async () => {
    const mi = new ManifestInstance({ scope: "test", documents: [], kinds: new Map() });
    const prompt = await mi.buildPrompt({ agent: "nonexistent" });
    expect(prompt).toContain("not found");
  });

  test("defaultAgent uses root adapter", async () => {
    const kinds = new Map<string, KindPort>();
    kinds.set("github.com/ruinosus/dna/v1\0Genome", makeKindPort({
      apiVersion: "github.com/ruinosus/dna/v1", kind: "Genome", alias: "helix-genome",
      isRoot: true,
      getDefaultAgentName: () => "brad",
    }));
    kinds.set("github.com/ruinosus/dna/v1\0Agent", makeKindPort({
      apiVersion: "github.com/ruinosus/dna/v1", kind: "Agent", alias: "helix-agent",
      isPromptTarget: true,
    }));
    const docs = [
      Document.fromRaw({ apiVersion: "github.com/ruinosus/dna/v1", kind: "Genome", metadata: { name: "my-mod" }, spec: { default_agent: "brad" } }),
      Document.fromRaw({ apiVersion: "github.com/ruinosus/dna/v1", kind: "Agent", metadata: { name: "brad" }, spec: { instruction: "hi" } }),
    ];
    const mi = new ManifestInstance({ scope: "test", documents: docs, kinds });
    expect(mi.defaultAgent()?.name).toBe("brad");
  });

  test("generateLock produces SHA256 entries", async () => {
    const docs = [
      Document.fromRaw({ apiVersion: "a/v1", kind: "A", metadata: { name: "a1" }, spec: { x: 1 } }),
      Document.fromRaw({ apiVersion: "b/v1", kind: "B", metadata: { name: "b1" }, spec: {} }),
    ];
    const mi = new ManifestInstance({ scope: "test", documents: docs, kinds: new Map() });
    const lock = mi.generateLock();

    expect(lock.scope).toBe("test");
    expect(lock.lockVersion).toBe(3);
    expect(lock.documents.length).toBe(2);
    for (const entry of lock.documents) {
      expect(entry.sha256).toMatch(/^[0-9a-f]{64}$/);
    }
    expect(lock.documents[0].name).toBe("a1");
    expect(lock.documents[1].name).toBe("b1");
  });

  test("resolve returns self when no layers", async () => {
    const mi = new ManifestInstance({ scope: "test", documents: [], kinds: new Map() });
    expect(mi.resolve()).toBe(mi);
  });

  test("ref returns value as-is when no source", async () => {
    const mi = new ManifestInstance({ scope: "test", documents: [], kinds: new Map() });
    expect(await mi.ref("hello")).toBe("hello");
    expect(await mi.ref("")).toBe("");
  });
});

// ---------------------------------------------------------------------------
// Error hierarchy
// ---------------------------------------------------------------------------

describe("ResolveError hierarchy", () => {
  test("ResolveNotFoundError instanceof ResolveError", async () => {
    const err = new ResolveNotFoundError("not found");
    expect(err).toBeInstanceOf(ResolveError);
    expect(err).toBeInstanceOf(ResolveNotFoundError);
    expect(err).toBeInstanceOf(Error);
    expect(err.message).toBe("not found");
  });

  test("ResolveAuthError instanceof ResolveError", async () => {
    const err = new ResolveAuthError("forbidden");
    expect(err).toBeInstanceOf(ResolveError);
    expect(err).toBeInstanceOf(ResolveAuthError);
  });

  test("ResolveNetworkError instanceof ResolveError", async () => {
    const err = new ResolveNetworkError("timeout");
    expect(err).toBeInstanceOf(ResolveError);
    expect(err).toBeInstanceOf(ResolveNetworkError);
  });

  test("ResolveError is not ResolveNotFoundError", async () => {
    const err = new ResolveError("generic");
    expect(err).toBeInstanceOf(ResolveError);
    expect(err).not.toBeInstanceOf(ResolveNotFoundError);
  });
});

// ---------------------------------------------------------------------------
// buildPrompt filters (enabledSkills / enabledGuardrails)
// ---------------------------------------------------------------------------

describe("buildPrompt filters", () => {
  function makeMi() {
    const kinds = new Map<string, KindPort>();
    kinds.set("github.com/ruinosus/dna/v1\0Agent", makeKindPort({
      apiVersion: "github.com/ruinosus/dna/v1", kind: "Agent", alias: "helix-agent",
      isPromptTarget: true,
      depFilters: () => ({ skills: "agentskills-skill", guardrails: "guardrail-guardrail" }),
      promptTemplate: () => "BASE {{#agentskills-skill}}SKILL:{{name}} {{/agentskills-skill}}{{#guardrail-guardrail}}GUARD:{{name}} {{/guardrail-guardrail}}",
    }));
    kinds.set("agentskills.io/v1\0Skill", makeKindPort({
      apiVersion: "agentskills.io/v1", kind: "Skill", alias: "agentskills-skill",
    }));
    kinds.set("guardrail.io/v1\0Guardrail", makeKindPort({
      apiVersion: "guardrail.io/v1", kind: "Guardrail", alias: "guardrail-guardrail",
    }));

    const docs = [
      Document.fromRaw({
        apiVersion: "github.com/ruinosus/dna/v1", kind: "Agent",
        metadata: { name: "brad" },
        spec: { skills: ["skill-a", "skill-b"], guardrails: ["guard-x"] },
      }),
      Document.fromRaw({ apiVersion: "agentskills.io/v1", kind: "Skill", metadata: { name: "skill-a" }, spec: {} }),
      Document.fromRaw({ apiVersion: "agentskills.io/v1", kind: "Skill", metadata: { name: "skill-b" }, spec: {} }),
      Document.fromRaw({ apiVersion: "guardrail.io/v1", kind: "Guardrail", metadata: { name: "guard-x" }, spec: {} }),
    ];
    return new ManifestInstance({ scope: "test", documents: docs, kinds });
  }

  test("enabledSkills=undefined keeps all (current behavior)", async () => {
    const mi = makeMi();
    const full = await mi.buildPrompt({ agent: "brad" });
    const same = await mi.buildPrompt({ agent: "brad", enabledSkills: undefined });
    expect(same).toBe(full);
  });

  test("enabledSkills=[] removes all skills", async () => {
    const mi = makeMi();
    const full = await mi.buildPrompt({ agent: "brad" });
    const noSkills = await mi.buildPrompt({ agent: "brad", enabledSkills: [] });
    expect(noSkills).not.toContain("SKILL:");
    expect(noSkills.length).toBeLessThan(full.length);
  });

  test("enabledSkills filters to subset", async () => {
    const mi = makeMi();
    const full = await mi.buildPrompt({ agent: "brad" });
    const oneSkill = await mi.buildPrompt({ agent: "brad", enabledSkills: ["skill-a"] });
    expect(oneSkill).toContain("SKILL:skill-a");
    expect(oneSkill).not.toContain("SKILL:skill-b");
    expect(oneSkill.length).toBeLessThan(full.length);
  });

  test("enabledGuardrails=[] removes all guardrails", async () => {
    const mi = makeMi();
    const full = await mi.buildPrompt({ agent: "brad" });
    const noGuards = await mi.buildPrompt({ agent: "brad", enabledGuardrails: [] });
    expect(noGuards).not.toContain("GUARD:");
    expect(noGuards.length).toBeLessThan(full.length);
  });

  test("both filters together", async () => {
    const mi = makeMi();
    const result = await mi.buildPrompt({ agent: "brad", enabledSkills: [], enabledGuardrails: [] });
    expect(result.length).toBeGreaterThan(0);
    expect(result).not.toContain("SKILL:");
    expect(result).not.toContain("GUARD:");
  });

  test("nonexistent skill produces same as empty", async () => {
    const mi = makeMi();
    const filtered = await mi.buildPrompt({ agent: "brad", enabledSkills: ["nope"] });
    const noSkills = await mi.buildPrompt({ agent: "brad", enabledSkills: [] });
    expect(filtered).toBe(noSkills);
  });
});
