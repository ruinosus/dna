/**
 * Deterministic hash-based embedding — the zero-dependency offline floor.
 *
 * TypeScript twin of `dna/kernel/embedding.py`. This is the default
 * `EmbeddingPort` the kernel falls back to when no real provider (e.g. the
 * optional ONNX all-MiniLM-L6-v2 adapter) is registered. It is NOT a semantic
 * embedder — it is a stable, content-addressed vector so the search plane and
 * its tests have *something* deterministic to run against in CI and offline,
 * without pulling any ML dependency.
 *
 * Parity contract (rsh-memory-similarity-evolution → rec-embedding-port): this
 * produces the BIT-IDENTICAL vector to the Python `fake_embed_one` for the same
 * string — guaranteed *by construction*:
 *
 *   1. Tokenization is `[a-z0-9]+` over the lower-cased text — identical token
 *      lists in TS (`String.match`) and Py (`re.findall`) for ASCII input.
 *   2. Each token is hashed with SHA-256 (`js-sha256` / stdlib `hashlib`); the
 *      first 4 bytes pick a dimension (big-endian uint32 mod `dims`) and the
 *      5th byte's low bit picks a sign (±1). Accumulation is INTEGER, so the
 *      pre-normalization vector is exact on both sides regardless of order.
 *   3. L2-normalization divides each integer component by `sqrt(sum(cᵢ²))`.
 *      The sum-of-squares is an exact integer; `sqrt` and division are both
 *      IEEE-754 correctly-rounded, so the resulting doubles are bit-identical.
 *
 * The golden fixture `tests/parity-fixtures/fake-embedding-golden.json` pins a
 * handful of strings to their exact vectors; both language suites assert
 * against it.
 */
import { sha256 } from "js-sha256";

import type { EmbeddingPort } from "./protocols.js";

/**
 * Default dimensionality of the fake space. Matches all-MiniLM-L6-v2 (the real
 * ONNX provider) so swapping providers keeps the vector length — and any
 * downstream vector-store column width — stable.
 */
export const FAKE_EMBEDDING_DIMS = 384;

/**
 * Stable identity of this embedding space. Versioned so a future change to the
 * hashing scheme is a NEW space (old vectors stay honestly incomparable).
 */
export const FAKE_EMBEDDING_MODEL_ID = "dna-fake-hash-v1";

const TOKEN_RE = /[a-z0-9]+/g;

/**
 * Deterministic, L2-normalized hash embedding of a single string. Bit-identical
 * to the Python `fake_embed_one`. Empty/tokenless text → all-zeros (an all-zero
 * vector is honestly "no signal", never normalized).
 */
export function fakeEmbedOne(text: string, dims: number = FAKE_EMBEDDING_DIMS): number[] {
  const counts = new Array<number>(dims).fill(0);
  const tokens = text.toLowerCase().match(TOKEN_RE) ?? [];
  for (const token of tokens) {
    const bytes = sha256.array(token); // 32 bytes, 0..255
    // big-endian uint32 of bytes[0..4) — `>>> 0` forces unsigned.
    const idx =
      (((bytes[0] << 24) | (bytes[1] << 16) | (bytes[2] << 8) | bytes[3]) >>> 0) % dims;
    const sign = bytes[4] & 1 ? 1 : -1;
    counts[idx] += sign;
  }
  let normSq = 0;
  for (const c of counts) normSq += c * c;
  if (normSq === 0) return counts; // already all-zeros
  const norm = Math.sqrt(normSq);
  return counts.map((c) => c / norm);
}

/**
 * Zero-dependency `EmbeddingPort` — the offline/CI default. Structurally
 * satisfies `EmbeddingPort` (`modelId`, `dims`, async `embed`).
 */
export class FakeEmbeddingProvider implements EmbeddingPort {
  readonly modelId = FAKE_EMBEDDING_MODEL_ID;
  readonly dims: number;

  constructor(dims: number = FAKE_EMBEDDING_DIMS) {
    this.dims = dims;
  }

  async embed(texts: string[]): Promise<number[][]> {
    return texts.map((t) => fakeEmbedOne(t, this.dims));
  }
}
