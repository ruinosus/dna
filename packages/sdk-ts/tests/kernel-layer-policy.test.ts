import { describe, it, expect } from "bun:test";
import type { WritableSourcePort } from "../src/kernel/protocols";

describe("WritableSourcePort signature — layer opts", () => {
  it("saveDocument accepts optional opts.layer", async () => {
    // Compile-time check. If tsc rejects this, the type is wrong.
    const stub: Pick<WritableSourcePort, "saveDocument"> = {
      async saveDocument(
        _scope: string, _kind: string, _name: string, _raw: unknown,
        _opts?: { author?: string; layer?: [string, string] },
      ) { return "v1"; },
    };
    expect(typeof stub.saveDocument).toBe("function");
  });

  it("deleteDocument accepts optional opts.layer", async () => {
    const stub: Pick<WritableSourcePort, "deleteDocument"> = {
      async deleteDocument(
        _scope: string, _kind: string, _name: string,
        _opts?: { layer?: [string, string] },
      ) {},
    };
    expect(typeof stub.deleteDocument).toBe("function");
  });
});

import { Kernel } from "../src/kernel";
import { HelixExtension } from "../src/extensions/helix";
import { FilesystemSource, FilesystemCache } from "../src/adapters/filesystem";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

function setupKernel(tmp: string, moduleYaml: string) {
  const scopeDir = join(tmp, "s");
  mkdirSync(scopeDir, { recursive: true });
  writeFileSync(join(scopeDir, "Genome.yaml"), moduleYaml);
  const k = new Kernel();
  k.load(new HelixExtension() as any);
  const src = new FilesystemSource(tmp) as any;
  k.source(src);
  // FilesystemSource does NOT implement WritableSourcePort in TS SDK today.
  // The policy check runs BEFORE the adapter call, so a stub suffices.
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

describe("LayerPolicy enforcement — TS", () => {
  // Phase 16 — overlay policy now lives in LayerPolicy docs at
  // ``<scope>/policies/<id>.yaml``. The legacy ``Module.spec.layers``
  // path is gone. ``setupKernel`` writes only the Module/Genome root;
  // tests that need a policy write a LayerPolicy file alongside.
  function writeLayerPolicy(tmp: string, layerId: string, policies: Record<string, string>) {
    const dir = join(tmp, "s", "policies");
    mkdirSync(dir, { recursive: true });
    const lines = [
      "apiVersion: github.com/ruinosus/dna/policy/v1",
      "kind: LayerPolicy",
      "metadata:",
      `  name: ${layerId}-default`,
      "spec:",
      `  layer_id: ${layerId}`,
      "  policies:",
      ...Object.entries(policies).map(([k, v]) => `    ${k}: ${v}`),
    ];
    writeFileSync(join(dir, `${layerId}.yaml`), lines.join("\n") + "\n");
  }

  it("LOCKED rejects any write", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "dna-pol-locked-"));
    try {
      const k = setupKernel(tmp, `apiVersion: github.com/ruinosus/dna/v1
kind: Genome
metadata:
  name: s
spec: {}
`);
      writeLayerPolicy(tmp, "tenant", { "helix-agent": "locked" });
      const raw = { apiVersion: "github.com/ruinosus/dna/helix/v1", kind: "Agent", metadata: { name: "x" }, spec: {} };
      await expect(k.writeDocument("s", "Agent", "x", raw, { layer: ["tenant", "T1"] }))
        .rejects.toThrow(/LOCKED/);
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  it("OPEN allows write", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "dna-pol-open-"));
    try {
      const k = setupKernel(tmp, `apiVersion: github.com/ruinosus/dna/v1
kind: Genome
metadata:
  name: s
spec: {}
`);
      writeLayerPolicy(tmp, "tenant", { "helix-agent": "open" });
      const raw = { apiVersion: "github.com/ruinosus/dna/helix/v1", kind: "Agent", metadata: { name: "x" }, spec: {} };
      // Should not throw
      await k.writeDocument("s", "Agent", "x", raw, { layer: ["tenant", "T1"] });
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  it("no Module doc defaults to OPEN (no exception)", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "dna-pol-none-"));
    try {
      const k = setupKernel(tmp, `apiVersion: github.com/ruinosus/dna/v1
kind: Genome
metadata:
  name: s
spec: {}
`);
      const raw = { apiVersion: "github.com/ruinosus/dna/helix/v1", kind: "Agent", metadata: { name: "x" }, spec: {} };
      await k.writeDocument("s", "Agent", "x", raw, { layer: ["tenant", "T1"] });
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });
});
