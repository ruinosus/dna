# Contrato — superfície MCP do card de memória

**Phase 1 do `/speckit-plan`** — 2026-07-21. A superfície exposta a hosts
MCP (Claude.ai custom connector, console do portal, e qualquer outro cliente).

## 1. Recurso de UI

| Aspecto | Contrato |
|---|---|
| `resources/read` de `ui://dna/memory-list` | responde o template estático |
| mimeType | `text/html;profile=mcp-app` |
| Conteúdo | autocontido (lib ext-apps bundlada); zero URL externa; zero dado de tenant/segredo/token |
| Cacheabilidade | pública, por URI (template imutável entre releases; mudança de conteúdo = release) |

## 2. Declaração das tools

`tools/list` DEVE mostrar `list_memories` e `recall` apontando o template de
UI na própria declaração (FastMCP ≥3.2, `app=AppConfig(resource_uri=…)`).

## 3. Resultado das tools (inalterado)

- `content` textual: **byte-idêntico ao atual** — o contrato com todo host
  sem MCP Apps (LangGraph/copilot incluídos). Dados sempre no `content`
  primário.
- `structured_content`: shape existente, sem mudança; é o que o host com a
  extensão empurra ao card via `ontoolresult`.
- Nenhum resíduo do modelo pré-spec (`_meta` de UI) na resposta.

## 4. Comportamento por host

| Situação | Comportamento |
|---|---|
| Host com MCP Apps | renderiza o card com os dados da sessão autenticada |
| Host sem MCP Apps | `content` textual de hoje, byte-idêntico |
| Template ilegível no host | o host ignora a UI; `content` segue valendo |
| `structured_content` vazio | empty state do card ("nenhuma memória") |
| ChatGPT (sem tool-calling da UI) | irrelevante nesta entrega — card é só leitura |

## 5. Interação

Só leitura. O card não expõe nenhuma ação nesta entrega.
