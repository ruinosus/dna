import { describe, it, expect } from "bun:test";
import { LayerPolicyViolationError } from "../src/kernel/protocols";

describe("LayerPolicyViolationError", () => {
  it("is an Error subclass", async () => {
    const err = new LayerPolicyViolationError("test reason");
    expect(err instanceof Error).toBe(true);
    expect(err.message).toBe("test reason");
    expect(err.name).toBe("LayerPolicyViolationError");
  });
});

describe("Kernel.writeDocument forwards layer to adapter", () => {
  it("forwards layer opt to saveDocument", async () => {
    const { Kernel } = await import("../src/kernel");
    const k = new Kernel();
    const calls: any[] = [];
    // Minimal WritableSourcePort-shaped stub
    const fakeSrc: any = {
      async saveDocument(scope: string, kind: string, name: string, raw: unknown, opts?: any) {
        calls.push({ method: "save", scope, kind, name, opts });
        return "v1";
      },
      async deleteDocument(scope: string, kind: string, name: string, opts?: any) {
        calls.push({ method: "delete", scope, kind, name, opts });
      },
      async loadBootstrapDocs() { return []; },
      async loadDocument() { return null; },
      async loadLayer() { return []; },
      async capabilities() { return {}; },
      async listVersions() { return []; },
      async getVersion() { return null; },
      async publish() { return "v1"; },
      async loadDrafts() { return []; },
      async listScopes() { return []; },
      async saveManifest() { return "v1"; },
    };
    k.source(fakeSrc);
    k.writableSource(fakeSrc);
    await k.writeDocument("s", "K", "n",
      { apiVersion: "x", kind: "K", metadata: { name: "n" }, spec: {} },
      { layer: ["tenant", "T1"] },
    );
    expect(calls.length).toBe(1);
    // Phase 2a: kernel translates layer=("tenant",X) → tenant=X at the
    // boundary, so the adapter receives opts.tenant (not opts.layer).
    expect(calls[0].opts?.tenant).toBe("T1");
    expect(calls[0].opts?.layer).toBeUndefined();
  });

  it("forwards layer opt to deleteDocument", async () => {
    const { Kernel } = await import("../src/kernel");
    const k = new Kernel();
    const calls: any[] = [];
    const fakeSrc: any = {
      async saveDocument() { return "v1"; },
      async deleteDocument(scope: string, kind: string, name: string, opts?: any) {
        calls.push({ method: "delete", scope, kind, name, opts });
      },
      async loadBootstrapDocs() { return []; },
      async loadDocument() { return null; },
      async loadLayer() { return []; },
      async capabilities() { return {}; },
      async listVersions() { return []; },
      async getVersion() { return null; },
      async publish() { return "v1"; },
      async loadDrafts() { return []; },
      async listScopes() { return []; },
      async saveManifest() { return "v1"; },
    };
    k.source(fakeSrc);
    k.writableSource(fakeSrc);
    await k.deleteDocument("s", "K", "n", { layer: ["tenant", "T1"] });
    expect(calls.length).toBe(1);
    // Phase 2a: kernel translates layer=("tenant",X) → tenant=X at the
    // boundary, so the adapter receives opts.tenant (not opts.layer).
    expect(calls[0].opts?.tenant).toBe("T1");
    expect(calls[0].opts?.layer).toBeUndefined();
  });
});
