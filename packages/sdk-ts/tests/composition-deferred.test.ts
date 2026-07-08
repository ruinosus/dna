/**
 * Two-planes F2.5 Task 2 (TS twin of Py test_mi_record_exclusion):
 * CompositionEngine.validate() defers refs whose TARGET Kind is
 * plane="record" — they are NOT missing (spec D6). Records are excluded
 * from the MI materialization on the Py side; an index check would
 * report false-missing (e.g. Mitigation→Finding).
 */
import { describe, expect, test } from "bun:test";
import { ManifestInstance } from "../src/kernel/instance.js";
import { Document } from "../src/kernel/document.js";
import { isCompositionValid, type KindPort } from "../src/kernel/protocols.js";

const API = "test.io/v1";

function kp(partial: Record<string, unknown>): KindPort {
  return {
    apiVersion: API,
    depFilters: () => null,
    ...partial,
  } as unknown as KindPort;
}

const mitigationKp = kp({
  kind: "MitigationLike",
  alias: "test-mitigationlike",
  depFilters: () => ({ story: "test-storylike", agent: "test-agentlike" }),
});
const storyKp = kp({ kind: "StoryLike", alias: "test-storylike", plane: "record" });
const agentKp = kp({ kind: "AgentLike", alias: "test-agentlike" });

function kindsMap(): Map<string, KindPort> {
  return new Map([
    [`${API}\0MitigationLike`, mitigationKp],
    [`${API}\0StoryLike`, storyKp],
    [`${API}\0AgentLike`, agentKp],
  ]);
}

function doc(kind: string, name: string, spec: Record<string, unknown> = {}): Document {
  return Document.fromRaw({ apiVersion: API, kind, metadata: { name }, spec });
}

function mi(documents: Document[]): ManifestInstance {
  return new ManifestInstance({ scope: "scope-x", documents, kinds: kindsMap() });
}

describe("CompositionEngine deferred (two-planes F2.5)", () => {
  test("record ref is deferred, not missing; valid stays true", () => {
    const instance = mi([
      doc("AgentLike", "a-1"),
      doc("MitigationLike", "m-1", { story: "s-77", agent: "a-1" }),
    ]);
    const result = instance.composition.validate();
    expect(result.deferred.some((d) => d.includes("s-77"))).toBe(true);
    expect(result.missing.some((m) => m.includes("s-77"))).toBe(false);
    expect(result.resolved.some((r) => r.includes("a-1"))).toBe(true);
    expect(isCompositionValid(result)).toBe(true);
  });

  test("missing composition ref still reported missing", () => {
    const instance = mi([
      doc("MitigationLike", "m-1", { story: "s-77", agent: "a-ghost" }),
    ]);
    const result = instance.composition.validate();
    expect(result.missing.some((m) => m.includes("a-ghost"))).toBe(true);
    expect(isCompositionValid(result)).toBe(false);
  });

  test("no record refs → deferred empty", () => {
    const instance = mi([
      doc("AgentLike", "a-1"),
      doc("MitigationLike", "m-1", { agent: "a-1" }),
    ]);
    const result = instance.composition.validate();
    expect(result.deferred).toEqual([]);
  });
});
