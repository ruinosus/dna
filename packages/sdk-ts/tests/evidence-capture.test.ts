// typescript/tests/evidence-capture.test.ts
import { describe, test, expect } from "bun:test";
import {
  computeContentHash,
  buildEvidenceDoc,
  extractSuite,
} from "../src/kernel/evidence-capture";

// ---------------------------------------------------------------------------
// computeContentHash
// ---------------------------------------------------------------------------

describe("computeContentHash", () => {
  test("canonical JSON with recursively sorted keys", async () => {
    const hash1 = await computeContentHash({ b: 2, a: 1 });
    const hash2 = await computeContentHash({ a: 1, b: 2 });
    expect(hash1).toBe(hash2);
    expect(hash1).toHaveLength(64);
  });

  test("nested objects sorted recursively", async () => {
    const hash1 = await computeContentHash({ outer: { z: 1, a: 2 }, first: 1 });
    const hash2 = await computeContentHash({ first: 1, outer: { a: 2, z: 1 } });
    expect(hash1).toBe(hash2);
  });

  test("different content different hash", async () => {
    const h1 = await computeContentHash({ a: 1 });
    const h2 = await computeContentHash({ a: 2 });
    expect(h1).not.toBe(h2);
  });

  test("handles nested arrays", async () => {
    const h = await computeContentHash({ outer: { inner: [1, 2, 3] } });
    expect(h).toHaveLength(64);
  });

  test("handles non-dict values", async () => {
    const h = await computeContentHash([1, 2, 3]);
    expect(h).toHaveLength(64);
  });

  test("deterministic across calls", async () => {
    const content = { key: "value", nested: { x: 10 } };
    expect(await computeContentHash(content)).toBe(await computeContentHash(content));
  });
});

// ---------------------------------------------------------------------------
// extractSuite
// ---------------------------------------------------------------------------

describe("extractSuite", () => {
  test("EvalRun -> spec.suite", async () => {
    expect(extractSuite("EvalRun", { suite: "smoke" }, null)).toBe("smoke");
  });

  test("Finding -> spec.source", async () => {
    expect(extractSuite("Finding", { source: "reads" }, null)).toBe("reads");
  });

  test("EvalBaseline -> spec.suite", async () => {
    expect(extractSuite("EvalBaseline", { suite: "baseline-1" }, null)).toBe(
      "baseline-1",
    );
  });

  test("explicit overrides spec", async () => {
    expect(extractSuite("EvalRun", { suite: "old" }, "explicit")).toBe(
      "explicit",
    );
  });

  test("non-eval kind -> null", async () => {
    expect(extractSuite("Agent", {}, null)).toBeNull();
  });

  test("eval kind without suite or source -> null", async () => {
    expect(extractSuite("EvalRun", {}, null)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// buildEvidenceDoc
// ---------------------------------------------------------------------------

describe("buildEvidenceDoc", () => {
  test("creates valid Evidence Kind shape", async () => {
    const doc = await buildEvidenceDoc({
      eventType: "eval_run_completed",
      kind: "EvalRun",
      name: "run1",
      spec: { suite: "smoke", passed: 5 },
      author: "pytest",
    });
    expect(doc.apiVersion).toBe("github.com/ruinosus/dna/evidence/v1");
    expect(doc.kind).toBe("Evidence");
    expect((doc.spec as any).event_type).toBe("eval_run_completed");
    expect((doc.spec as any).sha256).toHaveLength(64);
    expect((doc.spec as any).document_ref).toBe("EvalRun:run1");
    expect((doc.spec as any).suite).toBe("smoke");
  });

  test("sha256 matches computeContentHash", async () => {
    const spec = { important: "data" };
    const doc = await buildEvidenceDoc({
      eventType: "custom",
      kind: "Item",
      name: "item1",
      spec,
      author: "test",
    });
    expect((doc.spec as any).sha256).toBe(await computeContentHash(spec));
  });

  test("metadata name includes event type and hash prefix", async () => {
    const doc = await buildEvidenceDoc({
      eventType: "finding_created",
      kind: "Finding",
      name: "f1",
      spec: { source: "reads", severity: "high" },
      author: "system",
    });
    const name = (doc.metadata as any).name as string;
    expect(name).toMatch(/^ev-finding_created-[a-f0-9]{12}$/);
  });

  test("captured_at is ISO date string", async () => {
    const doc = await buildEvidenceDoc({
      eventType: "custom",
      kind: "Item",
      name: "x",
      spec: {},
      author: "test",
    });
    const capturedAt = (doc.spec as any).captured_at as string;
    expect(new Date(capturedAt).toISOString()).toBe(capturedAt);
  });

  test("snapshot contains the original spec", async () => {
    const spec = { foo: "bar", count: 42 };
    const doc = await buildEvidenceDoc({
      eventType: "custom",
      kind: "Item",
      name: "x",
      spec,
      author: "test",
    });
    expect((doc.spec as any).snapshot).toEqual(spec);
  });

  test("suite null for non-eval kind", async () => {
    const doc = await buildEvidenceDoc({
      eventType: "document_created",
      kind: "Agent",
      name: "a1",
      spec: { description: "test" },
      author: "sdk",
    });
    expect((doc.spec as any).suite).toBeNull();
  });

  test("explicit suite overrides spec", async () => {
    const doc = await buildEvidenceDoc({
      eventType: "eval_run_completed",
      kind: "EvalRun",
      name: "r1",
      spec: { suite: "old" },
      author: "test",
      suite: "override",
    });
    expect((doc.spec as any).suite).toBe("override");
  });
});
