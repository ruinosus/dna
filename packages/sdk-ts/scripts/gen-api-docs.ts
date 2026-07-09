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
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
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

/**
 * Neutralize `[][]` in the emitted markdown OUTSIDE fenced code blocks.
 *
 * typedoc-plugin-markdown renders an array-of-array type (`number[][]`, e.g.
 * `EmbeddingPort.embed(): Promise<number[][]>`) inline as `` `number`[][] ``.
 * A bare `[][]` is Markdown for an empty reference-style link (`[label][ref]`
 * with both empty), which mkdocs-autorefs then tries to resolve to the empty
 * identifier `''` — a hard `mkdocs build --strict` crash (griffe: "Empty
 * strings are not supported"). Escaping the brackets renders the exact same
 * literal `[][]` while defusing the link parse. Inside ```-fenced code the
 * sequence is not a link, so those blocks are left untouched (escaping there
 * would leak backslashes into the rendered code).
 */
function defuseEmptyRefLinks(md: string): string {
  let inFence = false;
  return md
    .split("\n")
    .map((line) => {
      if (/^\s*```/.test(line)) {
        inFence = !inFence;
        return line;
      }
      if (inFence) return line;
      return line.replaceAll("[][]", "\\[\\]\\[\\]");
    })
    .join("\n");
}

const files = readdirSync(OUT).filter((f) => f.endsWith(".md"));
let defused = 0;
for (const f of files) {
  const p = join(OUT, f);
  const src = readFileSync(p, "utf-8");
  const out = defuseEmptyRefLinks(src);
  if (out !== src) {
    writeFileSync(p, out);
    defused++;
  }
}

console.log(
  `Wrote ${files.length} TypeScript reference pages to docs/reference/typescript/`
  + (defused ? ` (defused [][] empty-ref links in ${defused})` : ""),
);
