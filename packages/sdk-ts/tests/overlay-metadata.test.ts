/**
 * Phase 2 overlay-metadata stamping — TypeScript twin of
 * python/tests/test_overlay_metadata.py.
 *
 * Studio surfaces ``metadata.has_overlay`` + ``metadata.overlay_fields``
 * on the editors so the user knows whether they're seeing a
 * base+overlay merge and which fields are tenant-specific.
 */

import { describe, test, expect } from "bun:test";
import {
  DefaultLayerResolver,
  type LayerSource,
} from "../src/kernel/layer-resolver.js";
import { LayerPolicy } from "../src/kernel/protocols.js";

class FakeSource implements LayerSource {
  constructor(
    private layers: Record<string, Record<string, unknown>[]>,
  ) {}
  loadLayer(_scope: string, layerId: string, value: string) {
    return this.layers[`${layerId}=${value}`] ?? [];
  }
}

const baseDoc = (): Record<string, unknown> => ({
  apiVersion: "github.com/ruinosus/dna/eval/v1",
  kind: "EvalCase",
  metadata: { name: "fairness-bias" },
  spec: {
    prompt: "base prompt",
    expected_keywords: ["fairness", "bias"],
    forbidden_keywords: ["gender"],
  },
});

// ---------------------------------------------------------------------------
// OPEN policy
// ---------------------------------------------------------------------------

describe("DefaultLayerResolver — overlay metadata (OPEN)", () => {
  test("stamps has_overlay + overlay_fields with overridden keys", () => {
    const resolver = new DefaultLayerResolver();
    const overlay = {
      kind: "EvalCase",
      metadata: { name: "fairness-bias" },
      spec: {
        forbidden_keywords: ["gender", "pronoun"],
        prompt: "tenant prompt",
      },
    };
    const src = new FakeSource({ "tenant=acme": [overlay] });
    const result = resolver.resolve(
      [baseDoc()],
      { tenant: "acme" },
      src,
      "hr-screening",
      {},
    );
    expect(result.length).toBe(1);
    const md = result[0].metadata as Record<string, unknown>;
    expect(md.has_overlay).toBe(true);
    expect((md.overlay_fields as string[]).sort()).toEqual([
      "forbidden_keywords",
      "prompt",
    ]);
    const spec = result[0].spec as Record<string, unknown>;
    expect(spec.forbidden_keywords).toEqual(["gender", "pronoun"]);
    expect(spec.prompt).toBe("tenant prompt");
    expect(spec.expected_keywords).toEqual(["fairness", "bias"]);
  });

  test("no overlay → no metadata stamp", () => {
    const resolver = new DefaultLayerResolver();
    const src = new FakeSource({});
    const result = resolver.resolve(
      [baseDoc()],
      { tenant: "acme" },
      src,
      "hr-screening",
      {},
    );
    const md = result[0].metadata as Record<string, unknown>;
    expect(md.has_overlay === true).toBe(false);
    expect(md.overlay_fields).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Overlay-only add
// ---------------------------------------------------------------------------

describe("DefaultLayerResolver — overlay-only add", () => {
  test("new doc gets has_overlay=true, overlay_fields=null sentinel", () => {
    const resolver = new DefaultLayerResolver();
    const overlayOnly = {
      apiVersion: "github.com/ruinosus/dna/eval/v1",
      kind: "EvalCase",
      metadata: { name: "tenant-only-case" },
      spec: { prompt: "acme exclusive" },
    };
    const src = new FakeSource({ "tenant=acme": [overlayOnly] });
    const result = resolver.resolve(
      [baseDoc()],
      { tenant: "acme" },
      src,
      "hr-screening",
      {},
    );
    const added = result.find(
      (d) =>
        ((d.metadata as Record<string, unknown>)?.name as string) ===
        "tenant-only-case",
    )!;
    const md = added.metadata as Record<string, unknown>;
    expect(md.has_overlay).toBe(true);
    expect(md.overlay_fields).toBe(null);
    // Base doc untouched.
    const baseMatch = result.find(
      (d) =>
        ((d.metadata as Record<string, unknown>)?.name as string) ===
        "fairness-bias",
    )!;
    expect((baseMatch.metadata as Record<string, unknown>).has_overlay).toBe(
      undefined,
    );
  });
});

// ---------------------------------------------------------------------------
// RESTRICTED policy
// ---------------------------------------------------------------------------

describe("DefaultLayerResolver — overlay metadata (RESTRICTED)", () => {
  test("stamps only keys that actually merged (drops new keys)", () => {
    const resolver = new DefaultLayerResolver();
    const overlay = {
      kind: "EvalCase",
      metadata: { name: "fairness-bias" },
      spec: {
        forbidden_keywords: ["gender", "pronoun"],
        new_field: "value", // not in base — restricted drops it
      },
    };
    const src = new FakeSource({ "tenant=acme": [overlay] });
    const result = resolver.resolve(
      [baseDoc()],
      { tenant: "acme" },
      src,
      "hr-screening",
      { EvalCase: LayerPolicy.RESTRICTED },
    );
    const md = result[0].metadata as Record<string, unknown>;
    expect(md.overlay_fields).toEqual(["forbidden_keywords"]);
    const spec = result[0].spec as Record<string, unknown>;
    expect("new_field" in spec).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// LOCKED policy
// ---------------------------------------------------------------------------

describe("DefaultLayerResolver — overlay metadata (LOCKED)", () => {
  test("locked doc has no overlay metadata", () => {
    const resolver = new DefaultLayerResolver();
    const overlay = {
      kind: "EvalCase",
      metadata: { name: "fairness-bias" },
      spec: { forbidden_keywords: ["gender", "pronoun"] },
    };
    const src = new FakeSource({ "tenant=acme": [overlay] });
    // Silence the warn from locked policy.
    const origWarn = console.warn;
    console.warn = () => {};
    try {
      const result = resolver.resolve(
        [baseDoc()],
        { tenant: "acme" },
        src,
        "hr-screening",
        { EvalCase: LayerPolicy.LOCKED },
      );
      const md = result[0].metadata as Record<string, unknown>;
      expect(md.has_overlay === true).toBe(false);
      const spec = result[0].spec as Record<string, unknown>;
      expect(spec.forbidden_keywords).toEqual(["gender"]);
    } finally {
      console.warn = origWarn;
    }
  });
});

// ---------------------------------------------------------------------------
// Multi-layer dimension union
// ---------------------------------------------------------------------------

describe("DefaultLayerResolver — multi-layer overlay metadata", () => {
  test("unions overlay_fields across layer dimensions", () => {
    const resolver = new DefaultLayerResolver();
    const tenantOverlay = {
      kind: "EvalCase",
      metadata: { name: "fairness-bias" },
      spec: { forbidden_keywords: ["gender", "pronoun"] },
    };
    const envOverlay = {
      kind: "EvalCase",
      metadata: { name: "fairness-bias" },
      spec: { prompt: "env-specific prompt" },
    };
    const src = new FakeSource({
      "tenant=acme": [tenantOverlay],
      "env=prod": [envOverlay],
    });
    const result = resolver.resolve(
      [baseDoc()],
      { tenant: "acme", env: "prod" },
      src,
      "hr-screening",
      {},
    );
    const md = result[0].metadata as Record<string, unknown>;
    expect(md.has_overlay).toBe(true);
    expect((md.overlay_fields as string[]).sort()).toEqual([
      "forbidden_keywords",
      "prompt",
    ]);
  });
});
