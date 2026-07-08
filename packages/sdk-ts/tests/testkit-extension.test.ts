/**
 * testkit TS twin (parity with Python) — TestGuide + TestRun artifact Kinds.
 */
import { describe, expect, test } from "bun:test";
import { createKernelWithBuiltins } from "../src/bootstrap.js";
import { TestkitExtension } from "../src/extensions/testkit.js";
import type { KindPort } from "../src/kernel/protocols.js";

function kindByAlias(alias: string) {
  const k = createKernelWithBuiltins() as unknown as {
    _kinds: Map<string, { alias: string; kind: string; apiVersion: string; storage?: { pattern?: string; container?: string } }>;
  };
  return [...k._kinds.values()].find((x) => x.alias === alias);
}

describe("TestkitExtension", () => {
  test("registers TestGuide (yaml, GLOBAL, github.com/ruinosus/dna/testkit/v1)", () => {
    const kp = kindByAlias("testkit-test-guide");
    expect(kp).toBeDefined();
    expect(kp!.kind).toBe("TestGuide");
    expect(kp!.apiVersion).toBe("github.com/ruinosus/dna/testkit/v1");
    expect(kp!.storage?.pattern).toBe("yaml");
    expect(kp!.storage?.container).toBe("test-guides");
  });

  test("registers TestRun (yaml, GLOBAL, github.com/ruinosus/dna/testkit/v1)", () => {
    const kp = kindByAlias("testkit-test-run");
    expect(kp).toBeDefined();
    expect(kp!.kind).toBe("TestRun");
    expect(kp!.apiVersion).toBe("github.com/ruinosus/dna/testkit/v1");
    expect(kp!.storage?.pattern).toBe("yaml");
    expect(kp!.storage?.container).toBe("test-runs");
  });

  test("kinds() parity", () => {
    const aliases = new TestkitExtension().kinds().map((k: KindPort) => k.alias);
    expect(aliases).toEqual(["testkit-test-guide", "testkit-test-run"]);
  });

  test("kind_of_test enum excludes unit", () => {
    const kp = new TestkitExtension().kinds()[0]!;
    const schema = kp.schema!() as Record<string, any>;
    const enumv = schema.properties.kind_of_test.enum;
    expect(new Set(enumv)).toEqual(new Set(["manual", "smoke", "e2e", "regression", "integration"]));
    expect(enumv).not.toContain("unit");
  });

  test("TestRun outcome enum", () => {
    const kp = new TestkitExtension().kinds()[1]!;
    const schema = kp.schema!() as Record<string, any>;
    expect(new Set(schema.properties.outcome.enum)).toEqual(
      new Set(["pass", "fail", "partial", "blocked"]),
    );
  });
});
