/**
 * Summary projection vocabulary (Chunk 2 / Task 4 — spec D2).
 * Twin of packages/sdk-py/tests/test_summary_projection_vocab.py — identical
 * expectations for EACH of the 7 primitives + the real-class behaviors of the
 * 6 kinds migrating to descriptors in lotes 2-3.
 *
 * Plain (non-projection) values keep today's meaning (the projected default),
 * so the shipped descriptors stay untouched.
 */
import { describe as suite, expect, test } from "bun:test";
import { KindDefinitionSchema } from "../src/kernel/models.js";
import { DeclarativeKindPort } from "../src/kernel/meta.js";
import type { Document } from "../src/kernel/document.js";

function port(
  summary: Record<string, unknown>,
  schema?: Record<string, unknown>,
): DeclarativeKindPort {
  const raw = {
    apiVersion: "github.com/ruinosus/dna/core/v1",
    kind: "KindDefinition",
    metadata: { name: "x-record" },
    spec: {
      target_api_version: "github.com/ruinosus/dna/x/v1",
      target_kind: "XRecord",
      alias: "x-record",
      origin: "github.com/ruinosus/dna/x",
      storage: { type: "yaml", container: "x-records" },
      schema: schema ?? { type: "object", properties: {} },
      summary,
    },
  };
  return DeclarativeKindPort.fromTyped(KindDefinitionSchema.parse(raw));
}

function doc(spec: Record<string, unknown>): Document {
  return { spec } as unknown as Document;
}

suite("summary projection vocabulary (D2)", () => {
  // ── 1. plain values (back-compat) ──────────────────────────────────────
  test("plain value is projected default", () => {
    const p = port({ status: "pending", program: "" });
    expect(p.summary(doc({ status: "running", program: "foo" }))).toEqual({
      status: "running",
      program: "foo",
    });
    expect(p.summary(doc({}))).toEqual({ status: "pending", program: "" });
  });

  test("bare doc with no spec → empty spec → default", () => {
    const p = port({ status: "pending" });
    expect(p.summary({} as unknown as Document)).toEqual({ status: "pending" });
  });

  // ── 2. count_of (list OR string; missing/None → 0) ─────────────────────
  test("count_of over a list", () => {
    const p = port({ affect_count: { count_of: "palette" } });
    expect(p.summary(doc({ palette: [1, 2, 3] }))).toEqual({ affect_count: 3 });
    expect(p.summary(doc({ palette: [] }))).toEqual({ affect_count: 0 });
    expect(p.summary(doc({}))).toEqual({ affect_count: 0 });
    expect(p.summary(doc({ palette: null }))).toEqual({ affect_count: 0 });
  });

  test("count_of over a string (body_length)", () => {
    const p = port({ body_length: { count_of: "body" } });
    expect(p.summary(doc({ body: "hello" }))).toEqual({ body_length: 5 });
    expect(p.summary(doc({ body: "" }))).toEqual({ body_length: 0 });
    expect(p.summary(doc({}))).toEqual({ body_length: 0 });
  });

  test("count_of over a non-str/list target → 0 (Py↔TS parity pin)", () => {
    // count_of's contract is "length of a sequence". Over a NON-str/list
    // target it must yield 0 in BOTH runtimes. Python's bare len() would
    // element-count a dict and HARD CRASH on an int/float; this guard pins
    // both runtimes to 0.
    const p = port({ n: { count_of: "target" } });
    expect(p.summary(doc({ target: { a: 1, b: 2 } }))).toEqual({ n: 0 });
    expect(p.summary(doc({ target: 42 }))).toEqual({ n: 0 });
    expect(p.summary(doc({ target: 3.14 }))).toEqual({ n: 0 });
  });

  // ── 3. path (dict-only walk; missing → null) ───────────────────────────
  test("path nested walk", () => {
    const p = port({ applied_change: { path: "applied_change.action" } });
    expect(p.summary(doc({ applied_change: { action: "swap" } }))).toEqual({
      applied_change: "swap",
    });
    expect(p.summary(doc({ applied_change: {} }))).toEqual({ applied_change: null });
    expect(p.summary(doc({}))).toEqual({ applied_change: null });
    expect(p.summary(doc({ applied_change: null }))).toEqual({ applied_change: null });
  });

  test("path single segment", () => {
    const p = port({ program: { path: "program" } });
    expect(p.summary(doc({ program: "foo" }))).toEqual({ program: "foo" });
    expect(p.summary(doc({}))).toEqual({ program: null });
  });

  // ── 4. format (plain / all_or_empty / placeholder_defaults) ────────────
  test("format plain — per-missing blank", () => {
    const p = port({ r: { format: "{a}/{b}" } });
    expect(p.summary(doc({ a: 1, b: 2 }))).toEqual({ r: "1/2" });
    expect(p.summary(doc({ b: 2 }))).toEqual({ r: "/2" });
    expect(p.summary(doc({ a: 1 }))).toEqual({ r: "1/" });
    expect(p.summary(doc({}))).toEqual({ r: "/" });
  });

  test("format all_or_empty — autoagent passed/total", () => {
    const p = port({ passed: { format: "{passed}/{total}", all_or_empty: true } });
    expect(p.summary(doc({ passed: 5, total: 10 }))).toEqual({ passed: "5/10" });
    expect(p.summary(doc({ passed: 5 }))).toEqual({ passed: "" });
    expect(p.summary(doc({ total: 10 }))).toEqual({ passed: "" });
    expect(p.summary(doc({}))).toEqual({ passed: "" });
    expect(p.summary(doc({ passed: null, total: 10 }))).toEqual({ passed: "" });
    expect(p.summary(doc({ passed: 0, total: 0 }))).toEqual({ passed: "0/0" });
  });

  test("format placeholder_defaults — autolab iter", () => {
    const p = port({
      iter: {
        format: "{total_iterations_completed}/{max_iterations}",
        placeholder_defaults: { total_iterations_completed: 0, max_iterations: 0 },
      },
    });
    expect(p.summary(doc({}))).toEqual({ iter: "0/0" });
    expect(
      p.summary(doc({ total_iterations_completed: 3, max_iterations: 5 })),
    ).toEqual({ iter: "3/5" });
    expect(p.summary(doc({ total_iterations_completed: 3 }))).toEqual({ iter: "3/0" });
    expect(
      p.summary(doc({ total_iterations_completed: null, max_iterations: 5 })),
    ).toEqual({ iter: "0/5" });
  });

  // ── 5. truncate (string[:N]) ───────────────────────────────────────────
  test("truncate with default — commit", () => {
    const p = port({ commit: { path: "commit", truncate: 7, default: "" } });
    expect(p.summary(doc({ commit: "abcdef1234567" }))).toEqual({ commit: "abcdef1" });
    expect(p.summary(doc({ commit: "abc" }))).toEqual({ commit: "abc" });
    expect(p.summary(doc({}))).toEqual({ commit: "" });
    expect(p.summary(doc({ commit: null }))).toEqual({ commit: "" });
    expect(p.summary(doc({ commit: "" }))).toEqual({ commit: "" });
  });

  // ── 6. round (banker's, == Python round) ───────────────────────────────
  test("round avg_score", () => {
    const p = port({ avg_score: { path: "avg_score", round: 4 } });
    expect(p.summary(doc({ avg_score: 0.123456789 }))).toEqual({ avg_score: 0.1235 });
    expect(p.summary(doc({ avg_score: null }))).toEqual({ avg_score: null });
    expect(p.summary(doc({}))).toEqual({ avg_score: null });
    expect(p.summary(doc({ avg_score: 1 }))).toEqual({ avg_score: 1 });
  });

  test("round with default — cost", () => {
    const p = port({ cost_usd: { path: "total_cost_usd", round: 4, default: 0.0 } });
    expect(p.summary(doc({ total_cost_usd: 1.234567 }))).toEqual({ cost_usd: 1.2346 });
    expect(p.summary(doc({}))).toEqual({ cost_usd: 0.0 });
    expect(p.summary(doc({ total_cost_usd: null }))).toEqual({ cost_usd: 0.0 });
  });

  test("round banker's half-to-even (pins the rule)", () => {
    const p0 = port({ v: { path: "v", round: 0 } });
    expect(p0.summary(doc({ v: 2.5 }))).toEqual({ v: 2 });
    expect(p0.summary(doc({ v: 3.5 }))).toEqual({ v: 4 });
    expect(p0.summary(doc({ v: 0.5 }))).toEqual({ v: 0 });
    expect(p0.summary(doc({ v: 1.5 }))).toEqual({ v: 2 });
    const p2 = port({ v: { path: "v", round: 2 } });
    expect(p2.summary(doc({ v: 0.125 }))).toEqual({ v: 0.12 });
    expect(p2.summary(doc({ v: 0.135 }))).toEqual({ v: 0.14 });
  });

  test("round:2 drift cases match CPython (Py↔TS parity pin)", () => {
    // round:2 is the spec's #1 stated parity risk — where a naive TS rounder
    // (EPS even-tie window / Math.round on the scaled double) drifts from
    // CPython round(). These pin the exact CPython results, identical to the
    // Python twin:
    //   0.005 → 0.01 (stored just over the half)
    //   0.025 → 0.03
    //   2.675 → 2.67 (stored 2.67499…, just under the half)
    const p2 = port({ v: { path: "v", round: 2 } });
    expect(p2.summary(doc({ v: 0.005 }))).toEqual({ v: 0.01 });
    expect(p2.summary(doc({ v: 0.025 }))).toEqual({ v: 0.03 });
    expect(p2.summary(doc({ v: 2.675 }))).toEqual({ v: 2.67 });
  });

  // ── 7. default (fires on missing OR null, post-resolve) ────────────────
  test("default — missing or null", () => {
    const p = port({ vis: { path: "defaults.visibility", default: "shared" } });
    expect(p.summary(doc({ defaults: { visibility: "private" } }))).toEqual({
      vis: "private",
    });
    expect(p.summary(doc({}))).toEqual({ vis: "shared" });
    expect(p.summary(doc({ defaults: {} }))).toEqual({ vis: "shared" });
    expect(p.summary(doc({ defaults: { visibility: null } }))).toEqual({
      vis: "shared",
    });
    // falsy-but-not-null does NOT fire default
    expect(p.summary(doc({ defaults: { visibility: "" } }))).toEqual({ vis: "" });
  });

  // ── 8. filter_falsy (leaf-keyed, drops falsy) ──────────────────────────
  test("filter_falsy leaf keys", () => {
    const p = port({
      applies_to: {
        paths: ["applies_to.scope", "applies_to.owner", "applies_to.memory_type"],
        filter_falsy: true,
      },
    });
    expect(
      p.summary(
        doc({ applies_to: { scope: "acme", owner: "bob", memory_type: "episodic" } }),
      ),
    ).toEqual({
      applies_to: { scope: "acme", owner: "bob", memory_type: "episodic" },
    });
    expect(
      p.summary(doc({ applies_to: { scope: "acme", owner: "", memory_type: null } })),
    ).toEqual({ applies_to: { scope: "acme" } });
    expect(p.summary(doc({}))).toEqual({ applies_to: {} });
    expect(p.summary(doc({ applies_to: {} }))).toEqual({ applies_to: {} });
  });

  test("memory-policy real shape", () => {
    const p = port({
      applies_to: {
        paths: ["applies_to.scope", "applies_to.owner", "applies_to.memory_type"],
        filter_falsy: true,
      },
      default_visibility: { path: "defaults.visibility", default: "shared" },
    });
    expect(p.summary(doc({}))).toEqual({
      applies_to: {},
      default_visibility: "shared",
    });
    expect(
      p.summary(
        doc({
          applies_to: { scope: "acme", owner: "bob" },
          defaults: { visibility: "private" },
        }),
      ),
    ).toEqual({
      applies_to: { scope: "acme", owner: "bob" },
      default_visibility: "private",
    });
  });

  // ── 9. unknown key / exclusivity → throw at load ───────────────────────
  test("unknown projection key throws at load", () => {
    expect(() => port({ x: { path: "a", bogus: 1 } })).toThrow(/unknown/);
  });

  test("format exclusive of others throws", () => {
    expect(() => port({ x: { format: "{a}", round: 2 } })).toThrow();
    expect(() => port({ x: { format: "{a}", path: "a" } })).toThrow();
  });

  test("count_of exclusive of path throws", () => {
    expect(() => port({ x: { count_of: "a", path: "a" } })).toThrow();
  });

  // ── 10. mixed full real-class summaries ────────────────────────────────
  test("autoagent-experiment full summary", () => {
    const p = port({
      program: { path: "program", default: "" },
      commit: { path: "commit", truncate: 7, default: "" },
      status: { path: "status", default: "" },
      passed: { format: "{passed}/{total}", all_or_empty: true },
      avg_score: { path: "avg_score", round: 4 },
      cost_usd: { path: "cost_usd" },
    });
    expect(
      p.summary(
        doc({
          program: "agent-x",
          commit: "abcdef1234567",
          status: "done",
          passed: 5,
          total: 10,
          avg_score: 0.987654,
          cost_usd: 1.23,
        }),
      ),
    ).toEqual({
      program: "agent-x",
      commit: "abcdef1",
      status: "done",
      passed: "5/10",
      avg_score: 0.9877,
      cost_usd: 1.23,
    });
    expect(p.summary(doc({}))).toEqual({
      program: "",
      commit: "",
      status: "",
      passed: "",
      avg_score: null,
      cost_usd: null,
    });
  });

  test("autolab-run full summary", () => {
    const p = port({
      program: { path: "program" },
      status: { path: "status", default: "pending" },
      iter: {
        format: "{total_iterations_completed}/{max_iterations}",
        placeholder_defaults: { total_iterations_completed: 0, max_iterations: 0 },
      },
      cost_usd: { path: "total_cost_usd", round: 4, default: 0.0 },
      best: { path: "best_experiment" },
    });
    expect(p.summary(doc({}))).toEqual({
      program: null,
      status: "pending",
      iter: "0/0",
      cost_usd: 0.0,
      best: null,
    });
    expect(
      p.summary(
        doc({
          program: "p1",
          status: "running",
          total_iterations_completed: 2,
          max_iterations: 8,
          total_cost_usd: 0.987654,
          best_experiment: "exp-3",
        }),
      ),
    ).toEqual({
      program: "p1",
      status: "running",
      iter: "2/8",
      cost_usd: 0.9877,
      best: "exp-3",
    });
  });
});
