# Implementation Plan: MCP Apps — card de memória (só leitura, dois hosts)

**Branch**: `feat/mcp-apps-memory-card` (spec dir `001-mcp-apps-memory-card`) | **Date**: 2026-07-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-mcp-apps-memory-card/spec.md` — que formaliza o design aprovado em `docs/superpowers/specs/2026-07-21-mcp-apps-memory-card-design.md` (autoridade).

## Summary

Completar o groundwork inerte do DNA 0.22.1 (`dna/emit/mcp_ui.py` +
`_with_memory_card`) para o modelo final de MCP Apps (SEP-1865): template
estático autocontido registrado como recurso `ui://dna/memory-list`
(`text/html;profile=mcp-app`), apontado na declaração de `list_memories` /
`recall` via FastMCP 3, dados via push (`ontoolresult`) da sessão
autenticada. Card só leitura, renderizando nos dois hosts — Claude.ai
(custom connector) e console do portal (`@ag-ui/mcp-apps-middleware` no
dna-cloud, trem de pin próprio). A regra §3 ("nada shippa meio-referenciado")
entra como requisito: apagar o padrão pré-spec e suas menções a futuro,
remover `mcp-ui-server`, e um grep-guard que quebra o teste.

## Technical Context

**Language/Version**: Python 3.12 (lado SDK: `packages/sdk-py` + `packages/cli`); TypeScript/Node (lado console, repo `ruinosus/dna-cloud`)

**Primary Dependencies**: `fastmcp>=3.2` (floor novo; ambiente resolve 3.4.4; hoje o pin é `>=2` — bump necessário), lib `@modelcontextprotocol/ext-apps` **bundlada no HTML** (nenhum CDN); lado console: `@ag-ui/mcp-apps-middleware` (CopilotKit ^1.63 já compatível). **Sai**: `mcp-ui-server` (extras `mcp` e dev de `packages/cli/pyproject.toml`)

**Storage**: N/A — nenhuma mudança de shape; o card renderiza o `structured_content` existente

**Testing**: pytest (golden byte-stable já existe em `packages/sdk-py/tests/goldens/mcp_ui/`; `packages/cli/tests/test_mcp_apps.py` refeito para o modelo final); smoke com o `basic-host` do `ext-apps`; grep-guard §3; lado console: teste node do pipeline do middleware

**Target Platform**: servidor MCP do DNA (stdio+HTTP) consumido por Claude.ai web/desktop (custom connector) e pelo copiloto do portal; hosts sem MCP Apps degradam para `content` textual byte-idêntico

**Project Type**: biblioteca + servidor MCP (monorepo `packages/{sdk-py,cli}`) com entrega irmã sequenciada no repo `dna-cloud`

**Performance Goals**: N/A nesta entrega (card só leitura; template estático cacheável por URI)

**Constraints**: CSP da spec deny-by-default → template 100% autocontido, zero URL externa; zero dado de tenant / segredo / token no HTML; zero regressão para clientes sem a extensão (byte-idêntico); console só mergeia com o pin do SDK novo publicado

**Scale/Scope**: 2 tools (`list_memories`, `recall`), 1 recurso `ui://`, 1 template; escopo fechado — "Fora deste documento: nada"

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` é o template não-ratificado do spec-kit
(nenhuma constituição de projeto foi estabelecida neste repo). Gate
vacuosamente aprovado. Os princípios operantes vêm do design doc (autoridade)
— em particular a regra §3, tratada como gate verificável (grep-guard) no DoD
— e das disciplinas já vigentes no repo (golden byte-stable, testes de
mutação "→ morre").

**Re-check pós-Phase 1**: sem violações; nenhuma entrada em Complexity
Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/001-mcp-apps-memory-card/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── mcp-surface.md   # Contrato da superfície MCP (recurso + declaração + degradação)
├── checklists/
│   └── requirements.md  # Spec quality checklist (/speckit-specify)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
# Lado SDK — ESTE repo (ruinosus/dna)
packages/sdk-py/
├── dna/emit/mcp_ui.py                  # template estático (ext-apps bundlado, JS ontoolresult);
│                                       #   limpeza §3: some toda menção a futuro/deferred/A2UI/twin
└── tests/
    ├── test_emit_mcp_ui.py             # golden byte-stable (mantido; conteúdo novo) + guard §3
    └── goldens/mcp_ui/                 # goldens regravados para o template estático

packages/cli/
├── dna_cli/_mcp_server.py              # registro @mcp.resource ui://dna/memory-list;
│                                       #   AppConfig(resource_uri=…) na declaração de
│                                       #   list_memories/recall; _with_memory_card sem _meta pré-spec
├── pyproject.toml                      # fastmcp>=3.2; mcp-ui-server REMOVIDO (extras mcp + dev)
└── tests/test_mcp_apps.py              # declaração carrega resourceUri; resources/read responde
                                        #   mimeType da spec; HTML sem dados/sem URL externa; grep-guard

# Lado console — repo IRMÃO (ruinosus/dna-cloud), entrega própria no trem de pin
#   runtime do copiloto + @ag-ui/mcp-apps-middleware; painel lateral "Memória" intacto
```

**Structure Decision**: monorepo existente do DNA; a feature toca as duas
superfícies já donas do groundwork (`dna/emit/mcp_ui.py` no sdk-py, servidor
MCP no cli). O lado console vive no repo `dna-cloud` e é sequenciado por pin
(release do SDK → bump do pin → entrega no dna-cloud); nenhum código do
console entra neste repo.

## Complexity Tracking

Sem violações a justificar — tabela vazia por decisão, não por omissão.
