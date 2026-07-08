/**
 * F3 (spec D3): builtin Kind descriptors as package data.
 *
 * Extensions ship builtin record Kinds as `kinds/*.kind.yaml` files next to
 * their module (same KindDefinition format as per-scope KIND.yaml docs — one
 * format, one funnel). `loadDescriptors` reads them relative to the calling
 * module's `import.meta.url` (the same pattern the template-owning extensions
 * use; package.json `files` ships `src/extensions/* /kinds/**`) and hands the
 * parsed raws to `kernel.kindFromDescriptor`.
 *
 * The Python twin is `dna/kernel/descriptor_loader.py`; the
 * descriptor FILES are parity-critical (byte-identical Py↔TS — see
 * `tests/descriptor-hash-parity.test.ts`).
 */
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load as yamlLoad } from "js-yaml";

const SUFFIX = ".kind.yaml";

/**
 * Parse every `<relKindsDir>/*.kind.yaml` next to the calling module.
 *
 * @param moduleUrl  the caller's `import.meta.url`
 * @param relKindsDir  dir relative to the module, e.g. `"sdlc/kinds"` for
 *   `src/extensions/sdlc.ts` → `src/extensions/sdlc/kinds/`
 *
 * Returns the raw objects sorted by filename (deterministic registration
 * order). A missing dir returns `[]` — extensions can call this
 * unconditionally. A descriptor that isn't a YAML mapping throws (a broken
 * packaged descriptor is a packaging bug, never a silent skip).
 */
export function loadDescriptors(
  moduleUrl: string,
  relKindsDir: string,
): Record<string, unknown>[] {
  const kindsDir = join(dirname(fileURLToPath(moduleUrl)), relKindsDir);
  if (!existsSync(kindsDir)) return [];

  const raws: Record<string, unknown>[] = [];
  for (const name of readdirSync(kindsDir).sort()) {
    if (!name.endsWith(SUFFIX)) continue;
    const raw = yamlLoad(readFileSync(join(kindsDir, name), "utf-8"));
    if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
      throw new Error(
        `descriptor ${relKindsDir}/${name} must be a YAML mapping ` +
        `(KindDefinition), got ${Array.isArray(raw) ? "array" : typeof raw}`,
      );
    }
    raws.push(raw as Record<string, unknown>);
  }
  return raws;
}
