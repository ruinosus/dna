---
name: ask-pt
tags: [ask, pt]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Skill, Read, Write, Edit, Bash]
---
Monta um ensaio de incidente com o nosso runbook de login (salve como login.drill.yaml):

"# Runbook — login fora do ar
1. Confira o painel de autenticação: taxa de falhas e desde quando.
2. Se o provedor de identidade estiver com problema, ative o modo de contingência.
3. Se não resolver em 20 minutos, escale."
