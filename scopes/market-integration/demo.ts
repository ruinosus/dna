/**
 * Proof of concept: SDK reads REAL market content without modification.
 *
 * Skills: from Anthropic (agentskills.io)
 * Souls: from SoulSpec (soulspec.org)
 * AGENTS.md: agents.md standard
 */

import { resolve } from "node:path";
import { Kernel } from "../../typescript/src/index.js";

const baseDir = resolve(import.meta.dir, ".dna");
const mi = Kernel.quick("market-demo", baseDir);

console.log("=".repeat(60));
console.log("MARKET INTEGRATION DEMO");
console.log("=".repeat(60));

// Skills (from Anthropic -- agentskills.io format)
const skills = mi.all("Skill");
console.log(`\nSkills found: ${skills.length}`);
for (const s of skills) {
  const meta = (s as any).metadata ?? {};
  const spec = (s as any).spec ?? {};
  const desc = (meta.description ?? "").slice(0, 80);
  console.log(`  ${meta.name}: ${desc}...`);
  console.log(`    license: ${spec.license ?? "?"}`);
  console.log(`    references: ${(spec.references ?? []).length}, scripts: ${(spec.scripts ?? []).length}, assets: ${(spec.assets ?? []).length}`);
}

// Souls (from SoulSpec -- soulspec.org format)
const souls = mi.all("Soul");
console.log(`\nSouls found: ${souls.length}`);
for (const soul of souls) {
  const spec = (soul as any).spec ?? {};
  const meta = (soul as any).metadata ?? {};
  console.log(`  ${meta.name} (${spec.displayName ?? spec.display_name}) v${spec.version}`);
  console.log(`    tags: ${JSON.stringify(spec.tags ?? [])}`);
  console.log(`    soul: ${spec.soul_content ? "yes" : "no"}`);
  console.log(`    identity: ${spec.identity_content ? "yes" : "no"}`);
  console.log(`    style: ${spec.style_content ? "yes" : "no"}`);
  console.log(`    agents: ${spec.agents_content ? "yes" : "no"}`);
  console.log(`    heartbeat: ${spec.heartbeat_content ? "yes" : "no"}`);
  console.log(`    examples: ${(spec.examples ?? []).length}`);
}

// AGENTS.md (agents.md format -- plain markdown)
const contexts = mi.all("AgentContext");
console.log(`\nAgent Contexts found: ${contexts.length}`);
for (const ctx of contexts) {
  const spec = (ctx as any).spec ?? {};
  const meta = (ctx as any).metadata ?? {};
  console.log(`  ${meta.name}: ${(spec.content ?? "").length} chars`);
}

// Build prompt (all together)
const prompt = mi.buildPrompt();
console.log(`\nPrompt built: ${prompt.length} chars`);
console.log(`  Preview: ${prompt.slice(0, 200)}...`);

// Describe all kinds
console.log(`\nKernel.describe():`);
const k = Kernel.auto();
for (const entry of k.describe()) {
  console.log(`  ${(entry.alias ?? "").padEnd(25)} ${entry.apiVersion.padEnd(20)} origin=${entry.origin ?? "?"}`);
}

// Module summary
console.log(`\nModule summary:`);
const summary = mi.summary();
for (const [kindName, docs] of Object.entries((summary as any).documents ?? {})) {
  console.log(`  ${kindName}: ${(docs as any[]).length} document(s)`);
}

console.log("\nALL MARKET CONTENT LOADED SUCCESSFULLY");
