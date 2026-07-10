/**
 * Market-fidelity demo (TypeScript): the SDK reads REAL marketplace
 * content without modification.
 *
 * Skills: Anthropic marketplace + Superpowers collection (agentskills.io)
 * Soul: soulspec.org  ·  AGENTS.md: agents.md
 *
 * Run (from the repo root):
 *
 *     cd packages/sdk-ts && bun install
 *     bun run ../../scopes/market-integration/demo.ts
 */
// In your own project this is: import { quickInstance } from "dna-sdk";
import { quickInstance } from "../../packages/sdk-ts/src/index.ts";
import { resolve } from "node:path";

const baseDir = resolve(import.meta.dir, ".dna");
const mi = await quickInstance("market-demo", baseDir);

console.log("=".repeat(60));
console.log("MARKET INTEGRATION DEMO — REAL CONTENT");
console.log("=".repeat(60));

const skills = mi.documents.filter((d) => d.kind === "Skill");
console.log(`\nSkills found: ${skills.length}`);
for (const s of skills) {
  const spec = s.spec as Record<string, unknown>;
  const desc = String(s.metadata?.description ?? "").slice(0, 72);
  const n = (f: string) => Object.keys((spec[f] as object) ?? {}).length;
  console.log(`  ${s.name}: ${desc}...`);
  console.log(`    references: ${n("references")}, scripts: ${n("scripts")}, assets: ${n("assets")}`);
}

const souls = mi.documents.filter((d) => d.kind === "Soul");
console.log(`\nSouls found: ${souls.length}`);
for (const soul of souls) {
  const spec = soul.spec as Record<string, unknown>;
  const files = [
    ["SOUL.md", "soul_content"], ["IDENTITY.md", "identity_content"],
    ["STYLE.md", "style_content"], ["AGENTS.md", "agents_content"],
    ["HEARTBEAT.md", "heartbeat_content"],
  ].filter(([, f]) => spec[f]).map(([label]) => label);
  const label = spec.display_name ? `${soul.name} (${spec.display_name})` : soul.name;
  console.log(`  ${label} — ${files.join(", ")}`);
}

const contexts = mi.documents.filter((d) => d.kind === "AgentDefinition");
console.log(`\nAgent definitions (AGENTS.md): ${contexts.length}`);

console.log(`\n${"=".repeat(60)}`);
console.log(`TOTAL: ${skills.length} skills + ${souls.length} souls + ${contexts.length} agent definitions`);
console.log("ALL LOADED FROM REAL MARKET SOURCES — ZERO MODIFICATION");
console.log("=".repeat(60));
