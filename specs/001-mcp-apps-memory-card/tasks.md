# Tasks: MCP Apps — card de memória (só leitura, dois hosts)

**Input**: Design documents from `/specs/001-mcp-apps-memory-card/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/mcp-surface.md, quickstart.md

**Tests**: INCLUÍDOS — o design fixa o test-gate explicitamente (§Testes e
verificação), com disciplina de mutação ("mutação → morre"). Testes primeiro,
falhando, antes da implementação.

**Organization**: Tasks agrupadas por user story. US1 (lado SDK) é o MVP e é
completa em si; US2 (console) vive no repo irmão `ruinosus/dna-cloud` e só
mergeia com o pin do SDK novo publicado; US3 (degradação) trava o
byte-idêntico.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: dependências no estado que o design fixa

- [ ] T001 Subir o floor `fastmcp>=3.2` e **remover** `mcp-ui-server` dos extras `mcp` e dev em `packages/cli/pyproject.toml` (incluindo os comentários que o citam — regra §3)
- [ ] T002 [P] Vendorizar a lib `@modelcontextprotocol/ext-apps` como asset embutível (para bundle inline no HTML; nenhum CDN) em `packages/sdk-py/dna/emit/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: apagar o modelo pré-spec e travar a baseline de degradação — bloqueia todas as stories

**⚠️ CRITICAL**: nenhuma story começa antes desta fase fechar

- [ ] T003 Limpeza §3 em `packages/sdk-py/dna/emit/mcp_ui.py`: remover TODA menção a futuro — A2UI/"deferred", twin TS "follow-up", `externalUrl`/`rawHtml` do modelo pré-spec — em código, docstring e comentário (ideia futura já vive nos itens de board i-060/i-061/i-062)
- [ ] T004 Remover o wiring pré-spec (`_meta` de UI) de `_with_memory_card` em `packages/cli/dna_cli/_mcp_server.py`, preservando `content` textual e `structured_content` intactos
- [ ] T005 Capturar a baseline byte a byte do `content` textual de `list_memories`/`recall` como fixture em `packages/cli/tests/test_mcp_apps.py` (pré-requisito do gate de zero regressão)

**Checkpoint**: superfície sem rastro do modelo pré-spec; baseline travada

---

## Phase 3: User Story 1 — Card de memória renderiza no Claude.ai (Priority: P1) 🎯 MVP

**Goal**: template estático `ui://dna/memory-list` registrado, apontado na declaração de `list_memories`/`recall`, dados via push; lado SDK completo em si.

**Independent Test**: custom connector no Claude.ai renderiza o card com dados reais (aceitação do fundador) + test-gate verde + smoke no `basic-host`.

### Tests for User Story 1 (escrever primeiro; devem FALHAR antes da implementação)

- [ ] T006 [P] [US1] Teste: a declaração de `list_memories` e `recall` carrega o `resourceUri` do template (mutação: pointer removido → morre) em `packages/cli/tests/test_mcp_apps.py`
- [ ] T007 [P] [US1] Teste: `resources/read` de `ui://dna/memory-list` responde com mimeType `text/html;profile=mcp-app` (mutação: registro removido → morre) em `packages/cli/tests/test_mcp_apps.py`
- [ ] T008 [P] [US1] Teste: o HTML do template não contém dados de memória (mutação: dados assados de volta → morre) nem URL externa (mutação: CDN de volta → morre) em `packages/sdk-py/tests/test_emit_mcp_ui.py`
- [ ] T009 [P] [US1] Grep-guard §3: `TODO`/`deferred`/`follow-up`/`coming soon` em `mcp_ui.py` e no template quebra o teste (mutação: TODO plantado → morre) em `packages/sdk-py/tests/test_emit_mcp_ui.py`

### Implementation for User Story 1

- [ ] T010 [US1] Reescrever `memory_list_card_html()` como template ESTÁTICO em `packages/sdk-py/dna/emit/mcp_ui.py`: HTML + JS inline (ext-apps bundlada de T002), JS consome `app.ontoolresult` → renderiza `structured_content`; empty state honesto ("nenhuma memória"); campo ausente → vazio-honesto; tudo escapado; zero dado de tenant/segredo/token
- [ ] T011 [US1] Regravar os goldens byte-stable em `packages/sdk-py/tests/goldens/mcp_ui/` (conteúdo novo, disciplina mantida)
- [ ] T012 [US1] Registrar o recurso `ui://dna/memory-list` (`@mcp.resource`, mimeType `text/html;profile=mcp-app`) em `packages/cli/dna_cli/_mcp_server.py`
- [ ] T013 [US1] Apontar o template na declaração de `list_memories` e `recall` via FastMCP 3 (`app=AppConfig(resource_uri=…)`) em `packages/cli/dna_cli/_mcp_server.py`
- [ ] T014 [US1] Smoke de render real com o `basic-host` do `ext-apps` (card renderiza; empty state com zero memórias) — roteiro em `specs/001-mcp-apps-memory-card/quickstart.md` §3
- [ ] T015 [US1] Aceitação final: custom connector no Claude.ai (fundador), card com dados reais e nenhuma ação disponível — gate de `story done` do lado SDK, junto do test-gate

**Checkpoint**: lado SDK completo em si — Claude.ai renderiza sem nada do dna-cloud

---

## Phase 4: User Story 2 — O mesmo card no console do portal (Priority: P2)

**Goal**: o MESMO card `ui://` renderiza no chat do `/console`; painel lateral "Memória" intacto.

**Independent Test**: teste node do middleware no pipeline + card do fixture renderiza; validação visual como gate de deploy.

**⚠️ Sequenciamento**: tasks T017–T019 vivem no repo irmão `ruinosus/dna-cloud` e só mergeiam com o pin do SDK novo publicado (T016). Nenhum lado mergeia "esperando" o outro; se exigir bump de framework que não caiba, a feature fica `in-progress` — não mergeia metade (regra §3).

- [ ] T016 [US2] Release do SDK com US1 (tag `vX.Y.Z` → publica `dna-sdk`/`dna-cli` no PyPI) — pré-requisito do trem de pin (repo `ruinosus/dna`)
- [ ] T017 [US2] dna-cloud: adicionar `@ag-ui/mcp-apps-middleware` ao runtime do copiloto (CopilotKit ^1.63 já compatível) — repo `ruinosus/dna-cloud`
- [ ] T018 [US2] dna-cloud: teste node — middleware no pipeline + card do fixture renderiza; grep-guard §3 no código do middleware — repo `ruinosus/dna-cloud`
- [ ] T019 [US2] dna-cloud: bump do pin do SDK + validação visual no `/console` como gate de deploy; painel lateral "Memória" permanece inalterado — repo `ruinosus/dna-cloud`

**Checkpoint**: card renderizando nos DOIS hosts — a regra "entra inteiro" satisfeita

---

## Phase 5: User Story 3 — Degradação limpa em hosts sem MCP Apps (Priority: P3)

**Goal**: zero regressão — `content` textual byte-idêntico para todo cliente sem a extensão (LangGraph/copilot incluídos).

**Independent Test**: comparação byte a byte contra a baseline de T005.

- [ ] T020 [US3] Teste: `content` textual de `list_memories`/`recall` byte-idêntico à baseline de T005 num cliente sem a extensão, em `packages/cli/tests/test_mcp_apps.py`

**Checkpoint**: contrato de degradação travado por teste

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T021 Rodar a validação completa de `specs/001-mcp-apps-memory-card/quickstart.md` (test-gate + degradação + smoke)
- [ ] T022 [P] Entrada de CHANGELOG.md do lado SDK (sem nenhuma menção a trabalho futuro — regra §3; futuro vive em i-060/i-061/i-062)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências
- **Foundational (Phase 2)**: depende do Setup — BLOQUEIA todas as stories
- **US1 (Phase 3)**: depende da Phase 2 — MVP, completa em si
- **US2 (Phase 4)**: depende de US1 released (T016) — trem de pin, repo irmão
- **US3 (Phase 5)**: depende da Phase 2 (baseline T005); validável junto de US1
- **Polish (Phase 6)**: depende das stories desejadas completas

### Parallel Opportunities

- T001 ∥ T002 (arquivos diferentes)
- T006–T009 em paralelo (testes primeiro, arquivos/casos independentes)
- US3 (T020) pode andar em paralelo com US1 assim que T005 exista
- T017–T018 (dna-cloud) podem andar em paralelo após T016

## Implementation Strategy

**MVP = US1** (lado SDK): Setup → Foundational → US1 → validar
independentemente (test-gate + basic-host + aceitação do fundador). US3
trava a rede de segurança no mesmo trem. US2 entra no trem de pin do
dna-cloud com release publicado — incremental, sem quebrar o que já entrou,
e sem nenhum merge de metade.
