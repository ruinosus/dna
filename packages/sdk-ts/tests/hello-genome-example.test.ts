/**
 * examples/hello-genome must RUN — the README quick start is this example.
 *
 * Spawns `bun run run.ts` exactly as a user would and asserts the three
 * demonstrated behaviors: scope scan, market-Skill load under the owner's
 * namespace, and prompt composition (Py twin:
 * packages/sdk-py/tests/test_hello_genome_example.py).
 */
import { expect, test } from "bun:test";
import { join } from "node:path";

const EXAMPLE = join(import.meta.dir, "..", "..", "..", "examples", "hello-genome");

test("hello-genome run.ts executes and composes the prompt", () => {
  const res = Bun.spawnSync(["bun", "run", "run.ts"], { cwd: EXAMPLE });
  const out = res.stdout.toString();
  if (res.exitCode !== 0) {
    console.error(`run.ts failed:\n${res.stderr.toString()}`);
  }
  expect(res.exitCode).toBe(0);
  // 1. scope scan — every document identified by (apiVersion, kind, name)
  expect(out).toContain("scope: hello-genome");
  expect(out).toContain("github.com/ruinosus/dna/v1");
  // 2. the REAL marketplace skill loads under its owner's namespace
  expect(out).toContain("agentskills.io/v1");
  expect(out).toContain("verification-before-completion");
  // 3. prompt composition
  expect(out).toContain("You are Helio, a friendly assistant.");
});
