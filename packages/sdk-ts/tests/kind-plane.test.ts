import { describe, expect, test } from "bun:test";
import { Kernel } from "../src/kernel";
import { KindBase } from "../src/kernel/kind_base";
import { KindRegistrationError } from "../src/kernel/errors";
// ATENÇÃO: StorageDescriptor é interface type-only; o VALOR runtime é `SD`
// (protocols.ts:213) — mesmo import que post-save-emission.test.ts usa.
import { SD } from "../src/kernel/protocols";
import type { KindPort } from "../src/kernel/protocols";

function stubKind(kindName: string, extra: Partial<KindPort> & { plane?: string } = {}): KindPort {
  return {
    apiVersion: "test.io/v1",
    kind: kindName,
    alias: `test-${kindName.toLowerCase()}`,
    isRoot: false,
    isPromptTarget: false,
    promptTargetPriority: 0,
    flattenInContext: false,
    storage: SD.yaml("items"),
    depFilters: () => null,
    getDefaultAgentName: () => null,
    getLayerPolicies: () => null,
    parse: (raw) => raw,
    describe: () => null,
    summary: () => null,
    promptTemplate: () => null,
    ...extra,
  } as KindPort;
}

describe("two-planes: plane attr + registration lint", () => {
  test("KindBase defaults plane to composition", () => {
    class C extends KindBase {}
    expect(new (C as any)().plane).toBe("composition");
  });

  test("lint rejects record + isPromptTarget", () => {
    const k = new Kernel();
    expect(() =>
      k.kind(stubKind("BadPT", { plane: "record", isPromptTarget: true })),
    ).toThrow(KindRegistrationError);
  });

  test("lint rejects record + flattenInContext", () => {
    const k = new Kernel();
    expect(() =>
      k.kind(stubKind("BadFl", { plane: "record", flattenInContext: true })),
    ).toThrow(KindRegistrationError);
  });

  test("lint rejects record + isSchemaAffecting", () => {
    const k = new Kernel();
    expect(() =>
      k.kind(stubKind("BadSA", { plane: "record", isSchemaAffecting: true })),
    ).toThrow(KindRegistrationError);
  });

  test("lint rejects record + isRoot", () => {
    const k = new Kernel();
    expect(() =>
      k.kind(stubKind("BadRoot", { plane: "record", isRoot: true })),
    ).toThrow(KindRegistrationError);
  });

  test("lint rejects invalid plane value", () => {
    const k = new Kernel();
    expect(() => k.kind(stubKind("BadVal", { plane: "cacheless" }))).toThrow(
      KindRegistrationError,
    );
  });

  test("lint accepts valid record; missing plane = composition", () => {
    const k = new Kernel();
    k.kind(stubKind("GoodRec", { plane: "record" }));
    k.kind(stubKind("GoodComp", { isPromptTarget: true }));
  });
});

describe("two-planes: record-plane inventory (F1)", () => {
  test("every SDLC kind is a record", async () => {
    const { SdlcExtension } = await import("../src/extensions/sdlc.js");
    const k = new Kernel();
    k.load(new SdlcExtension());
    const sdlcKinds = Array.from(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (k as any)._kinds.values() as IterableIterator<KindPort>,
    ).filter((kp) => kp.origin === "github.com/ruinosus/dna/sdlc");
    expect(sdlcKinds.length).toBeGreaterThan(10); // sanity: ~26 kinds
    const nonRecords = sdlcKinds
      .filter((kp) => kp.plane !== "record")
      .map((kp) => kp.kind);
    expect(nonRecords).toEqual([]);
  });
});
