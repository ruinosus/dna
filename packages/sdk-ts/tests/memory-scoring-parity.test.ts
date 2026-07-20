/**
 * TS side of the Py↔TS memory-scoring parity (s-memory-verbs).
 *
 * Runs every case in `tests/fixtures/memory-scoring-parity.json` against the TS
 * pure-scoring port. The Python twin (`tests/test_memory_parity.py`) runs the
 * SAME fixture; Python is the source of truth for the numbers (regenerate via
 * `packages/sdk-py/scripts/gen_memory_parity.py`). A failure on either side is a
 * parity divergence.
 */
import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  ebbinghausRetention,
  currentlyValid,
  stabilityFromSpec,
  confidenceScoreNumeric,
} from "../src/memory/decay.js";
import { classifyMemoryType } from "../src/memory/memoryType.js";
import { timeOfDay } from "../src/memory/encodingContext.js";
import { scoreEngram, type EngramRef } from "../src/memory/ecphory.js";
import {
  cosineSimilarity,
  engramText,
  fuseSemanticRecall,
  semanticScoresFromVectors,
} from "../src/memory/semantic.js";
import { fakeEmbedOne } from "../src/kernel/embedding.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FX = JSON.parse(
  readFileSync(join(__dirname, "fixtures", "memory-scoring-parity.json"), "utf-8"),
);

const iso = (s: string): number => Date.parse(s.replace("Z", "+00:00"));

describe("memory scoring Py↔TS parity", () => {
  test("ebbinghausRetention", () => {
    for (const c of FX.ebbinghaus_retention) {
      expect(ebbinghausRetention(c.stability_days, c.days_since_recall)).toBeCloseTo(c.expected, 12);
    }
  });

  test("currentlyValid", () => {
    for (const c of FX.currently_valid) {
      expect(currentlyValid(c.valid_to, iso(c.now))).toBe(c.expected);
    }
  });

  test("stabilityFromSpec", () => {
    for (const c of FX.stability_from_spec) {
      expect(stabilityFromSpec(c.spec)).toBeCloseTo(c.expected, 12);
    }
  });

  test("confidenceScoreNumeric", () => {
    for (const c of FX.confidence_score_numeric) {
      expect(confidenceScoreNumeric(c.spec)).toBeCloseTo(c.expected, 12);
    }
  });

  test("classifyMemoryType", () => {
    for (const c of FX.classify_memory_type) {
      expect(classifyMemoryType(c.spec)).toBe(c.expected);
    }
  });

  test("timeOfDay", () => {
    for (const c of FX.time_of_day) {
      expect(timeOfDay(c.hour)).toBe(c.expected);
    }
  });


  test("scoreEngram", () => {
    for (const c of FX.score_engram) {
      const engram: EngramRef = { name: c.engram.name, spec: c.engram.spec };
      const s = scoreEngram(engram, c.cue_ctx);
      expect(s.score).toBeCloseTo(c.expected_score, 9);
      expect(s.matchedDims).toEqual(c.expected_matched);
    }
  });

  // ── semantic recall (s-memory-semantic-recall) ────────────────────────────

  test("cosineSimilarity over fake embeddings", () => {
    for (const c of FX.cosine_similarity_fake) {
      const got = cosineSimilarity(fakeEmbedOne(c.text_a), fakeEmbedOne(c.text_b));
      expect(got).toBeCloseTo(c.expected, 12);
    }
  });

  test("engramText", () => {
    for (const c of FX.engram_text) {
      expect(engramText(c.spec)).toBe(c.expected);
    }
  });

  test("fuseSemanticRecall", () => {
    for (const c of FX.semantic_recall_fusion) {
      const refs: EngramRef[] = c.engrams.map(
        (e: { name: string; spec: Record<string, unknown> }) => ({ name: e.name, spec: e.spec }),
      );
      const sem = semanticScoresFromVectors(
        c.engrams.map((e: { name: string }) => e.name),
        c.engrams.map((e: { spec: Record<string, unknown> }) => fakeEmbedOne(engramText(e.spec))),
        fakeEmbedOne(c.query),
      );
      const fused = fuseSemanticRecall(
        c.hits.map((h: Record<string, unknown>) => ({ ...h })),
        refs, c.query, sem, undefined, iso(c.now),
      );
      expect(fused.map((h) => h.name)).toEqual(c.expected_order);
      for (const h of fused) {
        const name = String(h.name);
        expect(h.score as number).toBeCloseTo(c.expected_scores[name], 12);
        if (name in c.expected_semantic) {
          expect(h.semantic as number).toBeCloseTo(c.expected_semantic[name], 12);
        }
        expect(h.rank_ecphory).toEqual(c.expected_rank_ecphory[name]);
      }
    }
  });
});
