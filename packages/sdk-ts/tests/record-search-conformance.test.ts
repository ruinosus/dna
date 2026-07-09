/**
 * The public RecordSearchProvider conformance kit × the sqlite-vec provider
 * (TS twin of `tests/test_record_search_conformance.py`).
 *
 * Runs the whole `recordSearchConformanceSuite` against
 * `SqliteVecRecordSearchProvider` with the deterministic `FakeEmbeddingProvider`
 * floor — fully offline. sqlite-vec is an OPTIONAL peer dep and loading its
 * extension is runtime-dependent (bun:sqlite needs a libsqlite3 that permits
 * extension loading; see driver.ts). When it can't load, the whole suite SKIPS
 * with a clear reason rather than failing — CI installs the extra + a suitable
 * libsqlite3 so these run for real.
 */
import { beforeAll, describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { Kernel } from "../src/kernel/index.js";
import {
  SqliteVecRecordSearchProvider,
} from "../src/adapters/search/sqlite-vec.js";
import { recordSearchConformanceSuite } from "../src/testing/index.js";

// Probe once whether this runtime can load sqlite-vec; skip the suite cleanly
// if not (the honest opt-in-extra story, mirroring the Python importorskip).
let available = false;
let skipReason = "";
const tmpDirs: string[] = [];

beforeAll(async () => {
  try {
    const dir = mkdtempSync(join(tmpdir(), "dna-search-probe-"));
    tmpDirs.push(dir);
    const provider = new SqliteVecRecordSearchProvider(new Kernel(), { dbDir: dir });
    await provider.index([{ scope: "probe", kind: "Story", name: "x", text: "hello world" }]);
    provider.close();
    available = true;
  } catch (err) {
    available = false;
    skipReason = err instanceof Error ? err.message : String(err);
  }
});

function factory() {
  return async () => {
    const dir = mkdtempSync(join(tmpdir(), "dna-search-kit-"));
    tmpDirs.push(dir);
    const provider = new SqliteVecRecordSearchProvider(new Kernel(), { dbDir: dir });
    return {
      provider,
      cleanup: () => {
        provider.close();
        rmSync(dir, { recursive: true, force: true });
      },
    };
  };
}

describe("RecordSearchProvider conformance × sqlite-vec", () => {
  for (const c of recordSearchConformanceSuite(factory())) {
    test(c.name, async () => {
      if (!available) {
        console.warn(`SKIP ${c.name}: sqlite-vec unavailable in this runtime — ${skipReason}`);
        return;
      }
      await c.run();
    });
  }

  test("migration owns schema + idempotent re-open, identity pinned", async () => {
    if (!available) {
      console.warn(`SKIP migration test: sqlite-vec unavailable — ${skipReason}`);
      return;
    }
    const dir = mkdtempSync(join(tmpdir(), "dna-search-mig-"));
    tmpDirs.push(dir);
    const k = new Kernel();
    const p1 = new SqliteVecRecordSearchProvider(k, { dbDir: dir });
    await p1.index([{ scope: "s", kind: "Story", name: "a", text: "hello world" }]);
    p1.close();
    // Re-open the SAME store: migrations already applied → data still searchable.
    const p2 = new SqliteVecRecordSearchProvider(k, { dbDir: dir });
    const hits = await p2.search({ scope: "s", queryText: "hello world", k: 5 });
    expect(hits.some((h) => h.name === "a")).toBe(true);
    p2.close();
    rmSync(dir, { recursive: true, force: true });
  });
});
