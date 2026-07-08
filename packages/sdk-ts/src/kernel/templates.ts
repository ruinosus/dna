/**
 * Template contract — file-tree scaffolds shipped by Extensions.
 *
 * Templates let an Extension declare reusable scaffolds for its Kinds.
 * Files live under an absolute path resolved by the Extension (e.g. via
 * `import.meta.url`), so they survive bundling and editable installs.
 * Kernel exposes `listTemplates()` + `scaffold()` to discover and
 * materialize them.
 *
 * 1:1 parity with `dna.kernel.templates` (Python). Field
 * naming is camelCased per this codebase's TS convention:
 *   files_root      -> filesRoot
 *   owner_extension -> ownerExtension
 *   post_init_hint  -> postInitHint
 *   upstream_ref    -> upstreamRef
 *   on_conflict     -> onConflict
 */

import { readdirSync, readFileSync, statSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";

/** Conflict policy when a destination file already exists. */
export type OnConflict = "error" | "skip" | "overwrite";

/**
 * A scaffoldable file tree declared by an Extension.
 *
 *  - `id`              Namespaced identifier: `<extension>/<name>`.
 *  - `label`           Human-friendly name shown in UIs.
 *  - `kind`            Primary Kind this template scaffolds (may span
 *                      multiple kinds in the file tree, but this is the
 *                      headline one for filtering/grouping).
 *  - `description`     One-line description.
 *  - `filesRoot`       Absolute path to the root of the template tree on
 *                      disk (typically resolved via `fileURLToPath` from
 *                      the Extension's `import.meta.url`).
 *  - `ownerExtension`  Name of the Extension that owns this template.
 *  - `postInitHint`    Optional shell/cli snippet shown after scaffold
 *                      (e.g. "cd .dna/<scope>/programs/research && bun
 *                      install").
 *  - `upstreamRef`     Optional upstream pin (e.g. a git sha of the
 *                      source repo the template was cloned from).
 */
export interface Template {
  readonly id: string;
  readonly label: string;
  readonly kind: string;
  readonly description: string;
  readonly filesRoot: string;
  readonly ownerExtension: string;
  readonly postInitHint?: string;
  readonly upstreamRef?: string;
}

/** Options accepted by {@link materialize}. */
export interface MaterializeOptions {
  /** Absolute path where files will be written (created if missing). */
  readonly targetRoot: string;
  /** Conflict policy. Defaults to `"error"`. */
  readonly onConflict?: OnConflict;
}

const VALID_ON_CONFLICT: ReadonlySet<OnConflict> = new Set([
  "error",
  "skip",
  "overwrite",
]);

/** Walk `root` recursively and return the absolute paths of every regular
 *  file, sorted lexicographically for determinism (mirrors Python's
 *  `sorted(rglob("*"))`). */
function walkFiles(root: string): string[] {
  const out: string[] = [];

  function visit(dir: string): void {
    const entries = readdirSync(dir).sort();
    for (const name of entries) {
      const full = join(dir, name);
      const st = statSync(full);
      if (st.isDirectory()) {
        visit(full);
      } else if (st.isFile()) {
        out.push(full);
      }
      // symlinks / sockets / etc. are ignored — same as Python's is_file()
    }
  }

  visit(root);
  out.sort();
  return out;
}

function isDirectory(path: string): boolean {
  try {
    return statSync(path).isDirectory();
  } catch {
    return false;
  }
}

function exists(path: string): boolean {
  try {
    statSync(path);
    return true;
  } catch {
    return false;
  }
}

/**
 * Copy every file under `template.filesRoot` into `opts.targetRoot`.
 *
 * Returns the list of written absolute paths. Binary-safe — files are
 * read and written as raw `Buffer` bytes. Preserves relative directory
 * structure.
 *
 * `onConflict`:
 *   - `"error"` (default): throw on any existing dest file
 *   - `"skip"`: leave existing dest files untouched
 *   - `"overwrite"`: replace existing dest files
 *
 * Throws:
 *   - `Error("unknown onConflict: ...")` on invalid policy value
 *     (runtime validation — TypeScript can catch most at compile time,
 *     but this mirrors Python's `ValueError` for defensive callers)
 *   - `Error("filesRoot does not exist: ...")` if the source tree is
 *     missing
 *   - `Error("destination exists: ...")` when `onConflict="error"` and
 *     the destination has a conflicting file
 */
export function materialize(
  template: Template,
  opts: MaterializeOptions,
): string[] {
  const onConflict: OnConflict = opts.onConflict ?? "error";
  if (!VALID_ON_CONFLICT.has(onConflict)) {
    throw new Error(`unknown onConflict: ${JSON.stringify(onConflict)}`);
  }

  if (!isDirectory(template.filesRoot)) {
    throw new Error(`filesRoot does not exist: ${template.filesRoot}`);
  }

  mkdirSync(opts.targetRoot, { recursive: true });

  const written: string[] = [];
  for (const src of walkFiles(template.filesRoot)) {
    const rel = relative(template.filesRoot, src);
    // normalise path separators defensively (relative already returns
    // platform-native separators; join below is platform-correct).
    const dst = join(opts.targetRoot, ...rel.split(sep));
    if (exists(dst)) {
      if (onConflict === "error") {
        throw new Error(`destination exists: ${dst}`);
      }
      if (onConflict === "skip") {
        continue;
      }
      // "overwrite" → fall through
    }
    mkdirSync(dirname(dst), { recursive: true });
    const buf = readFileSync(src); // Buffer — no encoding = binary-safe
    writeFileSync(dst, buf);
    written.push(dst);
  }
  return written;
}
