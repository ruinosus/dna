/**
 * rec-embedding-port — ONNX all-MiniLM-L6-v2 parity (TS side).
 *
 * The REAL embedder is parity-BY-ARTIFACT: `@huggingface/transformers` (TS) and
 * fastembed (Py) run the same all-MiniLM-L6-v2 ONNX. This suite embeds the
 * shared golden sentences via transformers.js and asserts cosine ≥ 0.99 against
 * the Py-generated vectors in `tests/parity-fixtures/onnx-embedding-golden.json`.
 *
 * DOUBLE-gated so it never runs in offline CI:
 *  - `DNA_OFFLINE=1` (the CI default) skips it; and
 *  - it skips unless the optional `@huggingface/transformers` peer resolves.
 *
 * Locally-proven cross-language cosine (transformers.js ↔ fastembed):
 * 1.000000 on both golden sentences — see the story report.
 */
import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

function transformersAvailable(): boolean {
  if (process.env.DNA_OFFLINE === "1") return false;
  try {
    // Resolve without importing (cheap availability probe).
    Bun.resolveSync("@huggingface/transformers", here);
    return true;
  } catch {
    return false;
  }
}

const GOLDEN = JSON.parse(
  readFileSync(
    join(here, "../../../tests/parity-fixtures/onnx-embedding-golden.json"),
    "utf-8",
  ),
) as { dims: number; sentences: string[]; vectors: number[][] };

function cosine(a: number[], b: number[]): number {
  let dot = 0;
  let na = 0;
  let nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}

describe.skipIf(!transformersAvailable())(
  "OnnxEmbeddingProvider — parity by artifact vs Py fastembed golden",
  () => {
    test("embeds golden sentences to cosine ≥ 0.99 of the Py vectors", async () => {
      const { OnnxEmbeddingProvider, ONNX_DIMS } = await import(
        "../src/adapters/embedding/onnx.js"
      );
      const prov = new OnnxEmbeddingProvider();
      expect(prov.dims).toBe(ONNX_DIMS);
      expect(ONNX_DIMS).toBe(GOLDEN.dims);

      const vecs = await prov.embed(GOLDEN.sentences);
      expect(vecs.length).toBe(GOLDEN.sentences.length);
      for (let i = 0; i < vecs.length; i++) {
        expect(vecs[i].length).toBe(ONNX_DIMS);
        const norm = Math.sqrt(vecs[i].reduce((s, x) => s + x * x, 0));
        expect(norm).toBeCloseTo(1.0, 3);
        expect(cosine(vecs[i], GOLDEN.vectors[i])).toBeGreaterThanOrEqual(0.99);
      }
    }, 120_000);
  },
);
