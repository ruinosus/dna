/**
 * s-sourceport-contract-cleanup — SourceCapabilities conformance (TS twin
 * of tests/test_source_capabilities_conformance.py).
 *
 * Adapters DECLARE their capabilities explicitly; the kernel consults
 * `sourceCapabilities()` instead of `typeof src.query === "function"`
 * feature-tests. This suite pins, per in-repo adapter:
 *
 *     declared == deriveCapabilities(adapter)   // structural oracle
 *
 * so a declaration can't lie about what the adapter actually implements.
 */
import { describe, expect, test } from "bun:test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { FilesystemSource } from "../src/adapters/filesystem/source.js";
import { PostgresSource } from "../src/adapters/postgres/source.js";
import {
  deriveCapabilities,
  sourceCapabilities,
  type SourceCapabilities,
} from "../src/kernel/capabilities.js";

function fsSource(): FilesystemSource {
  return new FilesystemSource(mkdtempSync(join(tmpdir(), "dna-caps-")));
}

function pgSource(): PostgresSource {
  // Fake pool — the pool is only touched on the first real operation.
  return new PostgresSource({ pool: {} as never });
}

describe("declaration honesty (declared == structural oracle)", () => {
  const cases: Array<[string, () => object]> = [
    ["FilesystemSource", fsSource],
    ["PostgresSource", pgSource],
  ];

  for (const [name, make] of cases) {
    test(name, () => {
      const src = make() as { capabilities(): SourceCapabilities };
      const declared = src.capabilities();
      const oracle = deriveCapabilities(src, declared.source);
      expect(declared).toEqual(oracle);
    });
  }
});

describe("sourceCapabilities accessor", () => {
  test("uses the declaration and memoizes per instance", () => {
    const src = fsSource();
    const first = sourceCapabilities(src);
    expect(first).toEqual(src.capabilities());
    expect(sourceCapabilities(src)).toBe(first);
  });

  test("undeclared adapter falls back to structural derivation", () => {
    class LegacyExternalSource {
      async loadAll(): Promise<Record<string, unknown>[]> {
        return [];
      }
      async loadOne(): Promise<Record<string, unknown> | null> {
        return null;
      }
    }
    const caps = sourceCapabilities(new LegacyExternalSource());
    expect(caps.source).toBe("LegacyExternalSource");
    expect(caps.granularOne).toBe(true);
    expect(caps.granularList).toBe(false);
    expect(caps.queryPushdown).toBe(false);
    expect(caps.drafts).toBe(false);
  });

  test("a broken capabilities() degrades to derivation, never crashes", () => {
    class BrokenCapsSource {
      capabilities(): never {
        throw new Error("boom");
      }
      async *query(): AsyncIterable<Record<string, unknown>> {}
    }
    const caps = sourceCapabilities(new BrokenCapsSource());
    expect(caps.queryPushdown).toBe(true); // derived from the real method
  });
});

describe("adapter expectations pinned", () => {
  test("filesystem: in-memory query core + granular reads; no write surface", () => {
    const caps = fsSource().capabilities();
    expect(caps.queryPushdown).toBe(true);
    expect(caps.granularOne).toBe(true);
    expect(caps.granularList).toBe(true); // listDocRefs (s-dna-port-surface-parity)
    expect(caps.drafts).toBe(false);
  });

  test("postgres: write half + versions/bundle-read + listDocRefs; query is Py-only", () => {
    const caps = pgSource().capabilities();
    expect(caps.queryPushdown).toBe(false); // F2: PG TS has no push-down
    expect(caps.versions).toBe(true);
    expect(caps.bundleRead).toBe(true);
    expect(caps.kernelAttachable).toBe(true);
    expect(caps.granularList).toBe(true); // listDocRefs (s-dna-port-surface-parity)
    expect(caps.granularOne).toBe(false); // loadOne stays Py-only this phase
  });
});
