/**
 * ONNX all-MiniLM-L6-v2 embedding provider (optional `@huggingface/transformers`
 * peer dep).
 *
 * The REAL embedder (rec-embedding-port): the same
 * `sentence-transformers/all-MiniLM-L6-v2` ONNX artifact run by
 * `@huggingface/transformers` (transformers.js, TS) and `fastembed` (Py) —
 * parity by artifact, not reimplementation. Cosine ≈ 1 across the two runtimes.
 *
 * Lazy-download + cache, the Chroma pattern: the model is a downloaded artifact,
 * never a bundled dependency. `@huggingface/transformers` is dynamically
 * imported on the FIRST `embed` call and the pipeline fetches + caches the ONNX
 * then — so this module never pulls transformers.js into a process that does
 * not embed, and it is not in the default dependency graph.
 */
import type { EmbeddingPort } from "../../kernel/protocols.js";

// Same model + vector width as the Py twin (adapters/embedding/onnx.py) and the
// fake floor (FAKE_EMBEDDING_DIMS) so providers are swap-compatible.
export const ONNX_MODEL_ID = "Xenova/all-MiniLM-L6-v2";
export const ONNX_DIMS = 384;

/**
 * `EmbeddingPort` backed by transformers.js feature-extraction. The heavy
 * dynamic import (`@huggingface/transformers`) is deferred to first use so
 * merely importing this module never pulls ML deps into a process that does not
 * embed.
 */
export class OnnxEmbeddingProvider implements EmbeddingPort {
  readonly modelId: string;
  readonly dims: number;
  // The transformers.js pipeline, lazily constructed on first embed().
  private _pipe: unknown = null;

  constructor(modelId: string = ONNX_MODEL_ID, dims: number = ONNX_DIMS) {
    this.modelId = modelId;
    this.dims = dims;
  }

  private async ensurePipe(): Promise<
    (texts: string[], opts: { pooling: "mean"; normalize: boolean }) => Promise<{
      tolist(): number[][];
    }>
  > {
    if (this._pipe === null) {
      let mod: { pipeline: (task: string, model: string) => Promise<unknown> };
      // NON-LITERAL specifier on purpose: the peer dep is OPTIONAL and its
      // type declarations are NOT installed by default, so a literal
      // `import("@huggingface/transformers")` would fail `tsc --noEmit` in CI
      // with TS2307. A string variable makes the dynamic import resolve to
      // `Promise<any>` at type-check time (still the same module at runtime).
      const spec: string = "@huggingface/transformers";
      try {
        // Dynamic import so the dep is optional and never bundled by default.
        mod = (await import(/* @vite-ignore */ spec)) as typeof mod;
      } catch (err) {
        throw new Error(
          "OnnxEmbeddingProvider needs the '@huggingface/transformers' peer dep: "
            + "npm install @huggingface/transformers",
          { cause: err },
        );
      }
      // Downloads + caches the ONNX artifact on first construction.
      this._pipe = await mod.pipeline("feature-extraction", this.modelId);
    }
    return this._pipe as never;
  }

  async embed(texts: string[]): Promise<number[][]> {
    if (texts.length === 0) return [];
    const pipe = await this.ensurePipe();
    // Mean-pooled + L2-normalized sentence vectors — same recipe fastembed
    // uses by default, matching sentence-transformers.
    const out = await pipe(texts, { pooling: "mean", normalize: true });
    return out.tolist();
  }
}
