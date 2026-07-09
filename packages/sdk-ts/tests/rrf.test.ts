/**
 * Reciprocal Rank Fusion — pure-function tests with synthetic ranks (TS twin of
 * `tests/test_rrf.py`). RRF is the deterministic fusion core shared by every
 * hybrid provider; correct and Py↔TS identical independent of any store.
 */
import { describe, expect, test } from "bun:test";

import { DEFAULT_RRF_K, reciprocalRankFusion } from "../src/adapters/search/rrf.js";

describe("reciprocalRankFusion", () => {
  test("empty input is empty", () => {
    expect(reciprocalRankFusion([])).toEqual([]);
    expect(reciprocalRankFusion([[], []])).toEqual([]);
  });

  test("single list preserves order, scores strictly decreasing", () => {
    const fused = reciprocalRankFusion([["a", "b", "c"]]);
    expect(fused.map(([d]) => d)).toEqual(["a", "b", "c"]);
    expect(fused[0]![1]).toBeGreaterThan(fused[1]![1]);
    expect(fused[1]![1]).toBeGreaterThan(fused[2]![1]);
  });

  test("agreement beats a single top", () => {
    const fused = new Map(reciprocalRankFusion([["x", "shared"], ["y", "shared"]]));
    expect(fused.get("shared")!).toBeGreaterThan(fused.get("x")!);
    expect(fused.get("shared")!).toBeGreaterThan(fused.get("y")!);
  });

  test("score formula matches the definition", () => {
    const k = DEFAULT_RRF_K;
    const fused = new Map(reciprocalRankFusion([["a", "b"], ["b", "a"]]));
    const expected = 1 / (k + 1) + 1 / (k + 2);
    expect(fused.get("a")!).toBeCloseTo(expected, 12);
    expect(fused.get("b")!).toBeCloseTo(expected, 12);
  });

  test("deterministic tiebreak by id ascending", () => {
    const fused = reciprocalRankFusion([["b", "a"], ["a", "b"]]);
    expect(fused.map(([d]) => d)).toEqual(["a", "b"]);
  });

  test("duplicate within one list scored at best rank", () => {
    const k = DEFAULT_RRF_K;
    const fused = new Map(reciprocalRankFusion([["a", "a", "b"]]));
    expect(fused.get("a")!).toBeCloseTo(1 / (k + 1), 12);
    expect(fused.get("b")!).toBeCloseTo(1 / (k + 3), 12);
  });

  test("larger k smooths more", () => {
    const high = new Map(reciprocalRankFusion([["a", "b"]], 1000));
    const low = new Map(reciprocalRankFusion([["a", "b"]], 1));
    expect(high.get("a")! - high.get("b")!).toBeLessThan(low.get("a")! - low.get("b")!);
  });

  test("non-positive k is rejected", () => {
    expect(() => reciprocalRankFusion([["a"]], 0)).toThrow();
  });
});
