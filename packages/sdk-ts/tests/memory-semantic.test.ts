/**
 * Semantic recall pure core (s-memory-semantic-recall) — TS unit twin of
 * `packages/sdk-py/tests/test_memory_semantic.py`'s pure-core half.
 *
 * Proves, offline with the deterministic fake embedder, that a paraphrase the
 * ecphory cue-match misses IS found once embedding similarity feeds
 * `scoreEngram`'s Path 3, and that RRF fusion promotes it over a
 * lexically-boosted decoy without ever dropping a candidate. The cross-language
 * numbers are pinned by `memory-scoring-parity.test.ts` (shared fixture).
 */
import { describe, expect, test } from "bun:test";

import { fakeEmbedOne } from "../src/kernel/embedding.js";
import type { EngramRef } from "../src/memory/ecphory.js";
import {
  cosineSimilarity,
  ecphoryRank,
  engramText,
  fuseSemanticRecall,
  semanticScoresFromVectors,
} from "../src/memory/semantic.js";

const NOW = Date.parse("2026-07-10T12:00:00+00:00");

const target: EngramRef = {
  name: "rem-target",
  spec: {
    area: "Feature/kernel",
    summary: "deep-copy before mutating documents",
    created_at: "2026-07-01T00:00:00+00:00",
  },
};
const decoy: EngramRef = {
  name: "rem-decoy",
  spec: {
    area: "Feature/ops",
    summary: "safely archive old reports nightly",
    created_at: "2026-07-01T00:00:00+00:00",
  },
};

function fakeSemanticScores(query: string, engrams: EngramRef[]): Record<string, number> {
  return semanticScoresFromVectors(
    engrams.map((e) => e.name),
    engrams.map((e) => fakeEmbedOne(engramText(e.spec))),
    fakeEmbedOne(query),
  );
}

describe("memory semantic core", () => {
  test("cosineSimilarity basics", () => {
    expect(cosineSimilarity([1, 0], [1, 0])).toBeCloseTo(1.0, 12);
    expect(cosineSimilarity([1, 0], [0, 1])).toBe(0.0);
    expect(cosineSimilarity([1, 0], [-1, 0])).toBeCloseTo(-1.0, 12);
    expect(cosineSimilarity([0, 0], [1, 1])).toBe(0.0); // all-zero = no signal
    expect(cosineSimilarity([], [])).toBe(0.0);
  });

  test("semanticScoresFromVectors drops non-positive; first wins on duplicates", () => {
    const scores = semanticScoresFromVectors(
      ["hit", "anti", "flat", "hit"],
      [[0.5, 0.5], [-1, 0], [0, 1], [1, 0]],
      [1, 0],
    );
    expect(Object.keys(scores)).toEqual(["hit"]);
    expect(scores.hit).toBeCloseTo(cosineSimilarity([1, 0], [0.5, 0.5]), 12);
  });

  test("engramText embeds the semantic payload only", () => {
    const text = engramText({
      area: "Feature/kernel",
      summary: "deep-copy before mutating",
      affect: "regret",
      created_at: "2026-07-01T00:00:00+00:00",
    });
    expect(text).toBe("Feature/kernel deep-copy before mutating");
  });

  test("paraphrase is found ONLY with semantic scores (the inert hook, fed)", () => {
    const query = "mutating documents safely"; // not a substring, not a token-subset
    const engrams = [target, decoy];

    expect(ecphoryRank(engrams, query, undefined, undefined, NOW)).toEqual([]);

    const sem = fakeSemanticScores(query, engrams);
    const ranked = ecphoryRank(engrams, query, sem, undefined, NOW);
    expect(ranked.map((s) => s.engram.name)).toEqual(["rem-target"]);
    expect(ranked[0].matchedDims[0]!.startsWith("semantic~")).toBeTrue();
  });

  test("fuseSemanticRecall promotes the paraphrase and annotates hits", () => {
    const query = "mutating documents safely";
    const engrams = [target, decoy];
    const sem = fakeSemanticScores(query, engrams);
    const hits = [
      { kind: "LessonLearned", name: "rem-decoy", score: 0.048 },
      { kind: "LessonLearned", name: "rem-target", score: 0.033 },
    ];

    const fused = fuseSemanticRecall(hits, engrams, query, sem, undefined, NOW);
    expect(fused.map((h) => h.name)).toEqual(["rem-target", "rem-decoy"]);

    const [top, second] = fused;
    expect(top.score as number).toBeCloseTo(1 / 62 + 1 / 61, 12); // recall#2 + ecphory#1
    expect(top.rank_recall).toBe(2);
    expect(top.rank_ecphory).toBe(1);
    expect(top.score_recall as number).toBeCloseTo(0.033, 12);
    expect(top.semantic as number).toBeCloseTo(sem["rem-target"], 12);
    // below the ecphory threshold: recall rank only, never dropped
    expect(second.score as number).toBeCloseTo(1 / 61, 12);
    expect(second.rank_recall).toBe(1);
    expect("rank_ecphory" in second).toBeFalse();
  });

  test("fuseSemanticRecall with empty hits", () => {
    expect(fuseSemanticRecall([], [], "anything", {}, undefined, NOW)).toEqual([]);
  });
});
