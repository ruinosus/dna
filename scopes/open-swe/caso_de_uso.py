"""
caso_de_uso.py — Caso de uso real: como um LLM agent se auto-configura via manifesto.

Cenario: Uma plataforma de coding agents onde:
  - Existem 2 agents (swe-agent e reviewer-agent) com roles e tools diferentes
  - Existem 3 skills (pr-review, branch-naming, debug-prod)
  - Existem 4 guardrails (safety, code-quality, pii-protection, review-ethics)
  - Existem 2 layers (tenant):
      base          -> budget $25/dia
      team-b        -> budget $50/dia (cliente enterprise)

O script simula o que o LLM agent faria na inicializacao:
  1. Carregar o manifesto
  2. Identificar quem ele e (agent) e como se comportar
  3. Descobrir quais skills ele pode usar nesse contexto
  4. Montar o system prompt combinando instrucao base + skills
  5. Aplicar overlay de layer se necessario
  6. Gerar diagramas

Tudo SEM hardcoding. Se o PO editar o YAML, o comportamento muda sem deploy.

Como rodar:
    cd examples/open-swe
    python caso_de_uso.py
"""

from pathlib import Path
import os, json
os.chdir(Path(__file__).parent)

from dna import Kernel

mi = Kernel.quick("open-swe")

print("=" * 70)
print("CASO DE USO: Agent se auto-configura via manifesto")
print("=" * 70)


# =====================================================================
# PASSO 1: Agent descobre quem ele e
# =====================================================================
print("\n" + "-" * 70)
print("PASSO 1: Agent descobre quem ele e")
print("-" * 70)

agent = mi.one("Agent", "swe-agent")
print(f"  Eu sou: {agent.metadata.name}")
print(f"  Descricao: {agent.metadata.description}")
print(f"  Model: {agent.spec.get('model', 'N/A')}")
print(f"  Tools: {agent.spec.get('tools', [])}")
print(f"  Soul: {agent.spec.get('soul', 'N/A')}")
print(f"  Skills: {agent.spec.get('skills', [])}")
print(f"  Guardrails: {agent.spec.get('guardrails', [])}")


# =====================================================================
# PASSO 2: Agent carrega sua instrucao base (system prompt)
# =====================================================================
print("\n" + "-" * 70)
print("PASSO 2: Agent carrega sua instrucao base (build_prompt)")
print("-" * 70)

system_prompt = mi.build_prompt(agent="swe-agent")
print(f"  System prompt ({len(system_prompt)} chars):")
print(f"  {system_prompt[:200].strip()}...")


# =====================================================================
# PASSO 3: Agent descobre quais skills ele pode usar
# =====================================================================
print("\n" + "-" * 70)
print("PASSO 3: Agent descobre quais skills pode usar")
print("-" * 70)

all_skills = mi.all("Skill")
print(f"\n  Todas as skills no modulo ({len(all_skills)}):")
for s in all_skills:
    print(f"    - {s.metadata.name:20} descricao={s.metadata.get('description', '')[:40]}")

# Skills declaradas pelo agent
agent_skills = agent.spec.get("skills", [])
print(f"\n  Skills declaradas por swe-agent ({len(agent_skills)}):")
for skill_name in agent_skills:
    skill = mi.one("Skill", skill_name)
    if skill:
        print(f"    - {skill.name}")

# Skills do reviewer-agent
reviewer = mi.one("Agent", "reviewer-agent")
if reviewer:
    reviewer_skills = reviewer.spec.get("skills", [])
    print(f"\n  Skills declaradas por reviewer-agent ({len(reviewer_skills)}):")
    for skill_name in reviewer_skills:
        print(f"    - {skill_name}")


# =====================================================================
# PASSO 4: Guardrails do agent
# =====================================================================
print("\n" + "-" * 70)
print("PASSO 4: Guardrails aplicadas ao agent")
print("-" * 70)

all_guardrails = mi.all("Guardrail")
agent_guardrails = agent.spec.get("guardrails", [])
print(f"\n  Todas as guardrails no modulo ({len(all_guardrails)}):")
for g in all_guardrails:
    in_agent = g.name in agent_guardrails
    rules = g.spec.get("rules", [])
    severity = g.spec.get("severity", "warn")
    marker = " <-- swe-agent" if in_agent else ""
    print(f"    - {g.name:20} severity={severity:5} rules={len(rules)}{marker}")


# =====================================================================
# PASSO 5: Comparar prompts de agentes diferentes
# =====================================================================
print("\n" + "-" * 70)
print("PASSO 5: Comparar prompts de agents diferentes")
print("-" * 70)

for name in ["swe-agent", "reviewer-agent"]:
    prompt = mi.build_prompt(agent=name)
    print(f"  {name:20} -> {len(prompt):,} chars")


# =====================================================================
# PASSO 6: Layer overlay — mesmo agent, budget diferente
# =====================================================================
print("\n" + "-" * 70)
print("PASSO 6: Layer overlay — team-b tem budget diferente")
print("-" * 70)

mi_b = mi.resolve(layers={"tenant": "team-b"})

budget_base = mi.root.spec.get("budget", {})
budget_b = mi_b.root.spec.get("budget", {})
print(f"  Budget base:     ${budget_base.get('daily_usd', 'N/A')}/dia  ${budget_base.get('monthly_usd', 'N/A')}/mes")
print(f"  Budget team-b:   ${budget_b.get('daily_usd', 'N/A')}/dia  ${budget_b.get('monthly_usd', 'N/A')}/mes")

# Comparar system prompts entre base e team-b
prompt_base = mi.build_prompt(agent="swe-agent")
prompt_b = mi_b.build_prompt(agent="swe-agent")
print(f"\n  Prompt base:   {len(prompt_base):,} chars")
print(f"  Prompt team-b: {len(prompt_b):,} chars")
if prompt_base != prompt_b:
    print("  -> Prompts DIFERENTES (layer overlay aplicado)")
else:
    print("  -> Prompts IGUAIS (layer nao alterou instrucao do agent)")


# =====================================================================
# PASSO 7: Summary + Diagramas
# =====================================================================
print("\n" + "-" * 70)
print("PASSO 7: summary() + diagramas")
print("-" * 70)

summary = mi.summary()
print(json.dumps(summary, indent=2, ensure_ascii=False, default=str)[:500])
print("  ...")

# Gerar diagramas
out = Path("docs")
diagrams = mi.export_diagrams_md(str(out))
print(f"\n  Diagramas gerados: {len(diagrams)} arquivos em docs/")
for fname in sorted(diagrams):
    print(f"    - {fname}")


print("\n" + "=" * 70)
print("FIM — Zero hardcoding. PO edita YAML, comportamento muda sem deploy.")
print("=" * 70)
