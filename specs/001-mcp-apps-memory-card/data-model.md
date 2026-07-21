# Data Model — MCP Apps: card de memória

**Phase 1 do `/speckit-plan`** — 2026-07-21. Sem mudança de shape: nenhuma
entidade nova é persistida; o card renderiza dados que já existem.

## Entidades

### Template do card de memória (recurso de UI)

| Campo | Valor / Regra |
|---|---|
| URI | `ui://dna/memory-list` (estável — hosts cacheiam por URI) |
| mimeType | `text/html;profile=mcp-app` |
| Conteúdo | HTML + JS inline; lib `@modelcontextprotocol/ext-apps` bundlada; **zero** URL externa |
| Dados embutidos | **Nenhum** — zero dado de tenant, zero segredo/token; público e cacheável |
| Contrato de renderização | o template define os campos que exibe; campo ausente → vazio-honesto |
| Estado vazio | "nenhuma memória" — o mesmo empty state honesto de hoje |

**Validação (mutações que devem morrer)**: dados assados de volta no HTML →
teste morre; URL externa (CDN) de volta → teste morre; golden byte-stable.

### `structured_content` das tools de memória (existente — inalterado)

- Shape atual de `list_memories` / `recall`, já espelhado por
  `_with_memory_card`. **Sem mudança.**
- Fluxo: resultado da tool → push (`ontoolresult`) → JS do template renderiza.
- Escopo de segurança: dados só existem na sessão autenticada; nunca no
  template.

### Declaração das tools `list_memories` / `recall`

- Cada declaração carrega o ponteiro para o template
  (`app=AppConfig(resource_uri="ui://dna/memory-list")`, FastMCP ≥3.2).
- **Validação (mutação)**: pointer removido da declaração → teste morre.

## Relacionamentos

```text
declaração(list_memories | recall) ──aponta──▶ recurso ui://dna/memory-list (estático, público)
resultado(list_memories | recall)  ──push────▶ card (sessão autenticada)
resultado(list_memories | recall).content (textual) ──sempre──▶ qualquer host (byte-idêntico ao atual)
```

## Transições de estado

Nenhuma — o card é só leitura nesta entrega; nenhuma ação, nenhuma escrita.
