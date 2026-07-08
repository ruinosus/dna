/**
 * Layer resolution tests — DefaultLayerResolver + await Kernel.instance() integration.
 *
 * 1:1 parity with Python test_layers scenarios.
 */

import { describe, test, expect } from "bun:test";
import { deepMerge, DefaultLayerResolver } from "../src/kernel/layer-resolver.js";
import { LayerPolicy } from "../src/kernel/protocols.js";

// ---------------------------------------------------------------------------
// deepMerge unit tests
// ---------------------------------------------------------------------------

describe("deepMerge", () => {
  test("merges nested objects", async () => {
    const base = { a: { x: 1, y: 2 }, b: "keep" };
    const overlay = { a: { y: 3, z: 4 } };
    const result = deepMerge(base, overlay);
    expect(result).toEqual({ a: { x: 1, y: 3, z: 4 }, b: "keep" });
  });

  test("replaces arrays (does not concatenate)", async () => {
    const result = deepMerge({ a: [1, 2] }, { a: [3] });
    expect(result.a).toEqual([3]);
  });

  test("adds new top-level keys", async () => {
    const result = deepMerge({ a: 1 }, { b: 2 });
    expect(result).toEqual({ a: 1, b: 2 });
  });

  test("does not mutate base", async () => {
    const base = { a: { x: 1 } };
    const overlay = { a: { x: 99 } };
    deepMerge(base, overlay);
    expect((base.a as { x: number }).x).toBe(1);
  });

  test("replaces scalar with object", async () => {
    const result = deepMerge({ a: "string" }, { a: { nested: true } });
    expect(result.a).toEqual({ nested: true });
  });

  test("replaces object with scalar", async () => {
    const result = deepMerge({ a: { nested: true } }, { a: "string" });
    expect(result.a).toBe("string");
  });
});

// ---------------------------------------------------------------------------
// DefaultLayerResolver unit tests
// ---------------------------------------------------------------------------

describe("DefaultLayerResolver", () => {
  const resolver = new DefaultLayerResolver();

  function fakeSource(overlays: Record<string, unknown>[]) {
    return { loadLayer: () => overlays };
  }

  // -- OPEN policy ---------------------------------------------------------

  test("open policy merges spec fields", async () => {
    const base = [
      { kind: "Agent", metadata: { name: "a" }, spec: { instruction: "base" } },
    ];
    const overlay = [
      { kind: "Agent", metadata: { name: "a" }, spec: { instruction: "override" } },
    ];
    const result = resolver.resolve(base, { t: "x" }, fakeSource(overlay), "s", {});
    expect((result[0].spec as Record<string, unknown>).instruction).toBe("override");
  });

  test("open policy deep merges nested spec", async () => {
    const base = [
      { kind: "Agent", metadata: { name: "a" }, spec: { config: { x: 1, y: 2 } } },
    ];
    const overlay = [
      { kind: "Agent", metadata: { name: "a" }, spec: { config: { y: 3, z: 4 } } },
    ];
    const result = resolver.resolve(base, { t: "x" }, fakeSource(overlay), "s", {});
    expect((result[0].spec as Record<string, unknown>).config).toEqual({ x: 1, y: 3, z: 4 });
  });

  test("open policy adds new documents", async () => {
    const base = [
      { kind: "Agent", metadata: { name: "a" }, spec: {} },
    ];
    const overlay = [
      { kind: "Agent", metadata: { name: "new" }, spec: { instruction: "new" } },
    ];
    const result = resolver.resolve(base, { t: "x" }, fakeSource(overlay), "s", {});
    expect(result.length).toBe(2);
    expect((result[1].metadata as Record<string, unknown>).name).toBe("new");
  });

  // -- LOCKED policy -------------------------------------------------------

  test("locked policy blocks spec changes", async () => {
    const base = [
      { kind: "Agent", metadata: { name: "a" }, spec: { instruction: "base" } },
    ];
    const overlay = [
      { kind: "Agent", metadata: { name: "a" }, spec: { instruction: "blocked" } },
    ];
    const result = resolver.resolve(base, { t: "x" }, fakeSource(overlay), "s", {
      Agent: LayerPolicy.LOCKED,
    });
    expect((result[0].spec as Record<string, unknown>).instruction).toBe("base");
  });

  test("locked policy blocks new documents", async () => {
    const base = [
      { kind: "Agent", metadata: { name: "a" }, spec: {} },
    ];
    const overlay = [
      { kind: "Agent", metadata: { name: "new" }, spec: { instruction: "new" } },
    ];
    const result = resolver.resolve(base, { t: "x" }, fakeSource(overlay), "s", {
      Agent: LayerPolicy.LOCKED,
    });
    expect(result.length).toBe(1);
  });

  // -- RESTRICTED policy ---------------------------------------------------

  test("restricted policy allows existing fields only", async () => {
    const base = [
      { kind: "Agent", metadata: { name: "a" }, spec: { instruction: "base" } },
    ];
    const overlay = [
      {
        kind: "Agent",
        metadata: { name: "a" },
        spec: { instruction: "updated", newField: "blocked" },
      },
    ];
    const result = resolver.resolve(base, { t: "x" }, fakeSource(overlay), "s", {
      Agent: LayerPolicy.RESTRICTED,
    });
    expect((result[0].spec as Record<string, unknown>).instruction).toBe("updated");
    expect((result[0].spec as Record<string, unknown>).newField).toBeUndefined();
  });

  test("restricted policy blocks new documents", async () => {
    const base = [
      { kind: "Agent", metadata: { name: "a" }, spec: {} },
    ];
    const overlay = [
      { kind: "Agent", metadata: { name: "new" }, spec: { instruction: "new" } },
    ];
    const result = resolver.resolve(base, { t: "x" }, fakeSource(overlay), "s", {
      Agent: LayerPolicy.RESTRICTED,
    });
    expect(result.length).toBe(1);
  });

  test("restricted policy deep merges existing nested keys", async () => {
    const base = [
      { kind: "Agent", metadata: { name: "a" }, spec: { config: { x: 1, y: 2 } } },
    ];
    const overlay = [
      { kind: "Agent", metadata: { name: "a" }, spec: { config: { y: 99 } } },
    ];
    const result = resolver.resolve(base, { t: "x" }, fakeSource(overlay), "s", {
      Agent: LayerPolicy.RESTRICTED,
    });
    expect((result[0].spec as Record<string, unknown>).config).toEqual({ x: 1, y: 99 });
  });

  // -- Policy resolution by alias ------------------------------------------

  test("resolves policy by kind alias suffix", async () => {
    const base = [
      { kind: "Agent", metadata: { name: "a" }, spec: { instruction: "base" } },
    ];
    const overlay = [
      { kind: "Agent", metadata: { name: "a" }, spec: { instruction: "locked" } },
    ];
    const result = resolver.resolve(base, { t: "x" }, fakeSource(overlay), "s", {
      "helix-agent": LayerPolicy.LOCKED,
    });
    expect((result[0].spec as Record<string, unknown>).instruction).toBe("base");
  });

  test("defaults to OPEN for unknown kinds", async () => {
    const base = [
      { kind: "CustomThing", metadata: { name: "c" }, spec: { val: "old" } },
    ];
    const overlay = [
      { kind: "CustomThing", metadata: { name: "c" }, spec: { val: "new" } },
    ];
    const result = resolver.resolve(base, { t: "x" }, fakeSource(overlay), "s", {
      Agent: LayerPolicy.LOCKED,
    });
    expect((result[0].spec as Record<string, unknown>).val).toBe("new");
  });

  // -- Empty overlay -------------------------------------------------------

  test("empty overlay spec is a no-op", async () => {
    const base = [
      { kind: "Agent", metadata: { name: "a" }, spec: { instruction: "base" } },
    ];
    const overlay = [
      { kind: "Agent", metadata: { name: "a" }, spec: {} },
    ];
    const result = resolver.resolve(base, { t: "x" }, fakeSource(overlay), "s", {});
    expect((result[0].spec as Record<string, unknown>).instruction).toBe("base");
  });

  test("no overlay docs returns base unchanged", async () => {
    const base = [
      { kind: "Agent", metadata: { name: "a" }, spec: { instruction: "base" } },
    ];
    const result = resolver.resolve(base, { t: "x" }, fakeSource([]), "s", {});
    expect(result).toEqual(base);
  });

  // -- Multiple layers -----------------------------------------------------

  test("multiple layers are applied in order", async () => {
    const base = [
      { kind: "Agent", metadata: { name: "a" }, spec: { instruction: "v0" } },
    ];
    // Source returns different overlays per call
    let callCount = 0;
    const multiSource = {
      loadLayer: () => {
        callCount++;
        return [
          {
            kind: "Agent",
            metadata: { name: "a" },
            spec: { instruction: `v${callCount}` },
          },
        ];
      },
    };
    const result = resolver.resolve(
      base,
      { layer1: "a", layer2: "b" },
      multiSource,
      "s",
      {},
    );
    // Second layer wins
    expect((result[0].spec as Record<string, unknown>).instruction).toBe("v2");
  });

  // -- Does not mutate inputs ----------------------------------------------

  test("does not mutate base documents", async () => {
    const base = [
      { kind: "Agent", metadata: { name: "a" }, spec: { instruction: "base" } },
    ];
    const overlay = [
      { kind: "Agent", metadata: { name: "a" }, spec: { instruction: "changed" } },
    ];
    resolver.resolve(base, { t: "x" }, fakeSource(overlay), "s", {});
    expect((base[0].spec as Record<string, unknown>).instruction).toBe("base");
  });
});
