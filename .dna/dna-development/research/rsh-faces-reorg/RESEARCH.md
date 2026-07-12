---
apiVersion: github.com/ruinosus/dna/sdlc/v1
kind: Research
metadata:
  name: rsh-faces-reorg
spec:
  title: Reorg das faces DNA (CLI/MCP/REST) — hexagonal, onde vive a camada de aplicação
  status: published
  objective: Decidir como reorganizar as 3 faces do DNA (CLI + MCP server + REST API) hoje empacotadas
    juntas em packages/cli, com a camada _impl compartilhada enterrada ali. Onde vive a application layer?
    Faces = módulos ou pacotes separados? Qual a migração incremental sem big-bang? Suporta o sp-faces-reorg.
  methodology: web-search-curated
  executive_summary: |
    A evidência converge limpa num veredito hexagonal (ports-and-adapters): a camada
    de aplicação/casos-de-uso transport-agnostic do DNA (os *_impl) DEVE viver no CORE
    (dependendo de nada externo), e CLI, MCP e REST viram adapters de ENTRADA finos que
    só traduzem o transporte (argv, payloads HTTP, JSON-RPC do MCP) e delegam pro core —
    nunca guardam lógica de negócio. Uma única porta pode servir as 3 faces ao mesmo
    tempo; adicionar uma face nova é plugar um adapter, sem tocar o core. Sobre
    empacotamento, a convenção real mais forte (Stainless, MCP Python SDK) é CO-LOCALIZAR
    a face-servidor com o core/SDK mas SHIPAR como distribuição SEPARADA versionada em
    lockstep — porque extras do Python só gateiam DEPENDÊNCIAS opcionais, não código, e o
    stack MCP/FastMCP (starlette+uvicorn) é pesado demais pra arrastar num `pip install
    dna-cli` puro (o próprio MCP Python SDK traz starlette/uvicorn como deps CORE). Pra
    ACA scale-to-zero: 1 processo uvicorn por container, replicação a cargo do orquestrador.
    O MOVIMENTO Nº1 é extrair a application layer PRA FORA da CLI pro core — esse é o
    refactor que sustenta tudo; separar os adapters em distribuições é follow-up mecânico
    que fica seguro depois que o core compartilhado existe. 22 de 25 claims confirmados
    (3 refutados na verificação adversarial).
  findings:
  - id: f-app-layer-in-core
    title: A camada _impl (casos de uso, transport-agnostic) pertence ao CORE, não à CLI — hexagonal põe
      domínio+aplicação no centro; CLI/REST/MCP são driving adapters
    evidence_rating: evidence-based
  - id: f-one-port-many-faces
    title: Uma porta tecnologia-agnóstica serve as 3 faces (CLI+REST+MCP) ao mesmo tempo; face nova =
      adapter novo, sem mexer no core (se reusa os casos de uso existentes)
    evidence_rating: evidence-based
  - id: f-thin-adapters
    title: 'Cada face é adapter FINO: traduz transporte + validação sintática/auth na borda (o auth/quota
      do MCP fica no adapter), mas a lógica de negócio fica no core'
    evidence_rating: evidence-based
  - id: f-separate-distributions
    title: 'Convenção 2025-26 (Stainless): co-localizar o servidor com o SDK mas SHIPAR como distribuição
      separada (dna-mcp/dna-api) versionada em lockstep — não enterrar na CLI'
    evidence_rating: evidence-based
  - id: f-extras-gate-deps-only
    title: Extras do Python (pip install pkg[mcp]) gateiam só DEPENDÊNCIAS, não código — não excluem o
      subpacote do wheel; face pesada opcional exige distribuição separada
    evidence_rating: evidence-based
  - id: f-mcp-sdk-pulls-server-stack
    title: O MCP Python SDK traz starlette+uvicorn+sse-starlette+httpx como deps CORE — MCP na CLI arrasta
      o stack ASGI inteiro pra todo `pip install dna-cli`
    evidence_rating: evidence-based
  - id: f-single-uvicorn-aca
    title: 'Pra ACA scale-to-zero: 1 processo uvicorn por container (dna mcp/api serve), replicação pelo
      orquestrador — não workers uvicorn in-process'
    evidence_rating: evidence-based
  recommendations:
  - id: rec-extract-app-layer
    priority: high
    summary: 'MOVIMENTO Nº1 (load-bearing): extrair a application layer / os *_impl PRA FORA de packages/cli
      pro core (um módulo dna application/service transport-agnostic). Todo o resto depende disso existir.
      É o refactor que sustenta a reorg.'
  - id: rec-thin-adapters
    priority: high
    summary: CLI, MCP e REST viram adapters finos que só traduzem transporte + validação de borda (auth/quota
      do MCP na borda) e delegam pro core. Zero lógica de negócio nas faces.
  - id: rec-separate-distributions
    priority: medium
    summary: Shipar dna-mcp + dna-api como distribuições SEPARADAS, co-localizadas no monorepo, versionadas
      em lockstep com o SDK — mantém `dna-cli`/`dna-sdk` puros leves (sem arrastar uvicorn/starlette).
      Extras não resolvem (só gateiam deps, não código).
  - id: rec-shim-entrypoints
    priority: medium
    summary: 'Migração incremental, sem big-bang: extrai o core primeiro, depois split das faces, com
      shims mantendo `dna mcp serve` / `dna api serve` funcionando o tempo todo.'
  - id: rec-single-uvicorn
    priority: low
    summary: 'Deploy ACA: 1 uvicorn por container por face; replicação a cargo do ACA (scale-to-zero).'
  created_at: '2026-07-12T16:53:50+00:00'
  updated_at: '2026-07-12T16:53:50+00:00'
---

# Research — Reorg das faces DNA (CLI/MCP/REST) — hexagonal, onde vive a camada de aplicação

Methodology: web-search-curated · 0 sources · 7 findings.

This file's spec (frontmatter above) is the authoritative data. The prose below is for human reading and is regenerated on each write. Edit via `dna research` CLI or the Studio viewer; raw frontmatter edits are also supported.
