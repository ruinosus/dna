"""
exemplo_uso.py — Demonstracao end-to-end do DNA SDK com Kernel + Extensions.

Como rodar:
    cd examples/open-swe
    python exemplo_uso.py
"""

from pathlib import Path
import os
os.chdir(Path(__file__).parent)

from dna import Kernel

mi = Kernel.quick("open-swe")

print("=" * 60)
print("DNA SDK — Demonstracao (Kernel + Extensions)")
print("=" * 60)

# ----------------------------------------------------------------
# 1. Navegacao generica — all() e one()
# ----------------------------------------------------------------
print("\n--- MODULO")
mod = mi.module
print(f"  Nome: {mod.metadata.name}")
print(f"  Agente padrao: {mod.spec.default_agent}")
print(f"  Budget diario: ${mod.spec.budget.daily_usd}")

# ----------------------------------------------------------------
# 2. ref() — resolve instrucao do agente
# ----------------------------------------------------------------
print("\n--- INSTRUCAO DO AGENTE (swe-agent)")
agent = mi.one("Agent", "swe-agent")
instruction = mi.ref(
    agent.spec.get("instruction"),
    data={"repository": "helix", "budget_daily": "25.00", "budget_monthly": "500.00"},
)
print(f"  Primeiros 200 chars:\n  {instruction[:200].strip()}")

# ----------------------------------------------------------------
# 3. Skills por trigger — logica no Skill, nao no MI
# ----------------------------------------------------------------
print("\n--- SKILLS para trigger 'pull_request'")
pr_skills = [s for s in mi.all("Skill") if s.matches_trigger("pull_request")]
for s in pr_skills:
    print(f"  - {s.metadata.name} (triggers: {s.triggers[:2]}...)")
    instr = mi.ref(s.spec.get("instruction"))
    print(f"    instrucao: {instr[:80].strip()}...")

# ----------------------------------------------------------------
# 4. Layer overlay
# ----------------------------------------------------------------
print("\n--- LAYER OVERLAY (tenant=team-b)")
mi_b = mi.resolve(layers={"tenant": "team-b"})
budget_base = mi.budget()
budget_b = mi_b.budget()
print(f"  Budget base:   ${budget_base['daily_usd']}/dia")
print(f"  Budget team-b: ${budget_b['daily_usd']}/dia  <- sobrescrito pelo overlay")

# ----------------------------------------------------------------
# 5. Summary para LLM agents
# ----------------------------------------------------------------
print("\n--- SUMMARY (para passar a um LLM agent como contexto)")
import json
summary = mi.summary()
print(json.dumps(summary, indent=2, ensure_ascii=False))

# ----------------------------------------------------------------
# 6. Kinds
# ----------------------------------------------------------------
print("\n--- KINDS NO MODULO")
for api_version, kind in mi.list_kinds():
    print(f"  {api_version} / {kind}")

print("\n--- KINDS NO REGISTRY")
for api_version, kind in sorted(mi.registry.list_kinds()):
    print(f"  {api_version} / {kind}")

print("\n--- Kernel + Extensions funcionando! API generica: all(), one(), ref().")
