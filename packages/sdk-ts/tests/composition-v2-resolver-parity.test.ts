/**
 * s-composition-v2-ts-twin — Py↔TS parity for the Composition Engine V2 resolver
 * module (kernel/resolver.ts twin of kernel/resolver.py).
 *
 * Mirrors the PURE-function tests from
 * packages/sdk-py/tests/test_composition_v2_resolver.py with IDENTICAL input
 * vectors → IDENTICAL outputs:
 *   - test_bootstrap_kinds_constant
 *   - test_v1_inheritable_constant
 *   - test_field_level_merge_pure
 *   - test_override_full_merge_pure
 *   - test_override_full_all_miss
 * plus serialize() wire-shape parity (snake_case keys, matching Python
 * ResolvedDocument.serialize / ResolutionPath.serialize).
 *
 * The Kernel.resolve_document ORCHESTRATION (parent-chain walk, observers,
 * granular cache) lives on the Python Kernel class and is a separate consumer
 * layer — out of scope for the resolver-module twin the story names.
 */
import { describe, expect, test } from "bun:test";
import {
  BOOTSTRAP_KINDS,
  DEFAULT_INHERITABLE_KINDS_V1,
  MAX_RESOLUTION_DEPTH,
  ResolutionLayer,
  ResolutionPath,
  ResolvedDocument,
  mergeFieldLevel,
  mergeOverrideFull,
  type Contribution,
} from "../src/kernel/resolver.js";

describe("resolver constants (parity with resolver.py)", () => {
  test("BOOTSTRAP_KINDS", () => {
    expect(BOOTSTRAP_KINDS.has("Genome")).toBe(true);
    expect(BOOTSTRAP_KINDS.has("LayerPolicy")).toBe(true);
    expect(BOOTSTRAP_KINDS.has("KindDefinition")).toBe(true);
  });

  test("DEFAULT_INHERITABLE_KINDS_V1", () => {
    expect(DEFAULT_INHERITABLE_KINDS_V1.has("Agent")).toBe(true);
    expect(DEFAULT_INHERITABLE_KINDS_V1.has("LottieAsset")).toBe(true);
    expect(DEFAULT_INHERITABLE_KINDS_V1.has("Story")).toBe(false);
  });

  test("MAX_RESOLUTION_DEPTH", () => {
    expect(MAX_RESOLUTION_DEPTH).toBe(16);
  });
});

describe("mergeFieldLevel (parity: test_field_level_merge_pure)", () => {
  test("local field wins, platform-only field inherited, fields_by_origin tracked", () => {
    const L1 = new ResolutionLayer({ scope: "child", tenant: null, found: true });
    const L2 = new ResolutionLayer({ scope: "_lib", tenant: null, found: true });
    const contribs: Contribution[] = [
      [L1, { apiVersion: "v1", kind: "Agent", metadata: { name: "jarvis" }, spec: { model: "gpt-5.4" } }],
      [L2, { apiVersion: "v1", kind: "Agent", metadata: { name: "jarvis" }, spec: { model: "gpt-5", persona: "jarvis-style" } }],
    ];
    const [merged, primary, fields] = mergeFieldLevel(contribs);
    expect(merged).not.toBeNull();
    const spec = (merged!.spec as Record<string, unknown>);
    expect(spec.model).toBe("gpt-5.4"); // local won
    expect(spec.persona).toBe("jarvis-style"); // inherited
    expect(primary!.scope).toBe("child"); // metadata from highest priority
    expect(fields["spec.model"]).toBe("child");
    expect(fields["spec.persona"]).toBe("_lib");
    // envelope carried from primary
    expect(merged!.apiVersion).toBe("v1");
    expect(merged!.kind).toBe("Agent");
    expect(merged!.metadata).toEqual({ name: "jarvis" });
  });

  test("all-null contributions → [null, null, {}]", () => {
    const L1 = new ResolutionLayer({ scope: "child", tenant: null, found: false });
    const [merged, primary, fields] = mergeFieldLevel([[L1, null]]);
    expect(merged).toBeNull();
    expect(primary).toBeNull();
    expect(fields).toEqual({});
  });

  test("non-object spec layer skipped silently", () => {
    const L1 = new ResolutionLayer({ scope: "child", tenant: null, found: true });
    const L2 = new ResolutionLayer({ scope: "_lib", tenant: null, found: true });
    const contribs: Contribution[] = [
      [L1, { apiVersion: "v1", kind: "K", metadata: {}, spec: "not-a-dict" }],
      [L2, { apiVersion: "v1", kind: "K", metadata: {}, spec: { a: 1 } }],
    ];
    const [merged] = mergeFieldLevel(contribs);
    // L1 is primary (envelope), but its non-dict spec is skipped; L2's spec merges in.
    expect((merged!.spec as Record<string, unknown>).a).toBe(1);
  });
});

describe("mergeOverrideFull (parity: test_override_full_merge_pure / _all_miss)", () => {
  test("first non-null wins entirely (local miss → platform wins)", () => {
    const L1 = new ResolutionLayer({ scope: "child", tenant: null, found: false });
    const L2 = new ResolutionLayer({ scope: "_lib", tenant: null, found: true });
    const contribs: Contribution[] = [
      [L1, null],
      [L2, { apiVersion: "v1", spec: { variant: "platform" } }],
    ];
    const [merged, winner] = mergeOverrideFull(contribs);
    expect(merged).not.toBeNull();
    expect((merged!.spec as Record<string, unknown>).variant).toBe("platform");
    expect(winner!.scope).toBe("_lib");
  });

  test("all miss → [null, null]", () => {
    const L1 = new ResolutionLayer({ scope: "child", tenant: null, found: false });
    const L2 = new ResolutionLayer({ scope: "_lib", tenant: null, found: false });
    const [merged, winner] = mergeOverrideFull([[L1, null], [L2, null]]);
    expect(merged).toBeNull();
    expect(winner).toBeNull();
  });
});

describe("serialize() wire parity (snake_case keys = Python)", () => {
  test("ResolutionPath.serialize + effectiveLayer", () => {
    const path = new ResolutionPath([
      new ResolutionLayer({ scope: "child", tenant: null, found: false }),
      new ResolutionLayer({ scope: "_lib", tenant: null, found: true, contributed: true }),
    ]);
    expect(path.effectiveLayer!.scope).toBe("_lib");
    const obj = path.serialize();
    expect(obj.steps).toEqual([
      { scope: "child", tenant: null, found: false, contributed: false, version_sha: null },
      { scope: "_lib", tenant: null, found: true, contributed: true, version_sha: null },
    ]);
    expect(obj.effective_layer).toEqual({ scope: "_lib", tenant: null });
  });

  test("ResolvedDocument.serialize (parity: test_provenance_serializes_for_json_api)", () => {
    const path = new ResolutionPath([
      new ResolutionLayer({ scope: "_lib", tenant: null, found: true, contributed: true }),
    ]);
    const rd = new ResolvedDocument({
      doc: { apiVersion: "github.com/ruinosus/dna/test/v1", kind: "LottieAsset", metadata: { name: "X" }, spec: { variant: "v1" } },
      provenance: path,
      isInherited: true,
      contributionsByField: { "spec.variant": "_lib" },
    });
    const obj = rd.serialize();
    expect(obj.doc).not.toBeNull();
    expect(obj.is_inherited).toBe(true);
    expect((obj.provenance as Record<string, unknown>).steps).toBeDefined();
    expect(((obj.provenance as Record<string, unknown>).effective_layer as Record<string, unknown>).scope).toBe("_lib");
    expect(obj.contributions_by_field).toEqual({ "spec.variant": "_lib" });
  });

  test("effectiveLayer is null when no layer found", () => {
    const path = new ResolutionPath([new ResolutionLayer({ scope: "child", tenant: null, found: false })]);
    expect(path.effectiveLayer).toBeNull();
    expect(path.serialize().effective_layer).toBeNull();
  });
});
