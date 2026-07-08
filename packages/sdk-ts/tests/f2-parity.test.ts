/**
 * Two-planes F2 — Py↔TS parity by shared fixture.
 *
 * Runs every case in tests/fixtures/f2-parity.json against the TS
 * in-memory query/count core (queryDocs/countDocs — the exact code path
 * FilesystemSource.query/count delegates to). The Py twin
 * (packages/sdk-py/tests/test_f2_parity_fixture.py) runs the SAME
 * fixture against the Py SourcePort protocol-default. A failure on
 * either side is a parity divergence with an immediate reproduction.
 */
import { describe, test, expect } from "bun:test";
import { readFileSync } from "node:fs";

import { queryDocs, countDocs, type CountResult } from "../src/kernel/protocols.js";

interface FixtureCase {
  name: string;
  op: "query" | "count";
  kind: string;
  filter?: Record<string, unknown>;
  order_by?: string[];
  limit?: number;
  offset?: number;
  group_by?: string;
  expected: string[] | CountResult;
}

const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/f2-parity.json", import.meta.url), "utf-8"),
) as { docs: Record<string, unknown>[]; cases: FixtureCase[] };

describe("F2 Py↔TS parity fixture", () => {
  test("fixture sanity: 2 kinds, cases present", () => {
    const kinds = new Set(fixture.docs.map((d) => d.kind));
    expect(kinds).toEqual(new Set(["Story", "Issue"]));
    expect(fixture.cases.length).toBeGreaterThanOrEqual(8);
  });

  for (const c of fixture.cases) {
    test(c.name, () => {
      if (c.op === "query") {
        const rows = queryDocs(fixture.docs, c.kind, {
          filter: c.filter,
          orderBy: c.order_by,
          limit: c.limit,
          offset: c.offset,
        });
        const names = rows.map(
          (r) => (r.metadata as Record<string, unknown> | undefined)?.name ?? null,
        );
        expect(names).toEqual(c.expected as string[]);
      } else {
        const res = countDocs(fixture.docs, c.kind, {
          filter: c.filter,
          groupBy: c.group_by,
        });
        expect(res).toEqual(c.expected as CountResult);
      }
    });
  }
});
