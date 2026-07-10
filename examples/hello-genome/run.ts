/**
 * hello-genome — the minimal DNA example (TypeScript).
 *
 * Loads the scope in ./.dna, lists every document by
 * (apiVersion, kind, name), and composes the agent's system prompt.
 *
 * Run it (from the repo root):
 *
 *     cd packages/sdk-ts && bun install
 *     bun run ../../examples/hello-genome/run.ts
 */
// In your own project this is: import { quickInstance } from "dna-sdk";
import { quickInstance } from "../../packages/sdk-ts/src/index.ts";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const base = join(dirname(fileURLToPath(import.meta.url)), ".dna");
const mi = await quickInstance("hello-genome", base);

console.log(`scope: ${mi.scope}`);
for (const d of mi.documents) {
  console.log(`  ${d.apiVersion.padEnd(32)} ${d.kind.padEnd(8)} ${d.name}`);
}

// The Skill is a REAL marketplace bundle, consumed byte-faithful under
// its owner's namespace (agentskills.io/v1).
const skill = mi.documents.find((d) => d.kind === "Skill")!;
console.log(`\nskill: ${skill.name}`);

console.log("\n--- composed prompt (agent: greeter) ---");
console.log(await mi.buildPrompt({ agent: "greeter" }));
