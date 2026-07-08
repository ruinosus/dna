import { describe, expect, test } from "bun:test";
import { KindBase } from "../src/kernel/kind_base.js";

// Minimal concrete KindBase for testing the inherited canonicalDigest.
class TestKind extends KindBase {
  readonly apiVersion = "github.com/ruinosus/dna/test/v1";
  readonly kind = "TestKind";
  readonly alias = "test-testkind";
  readonly storage = { pattern: "yaml", container: "tests" } as never;
}

const K = new TestKind();
const doc = (spec: Record<string, unknown>, name = "a", kind = "TestKind") =>
  ({ kind, name, spec }) as never;

describe("KindBase.canonicalDigest (s-sync-s1)", () => {
  test("invariant to key order", () => {
    expect(K.canonicalDigest(doc({ b: 1, a: 2, tools: ["x", "y"] }))).toBe(
      K.canonicalDigest(doc({ tools: ["x", "y"], a: 2, b: 1 })),
    );
  });

  test("ignores volatile fields (updated_at/version/created_at)", () => {
    const base = { model: "gpt-5-mini", instruction: "hi" };
    expect(
      K.canonicalDigest(doc({ ...base, updated_at: "T1", version: 1 })),
    ).toBe(
      K.canonicalDigest(doc({ ...base, updated_at: "T2", version: 27, created_at: "C" })),
    );
  });

  test("sensitive to real content", () => {
    expect(K.canonicalDigest(doc({ instruction: "review code" }))).not.toBe(
      K.canonicalDigest(doc({ instruction: "screen candidates" })),
    );
  });

  test("name + kind are identity", () => {
    expect(K.canonicalDigest(doc({ x: 1 }, "a"))).not.toBe(K.canonicalDigest(doc({ x: 1 }, "b")));
  });

  test("instruction_file resolved == inline; source_files is transport", () => {
    const inline = doc({ model: "m", instruction: "Review code." });
    const fileBacked = doc({
      model: "m",
      instruction: "Review code.",
      instruction_file: "instruction.md",
      source_files: { "instruction.md": "Review code.", "logo.png": "bytes" },
    });
    expect(K.canonicalDigest(inline)).toBe(K.canonicalDigest(fileBacked));
  });
});
