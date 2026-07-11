/**
 * Phase 16 — Genome + LayerPolicy Kind tests (TS twin of
 * python/tests/test_package_layerpolicy_kinds.py).
 *
 * 1:1 parity verified:
 *   - GenomeKind round-trip (identity, version, runtime fields)
 *   - OVERLAYABLE_FIELDS allowlist contains exactly the runtime defaults
 *   - LayerPolicyKind normalizes policy strings to lowercase
 *   - Both Kinds expose JSON schemas
 *   - preview() yields PreviewBlocks with expected fields
 *   - HelixExtension.register wires both Kinds into the kernel
 */

import { describe, expect, test } from "bun:test";

import { Document } from "../src/kernel/document.js";
import { HelixExtension } from "../src/extensions/helix.js";
import { HookRegistry } from "../src/kernel/hooks.js";
import {
  GenomeSchema,
  GenomeSpecSchema,
  LayerPolicySchema,
  LayerPolicySpecSchema,
} from "../src/kernel/models.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function findKind(kindName: string) {
  // Re-build via HelixExtension since the Kind classes are
  // module-private — registration is the public surface.
  const ext = new HelixExtension();
  const captured: Array<{ kind: string; alias: string; storage: { container: string; marker?: string } }> = [];
  const fakeKernel = {
    kind(kp: { kind: string; alias: string; storage: { container: string; marker?: string } }) {
      captured.push(kp);
    },
    reader() {},
    writer() {},
    compositionProfile() {},
    kindFromDescriptor() {},
    // s-write-path-despecialize — extensions register pre_save veto
    // hooks on kernel.hooks; the double needs a real registry.
    hooks: new HookRegistry(),
  };
  ext.register(fakeKernel);
  return captured.find((kp) => kp.kind === kindName);
}

function makeDoc(raw: Record<string, unknown>): Document {
  return Document.fromRaw(raw);
}

// ---------------------------------------------------------------------------
// GenomeKind
// ---------------------------------------------------------------------------

describe("GenomeSchema", () => {
  test("round-trip full spec", () => {
    const raw = {
      apiVersion: "github.com/ruinosus/dna/v1" as const,
      kind: "Genome" as const,
      metadata: { name: "hr-screening", description: "HR scope" },
      spec: {
        owner: "platform-team",
        owner_tenant: "platform",
        repository: "https://github.com/example/hr",
        visibility: "public" as const,
        version: "1.2.3",
        changelog_url: "https://example.com/changelog",
        deprecated: false,
        deprecated_message: null,
        default_agent: "talent-screener",
        default_llm: "gpt-4o",
        budget: { daily_usd: 50 },
        tags: ["hr", "screening"],
        dependencies: [{ source: "github:foo/bar@main" }],
      },
    };
    const parsed = GenomeSchema.parse(raw);
    expect(parsed.spec.owner).toBe("platform-team");
    expect(parsed.spec.owner_tenant).toBe("platform");
    expect(parsed.spec.version).toBe("1.2.3");
    expect(parsed.spec.default_agent).toBe("talent-screener");
    expect(parsed.spec.default_llm).toBe("gpt-4o");
    expect(parsed.spec.tags).toEqual(["hr", "screening"]);
    expect(parsed.spec.dependencies).toHaveLength(1);
  });

  test("minimal spec uses defaults", () => {
    const parsed = GenomeSchema.parse({
      apiVersion: "github.com/ruinosus/dna/v1" as const,
      kind: "Genome" as const,
      metadata: { name: "tiny" },
      spec: {},
    });
    expect(parsed.spec.visibility).toBe("public");
    expect(parsed.spec.deprecated).toBe(false);
    expect(parsed.spec.tags).toEqual([]);
    expect(parsed.spec.dependencies).toEqual([]);
  });

  test("rejects unknown visibility values", () => {
    expect(() =>
      GenomeSchema.parse({
        apiVersion: "github.com/ruinosus/dna/v1" as const,
        kind: "Genome" as const,
        metadata: { name: "bad" },
        spec: { visibility: "secret" as unknown as "public" },
      }),
    ).toThrow();
  });
});

describe("GenomeSpecSchema fields", () => {
  test("schema has both identity and runtime properties", () => {
    const shape = GenomeSpecSchema.shape;
    for (const f of [
      "owner",
      "owner_tenant",
      "repository",
      "visibility",
      "version",
      "changelog_url",
      "deprecated",
      "deprecated_message",
      "default_agent",
      "default_llm",
      "budget",
      "tags",
      "dependencies",
    ]) {
      expect(shape).toHaveProperty(f);
    }
  });

  test("schema does NOT carry inventory bill-of-materials arrays", () => {
    const shape = GenomeSpecSchema.shape;
    for (const f of [
      "agents",
      "skills",
      "actors",
      "use_cases",
      "tools",
      "guardrails",
      "layers",
      "custom_kinds",
    ]) {
      expect(shape).not.toHaveProperty(f);
    }
  });
});

describe("GenomeKind identity (via HelixExtension registration)", () => {
  test("kind, alias, storage", () => {
    const kp = findKind("Genome");
    expect(kp).toBeDefined();
    expect(kp!.alias).toBe("helix-genome");
    expect(kp!.storage.container).toBe("");
    expect(kp!.storage.marker).toBe("Genome.yaml");
  });
});

describe("GenomeKind OVERLAYABLE_FIELDS allowlist (parity with Python)", () => {
  // Static field on the class — we read it via dynamic import to keep
  // the test independent of class re-exports.
  test("contains runtime defaults and excludes identity", async () => {
    const mod = await import("../src/extensions/helix.js");
    // GenomeKind is module-private; read via the registered kind list.
    const ext = new mod.HelixExtension();
    let pkgKind: unknown;
    const fakeKernel = {
      kind(kp: unknown) {
        const k = kp as { kind: string };
        if (k.kind === "Genome") pkgKind = kp;
      },
      reader() {},
      writer() {},
      compositionProfile() {},
      // helix registers Tool (helix-tool) as a descriptor
      // (kinds/tool.kind.yaml, s-tool-kind-descriptor); no-op here.
      kindFromDescriptor() {},
      hooks: new HookRegistry(),
    };
    ext.register(fakeKernel);
    expect(pkgKind).toBeDefined();
    const overlayable = (pkgKind as { constructor: { OVERLAYABLE_FIELDS: Set<string> } }).constructor.OVERLAYABLE_FIELDS;
    expect(overlayable).toBeInstanceOf(Set);
    expect(overlayable.has("default_agent")).toBe(true);
    expect(overlayable.has("default_llm")).toBe(true);
    expect(overlayable.has("budget")).toBe(true);
    expect(overlayable.has("tags")).toBe(true);
    // Identity fields MUST NOT be in the allowlist.
    for (const forbidden of ["owner", "owner_tenant", "repository", "visibility", "version", "changelog_url", "deprecated", "deprecated_message", "dependencies"]) {
      expect(overlayable.has(forbidden)).toBe(false);
    }
  });
});

describe("GenomeKind preview / describe", () => {
  test("preview renders populated fields", () => {
    const ext = new HelixExtension();
    let pkgKind: unknown;
    const fakeKernel = {
      kind(kp: unknown) {
        const k = kp as { kind: string };
        if (k.kind === "Genome") pkgKind = kp;
      },
      reader() {},
      writer() {},
      compositionProfile() {},
      // helix registers Tool (helix-tool) as a descriptor
      // (kinds/tool.kind.yaml, s-tool-kind-descriptor); no-op here.
      kindFromDescriptor() {},
      hooks: new HookRegistry(),
    };
    ext.register(fakeKernel);
    const kp = pkgKind as { preview: (doc: Document) => Array<{ kind: string; fields?: Array<{ label: string }> }> };
    const blocks = kp.preview(
      makeDoc({
        apiVersion: "github.com/ruinosus/dna/v1",
        kind: "Genome",
        metadata: { name: "hr-screening" },
        spec: {
          owner_tenant: "platform",
          visibility: "public",
          version: "1.0.0",
          default_agent: "talent-screener",
          default_llm: "gpt-4o",
          dependencies: [{ source: "x" }, { source: "y" }],
        },
      }),
    );
    expect(blocks).toHaveLength(1);
    expect(blocks[0].kind).toBe("fields");
    const labels = (blocks[0].fields ?? []).map((f) => f.label);
    expect(labels).toContain("owner_tenant");
    expect(labels).toContain("version");
    expect(labels).toContain("default_agent");
    expect(labels).toContain("dependencies");
  });

  test("preview renders empty for blank spec", () => {
    const ext = new HelixExtension();
    let pkgKind: unknown;
    ext.register({
      kind(kp: unknown) {
        const k = kp as { kind: string };
        if (k.kind === "Genome") pkgKind = kp;
      },
      reader() {},
      writer() {},
      compositionProfile() {},
      // helix registers Tool (helix-tool) as a descriptor
      // (kinds/tool.kind.yaml, s-tool-kind-descriptor); no-op here.
      kindFromDescriptor() {},
      hooks: new HookRegistry(),
    });
    const kp = pkgKind as { preview: (doc: Document) => Array<{ kind: string }> };
    const blocks = kp.preview(
      makeDoc({
        apiVersion: "github.com/ruinosus/dna/v1",
        kind: "Genome",
        metadata: { name: "blank" },
        spec: {},
      }),
    );
    expect(blocks[0].kind).toBe("empty");
  });
});

// ---------------------------------------------------------------------------
// LayerPolicyKind
// ---------------------------------------------------------------------------

describe("LayerPolicySchema", () => {
  test("round-trip", () => {
    const parsed = LayerPolicySchema.parse({
      apiVersion: "github.com/ruinosus/dna/policy/v1" as const,
      kind: "LayerPolicy" as const,
      metadata: { name: "tenant-default" },
      spec: {
        layer_id: "tenant",
        policies: { "helix-agent": "locked", "agentskills-skill": "open" },
      },
    });
    expect(parsed.spec.layer_id).toBe("tenant");
    expect(parsed.spec.policies).toEqual({
      "helix-agent": "locked",
      "agentskills-skill": "open",
    });
  });

  test("default empty policies on missing", () => {
    const parsed = LayerPolicySchema.parse({
      apiVersion: "github.com/ruinosus/dna/policy/v1" as const,
      kind: "LayerPolicy" as const,
      metadata: { name: "x" },
      spec: { layer_id: "branch" },
    });
    expect(parsed.spec.policies).toEqual({});
  });
});

describe("LayerPolicyKind normalization (parity with Python LayerPolicySpec.from_raw)", () => {
  test("policy values are lowercased + falsy/non-string keys dropped", () => {
    const ext = new HelixExtension();
    let lpKind: unknown;
    ext.register({
      kind(kp: unknown) {
        const k = kp as { kind: string };
        if (k.kind === "LayerPolicy") lpKind = kp;
      },
      reader() {},
      writer() {},
      compositionProfile() {},
      // helix registers Tool (helix-tool) as a descriptor
      // (kinds/tool.kind.yaml, s-tool-kind-descriptor); no-op here.
      kindFromDescriptor() {},
      hooks: new HookRegistry(),
    });
    const kp = lpKind as { parse: (raw: Record<string, unknown>) => unknown };
    const parsed = kp.parse({
      apiVersion: "github.com/ruinosus/dna/policy/v1",
      kind: "LayerPolicy",
      metadata: { name: "tenant-default" },
      spec: {
        layer_id: "tenant",
        policies: {
          "helix-genome": "LOCKED",
          "agentskills-skill": "Restricted",
          "blanked": "",
          "kept": "open",
        },
      },
    }) as { spec: { policies: Record<string, string> } };
    expect(parsed.spec.policies["helix-genome"]).toBe("locked");
    expect(parsed.spec.policies["agentskills-skill"]).toBe("restricted");
    expect(parsed.spec.policies["kept"]).toBe("open");
    expect(parsed.spec.policies["blanked"]).toBeUndefined();
  });
});

describe("LayerPolicyKind identity", () => {
  test("kind, alias, storage", () => {
    const kp = findKind("LayerPolicy");
    expect(kp).toBeDefined();
    expect(kp!.alias).toBe("policy-layer-policy");
    expect(kp!.storage.container).toBe("policies");
  });

  test("schema has layer_id and policies", () => {
    const shape = LayerPolicySpecSchema.shape;
    expect(shape).toHaveProperty("layer_id");
    expect(shape).toHaveProperty("policies");
  });
});

// ---------------------------------------------------------------------------
// HelixExtension wiring
// ---------------------------------------------------------------------------

describe("HelixExtension.register", () => {
  test("registers Genome + LayerPolicy alongside Module during migration branch", () => {
    const ext = new HelixExtension();
    const captured: string[] = [];
    ext.register({
      kind(kp: unknown) {
        captured.push((kp as { kind: string }).kind);
      },
      reader() {},
      writer() {},
      compositionProfile() {},
      // helix registers Tool (helix-tool) as a descriptor
      // (kinds/tool.kind.yaml, s-tool-kind-descriptor); no-op here.
      kindFromDescriptor() {},
      hooks: new HookRegistry(),
    });
    expect(captured).toContain("Genome");
    expect(captured).toContain("Genome");
    expect(captured).toContain("LayerPolicy");
    expect(captured).toContain("Agent");
  });
});
