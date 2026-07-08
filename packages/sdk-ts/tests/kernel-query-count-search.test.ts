/**
 * Two-planes F2 (spec D2) — kernel.query/count/search public surface (TS).
 *
 * Mirrors the Py tests (test_kernel_query.py / test_kernel_count.py /
 * test_kernel_search.py) with a stub source capturing kwargs. The TS
 * kernel has NO origin/inheritance machinery (Py-only) — query/count are
 * pure delegation + tenant binding + cross-scope `scopes`.
 */
import { describe, test, expect, spyOn, afterEach } from "bun:test";

import { Kernel } from "../src/kernel/index.js";
import type {
  CountResult,
  SourceCountOpts,
  SourcePort,
  SourceQueryOpts,
} from "../src/kernel/protocols.js";

function row(name: string, spec: Record<string, unknown> = {}): Record<string, unknown> {
  return { kind: "Story", metadata: { name }, spec };
}

interface Captured {
  scope: string;
  kind: string;
  opts: SourceQueryOpts | SourceCountOpts | undefined;
}

function makeSource(opts: {
  rowsByScope?: Record<string, Record<string, unknown>[]>;
  countsByScope?: Record<string, CountResult>;
  withQuery?: boolean;
  withCount?: boolean;
}): { src: SourcePort; calls: Captured[] } {
  const calls: Captured[] = [];
  const rowsByScope = opts.rowsByScope ?? {};
  const countsByScope = opts.countsByScope ?? {};
  const src: SourcePort = {
    supportsReaders: false,
    loadBootstrapDocs: async () => [],
    loadAll: async () => [],
    resolveRef: async () => "",
    loadLayer: async () => [],
  };
  if (opts.withQuery !== false) {
    src.query = async function* (scope, kind, qopts) {
      calls.push({ scope, kind, opts: qopts });
      for (const r of rowsByScope[scope] ?? []) yield r;
    };
  }
  if (opts.withCount !== false) {
    src.count = async (scope, kind, copts) => {
      calls.push({ scope, kind, opts: copts });
      return countsByScope[scope] ?? { total: 2, groups: null };
    };
  }
  return { src, calls };
}

function makeKernel(sourceOpts: Parameters<typeof makeSource>[0], tenantBinding?: string) {
  const { src, calls } = makeSource(sourceOpts);
  const k = new Kernel();
  if (tenantBinding) k.tenant = tenantBinding;
  k.source(src);
  return { k, calls };
}

async function collect(it: AsyncIterable<Record<string, unknown>>) {
  const out: Record<string, unknown>[] = [];
  for await (const r of it) out.push(r);
  return out;
}

const names = (rows: Record<string, unknown>[]) =>
  rows.map((r) => (r.metadata as Record<string, unknown>).name);

// ---------------------------------------------------------------------------
// kernel.query — delegation + tenant binding + scopes
// ---------------------------------------------------------------------------

describe("kernel.query (TS)", () => {
  test("delegates opts to source.query", async () => {
    const { k, calls } = makeKernel({ rowsByScope: { sc: [row("s-1")] } });
    const out = await collect(k.query("sc", "Story", {
      filter: { status: "todo" },
      orderBy: ["-updated_at"],
      limit: 5,
      offset: 2,
    }));
    expect(names(out)).toEqual(["s-1"]);
    expect(calls).toHaveLength(1);
    expect(calls[0]!.scope).toBe("sc");
    expect(calls[0]!.kind).toBe("Story");
    const qopts = calls[0]!.opts as SourceQueryOpts;
    expect(qopts.filter).toEqual({ status: "todo" });
    expect(qopts.orderBy).toEqual(["-updated_at"]);
    expect(qopts.limit).toBe(5);
    expect(qopts.offset).toBe(2);
  });

  test("tenant binding: Kernel.tenant wins when opts.tenant absent; explicit wins over binding", async () => {
    const { k, calls } = makeKernel({ rowsByScope: {} }, "globex");
    await collect(k.query("sc", "Story"));
    expect((calls[0]!.opts as SourceQueryOpts).tenant).toBe("globex");
    await collect(k.query("sc", "Story", { tenant: "acme" }));
    expect((calls[1]!.opts as SourceQueryOpts).tenant).toBe("acme");
  });

  test("no tenant when neither set", async () => {
    const { k, calls } = makeKernel({ rowsByScope: {} });
    await collect(k.query("sc", "Story"));
    expect((calls[0]!.opts as SourceQueryOpts).tenant).toBeUndefined();
  });

  test("scopes: concat WITHOUT dedup — same name in two scopes yields both rows, in scope order", async () => {
    const { k, calls } = makeKernel({
      rowsByScope: {
        a: [row("s-1"), row("dup")],
        b: [row("dup"), row("s-9")],
      },
    });
    const out = await collect(k.query("a", "Story", { scopes: ["a", "b"] }));
    expect(names(out)).toEqual(["s-1", "dup", "dup", "s-9"]);
    expect(calls.map((c) => c.scope)).toEqual(["a", "b"]);
  });

  test("scopes wins over a diverging positional scope", async () => {
    const { k, calls } = makeKernel({
      rowsByScope: { a: [row("s-1")], b: [row("s-2")], x: [row("nope")] },
    });
    const out = await collect(k.query("x", "Story", { scopes: ["a", "b"] }));
    expect(names(out)).toEqual(["s-1", "s-2"]);
    expect(calls.map((c) => c.scope)).not.toContain("x");
  });

  test("scopes passes through kwargs + tenant binding per scope", async () => {
    const { k, calls } = makeKernel(
      { rowsByScope: { a: [row("s-1")], b: [] } },
      "globex",
    );
    await collect(k.query("a", "Story", { scopes: ["a", "b"], limit: 3 }));
    for (const c of calls) {
      expect((c.opts as SourceQueryOpts).limit).toBe(3);
      expect((c.opts as SourceQueryOpts).tenant).toBe("globex");
    }
  });

  test("no source registered → clear error", async () => {
    const k = new Kernel();
    await expect(collect(k.query("sc", "Story"))).rejects.toThrow(
      /No source registered/,
    );
  });

  test("source without query → clear capability error", async () => {
    const { k } = makeKernel({ withQuery: false });
    await expect(collect(k.query("sc", "Story"))).rejects.toThrow(
      /source does not implement query/,
    );
  });
});

// ---------------------------------------------------------------------------
// kernel.count — delegation + scopes sum/merge
// ---------------------------------------------------------------------------

describe("kernel.count (TS)", () => {
  test("delegates to source.count", async () => {
    const { k, calls } = makeKernel({
      countsByScope: {
        sc: { total: 2, groups: [{ key: "todo", count: 2 }] },
      },
    });
    const res = await k.count("sc", "Story", {
      filter: { status: "todo" },
      groupBy: "spec.status",
    });
    expect(res).toEqual({ total: 2, groups: [{ key: "todo", count: 2 }] });
    const copts = calls[0]!.opts as SourceCountOpts;
    expect(copts.filter).toEqual({ status: "todo" });
    expect(copts.groupBy).toBe("spec.status");
  });

  test("tenant binding mirrors query", async () => {
    const { k, calls } = makeKernel({}, "globex");
    await k.count("sc", "Story");
    expect((calls[0]!.opts as SourceCountOpts).tenant).toBe("globex");
    await k.count("sc", "Story", { tenant: "acme" });
    expect((calls[1]!.opts as SourceCountOpts).tenant).toBe("acme");
  });

  test("scopes: sums totals + merges groups by key, re-sorted count DESC", async () => {
    const { k, calls } = makeKernel({
      countsByScope: {
        a: { total: 3, groups: [{ key: "todo", count: 2 }, { key: "done", count: 1 }] },
        b: { total: 4, groups: [{ key: "done", count: 3 }, { key: null, count: 1 }] },
      },
    });
    const res = await k.count("a", "Story", {
      groupBy: "spec.status",
      scopes: ["a", "b"],
    });
    expect(calls.map((c) => c.scope)).toEqual(["a", "b"]);
    expect(res.total).toBe(7);
    expect(res.groups).toEqual([
      { key: "done", count: 4 },
      { key: "todo", count: 2 },
      { key: null, count: 1 },
    ]);
  });

  test("scopes group merge: null key LAST on count tie", async () => {
    const { k } = makeKernel({
      countsByScope: {
        a: { total: 1, groups: [{ key: null, count: 1 }] },
        b: { total: 1, groups: [{ key: "done", count: 1 }] },
      },
    });
    const res = await k.count("a", "Story", {
      groupBy: "spec.status",
      scopes: ["a", "b"],
    });
    expect(res.groups).toEqual([
      { key: "done", count: 1 },
      { key: null, count: 1 },
    ]);
  });

  test("scopes wins over positional scope; groups stay null without groupBy", async () => {
    const { k, calls } = makeKernel({});
    const res = await k.count("ignored", "Story", { scopes: ["a", "b"] });
    expect(calls.map((c) => c.scope)).toEqual(["a", "b"]);
    expect(res).toEqual({ total: 4, groups: null });
  });

  test("source without count → clear capability error", async () => {
    const { k } = makeKernel({ withCount: false });
    await expect(k.count("sc", "Story")).rejects.toThrow(
      /source does not implement count/,
    );
  });
});

// ---------------------------------------------------------------------------
// kernel.search — provider plugável + fallback léxico degraded
// ---------------------------------------------------------------------------

describe("kernel.search (TS)", () => {
  test("routes to the registered provider (degraded=false)", async () => {
    const { k } = makeKernel({});
    const calls: unknown[] = [];
    k.recordSearchProvider({
      async search(opts) {
        calls.push(opts);
        return [{ scope: opts.scope, kind: "Story", name: "s-hit", score: 0.9 }];
      },
    });
    const res = await k.search("sc", "tema x", { kind: "Story", k: 5 });
    expect(res.degraded).toBe(false);
    expect(res.hits.map((h) => h.name)).toEqual(["s-hit"]);
    expect(calls).toEqual([
      { scope: "sc", queryText: "tema x", kind: "Story", k: 5, tenant: "" },
    ]);
  });

  test("no provider → lexical token-set fallback, degraded=true (NEVER substring over JSON)", async () => {
    const { k } = makeKernel({
      rowsByScope: {
        sc: [
          row("s-match", { title: "cache invalidation storm" }),
          row("s-miss", { title: "totally unrelated" }),
        ],
      },
    });
    const res = await k.search("sc", "invalidation cache", { kind: "Story", k: 5 });
    expect(res.degraded).toBe(true);
    expect(res.hits.map((h) => h.name)).toEqual(["s-match"]);
    expect(res.hits[0]!.score as number).toBeGreaterThan(0);
  });

  test("lexical fallback matches tokens recursively over nested spec string values", async () => {
    const { k } = makeKernel({
      rowsByScope: {
        sc: [row("s-deep", { meta: { tags: ["cache", "storm"] } })],
      },
    });
    const res = await k.search("sc", "storm", { kind: "Story" });
    expect(res.hits.map((h) => h.name)).toEqual(["s-deep"]);
  });

  test("fallback without kind returns empty degraded", async () => {
    const { k } = makeKernel({});
    const res = await k.search("sc", "qualquer coisa");
    expect(res).toEqual({ hits: [], degraded: true });
  });

  test("provider error → lexical fallback, never crash", async () => {
    const { k } = makeKernel({
      rowsByScope: { sc: [row("s-1", { title: "abc" })] },
    });
    k.recordSearchProvider({
      async search() {
        throw new Error("gateway 403");
      },
    });
    const res = await k.search("sc", "abc", { kind: "Story" });
    expect(res.degraded).toBe(true);
    expect(res.hits.map((h) => h.name)).toEqual(["s-1"]);
  });

  test("score = present query tokens ÷ total; sorted DESC; cut at k", async () => {
    const { k } = makeKernel({
      rowsByScope: {
        sc: [
          row("s-half", { title: "cache only" }),
          row("s-full", { title: "cache invalidation here" }),
          row("s-also-full", { title: "invalidation cache too" }),
        ],
      },
    });
    const res = await k.search("sc", "cache invalidation", { kind: "Story", k: 2 });
    expect(res.hits).toHaveLength(2);
    expect(res.hits.map((h) => h.name)).toEqual(["s-full", "s-also-full"]);
    expect(res.hits[0]!.score).toBe(1);
  });

  // ---------------------------------------------------------------------------
  // Damper — warn once per episode, debug on repeats, reset on success
  // Mirrors the Py test_search_provider_failure_damper.
  // ---------------------------------------------------------------------------
  test("damper: first failure → warn; second → debug; success resets episode", async () => {
    const warnSpy = spyOn(console, "warn").mockImplementation(() => {});
    const debugSpy = spyOn(console, "debug").mockImplementation(() => {});

    try {
      const { k } = makeKernel({
        rowsByScope: { sc: [row("s-1", { title: "abc" })] },
      });

      let callCount = 0;
      k.recordSearchProvider({
        async search() {
          callCount++;
          // First two calls fail; third succeeds; fourth fails again.
          if (callCount === 3) {
            return [{ scope: "sc", kind: "Story", name: "s-1", score: 0.9 }];
          }
          throw new Error("provider down");
        },
      });

      // Call 1 — first failure in episode → must warn exactly once
      await k.search("sc", "abc", { kind: "Story" });
      expect(warnSpy).toHaveBeenCalledTimes(1);
      expect(debugSpy).toHaveBeenCalledTimes(0);

      // Call 2 — second consecutive failure → warn stays at 1, debug gets 1
      await k.search("sc", "abc", { kind: "Story" });
      expect(warnSpy).toHaveBeenCalledTimes(1);
      expect(debugSpy).toHaveBeenCalledTimes(1);

      // Call 3 — provider succeeds → episode resets (degraded=false)
      const resOk = await k.search("sc", "abc", { kind: "Story" });
      expect(resOk.degraded).toBe(false);
      // No new warn/debug on success
      expect(warnSpy).toHaveBeenCalledTimes(1);
      expect(debugSpy).toHaveBeenCalledTimes(1);

      // Call 4 — new failure episode starts → warn fires again
      await k.search("sc", "abc", { kind: "Story" });
      expect(warnSpy).toHaveBeenCalledTimes(2);
      expect(debugSpy).toHaveBeenCalledTimes(1);
    } finally {
      warnSpy.mockRestore();
      debugSpy.mockRestore();
    }
  });
});
