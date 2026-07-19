/**
 * TS side of the Py<->TS memory-interchange parity (s-memory-interchange-verbs).
 *
 * Runs every case in `tests/fixtures/memory-interchange-parity.json` against
 * the TS `toMif`/`fromMif` port. The Python twin
 * (`tests/test_memory_interchange_parity.py`) runs the SAME fixture; Python
 * is the source of truth (regenerate via
 * `packages/sdk-py/scripts/gen_memory_interchange_parity.py`). A failure on
 * either side is a parity divergence.
 */
import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { toMif, fromMif } from "../src/memory/interchange.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FX = JSON.parse(
  readFileSync(join(__dirname, "fixtures", "memory-interchange-parity.json"), "utf-8"),
);

describe("memory interchange Py<->TS parity", () => {
  test("toMif", () => {
    for (const c of FX.to_mif) {
      const got = toMif(c.spec, c.mif_id);
      expect(got).toEqual(c.expected);
    }
  });

  test("fromMif", () => {
    for (const c of FX.from_mif) {
      const got = fromMif(c.doc);
      expect(got).toEqual(c.expected);
    }
  });
});
