/**
 * rec-embeddable-provider — the core stays free of the sqlite-vec dependency
 * (TS side; twin of `tests/test_search_import_isolation.py`).
 *
 * The sqlite-vec RecordSearchProvider is an OPTIONAL peer dep (`sqlite-vec`).
 * Importing the SDK entrypoint, running the fake embedder, and importing the
 * pure RRF core must NEVER pull `sqlite-vec` into the module graph. Each check
 * runs in a FRESH bun subprocess so a sibling suite that DOES load the provider
 * can't contaminate this process's module cache.
 */
import { describe, expect, test } from "bun:test";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const SRC = join(here, "../src");

async function runClean(code: string): Promise<{ ok: boolean; stderr: string }> {
  const proc = Bun.spawn(["bun", "-e", code], { cwd: here, stderr: "pipe", stdout: "pipe" });
  const stderr = await new Response(proc.stderr).text();
  const exit = await proc.exited;
  return { ok: exit === 0, stderr };
}

const NOT_LOADED =
  "const leaked = Object.keys(require.cache ?? {}).some((p) => p.includes('sqlite-vec'));"
  + " if (leaked) { throw new Error('sqlite-vec leaked into the module graph'); }";

describe("search — core has no sqlite-vec dep (fresh-process guards)", () => {
  test("importing the SDK entrypoint does not load sqlite-vec", async () => {
    const { ok, stderr } = await runClean(
      `await import(${JSON.stringify(join(SRC, "index.ts"))}); ${NOT_LOADED}`,
    );
    expect(stderr).toBe("");
    expect(ok).toBe(true);
  });

  test("running the fake embedder pulls no sqlite-vec", async () => {
    const { ok, stderr } = await runClean(
      `const { Kernel } = await import(${JSON.stringify(join(SRC, "kernel/index.ts"))});`
      + " await new Kernel().embed(['hello']);"
      + ` ${NOT_LOADED}`,
    );
    expect(stderr).toBe("");
    expect(ok).toBe(true);
  });

  test("importing the pure RRF core pulls no sqlite-vec", async () => {
    const { ok, stderr } = await runClean(
      `const m = await import(${JSON.stringify(join(SRC, "adapters/search/rrf.ts"))});`
      + " if (!m.reciprocalRankFusion([['a','b'],['b','a']]).length) throw new Error('rrf broken');"
      + ` ${NOT_LOADED}`,
    );
    expect(stderr).toBe("");
    expect(ok).toBe(true);
  });
});
