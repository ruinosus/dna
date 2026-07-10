/**
 * The public memory-scoring conformance kit × the builtin embedders
 * (TS side of `tests/test_memory_conformance_kit.py`, s-memory-conformance-kit).
 *
 * Runs `memoryScoringConformanceSuite` on its default deterministic fake
 * floor (no factory — fully offline) AND through a trivial custom embedder
 * factory, proving the public `dna-sdk/testing` surface an embedder author
 * consumes. The kernel-bound memory VERB suite has no TS twin by design —
 * the verbs are Py-only by the SDK's declared boundary.
 */
import { describe, expect, test } from "bun:test";

import { fakeEmbedOne } from "../src/kernel/embedding.js";
import {
  memoryScoringConformanceSuite,
  type EmbedderFactory,
} from "../src/testing/index.js";

describe("memory-scoring conformance × fake floor (no factory)", () => {
  for (const c of memoryScoringConformanceSuite()) {
    test(c.name, async () => {
      await c.run();
    });
  }
});

describe("memory-scoring conformance × custom embedder factory", () => {
  let cleaned = 0;

  const factory: EmbedderFactory = async () => ({
    embedder: {
      async embed(texts: string[]): Promise<number[][]> {
        return texts.map((t) => fakeEmbedOne(t));
      },
    },
    cleanup: () => {
      cleaned += 1;
    },
  });

  const cases = memoryScoringConformanceSuite(factory);
  for (const c of cases) {
    test(c.name, async () => {
      await c.run();
    });
  }

  test("suite is exhaustive and cleanup ran per case", () => {
    expect(cases.map((c) => c.name)).toEqual([
      "cosine_tracks_similarity",
      "ecphory_weights_and_threshold",
      "ecphory_deterministic_ordering",
      "semantic_hook_lifts_paraphrase",
      "fusion_preserves_and_annotates",
      "decay_retention_monotonic",
      "bitemporal_fail_open",
    ]);
    expect(cleaned).toBe(cases.length);
  });
});
