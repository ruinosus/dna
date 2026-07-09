/**
 * RecordSearchProvider conformance kit (TS twin of
 * `dna/testing/record_search_conformance.py`).
 *
 * The behavioral contract every `RecordSearchProvider` implementation must
 * satisfy — the search-plane conformance kit. The sqlite-vec provider runs it
 * today; a future adapter runs the SAME kit. Cases assert only on PUBLIC
 * behavior (relative ranking, filtering, overlay shadowing, k-limit,
 * idempotence) under the deterministic fake embedder, so they hold for a real
 * embedder too and run fully offline.
 *
 * A `factory` is an async zero-arg callable returning `{ provider, cleanup }`.
 * The provider must expose async `index` / `search` / `delete`. Each case runs
 * against a FRESH provider (isolation), then always awaits cleanup.
 */

export const FIXTURE_SCOPE = "search-conformance-kit";

/** A record-search provider, structurally. */
export interface ConformanceProvider {
  index(records: Array<Record<string, unknown>>): Promise<number>;
  search(opts: {
    scope: string;
    queryText: string;
    kind?: string | null;
    k?: number;
    tenant?: string;
  }): Promise<Array<Record<string, unknown>>>;
  delete?(ids: Array<Record<string, unknown>>): Promise<number>;
  close?(): void | Promise<void>;
}

export type ProviderFactory = () => Promise<{
  provider: ConformanceProvider;
  cleanup?: () => void | Promise<void>;
}>;

export function fixtureRecords(): Array<Record<string, unknown>> {
  return [
    { scope: FIXTURE_SCOPE, kind: "Story", name: "s-memory", title: "Memory recall",
      text: "memory similarity vector embedding recall cognitive ecphory" },
    { scope: FIXTURE_SCOPE, kind: "Story", name: "s-banana", title: "Banana smoothie",
      text: "banana tropical yellow fruit smoothie breakfast" },
    { scope: FIXTURE_SCOPE, kind: "Story", name: "s-fusion", title: "Hybrid fusion",
      text: "hybrid search fusion reciprocal rank bm25 dense lexical" },
    { scope: FIXTURE_SCOPE, kind: "Genome", name: "g-root", title: "Root genome",
      text: "root genome package catalog identity" },
  ];
}

class SkipCase extends Error {}

async function indexFixture(p: ConformanceProvider): Promise<void> {
  await p.index(fixtureRecords().map((r) => ({ ...r })));
}

function names(hits: Array<Record<string, unknown>>): string[] {
  return hits.map((h) => h.name as string);
}

function assert(cond: unknown, msg: string): void {
  if (!cond) throw new Error(msg);
}

// ---------------------------------------------------------------------------
// cases
// ---------------------------------------------------------------------------

async function indexSearchRoundTrip(p: ConformanceProvider): Promise<void> {
  await indexFixture(p);
  const hits = await p.search({ scope: FIXTURE_SCOPE, queryText: "memory recall cognitive", k: 10 });
  assert(hits.length > 0, "search returned nothing after indexing");
  assert(hits[0]!.name === "s-memory", `expected s-memory first, got ${names(hits).join(",")}`);
  for (const h of hits) {
    assert(
      ["scope", "kind", "name", "score"].every((key) => key in h),
      `hit missing guaranteed keys: ${JSON.stringify(h)}`,
    );
    assert(h.scope === FIXTURE_SCOPE, "wrong scope on hit");
  }
}

async function rrfOrdersByRelevance(p: ConformanceProvider): Promise<void> {
  await indexFixture(p);
  const hits = await p.search({ scope: FIXTURE_SCOPE, queryText: "banana fruit smoothie", k: 10 });
  assert(hits.length > 0 && hits[0]!.name === "s-banana",
    `RRF must rank s-banana first, got ${names(hits).join(",")}`);
  const rank = new Map(names(hits).map((n, i) => [n, i]));
  if (rank.has("s-memory")) {
    assert(rank.get("s-banana")! < rank.get("s-memory")!,
      "relevant doc must outrank an unrelated one");
  }
}

async function kindFilter(p: ConformanceProvider): Promise<void> {
  await indexFixture(p);
  const hits = await p.search({ scope: FIXTURE_SCOPE, queryText: "root genome catalog", kind: "Genome", k: 10 });
  assert(hits.length > 0, "kind-filtered search found nothing");
  assert(hits.every((h) => h.kind === "Genome"),
    `kind filter leaked other kinds: ${JSON.stringify(hits.map((h) => [h.kind, h.name]))}`);
  assert(names(hits).includes("g-root"), "expected g-root");
}

async function kLimit(p: ConformanceProvider): Promise<void> {
  await indexFixture(p);
  const hits = await p.search({ scope: FIXTURE_SCOPE, queryText: "memory banana fusion genome", k: 2 });
  assert(hits.length <= 2, `k=2 must cap results, got ${hits.length}`);
}

async function emptyQuery(p: ConformanceProvider): Promise<void> {
  await indexFixture(p);
  for (const q of ["", "   "]) {
    const hits = await p.search({ scope: FIXTURE_SCOPE, queryText: q, k: 10 });
    assert(hits.length === 0, `empty query must return no hits, got ${names(hits).join(",")}`);
  }
}

async function idempotentIndex(p: ConformanceProvider): Promise<void> {
  await indexFixture(p);
  await indexFixture(p);
  const hits = await p.search({ scope: FIXTURE_SCOPE, queryText: "memory recall", k: 10 });
  const memory = hits.filter((h) => h.name === "s-memory");
  assert(memory.length === 1, `re-index duplicated the doc: ${memory.length} copies of s-memory`);
}

async function deleteRemoves(p: ConformanceProvider): Promise<void> {
  if (typeof p.delete !== "function") throw new SkipCase("no delete()");
  await indexFixture(p);
  await p.delete([{ scope: FIXTURE_SCOPE, kind: "Story", name: "s-banana" }]);
  const hits = await p.search({ scope: FIXTURE_SCOPE, queryText: "banana fruit smoothie", k: 10 });
  assert(!names(hits).includes("s-banana"), `deleted doc still returned: ${names(hits).join(",")}`);
}

async function tenantOverlayShadowsBase(p: ConformanceProvider): Promise<void> {
  await indexFixture(p);
  await p.index([{
    scope: FIXTURE_SCOPE, kind: "Story", name: "s-memory", tenant: "acme",
    title: "Memory recall (acme)",
    text: "memory similarity recall acme overlay variant tenant-specific",
  }]);
  const base = await p.search({ scope: FIXTURE_SCOPE, queryText: "memory recall", kind: "Story", k: 10, tenant: "" });
  const over = await p.search({ scope: FIXTURE_SCOPE, queryText: "memory recall", kind: "Story", k: 10, tenant: "acme" });
  assert(names(base).includes("s-memory"), "base s-memory missing");
  const baseHit = base.find((h) => h.name === "s-memory")!;
  assert(!String(baseHit.title ?? "").toLowerCase().includes("acme"),
    "tenant overlay leaked into a base-tenant search");
  const overMemory = over.filter((h) => h.name === "s-memory");
  assert(overMemory.length === 1, `overlay must shadow base (one s-memory), got ${overMemory.length}`);
  assert(String(overMemory[0]!.title ?? "").toLowerCase().includes("acme"),
    "tenant search must return the overlay variant, not the base");
}

const CASES: Array<{ name: string; requires: string; fn: (p: ConformanceProvider) => Promise<void> }> = [
  { name: "index_search_round_trip", requires: "always", fn: indexSearchRoundTrip },
  { name: "rrf_orders_by_relevance", requires: "always", fn: rrfOrdersByRelevance },
  { name: "kind_filter", requires: "always", fn: kindFilter },
  { name: "k_limit", requires: "always", fn: kLimit },
  { name: "empty_query_returns_empty", requires: "always", fn: emptyQuery },
  { name: "idempotent_index", requires: "always", fn: idempotentIndex },
  { name: "delete_removes", requires: "delete()", fn: deleteRemoves },
  { name: "tenant_overlay_shadows_base", requires: "index() tenant", fn: tenantOverlayShadowsBase },
];

export interface RecordSearchCase {
  name: string;
  requires: string;
  run(): Promise<void>;
}

export function recordSearchConformanceSuite(factory: ProviderFactory): RecordSearchCase[] {
  return CASES.map(({ name, requires, fn }) => ({
    name,
    requires,
    async run(): Promise<void> {
      const { provider, cleanup } = await factory();
      try {
        await fn(provider);
      } finally {
        if (cleanup) await cleanup();
        if (typeof provider.close === "function") {
          try {
            await provider.close();
          } catch {
            /* ignore */
          }
        }
      }
    },
  }));
}

export { SkipCase as SearchCaseNotApplicable };
