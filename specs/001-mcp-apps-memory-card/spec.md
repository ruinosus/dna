# Feature Specification: MCP Apps — card de memória (só leitura, dois hosts)

**Feature Branch**: `001-mcp-apps-memory-card`

**Created**: 2026-07-21

**Status**: Draft

**Input**: User description: "MCP Apps memory card: the memory card renders in both hosts (Claude.ai custom connector + portal console), read-only, per the approved design doc docs/superpowers/specs/2026-07-21-mcp-apps-memory-card-design.md"

> Fonte de verdade: o design aprovado pelo fundador em
> `docs/superpowers/specs/2026-07-21-mcp-apps-memory-card-design.md`
> (brainstorming de 2026-07-21). Esta spec formaliza aquele design; não o
> re-decide. Feature no board: `f-copilot-mcp-apps` (scope `dna-development`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Card de memória renderiza no Claude.ai (Priority: P1)

Um usuário do DNA Cloud conecta o MCP do DNA como custom connector no
Claude.ai (plano pago). Quando uma conversa aciona `list_memories` ou
`recall`, o host renderiza o card de memória interativo (MCP Apps /
SEP-1865) com as memórias da sessão autenticada do usuário — em vez de só o
texto. O card é **somente leitura**: nenhuma ação disponível.

**Why this priority**: é o canal onde o MCP do DNA Cloud é consumido hoje e o
critério de aceitação do fundador. O lado SDK é completo em si — o Claude.ai
renderiza sem nada do dna-cloud.

**Independent Test**: conectar o servidor MCP como custom connector no
Claude.ai e invocar `list_memories`/`recall`; o card renderiza com dados
reais. Validação final de aceitação feita pelo fundador (gate de `story done`
do lado SDK, junto do test-gate).

**Acceptance Scenarios**:

1. **Given** um host com suporte a MCP Apps e sessão autenticada, **When**
   `list_memories` ou `recall` executa, **Then** o card renderiza os dados do
   `structured_content` daquela resposta, empurrados via push
   (`ontoolresult`) — nunca assados no HTML do template.
2. **Given** o mesmo host, **When** o host lê o recurso `ui://dna/memory-list`
   (`resources/read`), **Then** recebe o template estático com o mimeType da
   spec (`text/html;profile=mcp-app`), sem nenhum dado de tenant, segredo ou
   token, e sem nenhuma URL externa (autocontido; CSP deny-by-default).
3. **Given** a declaração das tools `list_memories` e `recall`, **When** um
   host lista as tools, **Then** ambas apontam o template de UI na própria
   declaração da tool.
4. **Given** o card renderizado, **When** o usuário interage, **Then** não há
   nenhuma ação disponível (só leitura nesta entrega).

---

### User Story 2 - O mesmo card no console do portal (Priority: P2)

Um usuário do portal DNA Cloud conversa com o copiloto no `/console`. Quando
as tools de memória rodam, o MESMO card `ui://` renderiza no fluxo do chat.
O painel lateral "Memória" (React nativo) não muda — segue sendo a visão de
gestão.

**Why this priority**: é a segunda metade da regra "o que entra, entra
inteiro nos dois hosts". Sequenciada após o lado SDK porque só mergeia com o
pin do SDK novo já publicado (release → pin → uma entrega no dna-cloud);
nenhum dos dois lados mergeia "esperando" o outro.

**Independent Test**: teste de que o middleware de MCP Apps está no pipeline
do runtime do copiloto e o card do fixture renderiza (na medida do testável
em node); validação visual declarada como gate de deploy.

**Acceptance Scenarios**:

1. **Given** o console do portal com o pin do SDK novo publicado, **When**
   uma tool de memória roda no chat, **Then** o mesmo card `ui://` renderiza
   no fluxo do chat.
2. **Given** a entrega do lado console, **When** ela é avaliada para merge,
   **Then** só mergeia com o pin do SDK novo já publicado; se exigir bump de
   framework que não caiba, a feature fica `in-progress` — não mergeia metade.
3. **Given** o painel lateral "Memória", **When** esta feature entra,
   **Then** o painel permanece inalterado.

---

### User Story 3 - Degradação limpa em hosts sem MCP Apps (Priority: P3)

Um cliente MCP sem suporte à extensão (LangGraph/copilot atuais incluídos)
invoca as tools de memória e continua recebendo exatamente o `content`
textual de hoje — byte-idêntico. Zero regressão para clientes existentes
(a lição do M0: dados sempre no `content` primário).

**Why this priority**: é rede de segurança, não valor novo — mas é requisito
inegociável do design (zero regressão).

**Independent Test**: comparação byte a byte do `content` textual das
respostas de `list_memories`/`recall` antes/depois da entrega, num cliente
sem a extensão.

**Acceptance Scenarios**:

1. **Given** um host sem MCP Apps, **When** as tools de memória executam,
   **Then** a resposta textual (`content`) é byte-idêntica à atual.
2. **Given** um host onde o template é ilegível, **When** a tool executa,
   **Then** o host ignora a UI e o `content` segue valendo.

---

### Edge Cases

- `structured_content` vazio → empty state do card ("nenhuma memória") — o
  mesmo honesto de hoje; nada inventado.
- Campo ausente no `structured_content` → renderiza vazio-honesto, nunca
  inventado (o template define o contrato de renderização).
- ChatGPT (sem tool-calling da UI) → irrelevante nesta entrega — o card é só
  leitura.
- Template ilegível no host → o host ignora a UI; `content` segue valendo.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O template do card de memória DEVE ser estático e autocontido:
  HTML + JS inline com a lib de MCP Apps bundlada no HTML; nenhum CDN /
  nenhuma URL externa (CSP da spec é deny-by-default). Público e cacheável
  por URI: zero dado de tenant, zero segredo/token no HTML — nunca.
- **FR-002**: O servidor DEVE registrar o recurso `ui://dna/memory-list` e
  respondê-lo via `resources/read` com mimeType `text/html;profile=mcp-app`.
- **FR-003**: As tools `list_memories` e `recall` DEVEM apontar o template na
  própria declaração da tool.
- **FR-004**: O card DEVE renderizar o `structured_content` existente das
  tools de memória (sem mudança de shape), recebido via push da sessão
  autenticada (`ontoolresult`); campo ausente renderiza vazio-honesto, nunca
  inventado; `structured_content` vazio renderiza o empty state honesto
  ("nenhuma memória").
- **FR-005**: O card DEVE ser somente leitura nesta entrega — nenhuma ação.
- **FR-006**: Hosts sem a extensão DEVEM continuar recebendo o `content`
  textual atual, byte-idêntico. Zero regressão para clientes existentes.
- **FR-007**: O MESMO card `ui://` DEVE renderizar no chat do `/console` do
  portal quando as tools de memória rodam; o painel lateral "Memória" não
  muda.
- **FR-008**: Sequenciamento entre repos: o lado console só mergeia com o pin
  do SDK novo já publicado; nenhum lado mergeia "esperando" o outro — o lado
  SDK é completo em si.

### Non-Functional Requirements

- **NFR-001 — A regra "nada shippa meio-referenciado"** (§3 do design,
  requisito literal):
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

### Key Entities

- **Template do card de memória**: recurso `ui://dna/memory-list` — HTML
  estático, público, autocontido; define o contrato de renderização (os
  campos que exibe).
- **`structured_content` das tools de memória**: os dados reais, por sessão
  autenticada, no shape existente (sem mudança); espelhados no resultado da
  tool e empurrados ao card via push.
- **Declaração das tools `list_memories` / `recall`**: carrega o ponteiro
  para o template de UI.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O card renderiza com dados reais num custom connector do
  Claude.ai — validado pelo fundador (critério de `story done` do lado SDK,
  junto do test-gate).
- **SC-002**: O mesmo card renderiza no chat do `/console` do portal
  (validação visual como gate de deploy).
- **SC-003**: Clientes sem a extensão recebem `content` textual byte-idêntico
  ao atual — zero regressão (LangGraph/copilot incluídos).
- **SC-004**: O grep-guard da regra §3 passa com zero ocorrências na
  superfície entregue; um TODO plantado quebra o teste (mutação → morre).
- **SC-005**: O card renderiza de verdade no `basic-host` do `ext-apps`
  (smoke, sem host comercial).

## Assumptions

- MCP Apps (SEP-1865) tem status Final e entra na spec de 2026-07-28 (RC
  travada desde maio); hosts que renderizam hoje: Claude.ai web/desktop
  (inclusive custom connectors em planos pagos), ChatGPT, VS Code Insiders,
  Goose.
- O groundwork do DNA 0.22.1 (`dna/emit/mcp_ui.py`: card byte-golden;
  `_with_memory_card` no servidor) existe mas segue o modelo pré-spec e não
  renderiza em host nenhum; esta entrega o completa e apaga o padrão
  "deixamos para depois" que o gerou.
- Floor de dependência do lado SDK: `fastmcp>=3.2` (o ambiente já resolve
  3.4.4).
- Lado console: `@ag-ui/mcp-apps-middleware`, com CopilotKit ^1.63 já
  compatível.
- Proveniência e board ficam para features próprias, filadas no board no ato
  deste spec (itens já registrados no design: card interativo "esquecer" com
  desenho de consentimento; painel de proveniência como MCP App; watch de
  `externalIframes` / tool-calling da UI no ChatGPT).
- Fora deste documento: nada. O que não está aqui não existe nesta entrega —
  e não está mencionado em lugar nenhum do código entregue.
