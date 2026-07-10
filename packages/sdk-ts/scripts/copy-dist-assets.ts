#!/usr/bin/env bun
/**
 * Copy runtime (non-TypeScript) assets from src/ into dist/ for the npm
 * publication build (s-publish-registries).
 *
 * The compiled extension modules load these files at runtime RELATIVE TO
 * THEMSELVES via `import.meta.url`:
 *
 *   - `src/extensions/<ext>/kinds/*.kind.yaml` — record-Kind descriptors,
 *     read by `loadDescriptors(import.meta.url, "<ext>/kinds")`
 *     (src/kernel/descriptor-loader.ts). Parity-critical: byte-identical to
 *     the Python twin's descriptors.
 *   - `src/extensions/<ext>/DOCS*.md` — Kind prose docs, resolved next to the
 *     extension's source file via `_sourceUrl` (src/kernel/kind-registry.ts).
 *   - `src/extensions/<ext>/templates/**` — scaffold trees (none today, but
 *     the Template contract resolves them the same way; covered for free).
 *
 * tsc only emits .js/.d.ts, so without this copy the published package would
 * boot with zero record Kinds. The copy mirrors the full src/ tree of
 * non-.ts files 1:1 into dist/, preserving relative paths so every
 * `import.meta.url`-relative lookup keeps working from the compiled modules.
 */
import { copyFileSync, mkdirSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const pkgRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const srcRoot = join(pkgRoot, "src");
const distRoot = join(pkgRoot, "dist");

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir).sort()) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (!name.endsWith(".ts")) out.push(full);
  }
  return out;
}

const assets = walk(srcRoot);
for (const src of assets) {
  const dest = join(distRoot, relative(srcRoot, src));
  mkdirSync(dirname(dest), { recursive: true });
  copyFileSync(src, dest);
}
console.log(`Copied ${assets.length} runtime assets from src/ into dist/`);
