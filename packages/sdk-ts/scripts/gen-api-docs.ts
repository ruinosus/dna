#!/usr/bin/env bun
/**
 * Generate the TypeScript API reference (docs/reference/typescript/) from the
 * TSDoc of the exported surface in src/index.ts.
 *
 * Source-of-truth generator (TypeDoc + typedoc-plugin-markdown): the TSDoc in
 * the source is the single source of truth; these markdown pages are rebuilt
 * from it, never hand-edited. Kept a SIBLING of the Python reference — same
 * concepts, documented per-language against the exact TS names/types — never
 * fused (see docs/reference/index.md).
 *
 * TypeDoc (config: typedoc.json) emits flat markdown into
 * docs/reference/typescript/ (index.md + one file per exported symbol). The
 * reference SUMMARY.md spine picks them up via a literate-nav `*.md` wildcard,
 * so this script only has to run the generator.
 *
 * Usage:  bun run docs:api        (from packages/sdk-ts)
 */
import { readdirSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";

const HERE = resolve(import.meta.dir, "..");
const OUT = resolve(HERE, "../../docs/reference/typescript");

const td = spawnSync("bunx", ["typedoc", "--options", "typedoc.json"], {
  cwd: HERE,
  stdio: "inherit",
});
if (td.status !== 0) {
  console.error("TypeDoc failed");
  process.exit(td.status ?? 1);
}

const count = readdirSync(OUT).filter((f) => f.endsWith(".md")).length;
console.log(`Wrote ${count} TypeScript reference pages to docs/reference/typescript/`);
