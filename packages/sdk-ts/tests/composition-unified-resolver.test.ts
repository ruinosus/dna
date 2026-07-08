/**
 * s-unify-composition-subsystems (TS twin of Py
 * test_composition_unified_resolver.py) — every dep_filter reader
 * consumes the SAME canonical resolver (`resolveDepFilterTargetOver`):
 * a legacy `kind=<Name>` filter and an alias filter resolve IDENTICALLY
 * in `mi.composition.validate()`, `iterDocDeps` and the Kernel's
 * `resolveDepFilterTarget`. The record-plane rule is ONE rule: ref in
 * index → resolved; absent + record target → deferred (never missing).
 */
import { describe, expect, test } from "bun:test";
import { ManifestInstance } from "../src/kernel/instance.js";
import { Document } from "../src/kernel/document.js";
import { resolveDepFilterTargetOver } from "../src/kernel/kind-registry.js";
import type { KindPort } from "../src/kernel/protocols.js";

const API = "test.io/v1";

function kp(partial: Record<string, unknown>): KindPort {
  return {
    apiVersion: API,
    depFilters: () => null,
    summary: () => null,
    ...partial,
  } as unknown as KindPort;
}

const targetKp = kp({ kind: "TargetLike", alias: "test-targetlike" });
const recordKp = kp({ kind: "RecordLike", alias: "test-recordlike", plane: "record" });
const consumerKp = kp({
  kind: "ConsumerLike",
  alias: "test-consumerlike",
  depFilters: () => ({
    by_alias: "test-targetlike",
    by_legacy: "kind=TargetLike",
    rec: "test-recordlike",
  }),
});

function kindsMap(): Map<string, KindPort> {
  return new Map([
    [`${API}\0TargetLike`, targetKp],
    [`${API}\0RecordLike`, recordKp],
    [`${API}\0ConsumerLike`, consumerKp],
  ]);
}

function doc(kind: string, name: string, spec: Record<string, unknown> = {}): Document {
  return Document.fromRaw({ apiVersion: API, kind, metadata: { name }, spec });
}

function mi(documents: Document[]): ManifestInstance {
  return new ManifestInstance({ scope: "scope-x", documents, kinds: kindsMap() });
}

describe("unified composition resolver (s-unify-composition-subsystems)", () => {
  test("legacy kind= and alias filters resolve identically in validate()", () => {
    const instance = mi([
      doc("TargetLike", "t-1"),
      doc("ConsumerLike", "c-1", { by_alias: "t-1", by_legacy: "t-1" }),
    ]);
    const result = instance.composition.validate();
    expect(result.resolved.some((r) => r.includes("by_alias=t-1"))).toBe(true);
    expect(result.resolved.some((r) => r.includes("by_legacy=t-1"))).toBe(true);
    expect(result.missing).toEqual([]);
    expect(result.warnings).toEqual([]);
  });

  test("iterDocDeps resolves legacy kind= through the same resolver", () => {
    const instance = mi([
      doc("TargetLike", "t-1"),
      doc("ConsumerLike", "c-1", { by_alias: "t-1", by_legacy: "t-1" }),
    ]);
    const consumer = instance.documents.find((d) => d.kind === "ConsumerLike")!;
    const deps = instance.composition.iterDocDeps(consumer);
    const byLabel = Object.fromEntries(deps.map((d) => [d.label, d.targetKind]));
    expect(byLabel.by_alias).toBe("TargetLike");
    expect(byLabel.by_legacy).toBe("TargetLike");
  });

  test("resolveDepFilterTargetOver is the shared implementation", () => {
    const kinds = kindsMap();
    expect(resolveDepFilterTargetOver(kinds, "test-targetlike")).toBe(targetKp);
    expect(resolveDepFilterTargetOver(kinds, "kind=TargetLike")).toBe(targetKp);
    expect(resolveDepFilterTargetOver(kinds, "nope")).toBeNull();
  });

  test("record rule: in-index resolves, absent defers (never missing)", () => {
    // Record present in the doc set (source-plane shape) → resolved.
    const withRecord = mi([
      doc("TargetLike", "t-1"),
      doc("RecordLike", "r-1"),
      doc("ConsumerLike", "c-1", { by_alias: "t-1", by_legacy: "t-1", rec: "r-1" }),
    ]).composition.validate();
    expect(withRecord.resolved.some((r) => r.includes("rec=r-1"))).toBe(true);
    expect(withRecord.missing).toEqual([]);

    // Record absent (MI-plane shape — records excluded) → deferred.
    const withoutRecord = mi([
      doc("TargetLike", "t-1"),
      doc("ConsumerLike", "c-1", { by_alias: "t-1", by_legacy: "t-1", rec: "r-1" }),
    ]).composition.validate();
    expect(withoutRecord.deferred.some((d) => d.includes("rec=r-1"))).toBe(true);
    expect(withoutRecord.missing).toEqual([]);
  });
});
