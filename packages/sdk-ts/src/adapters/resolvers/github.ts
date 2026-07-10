/**
 * GitHubResolver — ResolverPort for github: URIs.
 *
 * 1:1 parity with Python dna.v3.adapters.resolvers.github.
 *
 * URI format: github:owner/repo[@ref][/path]
 */

import { mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import type { ResolvedItem, ResolverPort } from "../../kernel/protocols.js";
import { ResolveError, ResolveNotFoundError } from "../../kernel/protocols.js";
import { LocalResolver, rejectLegacyShorthand } from "./local.js";

export class GitHubResolver implements ResolverPort {
  cacheKey(uri: string): string {
    const raw = uri.replace(/^github:/, "");
    const safe = raw.replace(/[^a-zA-Z0-9_-]/g, "-").replace(/^-+|-+$/g, "");
    return `github-${safe}`;
  }

  async resolve(uri: string, dep: Record<string, unknown>): Promise<ResolvedItem[]> {
    // i-010 — reject the dead legacy shorthand (`skills: [...]`)
    // unconditionally, like the Py twin. Py rejects after fetch_tree (it
    // funnels through LocalResolver._collect_requested); here it fires
    // BEFORE cloning — same contract (loud ResolveError with the rewrite
    // recipe), no wasted network round-trip.
    rejectLegacyShorthand(dep);
    const raw = uri.replace(/^github:/, "");
    const match = raw.match(
      /^(?<owner>[^/]+)\/(?<repo>[^/@]+)(?:\/(?<path>[^@]+))?(?:@(?<ref>.+))?$/,
    );

    if (!match || !match.groups) {
      throw new ResolveError(`Invalid github URI: ${uri}`);
    }

    const { owner, repo, path: subPath, ref } = match.groups;
    const cloneUrl = `https://github.com/${owner}/${repo}.git`;
    const tmpDir = mkdtempSync(join(tmpdir(), "dna-github-"));

    const args = ["git", "clone", "--depth", "1"];
    if (ref) {
      args.push("--branch", ref);
    }
    args.push(cloneUrl, tmpDir);

    const result = Bun.spawnSync(args, { timeout: 60_000 });

    if (result.exitCode !== 0) {
      throw new ResolveNotFoundError(
        `Git clone failed for ${cloneUrl}: exit code ${result.exitCode}`,
      );
    }

    const source = subPath ? join(tmpDir, subPath) : tmpDir;
    const local = new LocalResolver(source);
    return local.resolve(subPath ? `local:.` : `local:`, dep);
  }
}
