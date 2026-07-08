/**
 * HttpResolver — ResolverPort for http:/https: URIs.
 *
 * 1:1 parity with Python dna.v3.adapters.resolvers.http.
 *
 * Fetches manifest documents from HTTP endpoints. Supports two modes:
 *
 * 1. **Index mode** (default): GET {uri}/index.json → list of {kind, name, path}.
 *    Each item is fetched individually: GET {uri}/{path} → raw dict.
 *
 * 2. **Bundle mode** (fallback): GET {uri} → list of raw dicts directly.
 */

import { mkdirSync, writeFileSync, mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import type { ResolvedItem, ResolverPort } from "../../kernel/protocols.js";
import {
  ResolveNotFoundError,
  ResolveNetworkError,
  ResolveError,
} from "../../kernel/protocols.js";

export class HttpResolver implements ResolverPort {
  cacheKey(uri: string): string {
    const safe = uri.replace(/[^a-zA-Z0-9_-]/g, "-").replace(/^-+|-+$/g, "");
    return `http-${safe}`.slice(0, 120);
  }

  async resolve(uri: string, dep: Record<string, unknown>): Promise<ResolvedItem[]> {
    const baseUrl = uri.replace(/\/$/, "");
    const requested = this._collectRequested(dep);

    // Try index mode first
    try {
      const index = this._fetchJson(`${baseUrl}/index.json`);
      if (Array.isArray(index)) {
        return this._resolveFromIndex(baseUrl, index as Record<string, unknown>[], requested);
      }
    } catch (e) {
      if (e instanceof ResolveError) {
        // Fall through to bundle mode
      } else {
        throw e;
      }
    }

    // Fallback: bundle mode
    try {
      const bundle = this._fetchJson(baseUrl);
      if (Array.isArray(bundle)) {
        return this._resolveFromBundle(bundle as Record<string, unknown>[], requested);
      }
    } catch (e) {
      if (e instanceof ResolveError) {
        throw new ResolveError(`HTTP resolve failed for ${uri}: ${e.message}`);
      }
      throw e;
    }

    throw new ResolveError(`HTTP endpoint returned unexpected format: ${uri}`);
  }

  private _fetchJson(url: string): unknown {
    const result = Bun.spawnSync(["curl", "-sf", "-H", "Accept: application/json", url]);

    if (result.exitCode !== 0) {
      const stderr = result.stderr.toString();
      // curl exit code 22 = HTTP 4xx/5xx, 6 = DNS failure, 28 = timeout
      if (stderr.includes("404") || result.stdout.toString().includes("404")) {
        throw new ResolveNotFoundError(`Not found: ${url}`);
      }
      if (result.exitCode === 6 || result.exitCode === 7 || result.exitCode === 28) {
        throw new ResolveNetworkError(`Network error fetching: ${url}`);
      }
      throw new ResolveError(`curl failed (exit ${result.exitCode}): ${url}`);
    }

    const body = result.stdout.toString();
    if (!body.trim()) {
      throw new ResolveNotFoundError(`Empty response from: ${url}`);
    }

    try {
      return JSON.parse(body);
    } catch (e) {
      throw new ResolveError(`Invalid JSON from ${url}: ${e}`);
    }
  }

  private _resolveFromIndex(
    baseUrl: string,
    index: Record<string, unknown>[],
    requested: Record<string, string[]> | null,
  ): ResolvedItem[] {
    const items: ResolvedItem[] = [];

    for (const entry of index) {
      const kind = (entry.kind as string) ?? "";
      const name = (entry.name as string) ?? "";
      const path = (entry.path as string) ?? "";

      if (requested && !this._matchesRequest(kind, name, requested)) {
        continue;
      }

      let raw: unknown;
      try {
        raw = this._fetchJson(`${baseUrl}/${path}`);
      } catch {
        continue;
      }

      const tmp = mkdtempSync(join(tmpdir(), "dna-http-"));
      const itemDir = join(tmp, name);
      mkdirSync(itemDir, { recursive: true });
      writeFileSync(join(itemDir, "manifest.yaml"), JSON.stringify(raw, null, 2));
      items.push({ name, kind, sourcePath: itemDir });
    }

    return items;
  }

  private _resolveFromBundle(
    bundle: Record<string, unknown>[],
    requested: Record<string, string[]> | null,
  ): ResolvedItem[] {
    const items: ResolvedItem[] = [];

    for (const raw of bundle) {
      const kind = (raw.kind as string) ?? "";
      const metadata = (raw.metadata as Record<string, unknown>) ?? {};
      const name = (metadata.name as string) ?? "";
      if (!name) continue;

      if (requested && !this._matchesRequest(kind, name, requested)) {
        continue;
      }

      const tmp = mkdtempSync(join(tmpdir(), "dna-http-"));
      const itemDir = join(tmp, name);
      mkdirSync(itemDir, { recursive: true });
      writeFileSync(join(itemDir, "manifest.yaml"), JSON.stringify(raw, null, 2));
      items.push({ name, kind, sourcePath: itemDir });
    }

    return items;
  }

  private _collectRequested(dep: Record<string, unknown>): Record<string, string[]> | null {
    const result: Record<string, string[]> = {};
    const items = (dep.items as Record<string, unknown>[]) ?? [];
    for (const item of items) {
      const kind = (item.kind as string) ?? "";
      if (kind) {
        result[kind] = (item.names as string[]) ?? [];
      }
    }
    return Object.keys(result).length > 0 ? result : null;
  }

  private _matchesRequest(kind: string, name: string, requested: Record<string, string[]>): boolean {
    if (!(kind in requested)) return false;
    const names = requested[kind];
    if (!names || names.length === 0) return true;
    return names.includes(name);
  }
}
