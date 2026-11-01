---
name: timeline-pt
tags: [purpose, timeline, pt]
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Read, Write, Edit, Bash]
---
Desenha o post-mortem da queda do nosso site ontem: às 14h10 o deploy saiu, às 14h18 os erros subiram, às 14h25 fizemos rollback, às 14h40 voltou ao normal. A causa foi uma migração de banco que travou a tabela de pedidos. Salve a receita como drawing.chalk.
