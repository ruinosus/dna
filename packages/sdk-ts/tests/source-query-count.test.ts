/**
 * Two-planes F2 (spec D2) — query/count on the TS SourcePort.
 *
 * Ports the Python scenarios (test_sourceport_query_protocol.py +
 * test_sourceport_count_protocol.py) over the TS pure helpers
 * (resolveFieldPath / matchFilter / applyOrderBy / queryDocs / countDocs)
 * plus a FilesystemSource integration pass over a tmp-dir scope.
 *
 * NULLS LAST in DESC is asserted from day one — TS is born with the
 * post-i-121 semantics (the Py side had to be fixed; parity with PG
 * `DESC NULLS LAST`).
 */
import { describe, test, expect } from "bun:test";
import { mkdirSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  QueryError,
  resolveFieldPath,
  matchFilter,
  applyOrderBy,
  queryDocs,
  countDocs,
  type RecordStorePort,
} from "../src/kernel/protocols.js";
import { FilesystemSource } from "../src/adapters/filesystem/source.js";
import { PostgresSource } from "../src/adapters/postgres/source.js";

function doc(
  kind: string,
  name: string,
  spec: Record<string, unknown>,
): Record<string, unknown> {
  return { kind, metadata: { name }, spec };
}

// ---------------------------------------------------------------------------
// resolveFieldPath
// ---------------------------------------------------------------------------

describe("resolveFieldPath", () => {
  const d = doc("Story", "s-1", { status: "todo", nested: { deep: 7 } });

  test("'name' resolves metadata.name", () => {
    expect(resolveFieldPath(d, "name")).toBe("s-1");
  });

  test("'kind' resolves top-level kind", () => {
    expect(resolveFieldPath(d, "kind")).toBe("Story");
  });

  test("unprefixed path resolves under spec.", () => {
    expect(resolveFieldPath(d, "status")).toBe("todo");
    expect(resolveFieldPath(d, "nested.deep")).toBe(7);
  });

  test("explicit spec./metadata. prefixes work", () => {
    expect(resolveFieldPath(d, "spec.status")).toBe("todo");
    expect(resolveFieldPath(d, "metadata.name")).toBe("s-1");
  });

  test("missing segment returns null (never undefined)", () => {
    expect(resolveFieldPath(d, "nope")).toBeNull();
    expect(resolveFieldPath(d, "nested.absent")).toBeNull();
    expect(resolveFieldPath(d, "status.too.deep")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// matchFilter — same operators as the Py _PG_OP_MAP + "in"
// ---------------------------------------------------------------------------

describe("matchFilter", () => {
  const d = doc("Story", "s-1", { status: "todo", priority: 3, title: "fix cache bug" });

  test("shorthand equality", () => {
    expect(matchFilter(d, { status: "todo" })).toBe(true);
    expect(matchFilter(d, { status: "done" })).toBe(false);
  });

  test("eq / neq operators", () => {
    expect(matchFilter(d, { status: { eq: "todo" } })).toBe(true);
    expect(matchFilter(d, { status: { neq: "todo" } })).toBe(false);
    expect(matchFilter(d, { status: { neq: "done" } })).toBe(true);
  });

  test("in operator", () => {
    expect(matchFilter(d, { status: { in: ["todo", "done"] } })).toBe(true);
    expect(matchFilter(d, { status: { in: ["done"] } })).toBe(false);
    // Empty / null membership list matches nothing (Py: `val or ()`).
    expect(matchFilter(d, { status: { in: [] } })).toBe(false);
    expect(matchFilter(d, { status: { in: null } })).toBe(false);
  });

  test("like operator — SQL %/_ wildcards, literals escaped", () => {
    expect(matchFilter(d, { title: { like: "fix%" } })).toBe(true);
    expect(matchFilter(d, { title: { like: "%cache%" } })).toBe(true);
    expect(matchFilter(d, { title: { like: "fix cache bu_" } })).toBe(true);
    expect(matchFilter(d, { title: { like: "cache" } })).toBe(false);
    // Regex metachars in the pattern are literals, not regex.
    expect(matchFilter(d, { title: { like: "fix.cache%" } })).toBe(false);
  });

  test("gt/gte/lt/lte — null never matches range ops", () => {
    expect(matchFilter(d, { priority: { gt: 2 } })).toBe(true);
    expect(matchFilter(d, { priority: { gte: 3 } })).toBe(true);
    expect(matchFilter(d, { priority: { lt: 3 } })).toBe(false);
    expect(matchFilter(d, { priority: { lte: 3 } })).toBe(true);
    expect(matchFilter(d, { absent: { gt: 0 } })).toBe(false);
  });

  test("unknown operator throws QueryError", () => {
    expect(() => matchFilter(d, { status: { regex: ".*" } })).toThrow(QueryError);
  });

  test("multi-key dict value is shorthand equality, not an operator", () => {
    // Py: only single-key dicts enter the operator branch.
    expect(matchFilter(d, { status: { eq: "todo", extra: 1 } })).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// applyOrderBy — NULLS LAST regardless of direction (i-121 born-correct)
// ---------------------------------------------------------------------------

describe("applyOrderBy", () => {
  const rows = [
    doc("Story", "null1", {}),
    doc("Story", "new", { updated_at: "2026-06-10" }),
    doc("Story", "old", { updated_at: "2026-06-01" }),
    doc("Story", "null2", {}),
  ];

  test("ascending — nulls last", () => {
    const out = applyOrderBy(rows, ["spec.updated_at"]);
    expect(out.map((r) => (r.metadata as any).name)).toEqual([
      "old", "new", "null1", "null2",
    ]);
  });

  test("descending — nulls STILL last (i-121 parity with PG DESC NULLS LAST)", () => {
    const out = applyOrderBy(rows, ["-spec.updated_at"]);
    const names = out.map((r) => (r.metadata as any).name);
    expect(names.slice(0, 2)).toEqual(["new", "old"]);
    expect(new Set(names.slice(2))).toEqual(new Set(["null1", "null2"]));
  });

  test("multi-key: secondary order applied within primary ties, stable", () => {
    const data = [
      doc("Story", "b2", { feature: "beta", priority: 2 }),
      doc("Story", "a1", { feature: "alpha", priority: 1 }),
      doc("Story", "b9", { feature: "beta", priority: 9 }),
      doc("Story", "a3", { feature: "alpha", priority: 3 }),
    ];
    const out = applyOrderBy(data, ["feature", "-priority"]);
    expect(out.map((r) => (r.metadata as any).name)).toEqual([
      "a3", "a1", "b9", "b2",
    ]);
  });

  test("numeric values sort numerically, not lexicographically", () => {
    const data = [
      doc("Story", "ten", { n: 10 }),
      doc("Story", "two", { n: 2 }),
    ];
    const out = applyOrderBy(data, ["n"]);
    expect(out.map((r) => (r.metadata as any).name)).toEqual(["two", "ten"]);
  });

  test("mixed int/str values fall back to stringified compare (no crash)", () => {
    const data = [
      doc("Story", "s", { v: "abc" }),
      doc("Story", "n", { v: 5 }),
    ];
    const out = applyOrderBy(data, ["v"]);
    expect(out.map((r) => (r.metadata as any).name)).toEqual(["n", "s"]);
  });

  test("does not mutate the input array", () => {
    const data = [doc("Story", "b", { x: 2 }), doc("Story", "a", { x: 1 })];
    const snapshot = data.map((r) => (r.metadata as any).name);
    applyOrderBy(data, ["x"]);
    expect(data.map((r) => (r.metadata as any).name)).toEqual(snapshot);
  });
});

// ---------------------------------------------------------------------------
// queryDocs / countDocs — the in-memory fallback core (mirror of the Py
// SourcePort protocol-default)
// ---------------------------------------------------------------------------

const DATASET = [
  doc("Story", "s-1", { status: "todo", priority: 3 }),
  doc("Story", "s-2", { status: "done", priority: 1 }),
  doc("Story", "s-3", { status: "todo" }),
  doc("Issue", "i-1", { status: "open" }),
];

describe("queryDocs", () => {
  test("filters by kind first", () => {
    const out = queryDocs(DATASET, "Issue");
    expect(out.map((r) => (r.metadata as any).name)).toEqual(["i-1"]);
  });

  test("filter + orderBy + limit/offset compose", () => {
    const out = queryDocs(DATASET, "Story", {
      filter: { status: "todo" },
      orderBy: ["priority"],
      limit: 1,
      offset: 1,
    });
    // priority asc nulls-last: s-1(3), s-3(null) → offset 1 → s-3
    expect(out.map((r) => (r.metadata as any).name)).toEqual(["s-3"]);
  });
});

describe("countDocs", () => {
  test("total without groupBy keeps groups null", () => {
    expect(countDocs(DATASET, "Story")).toEqual({ total: 3, groups: null });
  });

  test("groupBy counts per key, null key for missing field, count DESC then key ASC null-last", () => {
    const res = countDocs(DATASET, "Story", { groupBy: "spec.priority" });
    expect(res.total).toBe(3);
    expect(res.groups).toEqual([
      { key: 1, count: 1 },
      { key: 3, count: 1 },
      { key: null, count: 1 },
    ]);
  });

  test("groupBy status — tie sorted by key ASC", () => {
    const res = countDocs(DATASET, "Story", { groupBy: "status" });
    expect(res.groups).toEqual([
      { key: "todo", count: 2 },
      { key: "done", count: 1 },
    ]);
  });

  test("filter applies before counting", () => {
    expect(countDocs(DATASET, "Story", { filter: { status: "todo" } })).toEqual({
      total: 2,
      groups: null,
    });
  });
});

// ---------------------------------------------------------------------------
// FilesystemSource integration — query/count over an on-disk scope
// ---------------------------------------------------------------------------

describe("FilesystemSource query/count", () => {
  function makeScope(): string {
    const tmp = mkdtempSync(join(tmpdir(), "f2-fs-"));
    const scopeDir = join(tmp, "sc");
    mkdirSync(scopeDir, { recursive: true });
    const docs: Array<[string, string]> = [
      ["s-a.yaml", "kind: Story\nmetadata:\n  name: s-a\nspec:\n  status: todo\n  priority: 2\n"],
      ["s-b.yaml", "kind: Story\nmetadata:\n  name: s-b\nspec:\n  status: done\n  priority: 1\n"],
      ["s-c.yaml", "kind: Story\nmetadata:\n  name: s-c\nspec:\n  status: todo\n"],
      ["i-x.yaml", "kind: Issue\nmetadata:\n  name: i-x\nspec:\n  status: open\n"],
    ];
    for (const [file, content] of docs) writeFileSync(join(scopeDir, file), content);
    return tmp;
  }

  test("query: filter + order + limit over loadAll", async () => {
    const tmp = makeScope();
    try {
      const src = new FilesystemSource(tmp);
      const rows: Record<string, unknown>[] = [];
      for await (const r of src.query("sc", "Story", {
        filter: { status: "todo" },
        orderBy: ["-priority"],
        limit: 2,
      })) rows.push(r);
      // -priority DESC nulls last: s-a(2), s-c(null)
      expect(rows.map((r) => (r.metadata as any).name)).toEqual(["s-a", "s-c"]);
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  test("count: total + groupBy with null key", async () => {
    const tmp = makeScope();
    try {
      const src = new FilesystemSource(tmp);
      const res = await src.count("sc", "Story", { groupBy: "spec.priority" });
      expect(res).toEqual({
        total: 3,
        groups: [
          { key: 1, count: 1 },
          { key: 2, count: 1 },
          { key: null, count: 1 },
        ],
      });
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });

  test("opts.tenant is a documented NO-OP on the FS TS adapter", async () => {
    // The FS TS source has no tenant-aware overlay in loadAll (divergence
    // from Py, tracked for F2.5) — passing tenant must not change results.
    const tmp = makeScope();
    try {
      const src = new FilesystemSource(tmp);
      const plain = await src.count("sc", "Story");
      const tenanted = await src.count("sc", "Story", { tenant: "acme" });
      expect(tenanted).toEqual(plain);
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });
});

// ---------------------------------------------------------------------------
// RecordStorePort conformance — BY COMPOSITION in F2.
//
// No single TS adapter satisfies all 4 ops yet (FS has no save/delete;
// PG TS has no query/count push-down this phase). The COMPILE-TIME
// conformance assertions live next to each adapter class (tsconfig
// excludes tests/ from `bun run typecheck`, so type-level checks in this
// file would be decorative) — here we assert the runtime structure.
// Full conformance arrives when TS gains a writable FS source / PG
// push-down (F2.5+).
// ---------------------------------------------------------------------------

describe("RecordStorePort conformance (composition)", () => {
  test("FilesystemSource provides the query|count half", () => {
    const fs = new FilesystemSource("/tmp/nope");
    const half: Pick<RecordStorePort, "query" | "count"> = fs;
    expect(typeof half.query).toBe("function");
    expect(typeof half.count).toBe("function");
  });

  test("PostgresSource provides the saveDocument|deleteDocument half (no query/count in F2)", () => {
    expect(typeof PostgresSource.prototype.saveDocument).toBe("function");
    expect(typeof PostgresSource.prototype.deleteDocument).toBe("function");
    // F2: query/count push-down is Py-only — TS PG doesn't even have query.
    expect((PostgresSource.prototype as any).query).toBeUndefined();
    expect((PostgresSource.prototype as any).count).toBeUndefined();
  });
});
