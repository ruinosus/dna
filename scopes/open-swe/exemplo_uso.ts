/**
 * exemplo_uso.ts — Demonstracao end-to-end do DNA SDK (TypeScript).
 *
 * Como rodar:
 *   cd examples/open-swe
 *   bun run exemplo_uso.ts
 */

import { join } from "node:path";
import { Kernel, HelixExtension, FilesystemAdapter } from "../../typescript/src/index.js";
import { matchesTrigger, type Agent, type Skill, type Module } from "../../typescript/src/extensions/helix/skill.js";

const k = new Kernel();
k.load(new HelixExtension());
const fs = k._sources.filesystem as FilesystemAdapter;
fs.baseDir = join(import.meta.dir, ".dna");
const mi = k.instance("open-swe");

console.log("=".repeat(60));
console.log("DNA SDK — Demonstracao (TypeScript, Kernel + Extensions)");
console.log("=".repeat(60));

// 1. Navegacao generica
console.log("\n--- MODULO");
const mod = mi.module as Module;
console.log(`  Nome: ${mod.metadata.name}`);
console.log(`  Agente padrao: ${mod.spec.default_agent}`);
console.log(`  Budget diario: $${mod.spec.budget?.daily_usd}`);

// 2. ref() — resolve instrucao
console.log("\n--- INSTRUCAO DO AGENTE (swe-agent)");
const agent = mi.one("Agent", "swe-agent") as Agent;
const instruction = mi.ref(agent.spec.instruction, {
  repository: "helix",
  budget_daily: "25.00",
  budget_monthly: "500.00",
});
console.log(`  Primeiros 200 chars:\n  ${instruction.slice(0, 200).trim()}`);

// 3. Skills por trigger
console.log("\n--- SKILLS para trigger 'pull_request'");
const prSkills = (mi.all("Skill") as Skill[]).filter((s) => matchesTrigger(s, "pull_request"));
for (const s of prSkills) {
  console.log(`  - ${s.metadata.name} (triggers: ${s.spec.triggers.slice(0, 2)}...)`);
  const instr = mi.ref(s.spec.instruction);
  console.log(`    instrucao: ${instr.slice(0, 80).trim()}...`);
}

// 4. Layer overlay
console.log("\n--- LAYER OVERLAY (tenant=team-b)");
const miB = mi.resolve({ tenant: "team-b" });
const budgetBase = mi.budget();
const budgetB = miB.budget();
console.log(`  Budget base:   $${budgetBase.daily_usd}/dia`);
console.log(`  Budget team-b: $${budgetB.daily_usd}/dia  <- sobrescrito pelo overlay`);

// 5. Summary
console.log("\n--- SUMMARY");
console.log(JSON.stringify(mi.summary(), null, 2));

// 6. Kinds
console.log("\n--- KINDS NO MODULO");
for (const [av, knd] of mi.listKinds()) {
  console.log(`  ${av} / ${knd}`);
}

console.log("\n--- KINDS NO REGISTRY");
for (const [av, knd] of k.registry.listKinds().sort()) {
  console.log(`  ${av} / ${knd}`);
}

console.log("\n--- Kernel + Extensions funcionando! API generica: all(), one(), ref().");
