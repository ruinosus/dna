/**
 * Phase 16 — TS twin of python/tests/test_layer_policy_phase16.py.
 *
 * Covers:
 *  - Kernel.NON_OVERLAYABLE_KINDS allowlist hard-locks Genome /
 *    KindDefinition / LayerPolicy regardless of declared policy.
 *  - LayerPolicy docs override the legacy Module.spec.layers when both
 *    declare a policy for the same (layer_id, alias) tuple.
 *  - LayerPolicy docs alone (no Module.spec.layers) drive enforcement.
 */

import { describe, it, expect } from "bun:test";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { Kernel } from "../src/kernel";
import { createKernelWithBuiltins } from "../src/bootstrap";
import { HelixExtension } from "../src/extensions/helix";
import { FilesystemSource, FilesystemCache } from "../src/adapters/filesystem";

function setup(tmp: string, files: { manifestYaml?: string; policies?: Record<string, string> }) {
  const scopeDir = join(tmp, "s");
  mkdirSync(scopeDir, { recursive: true });
  if (files.manifestYaml) {
    writeFileSync(join(scopeDir, "Genome.yaml"), files.manifestYaml);
  }
  if (files.policies) {
    const policiesDir = join(scopeDir, "policies");
    mkdirSync(policiesDir, { recursive: true });
    for (const [name, body] of Object.entries(files.policies)) {
      writeFileSync(join(policiesDir, `${name}.yaml`), body);
    }
  }
  const k = new Kernel();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  k.load(new HelixExtension() as any);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const src = new FilesystemSource(tmp) as any;
  k.source(src);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const writableStub: any = {
    async saveDocument() { return "v1"; },
    async deleteDocument() {},
    async loadBootstrapDocs() { return []; },
    async loadDocument() { return null; },
    async loadLayer() { return []; },
    async capabilities() { return {}; },
    async listVersions() { return []; },
    async getVersion() { return null; },
    async publish() { return "v1"; },
    async loadDrafts() { return []; },
    async listScopes() { return ["s"]; },
    async saveManifest() { return "v1"; },
  };
  k.writableSource(writableStub);
  k.cache(new FilesystemCache(join(tmp, ".dna-cache")));
  return k;
}

const agentRaw = {
  apiVersion: "github.com/ruinosus/dna/v1",
  kind: "Agent",
  metadata: { name: "brad" },
  spec: { instruction: "x" },
};

const minimalModule = `apiVersion: github.com/ruinosus/dna/v1
kind: Genome
metadata:
  name: s
spec: {}
`;

// ---------------------------------------------------------------------------
// NON_OVERLAYABLE_KINDS allowlist
// ---------------------------------------------------------------------------

describe("Kernel.NON_OVERLAYABLE_KINDS allowlist (Phase 16)", () => {
  // Now a derived INSTANCE getter (s-kernel-kindport-classification-attrs).
  it("contains Genome, KindDefinition, LayerPolicy", () => {
    const k = createKernelWithBuiltins();
    expect(k.NON_OVERLAYABLE_KINDS.has("Genome")).toBe(true);
    expect(k.NON_OVERLAYABLE_KINDS.has("KindDefinition")).toBe(true);
    expect(k.NON_OVERLAYABLE_KINDS.has("LayerPolicy")).toBe(true);
  });

  it("does not contain Agent or Skill", () => {
    const k = createKernelWithBuiltins();
    expect(k.NON_OVERLAYABLE_KINDS.has("Agent")).toBe(false);
    expect(k.NON_OVERLAYABLE_KINDS.has("Skill")).toBe(false);
  });

  it("Genome write to overlay raises non-overlayable", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "dna-nonov-pkg-"));
    try {
      const k = setup(tmp, { manifestYaml: minimalModule });
      const raw = {
        apiVersion: "github.com/ruinosus/dna/v1",
        kind: "Genome",
        metadata: { name: "s" },
        spec: { version: "1.0.0" },
      };
      await expect(k.writeDocument("s", "Genome", "s", raw, { layer: ["tenant", "T1"] }))
        .rejects.toThrow(/non-overlayable/);
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  it("KindDefinition write to overlay raises", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "dna-nonov-kd-"));
    try {
      const k = setup(tmp, { manifestYaml: minimalModule });
      const raw = {
        apiVersion: "dna.kind/v1",
        kind: "KindDefinition",
        metadata: { name: "MyKind" },
        spec: { target_kind: "MyKind", target_api_version: "demo/v1", alias: "demo-mykind" },
      };
      await expect(k.writeDocument("s", "KindDefinition", "MyKind", raw, { layer: ["tenant", "T1"] }))
        .rejects.toThrow(/non-overlayable/);
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  it("LayerPolicy write to overlay raises", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "dna-nonov-lp-"));
    try {
      const k = setup(tmp, { manifestYaml: minimalModule });
      const raw = {
        apiVersion: "github.com/ruinosus/dna/policy/v1",
        kind: "LayerPolicy",
        metadata: { name: "tenant-default" },
        spec: { layer_id: "tenant", policies: { "helix-agent": "open" } },
      };
      await expect(k.writeDocument("s", "LayerPolicy", "tenant-default", raw, { layer: ["tenant", "T1"] }))
        .rejects.toThrow(/non-overlayable/);
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  it("Agent write to overlay is unaffected by allowlist", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "dna-nonov-ua-"));
    try {
      const k = setup(tmp, { manifestYaml: minimalModule });
      // Should NOT raise (default policy is OPEN, allowlist doesn't fire).
      await k.writeDocument("s", "Agent", "brad", agentRaw, {
        layer: ["tenant", "T1"],
      });
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });
});

// ---------------------------------------------------------------------------
// LayerPolicy docs drive enforcement
// ---------------------------------------------------------------------------

describe("LayerPolicy docs (Phase 16)", () => {
  it("locks Agent when no Module.spec.layers but LayerPolicy doc says LOCKED", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "dna-lpd-locked-"));
    try {
      const k = setup(tmp, {
        manifestYaml: minimalModule,
        policies: {
          "tenant-default": `apiVersion: github.com/ruinosus/dna/policy/v1
kind: LayerPolicy
metadata:
  name: tenant-default
spec:
  layer_id: tenant
  policies:
    helix-agent: locked
`,
        },
      });
      await expect(k.writeDocument("s", "Agent", "brad", agentRaw, { layer: ["tenant", "T1"] }))
        .rejects.toThrow(/LOCKED/);
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  it("LayerPolicy doc filters by layer_id", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "dna-lpd-filter-"));
    try {
      // Policy is for "branch" layer, not "tenant" — write to tenant succeeds.
      const k = setup(tmp, {
        manifestYaml: minimalModule,
        policies: {
          "branch-rules": `apiVersion: github.com/ruinosus/dna/policy/v1
kind: LayerPolicy
metadata:
  name: branch-rules
spec:
  layer_id: branch
  policies:
    helix-agent: locked
`,
        },
      });
      await k.writeDocument("s", "Agent", "brad", agentRaw, { layer: ["tenant", "T1"] });
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });
});

// ---------------------------------------------------------------------------
// LayerPolicy doc wins over Module.spec.layers
// ---------------------------------------------------------------------------

describe("Conflict resolution (Phase 16)", () => {
  it("LayerPolicy doc overrides Module.spec.layers", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "dna-conflict-"));
    try {
      const k = setup(tmp, {
        manifestYaml: `apiVersion: github.com/ruinosus/dna/v1
kind: Genome
metadata:
  name: s
spec:
  layers:
    tenant:
      helix-agent: open
`,
        policies: {
          "tenant-default": `apiVersion: github.com/ruinosus/dna/policy/v1
kind: LayerPolicy
metadata:
  name: tenant-default
spec:
  layer_id: tenant
  policies:
    helix-agent: locked
`,
        },
      });
      await expect(k.writeDocument("s", "Agent", "brad", agentRaw, { layer: ["tenant", "T1"] }))
        .rejects.toThrow(/LOCKED/);
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  // Phase 16 commit 4 — legacy Module.spec.layers fallback REMOVED.
  // The previous "Module.spec.layers used when no LayerPolicy doc"
  // test is intentionally deleted. LayerPolicy docs are the only
  // source of truth for overlay rules now.
});
