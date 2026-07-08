/**
 * FilesystemCache — CachePort backed by .dna-cache/ directories.
 *
 * 1:1 parity with Python dna.v3.adapters.filesystem.cache.
 */

import { access, cp, mkdir, readFile, readdir, rm, stat } from "node:fs/promises";
import { resolve, join, dirname } from "node:path";

async function pathExists(p: string): Promise<boolean> {
  try { await access(p); return true; } catch { return false; }
}
import yaml from "js-yaml";
import type { CacheItem, CachePort, ReaderPort } from "../../kernel/protocols.js";
import { FilesystemBundleHandle } from "../../kernel/bundle-handle.js";

export class FilesystemCache implements CachePort {
  readonly baseDir: string;
  private readonly _cacheDir: string;

  constructor(baseDir: string) {
    this.baseDir = resolve(baseDir);
    this._cacheDir = join(dirname(this.baseDir), ".dna-cache");
  }

  async has(scope: string, key: string): Promise<boolean> {
    return pathExists(join(this._cacheDir, scope, key));
  }

  async store(scope: string, key: string, items: CacheItem[]): Promise<void> {
    const destBase = join(this._cacheDir, scope, key);
    await mkdir(destBase, { recursive: true });

    for (const item of items) {
      const subDir = item.kind
        ? join(destBase, item.kind.toLowerCase() + "s")
        : destBase;
      const dest = join(subDir, item.name);

      if (await pathExists(dest)) {
        await rm(dest, { recursive: true, force: true });
      }
      await mkdir(dirname(dest), { recursive: true });
      await cp(item.contentPath, dest, { recursive: true });
    }
  }

  async loadKey(
    scope: string,
    key: string,
    readers?: ReaderPort[],
  ): Promise<Record<string, unknown>[]> {
    const keyDir = join(this._cacheDir, scope, key);
    if (!(await pathExists(keyDir))) return [];

    const documents: Record<string, unknown>[] = [];
    await this._readTree(keyDir, readers ?? [], documents);
    return documents;
  }

  async loadAll(
    scope: string,
    readers?: ReaderPort[],
  ): Promise<Record<string, unknown>[]> {
    const scopeDir = join(this._cacheDir, scope);
    if (!(await pathExists(scopeDir))) return [];

    const documents: Record<string, unknown>[] = [];
    await this._readTree(scopeDir, readers ?? [], documents);
    return documents;
  }

  private async _readTree(
    directory: string,
    readers: ReaderPort[],
    documents: Record<string, unknown>[],
  ): Promise<void> {
    const entries = (await readdir(directory)).sort();
    for (const entry of entries) {
      const full = join(directory, entry);
      if (!(await stat(full)).isDirectory()) continue;

      let matched = false;
      const handle = new FilesystemBundleHandle(full);
      for (const reader of readers) {
        try {
          if (await reader.detect(handle)) {
            const doc = await reader.read(handle);
            if (
              doc != null &&
              typeof doc === "object" &&
              "kind" in doc
            ) {
              documents.push(doc);
            }
            matched = true;
            break;
          }
        } catch {
          // Skip reader errors
        }
      }
      if (matched) continue;

      let hasYaml = false;
      const subEntries = (await readdir(full)).sort();
      for (const sub of subEntries) {
        if (!sub.endsWith(".yaml") && !sub.endsWith(".yml")) continue;
        const yf = join(full, sub);
        if (!(await stat(yf)).isFile()) continue;
        try {
          const content = yaml.load(await readFile(yf, "utf-8"));
          if (
            content != null &&
            typeof content === "object" &&
            "kind" in (content as Record<string, unknown>)
          ) {
            documents.push(content as Record<string, unknown>);
            hasYaml = true;
          }
        } catch {
          // Skip unparseable YAML
        }
      }

      if (!hasYaml) {
        await this._readTree(full, readers, documents);
      }
    }
  }
}
