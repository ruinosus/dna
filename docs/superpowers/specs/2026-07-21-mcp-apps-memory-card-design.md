# MCP Apps: o card de memória — design

- **Data**: 2026-07-21
- **Status**: aprovado pelo fundador (brainstorming desta data)
- **Feature no board**: `f-copilot-mcp-apps` (scope `dna-development`)
- **Próximo passo do fluxo**: `/speckit.specify` formaliza este design → plan → tasks → `dna specify import`

## Contexto

MCP Apps (SEP-1865) é a primeira extensão oficial do MCP — UI interativa
renderizada pelo host em iframe sandboxed, com template HTML pré-declarado em
recurso `ui://` e dados via push (`ontoolresult`). Status **Final**; entra na
spec de 2026-07-28 (RC travada desde maio). Hosts que renderizam hoje:
Claude.ai web/desktop (inclusive **custom connectors em planos pagos** — o
canal onde o MCP do DNA Cloud é consumido), ChatGPT, VS Code Insiders, Goose.
Host sem suporte lê só o `content` textual — degradação limpa.

O DNA 0.22.1 tem groundwork (`dna/emit/mcp_ui.py`: card de memória
byte-golden; `_with_memory_card` no servidor) que **não renderiza em host
nenhum**: segue o modelo pré-spec (`_meta` no resultado, recurso não
registrado, dados assados no HTML). Este design o completa — e apaga o padrão
"deixamos para depois" que o gerou.

## Decisões do fundador (registradas no brainstorming)

1. **Escopo**: card de memória renderizando **nos dois hosts** — Claude.ai
   (custom connector) e console do portal (via `@ag-ui/mcp-apps-middleware`,
   CopilotKit ^1.63 já compatível). Proveniência e board ficam para features
   próprias, **filadas no board no ato deste spec** (ver §Regra).
2. **Interação**: **só leitura** nesta entrega. Nenhuma ação no card.
3. **A regra "nada shippa meio-referenciado"** (motivada pelo padrão
   comprovado hoje: `prompt_kernel.py` prometendo teste que nunca existiu; o
   próprio `mcp_ui.py` shippado inerte à espera de follow-up):
   - O que entra, entra **inteiro nos dois hosts**. Se o lado console exigir
     bump de framework que não caiba, a feature fica `in-progress` — não
     mergeia metade.
   - O que não entra **não deixa rastro**: zero menção a "esquecer", A2UI,
     `externalIframes`, "follow-up" em código, docstring ou doc — inclusive
     **limpando as menções que já existem** em `mcp_ui.py`. `mcp-ui-server`
     sai das dependências.
   - Ideia futura vive num único lugar: **item de board com dono**, filado
     junto deste spec.
   - **Guard verificável no DoD**: grep na superfície entregue — `TODO`,
     `deferred`, `follow-up`, `coming soon` em `mcp_ui.py`, no template e no
     código do middleware **quebra o teste** (mesmo espírito do
     `guard:no-mock` do dna-cloud).

## Arquitetura

### Lado SDK (`ruinosus/dna`)

- **Template**: `memory_list_card_html()` vira template **estático** — HTML +
  JS inline (a lib `@modelcontextprotocol/ext-apps` **bundlada no HTML**;
  nenhum CDN — a CSP da spec é deny-by-default e o card fica autocontido).
  O JS consome `app.ontoolresult` → renderiza o `structured_content` que
  `_with_memory_card` já espelha hoje. Empty state honesto preservado.
- **Registro**: recurso `ui://dna/memory-list` registrado no servidor
  (`@mcp.resource`), mimeType `text/html;profile=mcp-app`.
- **Declaração**: `list_memories` e `recall` apontam o template **na
  declaração da tool** via FastMCP 3 (`app=AppConfig(resource_uri=…)`).
  Floor de dependência: `fastmcp>=3.2` (o ambiente já resolve 3.4.4).
- **Multi-tenant seguro por construção**: o template é estático e público
  (cacheável por URI, zero dado de tenant); dados só via push da sessão
  autenticada; tudo escapado (já é). Nenhum segredo/token no HTML — nunca.
- **Degradação**: hosts sem a extensão continuam recebendo o `content`
  textual atual, byte-idêntico. Zero regressão para clientes existentes
  (LangGraph/copilot incluídos — a lição do M0: dados sempre no `content`
  primário).

### Lado console (`ruinosus/dna-cloud`)

- `@ag-ui/mcp-apps-middleware` no runtime do copiloto: o MESMO card `ui://`
  renderiza no chat do `/console` quando as tools de memória rodam.
- O painel lateral "Memória" (React nativo) **não muda** — o card aparece no
  fluxo do chat; o painel segue sendo a visão de gestão.
- Sequenciamento entre repos: o lado console só mergeia com o pin do SDK novo
  já publicado (release → pin → uma entrega no dna-cloud). Nenhum dos dois
  lados mergeia "esperando" o outro — o do SDK é completo em si (Claude.ai
  renderiza sem nada do dna-cloud), o do console entra no mesmo trem de pin.

## Dados

Sem mudança de shape: o card renderiza o `structured_content` existente das
tools de memória. O template define o contrato de renderização (campos que
exibe); campo ausente renderiza vazio-honesto, nunca inventado.

## Erros e degradação

| Situação | Comportamento |
|---|---|
| Host sem MCP Apps | `content` textual de hoje, byte-idêntico |
| Template ilegível no host | o host ignora a UI; `content` segue valendo |
| `structured_content` vazio | empty state do card ("nenhuma memória") — o mesmo honesto de hoje |
| ChatGPT (sem tool-calling da UI) | irrelevante nesta entrega — card é só leitura |

## Testes e verificação

- Golden byte-stable do template (já existe; muda o conteúdo, mantém a
  disciplina).
- Teste: a **declaração** de `list_memories`/`recall` carrega o
  `resourceUri` (mutação: pointer removido → morre).
- Teste: o recurso `ui://dna/memory-list` responde via `resources/read` com o
  mimeType da spec (mutação: registro removido → morre).
- Teste: o HTML do template **não contém dados de memória** (mutação: dados
  assados de volta → morre) e **não contém URL externa** (CDN de volta →
  morre).
- **Grep-guard da regra §3** na superfície entregue (mutação: um TODO
  plantado → morre).
- Smoke com o `basic-host` do `ext-apps` (render de verdade, sem host
  comercial).
- Console: teste de que o middleware está no pipeline e o card do fixture
  renderiza (na medida do testável em node; validação visual declarada como
  gate de deploy).
- **Validação final de aceitação**: custom connector no Claude.ai (fundador),
  card renderizando com dados reais — é o critério de `story done` do lado
  SDK, junto do test-gate.

## Itens de board filados junto deste spec (a regra §3 em ação)

1. Card interativo — ação "esquecer" com desenho de consentimento
   (host-consent + o análogo do HITL). Depende desta entrega.
2. Painel de proveniência (`compose_prompt(explain=true)`) como MCP App.
   Depende desta entrega.
3. Watch: `externalIframes` (embutir rota do portal) e tool-calling da UI no
   ChatGPT — reavaliar quando os hosts moverem.

## Fora deste documento

Nada. O que não está aqui não existe nesta entrega — e não está mencionado em
lugar nenhum do código entregue.
