# Research — MCP Apps: card de memória

**Phase 0 do `/speckit-plan`** — 2026-07-21.

Nenhum `NEEDS CLARIFICATION` restou na Technical Context: o design aprovado
pelo fundador (`docs/superpowers/specs/2026-07-21-mcp-apps-memory-card-design.md`,
brainstorming de 2026-07-21) já resolveu as incógnitas. Este arquivo
consolida as decisões no formato do spec-kit; a autoridade é o design doc.

## D1 — Modelo de entrega da UI: MCP Apps (SEP-1865), template pré-declarado

- **Decision**: recurso `ui://dna/memory-list` registrado no servidor,
  mimeType `text/html;profile=mcp-app`, apontado na **declaração** das tools;
  dados via push (`ontoolresult`).
- **Rationale**: é a primeira extensão oficial do MCP, status **Final**,
  entra na spec de 2026-07-28 (RC travada desde maio). Hosts que renderizam
  hoje: Claude.ai web/desktop (inclusive custom connectors em planos pagos —
  o canal do DNA Cloud), ChatGPT, VS Code Insiders, Goose.
- **Alternatives considered**: o modelo pré-spec já shippado no 0.22.1
  (`_meta` no resultado, recurso não registrado, dados assados no HTML) —
  rejeitado: não renderiza em host nenhum; esta entrega o apaga. A2UI /
  `externalIframes`: fora — viram itens de board com dono (regra §3).

## D2 — Escopo: dois hosts, só leitura

- **Decision**: card renderiza no Claude.ai (custom connector) e no console
  do portal (`@ag-ui/mcp-apps-middleware`); nenhuma ação no card.
- **Rationale**: decisões 1 e 2 do fundador no brainstorming. Proveniência e
  board ficam para features próprias filadas no ato; interatividade
  ("esquecer") exige desenho de consentimento — item de board próprio.
- **Alternatives considered**: um host só (viola "entra inteiro nos dois
  hosts"); card interativo já nesta entrega (rejeitado — consentimento/HITL
  não desenhado).

## D3 — Template estático autocontido

- **Decision**: `memory_list_card_html()` vira template estático — HTML + JS
  inline com `@modelcontextprotocol/ext-apps` **bundlada no HTML**; nenhum
  CDN. JS consome `app.ontoolresult` → renderiza o `structured_content` que
  `_with_memory_card` já espelha. Empty state honesto preservado.
- **Rationale**: a CSP da spec é deny-by-default — o card precisa ser
  autocontido. Template estático e público = multi-tenant seguro por
  construção (cacheável por URI, zero dado de tenant; dados só via push da
  sessão autenticada; tudo escapado; nenhum segredo/token no HTML — nunca).
- **Alternatives considered**: dados assados no HTML (modelo pré-spec —
  vaza dado por URI cacheável e não renderiza); CDN (quebra na CSP).

## D4 — Mecanismo de declaração: FastMCP 3

- **Decision**: `app=AppConfig(resource_uri=…)` na declaração de
  `list_memories` e `recall`; floor de dependência `fastmcp>=3.2` (o
  ambiente já resolve 3.4.4). `mcp-ui-server` sai das dependências.
- **Rationale**: é o mecanismo nativo do framework para apontar o template
  na declaração da tool; `mcp-ui-server` pertence ao modelo pré-spec apagado.
- **Alternatives considered**: manter `mcp-ui-server` + `_meta` (modelo
  pré-spec, rejeitado); reimplementar a declaração à mão (desnecessário com
  FastMCP ≥3.2).

## D5 — Degradação e compatibilidade

- **Decision**: hosts sem a extensão continuam recebendo o `content` textual
  atual, **byte-idêntico**. Dados sempre no `content` primário.
- **Rationale**: zero regressão para clientes existentes (LangGraph/copilot
  incluídos) — a lição do M0.
- **Alternatives considered**: mover dados para o canal da UI (rejeitado —
  quebraria todo host sem a extensão).

## D6 — A regra §3 como gate verificável

- **Decision**: grep-guard no DoD — `TODO`, `deferred`, `follow-up`,
  `coming soon` em `mcp_ui.py`, no template e no código do middleware
  **quebra o teste**; menções existentes a futuro (A2UI, twin TS,
  "follow-up") são limpas; ideia futura vive só como item de board com dono.
- **Rationale**: o padrão "deixamos para depois" é comprovado no repo
  (`prompt_kernel.py` prometendo teste que nunca existiu; o próprio
  `mcp_ui.py` shippado inerte). Mesmo espírito do `guard:no-mock` do
  dna-cloud.
- **Alternatives considered**: disciplina por convenção/review (já falhou
  duas vezes — por isso o guard é executável).

## D7 — Sequenciamento entre repos

- **Decision**: lado SDK completo em si (Claude.ai renderiza sem nada do
  dna-cloud); lado console só mergeia com o pin do SDK novo já publicado
  (release → pin → uma entrega no dna-cloud). Nenhum lado mergeia
  "esperando" o outro.
- **Rationale**: evita merge de metade (regra §3) e segue o trem de pin já
  praticado entre os repos.
- **Alternatives considered**: mergear console apontando para SDK não
  publicado (viola a disciplina de pin e a regra §3).
