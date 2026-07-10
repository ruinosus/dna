/**
 * s-dna-eval-kit — the TS EvalExtension registers the four Eval Kinds
 * from the SAME kinds/*.kind.yaml descriptors as Python (byte-identical
 * package data, enforced by tests/test_descriptor_hash_parity.py). The
 * local runner is Py-primary by design (declaration travels, execution
 * is the host's — see src/extensions/eval.ts); these tests pin the TS
 * side of the Kind contract: identity, plane, storage, dep_filters and
 * schema-validating parse.
 */
import { describe, expect, test } from "bun:test";
import { createKernelWithBuiltins } from "../src/bootstrap.js";

type Port = {
  alias: string;
  kind: string;
  apiVersion: string;
  plane?: string;
  isRuntimeArtifact?: boolean;
  storage?: { pattern?: string; container?: string };
  dependencies?(): Record<string, string> | null;
  schema(): unknown;
  parse(r: Record<string, unknown>): unknown;
  __declarative__?: boolean;
};

const API = "github.com/ruinosus/dna/eval/v1";

function kindByAlias(alias: string): Port | undefined {
  const k = createKernelWithBuiltins() as unknown as { _kinds: Map<string, Port> };
  return [...k._kinds.values()].find((x) => x.alias === alias);
}

const EXPECTED: Array<[string, string, string]> = [
  ["EvalCase", "eval-eval-case", "eval-cases"],
  ["EvalSuite", "eval-eval-suite", "eval-suites"],
  ["EvalRun", "eval-eval-run", "eval-runs"],
  ["EvalBaseline", "eval-eval-baseline", "eval-baselines"],
];

describe("EvalExtension — descriptor-backed Eval Kinds (TS twin)", () => {
  for (const [kind, alias, container] of EXPECTED) {
    test(`${kind} registers declaratively with the right identity`, () => {
      const kp = kindByAlias(alias);
      expect(kp).toBeDefined();
      expect(kp!.kind).toBe(kind);
      expect(kp!.apiVersion).toBe(API);
      expect(kp!.plane).toBe("record");
      expect(kp!.__declarative__).toBe(true);
      expect(kp!.storage?.pattern).toBe("yaml");
      expect(kp!.storage?.container).toBe(container);
    });
  }

  test("EvalRun is the only runtime artifact of the family", () => {
    expect(kindByAlias("eval-eval-run")!.isRuntimeArtifact).toBe(true);
    expect(kindByAlias("eval-eval-case")!.isRuntimeArtifact ?? false).toBe(false);
    expect(kindByAlias("eval-eval-baseline")!.isRuntimeArtifact ?? false).toBe(false);
  });

  test("EvalSuite.cases dep_filter targets the EvalCase alias", () => {
    const kp = kindByAlias("eval-eval-suite")!;
    expect(kp.dependencies?.()).toEqual({ cases: "eval-eval-case" });
  });

  test("EvalCase parse validates: valid case round-trips", () => {
    const kp = kindByAlias("eval-eval-case")!;
    const raw = {
      apiVersion: API, kind: "EvalCase", metadata: { name: "identity" },
      spec: {
        description: "identity composes",
        target: { type: "prompt", agent: "greeter" },
        checks: [{ type: "contains", value: "Helio" }],
      },
    };
    expect(kp.parse(raw)).toEqual(raw);
  });

  test("EvalCase parse rejects an upstream field that did not travel", () => {
    const kp = kindByAlias("eval-eval-case")!;
    expect(() => kp.parse({
      apiVersion: API, kind: "EvalCase", metadata: { name: "bad" },
      spec: {
        checks: [{ type: "contains", value: "x" }],
        trajectory_mode: "strict",
      },
    })).toThrow(/validation failed/);
  });

  test("EvalCase parse rejects an unknown check type", () => {
    const kp = kindByAlias("eval-eval-case")!;
    expect(() => kp.parse({
      apiVersion: API, kind: "EvalCase", metadata: { name: "bad" },
      spec: { checks: [{ type: "llm_judge", value: "be nice" }] },
    })).toThrow(/validation failed/);
  });

  test("EvalRun parse requires the ledger fields", () => {
    const kp = kindByAlias("eval-eval-run")!;
    expect(() => kp.parse({
      apiVersion: API, kind: "EvalRun", metadata: { name: "r1" },
      spec: { suite: "s1" },
    })).toThrow(/validation failed/);
  });
});
