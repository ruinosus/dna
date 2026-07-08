/**
 * FSLike — filesystem abstraction for readers/writers.
 *
 * Allows the SDK to run in Node.js (nodeFS), Tauri/webview (VFS adapter),
 * or in-memory (createMemoryFS for tests).
 */

import {
  existsSync,
  readFileSync,
  readdirSync,
  statSync,
  writeFileSync,
  mkdirSync,
} from "node:fs";
import { dirname } from "node:path";

// ---------------------------------------------------------------------------
// Interface
// ---------------------------------------------------------------------------

export interface FSLike {
  exists(path: string): boolean;
  readFile(path: string): string;
  readDir(path: string): string[];
  isDirectory(path: string): boolean;
  isFile(path: string): boolean;
  writeFile(path: string, content: string): void;
  mkdir(path: string): void;
}

// ---------------------------------------------------------------------------
// Node.js adapter (default)
// ---------------------------------------------------------------------------

export const nodeFS: FSLike = {
  exists: (p) => existsSync(p),
  readFile: (p) => readFileSync(p, "utf-8"),
  readDir: (p) => readdirSync(p).sort(),
  isDirectory: (p) => {
    try { return statSync(p).isDirectory(); } catch { return false; }
  },
  isFile: (p) => {
    try { return statSync(p).isFile(); } catch { return false; }
  },
  writeFile: (p, c) => {
    mkdirSync(dirname(p), { recursive: true });
    writeFileSync(p, c);
  },
  mkdir: (p) => mkdirSync(p, { recursive: true }),
};

// ---------------------------------------------------------------------------
// In-memory adapter (tests)
// ---------------------------------------------------------------------------

export function createMemoryFS(
  initial: Record<string, string> = {},
): FSLike {
  const files = new Map<string, string>(Object.entries(initial));

  function dirs(): Set<string> {
    const result = new Set<string>();
    for (const key of files.keys()) {
      const parts = key.split("/");
      for (let i = 1; i < parts.length; i++) {
        result.add(parts.slice(0, i).join("/"));
      }
    }
    return result;
  }

  return {
    exists: (p) => files.has(p) || dirs().has(p),
    readFile: (p) => {
      const c = files.get(p);
      if (c === undefined) throw new Error(`ENOENT: ${p}`);
      return c;
    },
    readDir: (p) => {
      const prefix = p.endsWith("/") ? p : p + "/";
      const entries = new Set<string>();
      for (const key of files.keys()) {
        if (key.startsWith(prefix)) {
          const rest = key.slice(prefix.length);
          const first = rest.split("/")[0];
          if (first) entries.add(first);
        }
      }
      for (const d of dirs()) {
        if (d.startsWith(prefix)) {
          const rest = d.slice(prefix.length);
          const first = rest.split("/")[0];
          if (first) entries.add(first);
        }
      }
      return [...entries].sort();
    },
    isDirectory: (p) => dirs().has(p),
    isFile: (p) => files.has(p),
    writeFile: (p, c) => { files.set(p, c); },
    mkdir: () => {},
  };
}

// ---------------------------------------------------------------------------
// Shared helpers (used by readers in extensions)
// ---------------------------------------------------------------------------

export function relativePath(root: string, full: string): string {
  return full.startsWith(root + "/") ? full.slice(root.length + 1) : full;
}

const BINARY_EXTENSIONS = new Set([
  ".tar", ".gz", ".zip", ".png", ".jpg", ".jpeg", ".gif",
  ".pdf", ".wasm", ".bin", ".exe", ".so", ".dylib", ".ico",
]);

export function readTextSafe(fs: FSLike, path: string): string | null {
  for (const ext of BINARY_EXTENSIONS) {
    if (path.endsWith(ext)) return null;
  }
  try {
    return fs.readFile(path);
  } catch {
    return null;
  }
}

export function collectDir(
  fs: FSLike,
  directory: string,
  root: string,
): Record<string, string> {
  const files: Record<string, string> = {};
  _collectRecursive(fs, root, directory, files);
  return files;
}

function _collectRecursive(
  fs: FSLike,
  root: string,
  directory: string,
  files: Record<string, string>,
): void {
  for (const entry of fs.readDir(directory)) {
    const full = `${directory}/${entry}`;
    if (fs.isDirectory(full)) {
      _collectRecursive(fs, root, full, files);
    } else if (fs.isFile(full)) {
      const text = readTextSafe(fs, full);
      if (text !== null) {
        files[relativePath(root, full)] = text;
      }
    }
  }
}
