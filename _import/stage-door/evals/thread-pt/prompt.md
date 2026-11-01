---
name: thread-pt
tags: [thread, pt]
max_turns: 30
timeout_seconds: 900
allowed_tools: [Skill, Read, Write, Edit, Bash]
---
Monta o nosso way of working a partir desta tabela e salve como compras.way.yaml. Pode decidir o que for pequeno, não me pergunte nada, e gere tudo.

| Etapa | Descrição | Entradas | Saídas | Papéis | Métricas |
|---|---|---|---|---|---|
| 1. Pedido | A área pede a compra | Necessidade da área | Pedido de compra | Solicitante | Pedidos por mês |
| 2. Cotação | Compras cota com fornecedores | Pedido de compra; catálogo de fornecedores | Mapa de cotações | Comprador | Tempo de cotação |
| 3. Aprovação (gate) | O gestor aprova o gasto | Mapa de cotações | Compra aprovada; motivo da recusa | Gestor | % aprovadas |
| 4. Contratação | Compras fecha com o fornecedor | Compra aprovada | Contrato assinado | Comprador | Tempo até o contrato |
| 5. Recebimento | A área recebe e confere | Contrato assinado | Recebimento conferido | Solicitante | % recebido sem problema |

Se a aprovação recusar, volta para a Cotação.
