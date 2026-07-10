/**
 * LocalResolver — ResolverPort for local: URIs.
 *
 * 1:1 parity with Python dna.v3.adapters.resolvers.local.
 */

import { existsSync, readdirSync, statSync } from "node:fs";
import { resolve, join } from "node:path";
import { ResolveError } from "../../kernel/protocols.js";
import type { ResolvedItem, ResolverPort } from "../../kernel/protocols.js";

// i-009 / i-010 — pre-v3 dependency shorthand: category-list keys at the dep
// top level (`skills: [...]`). DEAD format — the Genome contract is
// `items: [{kind, names}]` and no resolver ever read the shorthand, so it
// silently fell through to _resolveAll with the wrong granularity
// (bundle SUBDIRECTORIES instead of bundles). Rejected loudly instead.
// Twin of LEGACY_SHORTHAND_KEYS / reject_legacy_shorthand in
// dna/adapters/resolvers/local.py — same keys, same message.
export const LEGACY_SHORTHAND_KEYS = [
  "skills",
  "souls",
  "agents",
  "actors",
  "guardrails",
] as const;

/**
 * Throw ResolveError if the dep uses the dead pre-v3 category shorthand.
 *
 * Shared by the local, github and http resolvers so the legacy format
 * fails loud (an entry in `mi.resolveErrors`) with a rewrite recipe
 * instead of silently resolving at the wrong granularity.
 */
export function rejectLegacyShorthand(dep: Record<string, unknown>): void {
  const legacy = LEGACY_SHORTHAND_KEYS.filter((k) => Array.isArray(dep[k]));
  if (legacy.length > 0) {
    const source = typeof dep.source === "string" ? dep.source : "<unknown>";
    const singular = legacy[0].replace(/s+$/, "");
    const kind = singular.charAt(0).toUpperCase() + singular.slice(1);
    throw new ResolveError(
      `Dependency '${source}' uses the legacy '${legacy[0]}:' shorthand, ` +
        `which is no longer read. Rewrite it in the v3 items format:\n` +
        `  items:\n` +
        `  - kind: ${kind}\n` +
        `    names: [...]`,
    );
  }
}

export class LocalResolver implements ResolverPort {
  readonly baseDir: string | null;

  constructor(baseDir?: string) {
    this.baseDir = baseDir ? resolve(baseDir) : null;
  }

  cacheKey(uri: string): string {
    const path = uri.replace(/^local:/, "");
    const safe = path.replace(/[^a-zA-Z0-9_-]/g, "-").replace(/^-+|-+$/g, "");
    return `local-${safe}`;
  }

  async resolve(uri: string, dep: Record<string, unknown>): Promise<ResolvedItem[]> {
    const pathStr = uri.replace(/^local:/, "");
    let localPath = pathStr;

    if (!localPath.startsWith("/") && this.baseDir) {
      localPath = resolve(this.baseDir, pathStr);
    }

    if (!existsSync(localPath)) {
      return [];
    }

    // Normalize dep format
    const requested = this._collectRequested(dep);
    if (requested) {
      return this._resolveByCategory(localPath, requested);
    }
    return this._resolveAll(localPath);
  }

  private _collectRequested(
    dep: Record<string, unknown>,
  ): Record<string, string[]> | null {
    // The legacy pre-v3 shorthand (`skills: [...]` at the dep top level)
    // throws ResolveError (i-009/i-010) — see `rejectLegacyShorthand`.
    rejectLegacyShorthand(dep);
    const result: Record<string, string[]> = {};
    const items = (dep.items as Record<string, unknown>[]) ?? [];
    for (const item of items) {
      const kind = (item.kind as string) ?? "";
      if (kind) {
        const category = kind.toLowerCase() + "s"; // Skill -> skills
        result[category] = (item.names as string[]) ?? []; // [] = all
      }
    }
    return Object.keys(result).length > 0 ? result : null;
  }

  private _resolveAll(source: string): ResolvedItem[] {
    const items: ResolvedItem[] = [];
    const entries = readdirSync(source).sort();
    for (const entry of entries) {
      const full = join(source, entry);
      if (!statSync(full).isDirectory() || entry.startsWith(".")) continue;
      // Recurse into category dirs (skills/, souls/, agents/)
      const subEntries = readdirSync(full).sort();
      for (const sub of subEntries) {
        const itemDir = join(full, sub);
        if (statSync(itemDir).isDirectory()) {
          items.push({ name: sub, kind: "", sourcePath: itemDir });
        }
      }
    }
    return items;
  }

  private _resolveByCategory(
    source: string,
    requested: Record<string, string[]>,
  ): ResolvedItem[] {
    const items: ResolvedItem[] = [];
    for (const [category, names] of Object.entries(requested)) {
      const categoryDir = join(source, category);
      if (!existsSync(categoryDir)) continue;

      if (names.length > 0) {
        // Import specific names
        for (const name of names) {
          for (const candidate of [join(categoryDir, name), join(source, name)]) {
            if (existsSync(candidate) && statSync(candidate).isDirectory()) {
              items.push({ name, kind: "", sourcePath: candidate });
              break;
            }
          }
        }
      } else {
        // Import all from category
        const entries = readdirSync(categoryDir).sort();
        for (const entry of entries) {
          const subdir = join(categoryDir, entry);
          if (statSync(subdir).isDirectory()) {
            items.push({ name: entry, kind: "", sourcePath: subdir });
          }
        }
      }
    }
    return items;
  }
}
