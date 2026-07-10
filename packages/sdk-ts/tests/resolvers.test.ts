import { afterEach, describe, test, expect } from "bun:test";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { HttpResolver } from "../src/adapters/resolvers/http.js";
import { GitHubResolver } from "../src/adapters/resolvers/github.js";
import { LocalResolver } from "../src/adapters/resolvers/local.js";
import { ResolveError } from "../src/kernel/protocols.js";

describe("HttpResolver", () => {
  test("cacheKey is deterministic", async () => {
    const r = new HttpResolver();
    expect(r.cacheKey("http://example.com/deps")).toBe(r.cacheKey("http://example.com/deps"));
  });
  test("cacheKey sanitizes special chars", async () => {
    const r = new HttpResolver();
    const key = r.cacheKey("https://registry.example.com/v1/packages");
    expect(key).not.toContain(":");
    expect(key).not.toContain("/");
  });
  test("cacheKey is prefixed with http-", async () => {
    const r = new HttpResolver();
    expect(r.cacheKey("https://example.com/pkg")).toMatch(/^http-/);
  });
  test("cacheKey is truncated to 120 chars", async () => {
    const r = new HttpResolver();
    const longUri = "https://" + "a".repeat(200);
    expect(r.cacheKey(longUri).length).toBeLessThanOrEqual(120);
  });
});

describe("GitHubResolver", () => {
  test("cacheKey is deterministic", async () => {
    const r = new GitHubResolver();
    expect(r.cacheKey("github:org/repo")).toBe(r.cacheKey("github:org/repo"));
  });
  test("cacheKey includes ref", async () => {
    const r = new GitHubResolver();
    const k1 = r.cacheKey("github:org/repo@main");
    const k2 = r.cacheKey("github:org/repo@v2");
    expect(k1).not.toBe(k2);
  });
  test("cacheKey is prefixed with github-", async () => {
    const r = new GitHubResolver();
    expect(r.cacheKey("github:org/repo")).toMatch(/^github-/);
  });
  test("cacheKey sanitizes special chars", async () => {
    const r = new GitHubResolver();
    const key = r.cacheKey("github:org/repo@v1.2.3");
    expect(key).not.toContain(":");
    expect(key).not.toContain("/");
  });
});

/**
 * i-010 — TS twin of Python `TestLegacyDepShorthandRejected`
 * (packages/sdk-py/tests/test_dependency_resolution.py, i-009).
 *
 * The pre-v3 dep shorthand (`skills: [...]` as a top-level dep key) is a
 * DEAD format: the Genome contract is `items: [{kind, names}]`. Silently
 * ignoring it made resolution fall through to `_resolveAll` with the wrong
 * granularity — pointed at a flat tree it returned the bundle
 * SUBDIRECTORIES (references/, scripts/) instead of the bundles. The
 * shorthand is now rejected loudly with a rewrite recipe, mirroring
 * `reject_legacy_shorthand` in dna/adapters/resolvers/local.py.
 *
 * Delta vs Py worth knowing: Py's GitHubResolver rejects after fetch_tree
 * (it delegates to LocalResolver._collect_requested unconditionally); the
 * TS GitHubResolver rejects BEFORE cloning — same contract (ResolveError,
 * same message), cheaper, and testable without network.
 */
describe("legacy dep shorthand rejection (i-010)", () => {
  // Simulate a remote repo with the same shape as the Py fixture
  // `_create_remote_repo`: skills/{tdd,debugging}/SKILL.md + souls/expert.
  let tmp: string;

  function createRemoteRepo(): string {
    tmp = mkdtempSync(join(tmpdir(), "dna-shorthand-"));
    const repo = join(tmp, "remote-repo");
    for (const [name, content] of [
      ["tdd", "# TDD Skill\nWrite tests first."],
      ["debugging", "# Debug Skill\nFind root cause."],
    ]) {
      const d = join(repo, "skills", name);
      mkdirSync(d, { recursive: true });
      writeFileSync(join(d, "SKILL.md"), content);
    }
    const soulDir = join(repo, "souls", "expert");
    mkdirSync(soulDir, { recursive: true });
    writeFileSync(join(soulDir, "SOUL.md"), "# Expert Soul\nDeep technical knowledge.");
    return repo;
  }

  afterEach(() => {
    if (tmp) rmSync(tmp, { recursive: true, force: true });
  });

  test("local resolver rejects the skills shorthand", async () => {
    const remote = createRemoteRepo();
    const resolver = new LocalResolver();
    const dep = { source: `local:${remote}`, skills: ["tdd", "debugging"] };
    let err: unknown;
    try {
      await resolver.resolve(`local:${remote}`, dep);
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(ResolveError);
    const msg = (err as Error).message;
    expect(msg).toContain("skills"); // names the offending key
    expect(msg).toContain("items"); // points at the v3 contract
  });

  test("github resolver rejects the shorthand before cloning", async () => {
    // The Py twin monkeypatches fetch_tree; here the rejection fires
    // before the clone, so no network/git seam is needed at all.
    const r = new GitHubResolver();
    const dep = {
      source: "github:anthropics/skills/skills@main",
      skills: ["tdd", "debugging"],
    };
    let err: unknown;
    try {
      await r.resolve("github:anthropics/skills/skills@main", dep);
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(ResolveError);
    expect((err as Error).message).toContain("items");
  });

  test("http resolver rejects the shorthand before fetching", async () => {
    // _collectRequested runs before any curl, so this needs no network.
    const r = new HttpResolver();
    const dep = {
      source: "https://registry.example.com/v1",
      guardrails: ["safety"],
    };
    let err: unknown;
    try {
      await r.resolve("https://registry.example.com/v1", dep);
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(ResolveError);
    const msg = (err as Error).message;
    expect(msg).toContain("guardrails");
    expect(msg).toContain("kind: Guardrail"); // rewrite recipe singularizes
  });

  test("control: the v3 items format still resolves", async () => {
    const remote = createRemoteRepo();
    const resolver = new LocalResolver();
    const dep = {
      source: `local:${remote}`,
      items: [{ kind: "Skill", names: ["tdd"] }],
    };
    const resolved = await resolver.resolve(`local:${remote}`, dep);
    expect(resolved.map((r) => r.name)).toEqual(["tdd"]);
  });
});
