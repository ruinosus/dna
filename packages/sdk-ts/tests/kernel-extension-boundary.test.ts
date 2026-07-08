/**
 * s-invert-layer-resolver-dep — kernel↛extensions boundary guard (ratchet).
 *
 * TS twin of python/tests/test_kernel_extension_boundary.py. The
 * microkernel must work with ZERO extensions loaded: no module in
 * src/kernel/ may import from src/extensions/ at runtime. Type-only
 * imports (`import type`) are allowed — they're erased at compile time.
 *
 * BASELINE is shrink-only: it lists the known remaining offender(s).
 * New kernel modules must NOT import extensions; when a baseline file
 * is cleaned up, remove it from the set so it can't regress.
 */

import { describe, test, expect } from "bun:test";
import { readdirSync, readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const KERNEL_DIR = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "src",
  "kernel",
);

// Shrink-only baseline — now EMPTY. The last offender (evidence-capture.ts)
// was inverted in s-invert-evidence-capture-dep: shouldCapture moved into the
// kernel and EvidenceExtension re-exports it. No kernel module imports
// src/extensions at runtime. Keep this empty — any new offender must be
// inverted, never baselined.
const BASELINE = new Set<string>([]);

/** Strip // line comments and /* block comments *​/ (naive but sufficient). */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

/**
 * Runtime imports of extension modules in a kernel source file.
 * Matches static `import ... from "…extensions/…"`, side-effect
 * `import "…extensions/…"`, `export … from "…extensions/…"` reexports
 * and dynamic `import("…extensions/…")`. Skips `import type` /
 * `export type` (type-only, erased at runtime).
 */
function extensionImports(fileName: string): string[] {
  const src = stripComments(
    readFileSync(join(KERNEL_DIR, fileName), "utf-8"),
  );
  const offenders: string[] = [];

  // Static import/export-from statements (possibly multiline).
  const staticRe =
    /(import|export)\s+(type\s+)?[^;'"]*?from\s*["']([^"']+)["']/g;
  for (const m of src.matchAll(staticRe)) {
    const [, , typeOnly, spec] = m;
    if (typeOnly) continue;
    if (/(^|\/)extensions\//.test(spec)) offenders.push(spec);
  }

  // Side-effect imports: import "…";
  for (const m of src.matchAll(/import\s*["']([^"']+)["']/g)) {
    if (/(^|\/)extensions\//.test(m[1])) offenders.push(m[1]);
  }

  // Dynamic imports: import("…")
  for (const m of src.matchAll(/import\s*\(\s*["']([^"']+)["']\s*\)/g)) {
    if (/(^|\/)extensions\//.test(m[1])) offenders.push(m[1]);
  }

  return offenders;
}

function kernelModules(): string[] {
  return readdirSync(KERNEL_DIR).filter((f) => f.endsWith(".ts")).sort();
}

describe("kernel↛extensions boundary (s-invert-layer-resolver-dep)", () => {
  test("no kernel module imports src/extensions at runtime", () => {
    const files = kernelModules();
    expect(files.length).toBeGreaterThan(0);

    const violations: string[] = [];
    for (const f of files) {
      if (BASELINE.has(f)) continue;
      for (const spec of extensionImports(f)) {
        violations.push(`${f}: ${spec}`);
      }
    }

    expect(
      violations,
      "Kernel modules import src/extensions — the microkernel must work " +
        "with zero extensions loaded. Move generic code into src/kernel/ " +
        "(leave a deprecated reexport shim), or define a Protocol port the " +
        `extension registers on the kernel. Violations: ${violations.join("; ")}`,
    ).toEqual([]);
  });

  test("baseline is shrink-only — cleaned files must leave the set", () => {
    for (const f of [...BASELINE].sort()) {
      const files = kernelModules();
      expect(files, `BASELINE entry ${f} no longer exists — remove it`).toContain(f);
      expect(
        extensionImports(f).length,
        `BASELINE entry ${f} no longer imports extensions — remove it from BASELINE`,
      ).toBeGreaterThan(0);
    }
  });
});
