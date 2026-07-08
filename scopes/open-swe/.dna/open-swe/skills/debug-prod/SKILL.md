---
name: debug-prod
description: "Instrucao para debugging em producao — restrita ao swe-agent e persona senior"
---

Ao debugar em producao:

1. **Nunca altere dados diretamente** — somente leitura
2. **Use queries read-only** — nenhum INSERT, UPDATE ou DELETE
3. **Colete logs antes de agir** — entenda o estado atual do sistema
4. **Escale se impactar SLA** — se o problema afeta usuarios, alerte o oncall imediatamente