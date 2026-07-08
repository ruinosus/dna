/**
 * BundleHandle — source-agnostic interface for reading + writing a
 * bundle's entries.
 *
 * 1:1 parity with python/dna/kernel/bundle_handle.py.
 *
 * Implementations:
 *   - `FilesystemBundleHandle` — wraps a real filesystem directory.
 *   - `DictBundleHandle` — in-memory, used by SQL/Postgres adapters
 *     (rehydrate bundle entries from `dna_bundle_entries` rows into
 *     a dict, hand to readers).
 *   - `PostgresBundleHandle` (Postgres adapter) — backed by
 *     `dna_bundle_entries` rows.
 *
 * Entry naming convention: a posix-style relative path inside the
 * bundle. Top-level entries are bare names (`"SKILL.md"`,
 * `"IDENTITY.md"`); nested entries use forward slashes
 * (`"scripts/run.py"`, `"references/spec.md"`).
 *
 * v1.0 async refactor: read/write methods return `Promise<...>`.
 * Async-everywhere is the contract — sync local-FS impls wrap their
 * sync IO in `Promise.resolve` (true `fs/promises` migration is a
 * v1.2 cleanup).
 */

import { access, readFile, readdir, stat, writeFile, mkdir } from "node:fs/promises";
import { join, dirname, basename, posix } from "node:path";

/** True iff the path exists. fs/promises doesn't ship a boolean
 *  `exists`; this is the canonical workaround. */
async function pathExists(p: string): Promise<boolean> {
  try { await access(p); return true; } catch { return false; }
}

export interface BundleHandle {
  /** Bundle directory name (used as default doc name when frontmatter
   *  omits `metadata.name`). */
  readonly name: string;

  /** True if the named entry (file or directory) exists in this bundle. */
  exists(entry: string): Promise<boolean>;

  /** Read entry content as text. Throws if absent. */
  readText(entry: string, encoding?: BufferEncoding): Promise<string>;

  /** Read entry content as bytes. Throws if absent. */
  readBytes(entry: string): Promise<Uint8Array>;

  /**
   * Yield entry names (relative to the bundle root).
   *
   * When `recursive=false` (default), only direct children are
   * yielded — both regular files and subdirectories.
   * When `recursive=true`, descend into subdirectories yielding only
   * regular files (no directory entries).
   */
  iterEntries(recursive?: boolean): Promise<string[]>;

  /** True if `entry` points at a regular file (not a directory). */
  isFile(entry: string): Promise<boolean>;

  /** Write text content. Read-only handles throw. */
  writeText(entry: string, content: string, encoding?: BufferEncoding): Promise<void>;

  /** Write bytes. Read-only handles throw. */
  writeBytes(entry: string, content: Uint8Array): Promise<void>;

  /**
   * Filesystem path when the handle wraps a real directory; null
   * otherwise. ESCAPE HATCH — prefer explicit read/write/iter methods.
   * Use only when an external library demands a real path (e.g.
   * `fs.cp`, third-party tooling).
   */
  readonly path: string | null;
}

// ---------------------------------------------------------------------------
// Filesystem implementation
// ---------------------------------------------------------------------------

export class FilesystemBundleHandle implements BundleHandle {
  constructor(private readonly _root: string) {}

  get name(): string { return basename(this._root); }
  get path(): string | null { return this._root; }

  async exists(entry: string): Promise<boolean> {
    return pathExists(join(this._root, entry));
  }

  async readText(entry: string, encoding: BufferEncoding = "utf-8"): Promise<string> {
    const p = join(this._root, entry);
    try {
      return await readFile(p, encoding);
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code === "ENOENT") {
        const err = new Error(`Bundle entry not found: ${entry}`) as Error & { code: string };
        err.code = "ENOENT";
        throw err;
      }
      throw e;
    }
  }

  async readBytes(entry: string): Promise<Uint8Array> {
    const p = join(this._root, entry);
    try {
      return new Uint8Array(await readFile(p));
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code === "ENOENT") {
        const err = new Error(`Bundle entry not found: ${entry}`) as Error & { code: string };
        err.code = "ENOENT";
        throw err;
      }
      throw e;
    }
  }

  async iterEntries(recursive: boolean = false): Promise<string[]> {
    if (!(await pathExists(this._root))) return [];
    const out: string[] = [];
    if (recursive) {
      const walk = async (dir: string, prefix: string): Promise<void> => {
        const entries = (await readdir(dir)).sort();
        for (const entry of entries) {
          const full = join(dir, entry);
          const rel = prefix ? posix.join(prefix, entry) : entry;
          const st = await stat(full);
          if (st.isDirectory()) await walk(full, rel);
          else out.push(rel);
        }
      };
      await walk(this._root, "");
    } else {
      for (const entry of (await readdir(this._root)).sort()) out.push(entry);
    }
    return out;
  }

  async isFile(entry: string): Promise<boolean> {
    const p = join(this._root, entry);
    try {
      return (await stat(p)).isFile();
    } catch {
      return false;
    }
  }

  async writeText(entry: string, content: string, encoding: BufferEncoding = "utf-8"): Promise<void> {
    const p = join(this._root, entry);
    await mkdir(dirname(p), { recursive: true });
    await writeFile(p, content, encoding);
  }

  async writeBytes(entry: string, content: Uint8Array): Promise<void> {
    const p = join(this._root, entry);
    await mkdir(dirname(p), { recursive: true });
    await writeFile(p, Buffer.from(content));
  }
}

// ---------------------------------------------------------------------------
// In-memory implementation (used by tests + SQL adapters)
// ---------------------------------------------------------------------------

export class DictBundleHandle implements BundleHandle {
  private _entries: Map<string, string | Uint8Array>;

  constructor(public readonly name: string, entries: Record<string, string | Uint8Array> = {}) {
    this._entries = new Map(Object.entries(entries));
  }

  get path(): string | null { return null; }

  async exists(entry: string): Promise<boolean> {
    if (this._entries.has(entry)) return true;
    // Treat parent paths as "directory entries" — true if any key
    // starts with `entry/`.
    const prefix = entry.endsWith("/") ? entry : `${entry}/`;
    for (const k of this._entries.keys()) if (k.startsWith(prefix)) return true;
    return false;
  }

  async readText(entry: string, _encoding: BufferEncoding = "utf-8"): Promise<string> {
    const v = this._entries.get(entry);
    if (v === undefined) {
      const err = new Error(`Bundle entry not found: ${entry}`) as Error & { code: string };
      err.code = "ENOENT";
      throw err;
    }
    return typeof v === "string" ? v : new TextDecoder().decode(v);
  }

  async readBytes(entry: string): Promise<Uint8Array> {
    const v = this._entries.get(entry);
    if (v === undefined) {
      const err = new Error(`Bundle entry not found: ${entry}`) as Error & { code: string };
      err.code = "ENOENT";
      throw err;
    }
    return typeof v === "string" ? new TextEncoder().encode(v) : v;
  }

  async iterEntries(recursive: boolean = false): Promise<string[]> {
    if (recursive) return Array.from(this._entries.keys()).sort();
    // Direct children only — extract first segment, deduplicate
    const directChildren = new Set<string>();
    for (const k of this._entries.keys()) {
      const slash = k.indexOf("/");
      directChildren.add(slash === -1 ? k : k.substring(0, slash));
    }
    return Array.from(directChildren).sort();
  }

  async isFile(entry: string): Promise<boolean> {
    return this._entries.has(entry);
  }

  async writeText(entry: string, content: string, _encoding: BufferEncoding = "utf-8"): Promise<void> {
    this._entries.set(entry, content);
  }

  async writeBytes(entry: string, content: Uint8Array): Promise<void> {
    this._entries.set(entry, content);
  }
}
