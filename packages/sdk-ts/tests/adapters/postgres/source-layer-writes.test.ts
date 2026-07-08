/**
 * PostgresSource — TS-side tenant-layer write parity (Chunk 3.8 of Eval Lab).
 *
 * Mirrors python-harness/tests/sdk/test_postgres_writable_layer.py to
 * keep both adapter implementations honest about tenant-layer support.
 *
 * Skipped cleanly when neither DNA_POSTGRES_TEST_URL nor DATABASE_URL
 * is set. Local devstack runs Postgres at
 *     postgresql://dna:dna@localhost:5432/dna
 *
 * Runs with:
 *   DNA_POSTGRES_TEST_URL=postgresql://dna:dna@localhost:5432/dna \
 *     bun test tests/adapters/postgres/source-layer-writes.test.ts
 */
import { afterAll, beforeAll, describe, expect, it } from "bun:test";
import { PostgresSource } from "../../../src/adapters/postgres/index.js";

const dsn =
  process.env.DNA_POSTGRES_TEST_URL ?? process.env.DATABASE_URL ?? null;

const SCHEMA = `dna_test_tenant_layer_ts_${process.pid}_${Date.now()}`;
const SCOPE = "test-tenant-layer-scope-ts";
const KIND = "EvalCase";
const TENANT = "acme-ts";

function evalCaseRaw(name: string, marker = "default") {
  return {
    apiVersion: "evals.io/v1",
    kind: KIND,
    metadata: { name },
    spec: {
      input: `hello-${marker}`,
      expected: `world-${marker}`,
    },
  };
}

describe.skipIf(!dsn)("PostgresSource — tenant-layer write parity (TS side)", () => {
  let src: PostgresSource;
  // pg Pool exposed via the adapter; used for direct SELECT assertions.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let pool: any;

  beforeAll(async () => {
    src = new PostgresSource({ connectionString: dsn!, schema: SCHEMA });
    await src.init();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    pool = (src as any)._pool;

    // Seed Module so the scope exists (parity with the Python fixture).
    await src.saveDocument(SCOPE, "Module", SCOPE, {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Genome",
      metadata: { name: SCOPE },
      spec: { default_agent: "bot" },
    });
  });

  afterAll(async () => {
    try {
      await pool.query(`DROP SCHEMA IF EXISTS "${SCHEMA}" CASCADE`);
    } finally {
      await src.close();
    }
  });

  // ------------------------------------------------------------
  // 1. layer=["tenant", X] routes to the tenant column.
  // ------------------------------------------------------------
  it("writes layer=['tenant', X] to the tenant column on dna_documents", async () => {
    const name = "case-1-ts";
    const raw = evalCaseRaw(name, "t1");
    try {
      await src.saveDocument(SCOPE, KIND, name, raw, {
        layer: ["tenant", TENANT],
      });

      const { rows } = await pool.query(
        `SELECT tenant, content FROM "${SCHEMA}".dna_documents
         WHERE scope=$1 AND kind=$2 AND name=$3 AND tenant=$4`,
        [SCOPE, KIND, name, TENANT],
      );
      expect(rows.length).toBe(1);
      expect(rows[0].tenant).toBe(TENANT);
      const loaded =
        typeof rows[0].content === "string"
          ? JSON.parse(rows[0].content)
          : rows[0].content;
      expect(loaded.spec.input).toBe("hello-t1");
    } finally {
      await pool.query(
        `DELETE FROM "${SCHEMA}".dna_documents
         WHERE scope=$1 AND kind=$2 AND name=$3`,
        [SCOPE, KIND, name],
      );
    }
  });

  // ------------------------------------------------------------
  // 2. Non-tenant layers raise the documented v1.1 follow-up error.
  // ------------------------------------------------------------
  it("rejects non-tenant layers with the documented error", async () => {
    const name = "case-2-ts";
    const raw = evalCaseRaw(name, "t2");
    let caught: Error | null = null;
    try {
      await src.saveDocument(SCOPE, KIND, name, raw, {
        layer: ["env", "production"],
      });
    } catch (e) {
      caught = e as Error;
    }
    expect(caught).not.toBeNull();
    expect(caught!.message).toMatch(/non-tenant layers|v1\.1/);
  });

  // ------------------------------------------------------------
  // 3. delete on tenant overlay must not touch the base row.
  // ------------------------------------------------------------
  it("delete-with-tenant-layer removes only the overlay row", async () => {
    const name = "case-3-ts";
    const baseRaw = evalCaseRaw(name, "base");
    const overlayRaw = evalCaseRaw(name, "overlay");
    try {
      await src.saveDocument(SCOPE, KIND, name, baseRaw); // base (tenant='')
      await src.saveDocument(SCOPE, KIND, name, overlayRaw, {
        layer: ["tenant", TENANT],
      });

      // Sanity: both rows exist.
      const before = await pool.query(
        `SELECT tenant FROM "${SCHEMA}".dna_documents
         WHERE scope=$1 AND kind=$2 AND name=$3 ORDER BY tenant`,
        [SCOPE, KIND, name],
      );
      expect(before.rows.map((r: { tenant: string }) => r.tenant)).toEqual([
        "",
        TENANT,
      ]);

      // Delete only the overlay.
      await src.deleteDocument(SCOPE, KIND, name, {
        layer: ["tenant", TENANT],
      });

      const after = await pool.query(
        `SELECT tenant, content FROM "${SCHEMA}".dna_documents
         WHERE scope=$1 AND kind=$2 AND name=$3`,
        [SCOPE, KIND, name],
      );
      expect(after.rows.length).toBe(1);
      expect(after.rows[0].tenant).toBe("");
      const loaded =
        typeof after.rows[0].content === "string"
          ? JSON.parse(after.rows[0].content)
          : after.rows[0].content;
      expect(loaded.spec.input).toBe("hello-base");
    } finally {
      await pool.query(
        `DELETE FROM "${SCHEMA}".dna_documents
         WHERE scope=$1 AND kind=$2 AND name=$3`,
        [SCOPE, KIND, name],
      );
    }
  });
});
