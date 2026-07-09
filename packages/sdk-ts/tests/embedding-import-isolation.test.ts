/**
 * rec-embedding-port — the core stays ML-dependency-free (TS side).
 *
 * The REAL embedder (ONNX all-MiniLM-L6-v2 via `@huggingface/transformers`) is
 * an OPTIONAL peer dep. Importing the SDK entrypoint and using the fake floor
 * must NEVER pull transformers.js: `OnnxEmbeddingProvider` DYNAMIC-imports it
 * only on the first `embed()` call. Bun twin of the Py
 * `test_embedding_import_isolation.py`.
 *
 * Each check runs in a FRESH `bun` subprocess (like the Py subprocess guard) so
 * a sibling test that DOES load transformers.js (the ONNX parity suite, when the
 * peer is installed locally) can't contaminate this process's module cache.
 */
import { describe, expect, test } from "bun:test";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const SRC = join(here, "../src");

/** Run `code` in a clean bun process; return { ok, stderr }. */
async function runClean(code: string): Promise<{ ok: boolean; stderr: string }> {
  const proc = Bun.spawn(["bun", "-e", code], {
    cwd: here,
    stderr: "pipe",
    stdout: "pipe",
  });
  const stderr = await new Response(proc.stderr).text();
  const exit = await proc.exited;
  return { ok: exit === 0, stderr };
}

// A transformers.js module resident in this fresh process would surface in the
// require cache — assert it never does.
const NOT_LOADED =
  "const leaked = Object.keys(require.cache ?? {}).some((p) => p.includes('@huggingface/transformers'));"
  + " if (leaked) { throw new Error('transformers.js leaked into the module graph'); }";

describe("embedding — core has no ML deps (fresh-process guards)", () => {
  test("importing the SDK entrypoint does not load transformers.js", async () => {
    const { ok, stderr } = await runClean(
      `await import(${JSON.stringify(join(SRC, "index.ts"))}); ${NOT_LOADED}`,
    );
    expect(stderr).toBe("");
    expect(ok).toBe(true);
  });

  test("running the fake embedding floor pulls no ML dep", async () => {
    const { ok, stderr } = await runClean(
      `const { Kernel } = await import(${JSON.stringify(join(SRC, "kernel/index.ts"))});`
      + " await new Kernel().embed(['the quick brown fox']);"
      + ` ${NOT_LOADED}`,
    );
    expect(stderr).toBe("");
    expect(ok).toBe(true);
  });

  test("importing + constructing the ONNX adapter is cheap (lazy import)", async () => {
    const { ok, stderr } = await runClean(
      `const m = await import(${JSON.stringify(join(SRC, "adapters/embedding/onnx.ts"))});`
      + " const p = new m.OnnxEmbeddingProvider();"
      + " if (p.dims !== 384 || !p.modelId) throw new Error('bad provider surface');"
      + ` ${NOT_LOADED}`,
    );
    expect(stderr).toBe("");
    expect(ok).toBe(true);
  });
});
