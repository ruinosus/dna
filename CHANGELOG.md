# Changelog

All notable changes to DNA are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Pre-1.0 notice.** DNA has not yet reached 1.0. Until then the public API
> may change between releases without a major-version bump; SemVer guarantees
> apply from 1.0.0 onward.

## [Unreleased]

## [0.23.0] — 2026-07-21

O workspace nasce herdando. Minor novo: a faixa interna vira
`dna-sdk>=0.23,<0.24`.


### ✨ Composição

- **Herança de definições por workspace-scope — a tese do overlay ganha o
  "resto para herdar"** (i-058). Um workspace Model B roteia para o scope
  `tenant-ws-<id>`, que nascia VAZIO e inalcançável por qualquer seed de boot
  (workspaces nascem depois do boot): o AgentBrowser do workspace novo vinha
  vazio e o compose caía no fallback mesmo com o scope base semeado. A cadeia
  transitiva de `Genome.spec.parent_scope` (`compute_resolution_chain`) já era
  honrada por `kernel.query` e `resolve_document`, mas NÃO pelos dois leitores
  que as superfícies de produto realmente usam — a materialização EAGER do
  ManifestInstance (que serve `list_agents` e `compose_prompt`) e o
  `kernel.get_document` (`get_skill`/`get_template`), ambos presos ao salto
  fixo V1 para `_lib`. Agora os quatro leitores andam a MESMA cadeia — um
  mecanismo, todos os consumidores: local vence por `(kind, name)`, parent
  mais próximo sombreia o mais distante, e o caso sem parent declarado é
  byte-idêntico ao comportamento anterior (a cadeia termina em `_lib` pelo
  fallback V1; golden + timing provaram ~igual no caso comum). Kinds de
  memória/board (`scope_inheritable=false`) continuam estruturalmente fora da
  herança — o base é conteúdo curado, nunca estado compartilhado — e a
  fronteira de staleness do cache de MI ficou documentada no builder e pinada
  por teste (um write no parent é visto imediatamente pelos builds
  por-request; um MI base já cacheado do filho não é derrubado — o mesmo
  contorno que writes em `_lib` sempre tiveram).
- **O scope do workspace nasce declarando o parent — e os existentes adotam
  no próximo sign-in** (i-058, a metade de aplicação). Com
  `DNA_WORKSPACE_DEFINITIONS_BASE` setado (novo env, lido em `boot_live` →
  `LiveDna.workspace_definitions_base`), `create_workspace_impl` escreve o
  Genome do scope `tenant-<id>` com `parent_scope` apontando para o base
  curado do host — entre o doc `Workspace` e o grant de owner, com
  compensação nas falhas — e `provision_workspace_owner_impl` (chamado a cada
  sign-in do portal) faz a ADOÇÃO idempotente dos workspaces nascidos antes
  do env existir: zero passos operacionais. Intent-preserving: um
  `parent_scope` autorado por operador nunca é sobrescrito, e o scope do
  vendor (que É o base do host) nunca é tocado. Sem o env (OSS/self-host),
  nada é escrito — comportamento estruturalmente idêntico ao de hoje. O
  dna-cloud liga com `DNA_WORKSPACE_DEFINITIONS_BASE=dna-development` nos
  containers `mcp`/`api`.

## [0.22.1] — 2026-07-21

Patch de cobrança honesta. A faixa interna NÃO muda: 0.22.1 é patch dentro
do mesmo minor (`dna-sdk>=0.22,<0.23` segue).


### ✨ Quota

- **`DNA_QUOTA_REQUIRE_TIERS=1` — fail-closed opt-in quando o registry de
  Tiers está vazio ou ilegível** (i-051). Caps vazios são AMBÍGUOS: num
  self-host OSS significam "nunca optou pelo pricing do DNA Cloud — não
  enforce nada" (a regra dura do open-core, default intocado); num deploy
  hosted cujo seed de Tiers falhou no boot significam "todos os caps
  evaporaram em silêncio" — fail-open exatamente onde o dinheiro exige
  fail-closed. O SDK não tem como distinguir as duas formas, então o HOST
  declara: com a flag ligada, registry vazio/ilegível vira `ToolError`
  explícito no guard ("tier registry empty/unreadable — … refusing") e o
  `except` fail-soft do `RegistryAccessor.tier()` PROPAGA em vez de degradar
  para `None` (defesa em profundidade: cada camada é testada por mutação em
  separado). A flag só é consultada no ramo COM token — o caminho
  stdio/local retorna antes, então o self-host continua estruturalmente fora
  do alcance dela. O dna-cloud liga a flag no container `mcp`; um self-host
  nunca precisa saber que ela existe.

### 🐛 Corrigido

- **Chamada negada não conta — e portanto nunca fatura** (i-050). O
  `enforce_quota` incrementava o contador diário ANTES de negar: acima do cap
  a chamada era negada (429) E somada em `dna_quota_counters` — exatamente a
  soma que o job de overage do dna-cloud lê (`SUM(calls) − included`). Ou
  seja, dava para cobrar overage por chamadas que o cliente nunca conseguiu
  executar. O incremento agora é condicional e atômico
  (`QuotaStore.try_incr_day`): no Postgres o cap viaja DENTRO do mesmo
  `INSERT … ON CONFLICT DO UPDATE` que já matava a corrida do
  read-modify-write, como `WHERE calls < :cap` — avaliado sob o row lock,
  então 512 tentativas concorrentes contra um cap de 100 admitem exatamente
  100 (provado com o mesmo hammer de 64×8 threads que protege o `incr_day`).
  O contador nunca passa do cap, o job de overage não tem excedente fantasma,
  e `calls_per_day` volta a significar o que o plano vende: um hard cap. O
  primitivo incondicional (`incr_day`) permanece no port de propósito — ele é
  o knob de um futuro soft cap com overage (permitir E contar acima do cap),
  que é decisão de produto, não reescrita.

## [0.22.0] — 2026-07-21

O trem da auditoria de anatomia: o dia em que o núcleo de composição passou a
entregar o que a docstring afirma, e a proveniência chegou à superfície paga.

### 🔒 Segurança

- **Isolamento de scope no caminho REST que realmente roda** (i-034, #196).
  `scope_is_bound` nunca era chamado nos modos de auth em produção — um bearer
  válido lia qualquer scope. Três regimes explícitos agora, com AUTENTICADO
  como eixo: não-autenticado livre (self-host OSS intocado), workspace
  resolvida na regra i-028, autenticado sem workspace só no que for
  explicitamente concedido (`DNA_TOKEN_SCOPES` / `--token-scope`, `*` como
  opt-out consciente). O mesmo fail-open existia no `_guard` do MCP e no
  passthrough de fonte sem workspaces — fechados juntos.
- **Fronteira de confiança no render Mustache** (i-046, #197). O render duplo
  re-expandia `{{` vindo de conteúdo de usuário — injeção de template quando o
  overlay de tenant é input de terceiro. Só a instruction do próprio agente
  mantém delimitadores vivos; todo outro valor é protegido por sentinelas.

### ✨ Proveniência no fio (i-045, #199)

- **`GET /v1/agents/{name}/prompt?explain=true`** (REST) e
  **`compose_prompt(explain=true)`** (MCP) — o mapa de proveniência por seção
  que só o `dna explain` alcançava chega às três faces. Opt-in: sem a flag o
  compose continua byte-idêntico (shape do JSON incluído); com ela a resposta
  ganha `sections` (artefato de origem, hash, versão, layer de origem,
  overlay de tenant por seção) e `attribution` — o marcador de honestidade:
  `declared` (template do kernel, correto por construção) vs `heuristic`
  (`promptTemplate` próprio; a detecção é match de string fail-soft). Os
  clientes `dna-client` (py + ts) expõem o parâmetro tipado.

### ✨ Memória

- **`POST /v1/memories/import`** (#192) — o import MIF pela face REST, escrito
  na partição PESSOAL do chamador. A identidade vem só das claims verificadas
  (`auth=config`); bearer compartilhado não é identidade (403); `DNA_PERSONAL_ID`
  vale apenas em `auth=none` local. Limites de 10 MiB / 5000 docs antes de
  qualquer escrita; bundle malformado é 400 com nada escrito. Pipeline única
  (`dna.memory.verbs.import_mif_docs`) compartilhada entre CLI e REST.

### ✨ Kinds e modelo de dados

- **`x-dna-ref`** (i-040, #193) — um campo de spec pode declarar que referencia
  outro Kind por nome de documento. Validação opt-in na escrita
  (`DNA_REF_VALIDATION`: `warn` default / `enforce` / `off`); Kind sem a
  anotação comporta-se exatamente como antes. 14 campos declarados no arco
  SDLC + portfolio.
- **MER gerado do registry** (#195) — `docs/reference/data-model.md`, com as
  relações em quatro camadas (declarada / composição / inferida-tracejada /
  não-resolvida-nomeada) e guard de drift no CI.

### 🛠 Kernel honesto (i-043, i-044, #197)

- `merge_field_level` faz o deep-merge que a docstring promete (dicts aninham,
  listas substituem — a semântica do `layer_resolver.deep_merge`), com
  proveniência por caminho de folha. Default `override_full` inalterado.
- A política de camada é casada pelo alias DECLARADO do registro; o fallback
  para `open` ficou barulhento e um typo de alias derruba teste em vez de
  degradar `locked`→`open` em silêncio.

### 🛠 Migrations

- **O baseline do Alembic ficou recuperável de verdade** (#191). A mensagem de
  recuperação mandava usar uma versão que nenhum wheel continha.
  `_LEGACY_BRIDGES` fecha o único degrau alcançável (9→10, o DROP idempotente
  de `dna_edges`), com sentinela de sanidade e recusa preservando dados se a
  tabela não estiver vazia. SQLite nunca foi afetado.

### 🔧 CLI

- **A Session é injetada pelo contexto do click** (f-cli-session-injection,
  #198). Os 25 monkeypatches em `dna_session` de módulo viraram um provider em
  `ctx.obj`; patchar o seam antigo agora falha ALTO. `sdlc_cmd.py` começou a
  ser desmembrado (7.221 → 4.608 linhas; journey/narrative/reference/initiative
  em módulos próprios). Superfície `--help` byte-idêntica (206 comandos).
- `gen_cli_docs.py` ficou reprodutível entre versões de Python (o 3.13 dedenta
  docstrings em tempo de compilação; `inspect.cleandoc` normaliza).


### ✨ Proveniência no fio (i-045)

- **`GET /v1/agents/{name}/prompt?explain=true`** (REST) e
  **`compose_prompt(explain=true)`** (MCP) — o mapa de proveniência por seção
  que só o `dna explain` alcançava chega à superfície paga. Opt-in: sem a flag
  o compose continua byte-idêntico (shape do JSON incluído); com ela a resposta
  ganha `sections` (artefato de origem, hash do conteúdo, versão, layer de
  origem e marcador de overlay de tenant por seção composta) e `attribution` —
  o marcador de honestidade do shape: `declared` (template do kernel, mapa
  correto por construção) vs `heuristic` (o agente tem `promptTemplate`
  próprio; a detecção de seções é match de string fail-soft e pode omitir ou
  sobre-reportar seções). O `prompt` composto é byte-idêntico com e sem a flag
  — explain nunca re-renderiza. Os clientes `dna-client` (py + ts) expõem o
  parâmetro tipado.

## [0.21.1] — 2026-07-21

Release de encanamento: nenhuma mudança nos pacotes, só o que faltava para o
cliente conseguir publicar.

- **`release-client.yml` aceita token de automação** além do OIDC. O trusted
  publishing do npm só pode ser configurado sobre um pacote **que já existe** —
  então o primeiro publish de um pacote novo não tinha como sair pelo CI, e caía
  num `npm login` manual com 2FA. O job agora usa `secrets.NPM_TOKEN` quando ele
  existe e cai no OIDC quando não existe.
- **Disparo manual** (`workflow_dispatch`) no `release-client`. A tag `v0.21.0`
  passou antes de a configuração de conta ficar pronta, e sem disparo manual não
  havia como publicar o cliente sem cortar uma versão nova.
- Esta versão é a **primeira publicação do `dna-client`** (PyPI + npm).


## [0.21.0] — 2026-07-20

### ✨ O ato de criação

- **`POST /v1/workspaces`** — cria um `Workspace` e o `WorkspaceMembership` de
  owner. O **id é cunhado pelo servidor**: não existe campo `workspace_id` na
  rota nem na assinatura do impl, então um id escolhido pelo cliente é
  impossível de passar, não apenas rejeitado. Isso implementa a decisão de
  produto **D5** (o workspace ganha id próprio; o `tid` do Azure vira apenas
  fato de autenticação).
- **`GET /v1/workspaces`** — enumera por membership ATIVA. Convite `pending`
  não aparece; identidade desconhecida recebe lista vazia, nunca a de outro.
- **`POST /v1/projects`** — `Project` com `workspace_id` explícito (decisão
  **A1**); 403 sem membership ativa.

### 🔒 Segurança — anti-takeover ganha implementação própria

`provision-owner` **não cria mais nada**; degradou para o reconcile idempotente
de login. A regra de entitlement deixou de ser "seu `tid` é igual ao id do
workspace" e passou a ser **"você já tem membership ativa aqui"**.

Com a criação sendo explícita e o id cunhado pelo servidor, **não sobra id não
reivindicado para disputar** — takeover passa a ser impossível por construção,
não por comparação de strings.

### 🧹 Encolhimento

- **`packages/sdk-ts` congelado** na tag `sdk-ts-final` (restaurar:
  `git checkout sdk-ts-final -- packages/sdk-ts`). A história TypeScript passa a
  ser o cliente REST gerado. −84.704 linhas.
- **Alembic no lugar dos payloads DDL à mão.** O ganho não é o runner (que era
  pequeno e justificado) e sim o `autogenerate`: havia **duas definições
  paralelas do schema** sem nada verificando que batiam — foi assim que uma
  coluna ficou duas semanas em drift silencioso.
- **7 Kinds órfãos removidos** — declarados para receber saída de motores de
  cognição que nunca existiram neste pacote.
- Andaime sem referência viva: BM25 escrito à mão, `dna/sync`, `dna/viz`,
  `@dna_tool`, `RedisCache`, `S3Source`, `dna_edges`.

### 🔒 Billing — o contador de consumo passa a existir

- **`dna_quota_counters`** — contagem durável por `(dia, tenant, tier)`, com
  incremento atômico. Antes só havia um store **em memória**, cujo docstring já
  admitia *"WRONG for real billing"*: um restart zerava o uso diário e cada
  réplica tinha o seu dict, então a cota efetiva era ~N × o limite.
  Provado com Postgres real: 64 threads × 8 = **512 contou 512**, e a mesma
  carga contra uma implementação read-modify-write contou **10, perdendo 502**.
- O port virou **de fato trocável** (`build_server(..., quota_store=)`); sem DSN
  o in-process continua o default legítimo para local e self-hosted.
- ⚠️ Consumidores hospedados precisam do extra novo **`dna-cli[quota]`**
  (psycopg2 — o port é síncrono e o `[postgres]` traz asyncpg, async-only).

### 🐛 Correções

- **`Epic` vazava do `_lib` para todo scope filho.** O rename `Milestone` →
  `Epic` (v1.3) deixou a classificação de herança presa ao nome morto, e a
  classe nunca declarou o atributo — então `Epic` era o **único** Kind do ledger
  que herdava, e um epic da plataforma aparecia dentro de todo projeto.
  `Milestone` **fica** na denylist: documento não migrado não pode *começar* a
  vazar porque o Kind dele foi aposentado.
- `SavedView` removido — zero leitores, e o próprio descriptor dizia
  *"waiting on a reader"*.

### 🔧 Clientes

`client-py` e `client-ts` cobrem agora **as 31 operações**, não só as 18 de
leitura. O guard de drift passou a ser chaveado por `(MÉTODO, path)` e a existir
**nos dois** clientes — antes era só GET, só no Python, e uma rota de escrita
nova entrava sem quebrar nada.


### ⚠️ Breaking

- **The TypeScript SDK (`packages/sdk-ts`, npm `dna-sdk`) is frozen and
  removed from the repository.** It was a ~31k-LOC 1:1 mirror of
  `packages/sdk-py`, kept in step by **manual parity**. It had no consumers:
  the one real TypeScript consumer evaluated it and chose REST instead.

  **Recovering it.** Every one of the 414 files is preserved at the tag
  [`sdk-ts-final`](https://github.com/ruinosus/dna/releases/tag/sdk-ts-final):

  ```bash
  git checkout sdk-ts-final -- packages/sdk-ts
  ```

  **What replaces it.** The portability promise is unchanged; the mechanism
  is different. The runtime is Python, and every other language reaches it
  through the two language-neutral faces — **REST** (`dna api serve`,
  described by `docs/openapi.json`) and **MCP** (`dna mcp serve`). TypeScript's
  package in this repo is now `packages/client-ts` (`dna-client` on npm), a
  typed REST client **generated from the OpenAPI document**, with
  `packages/client-py` (`dna-client` on PyPI) as its Python sibling. A
  generated client cannot drift from the runtime the way a hand-mirrored
  kernel can.

  Also removed: the `dna-sdk` npm publish job (`release.yml`), the `sdk-ts`
  CI job (`typescript.yml` — its `client-ts` job stays and is now the point
  of that workflow), the generated TypeDoc reference (`docs/reference/typescript/`),
  the Py↔TS parity matrix (`docs/reference/parity-matrix.md` and
  `scripts/gen_parity_matrix.py`), and the TypeScript twins of the
  `hello-genome`, `tools_as_data` and `shipping-a-scope` examples.

### Changed

- **The Py↔TS parity suites are reclassified as golden suites.** Each of the
  eleven was assessed by one question — *what does this protect if TypeScript
  does not exist?* Eight protect **Python** behavior that TypeScript merely
  rode along with, and were kept and renamed; three tested nothing but the
  mirror, and were deleted.

  | Suite | Now | Protects |
  |---|---|---|
  | `test_composition_parity_fixtures.py` | `test_composition_golden.py` | Composition-V2 resolution, 13 cases |
  | `test_embedding_onnx_parity.py` | `test_embedding_onnx_golden.py` | The all-MiniLM-L6-v2 ONNX vectors |
  | `test_f2_parity_fixture.py` | `test_f2_query_golden.py` | The query/count core |
  | `test_hash_parity.py` | `test_hash_golden.py` | `document_hash`'s canonical form + digest |
  | `test_memory_interchange_parity.py` | `test_memory_interchange_golden.py` | The MIF interchange wire format |
  | `test_memory_parity.py` | `test_memory_scoring_golden.py` | Ten pure memory-scoring surfaces |
  | `test_port_surface_parity.py` | `test_port_surface_golden.py` | Every `typing.Protocol` member — the extension contract |
  | `test_studio_ui_parity.py` | `test_studio_ui_golden.py` | `StudioUIMetadata` projection + locale fallback |
  | `test_descriptor_hash_parity.py` | *deleted* | Only compared Py descriptor files to their TS copies |
  | `test_kind_registry_parity.py` | *deleted* | Only compared the Py Kind registry to the TS one |
  | `test_parity_matrix_fresh.py` | *deleted* | Guarded the freshness of the (now removed) parity matrix page |

- **`tests/parity-fixtures/` is now `tests/golden-fixtures/`**, and
  `port-surface-parity.json` is now `port-surface.json` with the `ts` half of
  each member pair dropped. Four fixtures that lived in `packages/sdk-ts` but
  were read by Python suites moved to `packages/sdk-py/tests/goldens/`
  (`f2-query.json`, `memory-interchange.json`, `memory-scoring.json`,
  `studio-ui.json`) so nothing depends on a deleted package.

- **Documentation repositioned** from *"Dual SDK, one behavior"* to *"one
  runtime, any language"* — README, `docs/index.md`,
  `docs/concepts/microkernel-ports.md`, `docs/reference/index.md`, the
  tutorials, `CONTRIBUTING.md` and `AGENTS.md`.

## [0.20.0] — 2026-07-19

### ⚠️ Breaking

- **The `LessonLearned` Kind is renamed `Engram` and moves from
  `github.com/ruinosus/dna/sdlc/v1` to `github.com/ruinosus/dna/v1`.** Kind
  lookup is an EXACT `(apiVersion, kind)` tuple with **no fallback**, so there
  is no window in which both identities resolve — upgrading is a **hard cutover
  with a write freeze**, not a rolling one. Existing data must be migrated:

  ```bash
  python3 scripts/migrate_engram.py --source .dna                    # dry run
  python3 scripts/migrate_engram.py --source postgresql://...        # dry run
  python3 scripts/migrate_engram.py --source postgresql://... --apply
  ```

  Read `docs/guides/engram-postgres-cutover.md` first and **read the dry-run
  output**, not just its exit code.

### Added

- **Portable memory — `Engram <-> MIF` interchange** (`f-portable-memory`).
  `dna.memory.interchange` provides pure, deterministic `to_mif` / `from_mif`
  projections (Py + TS twins), with the fields MIF has no place for travelling
  intact in an `extensions.x-dna` vault. `mif-spec.dev/v1 · Memory` is
  registered as a passthrough Kind so a foreign MIF document can be stored
  verbatim alongside its native projection.
- **`dna memory export` / `dna memory import`** — the CLI verbs over that
  projection, including `--as native|passthrough|both`, `--bundle` (JSON-LD)
  and `--personal`.
- **`dna.memory.claude_export`** — a `claude-export -> MIF` adapter (~80 lines
  of code) for the official Claude account export. Note what it can and cannot
  promise: the export is free-form markdown prose, not discrete records, so
  **segmentation is inferred**, there are **no per-memory timestamps** (the
  stamped `created` is import time, not formation time) and **no ids** (they are
  minted deterministically, so re-import dedupes rather than duplicates).
- **`interchange_round_trip`** joins the public `memory_conformance_suite`,
  asserting field fidelity against the live descriptor — so a Kind that grows a
  field fails the case instead of quietly ceasing to be covered.

### Fixed

- **Consumer lane (WorkOS) could not reach personal memory.** WorkOS stamped no
  provider family, so `resolve_personal_oid` fell back to `entra` and demanded
  an `oid` claim a WorkOS token does not carry — personal memory failed closed
  for every Google/WorkOS sign-in. WorkOS now has its own family, keyed
  `personal:workos:<sub>`, deliberately distinct from a directly-configured
  Google IdP.
- **`dna memory import` could silently overwrite an unrelated memory.** The
  native projection named the Engram from a hash of the derived summary while
  the passthrough leg named it by MIF id; two documents sharing a title
  collided and the second replaced the first. Imported Engrams are now keyed by
  MIF id.
- **Unquoted ISO-8601 dates in a third-party MIF file corrupted temporal
  fields.** MIF's own examples write dates unquoted and YAML resolves those to
  `datetime` objects, which failed MIF's string-typed schema on import and
  crashed `--bundle` re-export. They are now coerced back to ISO strings at
  read time.


> **Bookkeeping note.** The entries below this line under the old
> `[Unreleased]` heading (MCP Apps / MCP-UI) in fact SHIPPED — they are present
> in the `v0.19.2` tag — but were never moved under a version heading, and
> `0.18.x`/`0.19.x` have no sections at all. Left in place rather than
> re-attributed to a guessed version; see the release notes for those tags.

### Added

- **MCP Apps — the DNA memory card renders INSIDE Claude / ChatGPT / VS Code /
  Goose** (`f-dna-cloud-copilot`, Phase 3 M0). The `list_memories` MCP tool now
  ships an interactive UI card (SEP-1865 "MCP Apps", ratified 2026-01-26)
  alongside its data: a self-contained `rawHtml` resource at `ui://dna/memory-list`
  (DNA-branded, no external asset), linked from the tool result's
  `_meta.ui.resourceUri`, so any MCP host renders the memory list as a card in a
  sandboxed iframe — DNA's "your context follows you across every client" thesis
  made *visible in the UI*, reached by `host → DNA MCP server` (the copilot
  `/agui` agent is bypassed). Hosts without MCP Apps ignore the resource and read
  the plain structured data (graceful degradation); the card carries no secret.
  Rides the optional `dna-cli[mcp]` extra (new dep `mcp-ui-server>=1`), lazily
  imported — the base install stays MCP-free.
- **MCP-UI emit surface scaffold** (`f-dna-cloud-copilot`, Phase 4 groundwork).
  `dna.emit.mcp_ui` — a standalone, byte-golden card surface (the `frontend.py`
  pattern, not a registered `EmitterPort`) that projects a tool's clean
  structured JSON into a `create_ui_resource`-shaped payload. AG-UI is labelled
  already-covered (backend emitters + `/agui`); A2UI is deferred to its external
  v1.0 (prepared for via the "data, not markup" discipline).

## [0.17.0] — 2026-07-16

### Added

- **AG-UI Copilot absorption — one declarative `Copilot` definition emits a servable
  agent-native copilot across THREE runtimes** (`e-dna-copilot-absorption`). The
  "AG-UI copilot" scaffold that two reference apps hand-built independently is now a
  first-class DNA emit capability — the single evolution point. A `Copilot` Kind
  (a binder over Agent/Tool/MCPFederation + `knowledge`/`hitl`/`frontend`/`persistence`
  /`hosting`) emits, from one neutral `build_copilot_context`:
    - **Three runtime targets** (`f-dna-copilot-emitter`, `f-copilot-agentframework-target`,
      `f-copilot-langgraph-target`) — **Agno**, **Microsoft Agent Framework** (+ the
      `workflow` capability), and **LangGraph** (the cleanest workflow target — a chain
      is graph nodes + edges). Each emits a servable AG-UI `/agui` app: the agent build,
      the `mcp:` tool-mount, tool-level HITL (Agno `external_execution` / MS-AF
      `request_info` / LangGraph `interrupt()`), and inbound-tenant injection — all
      parameterized per runtime from one context. `EmitResult` is multi-artifact;
      byte-equal instructions preserved.
    - **Shared CopilotKit frontend scaffold** (`f-copilot-frontend-scaffold`) — one
      console (chat + canvas + approval-card + suggested-prompts + `HttpAgent` bridge)
      + a per-runtime resume-adapter; a TS-only golden family.
    - **`MCPFederation` read/write tool split + min-role RBAC** (`f-mcpfederation-rbac`)
      — rank-based role floors via the `Role` Kind; `allowed_tools` back-compat preserved.
    - **Persistence** (`f-copilot-persistence`) — declarative `persistence`
      (checkpoint/memory/cache) + `knowledge.store` (vectors); emitted as real Postgres
      config across all three runtimes (killing the hardcoded in-memory default), with a
      documented Mongo path. `ref` → env-var seam.
    - **Hosting** (`f-copilot-hosting`) — the hosted-agent variant: **Azure AI Foundry**
      first-class (Dockerfile :8088 + `ResponsesHostServer` + `azure.ai.agent` manifest,
      degrading per-user concerns), LangGraph Platform + AgentOS documented. One def →
      self-hosted AG-UI app **and** hosted agent (variant selector).
    - **Infra binding** (`f-copilot-infra-binding`) — `dna emit <copilot> --infra`
      turns the declared persistence backends + hosting target into Terraform module
      inputs (the DNA→Terraform seam that closes the declarative-all-the-way-down loop).
    - **Retrofit validation** (`f-copilot-retrofit`) — the emitter reproduces both
      hand-built reference apps' load-bearing servable shape from one `Copilot` def each.
    - The 3-dimension DNA-native tenant contract throughout: `X-DNA-Tenant` +
      `X-DNA-Workspace` + `X-Tenant-OID` (workspace → scope via `default_scope`).

- **SDLC write tools on the DNA MCP server — the board is now creatable +
  manageable over MCP** (`f-mcp-sdlc-write`, stories `s-mcp-sdlc-write-tools` +
  `s-mcp-sdlc-write-guard` + `s-mcp-sdlc-write-tests`; epic `e-dna-portability`).
  The DNA MCP server exposed the SDLC board **read-only** (`sdlc_digest` /
  `list_stories` / `get_adr`); it now also **writes** it, closing the dogfood loop
  — any MCP client (Copilot, an agent, a bare client) can create + manage the
  board over DNA's own interface:
  - Five write tools mirroring the `dna sdlc` core verbs: `create_story`
    (`{name, feature, description, title?, priority?, labels?, ac?, dod?}`),
    `create_issue` (`{slug, description, type?, severity?, feature?}` → auto
    `i-NNN-<slug>`), `set_status` (`{kind, name, status, reason?}` — refuses a
    status invalid for the Kind), `comment` (`{kind, name, body, type?}` — the
    FOCUS-feed narration; a decision-shaped body auto-promotes), and
    `create_feature` (`{name, title, description, epic?, priority?, labels?}`).
  - **One write path, two faces.** The write logic is extracted into the
    transport-agnostic core `dna.application.sdlc` (pure spec builders + timeline
    event + doc envelope + status-enum guard, plus async kernel-level cores that
    route through `kernel.write_document` so cache invalidation, hooks + schema
    validation fire). Both the MCP tools **and** the `dna sdlc` CLI now call it —
    the CLI's `_build_raw` / `_append_timeline` / `_next_issue_number` + the status
    enums are thin adapters over the shared core (no duplicated write logic).
  - **Tenant-scoped + plan-guarded**, mirroring `remember`. Every write tool passes
    the same `_guard` tenancy + quota seam plus the new `sdlc_mode` gate — the
    read-vs-write refinement within the `sdlc` feature family (**Free = read**,
    **Pro = write**): a Free/read-only token writing is honestly denied, its reads
    stay allowed, and the stdio / local (no-token) path is unmetered + unrestricted.
    The SDLC board Kinds are `TenantScope.GLOBAL`, so isolation is by **scope**
    (Model B per-workspace scope), not a tenant overlay.
  - New `Tier` spec field **`sdlc_mode`** (`none`/`read`/`write`, default `none`;
    parity-critical Py↔TS descriptor + `sdlc_mode` on the example Free/Pro tiers),
    and a new timeline **`source: mcp`** so a board write is attributable to the
    MCP face.

- **`ActOnBehalfPort` — the provider-agnostic "act on behalf of the user" port (PoC)**
  (`f-act-on-behalf-port`, stories `s-aob-port-contract` + `s-aob-microsoft-as-port` +
  `s-aob-neutral-calendar` + `s-aob-google-skeleton`;
  [ADR-act-on-behalf-port](https://github.com/ruinosus/dna/blob/main/docs/adr/ADR-act-on-behalf-port.md)).
  The outbound twin of the pluggable N-provider IdP layer: where `_mcp_auth` made
  *verifying any identity* provider-agnostic, this port makes *acting on the signed-in
  user's productivity data* provider-agnostic. The Microsoft OBO is now the **reference
  implementation** of the port — **its shipped behavior is unchanged** (`ms_calendar_list`
  / `ms_files_search` / `ms_file_read` and `graph._obo` are untouched).
  - New `dna_cli.act_on_behalf` package: the contract (`ActContext` / `UserCredential` /
    `ActOnBehalfPort` / `ActOnBehalfUnavailable`), `MicrosoftOboProvider` (wraps the
    unchanged OBO exchanger), a provider-**neutral** `calendar_list` capability adapter
    that returns one neutral event shape whichever provider served it, and identity→provider
    dispatch driven by a **provider-family stamp** on the verified token (`entra → microsoft`,
    `google → google`).
  - New provider-neutral **`calendar_list`** MCP tool, registered ALONGSIDE the unchanged
    `ms_calendar_list` (which stays callable as the Microsoft binding/alias). It resolves the
    caller's provider from their verified identity and dispatches to the right port; same
    opt-in gate as the graph tools (off by default; OSS/stdio untouched).
  - `GoogleWorkspaceProvider` **skeleton** (calendar only): the OAuth (auth-code + refresh)
    shape with the **network boundary stubbed** (injectable seams — no live Google Cloud
    project), proving a second provider fits the same contract. `ActContext.raw_token` is
    Optional — Google needs no inbound assertion (the asymmetry Microsoft OBO requires).
    Full OAuth consent + refresh-token storage, Domain-Wide Delegation, `files`/`mail`, all
    write scopes, multi-provider fan-out, and prod credential hardening remain deferred.
  - TS parity: the `ActOnBehalfPort` / `ActContext` / `UserCredential` contract twin (camelCase)
    in `@ruinosus/dna` (execution is Python-side for the PoC; the *surface* is Py↔TS by
    construction).
- **Microsoft On-Behalf-Of (OBO) — the `files` tool-group** (`f-mcp-obo`, story
  `s-mcp-obo-files-group`; [ADR-mcp-obo](docs/adr/ADR-mcp-obo.md)). Mirrors the
  calendar slice for OneDrive / SharePoint, read-only over the delegated
  **`Files.Read`** scope. Two built-in MCP tools, gated on the config
  `graph.groups.files` block being enabled **and** an Entra inbound identity
  (non-Entra → an honest "OBO unavailable" error); each group opts in independently.
  - `ms_files_search` — search the signed-in user's files by text
    (`GET /me/drive/root/search(q='…')`); returns named fields only (name, id, web
    URL, last-modified, size, type), never file contents, a token, or the raw body.
    The OData query is single-quote-escaped (injection hygiene).
  - `ms_file_read` — read a file's content by id (`GET /me/drive/items/{id}`).
    Text-convertible files (text/\*, Markdown, CSV, JSON, XML, YAML, HTML, source,
    …) come back as extracted text (capped ~1 MiB, `truncated` flagged); binary
    Office (`.docx`/`.xlsx`/`.pptx`), images, and PDFs return metadata + a `web_url`
    + an honest not-text-extractable note (never a byte dump). Token B is confined
    to the single `graph.microsoft.com` metadata call — content is fetched from the
    driveItem's *preauthenticated* download URL with **no** `Authorization` header.
  - Both surfaces are governed, overlayable Tool documents (`ms_files_search.yaml`,
    `ms_file_read.yaml`). Guide + the Entra `Files.Read` delegated-permission admin
    step (scope id `10465720-29dd-4523-a11a-6a75c743c9d9`) added to
    [the OBO guide](docs/guides/mcp-obo.md).
  - Deferred (follow-up): rich Office (`.docx`/`.xlsx`/`.pptx`) → text extraction
    for `ms_file_read`, and the `mail` read group.

## [0.16.0] - 2026-07-15

### Added

- **Microsoft On-Behalf-Of (OBO) for the MCP server — first slice** (`f-mcp-obo`,
  stories `s-mcp-obo-exchanger` + `s-mcp-obo-config-gating` +
  `s-mcp-obo-calendar-tool`; [ADR-mcp-obo](docs/adr/ADR-mcp-obo.md)). The DNA MCP
  server can now exchange the verified inbound Entra token for a downstream
  Microsoft Graph token minted for the same user, and act on their Microsoft 365
  **on their behalf** — no new sign-in. First tool: `ms_calendar_list`
  (`GET /me/calendarView`, delegated `Calendars.Read`).
  - New `dna_cli.graph` adapter (optional `dna-cli[graph]` extra = `msal` + `httpx`,
    lazily imported): a per-request OBO exchanger (`graph/_obo.py`) that targets the
    token's **home tenant**, enforces the scope allow-list fail-closed, and maps
    consent / Conditional-Access / Graph errors to honest capability errors —
    **token B is never logged, persisted, or returned**.
  - A `graph:` block in `dna.config.yaml` (sibling to `auth:`): **OFF by default**,
    an explicit fail-closed scope allow-list, and the confidential-client
    credential referenced by **env-var NAME** (never a secret value in config).
  - Built-in `ms_calendar_list` MCP tool, gated on the config being enabled **and**
    an Entra inbound identity (non-Entra → an honest "OBO unavailable" error); its
    description + input schema come from a governed, overlayable Tool document.
  - Guide: [On-Behalf-Of — MCP tools act on your Microsoft 365](docs/guides/mcp-obo.md),
    including the exact Entra admin steps (client secret + delegated `Calendars.Read`
    + consent) to enable the live path.
  - Deferred to follow-on stories (`s-mcp-obo-read-groups`, `s-mcp-obo-prod-hardening`):
    the files/mail read groups, write tools, token caching, certificate /
    managed-identity credential, and guest/personal identity support.
- **Personal / private per-user memory — the memory whose key is the person**
  (`f-personal-memory`, epic `e-dna-portability`; stories
  `s-personal-memory-partition`, `s-personal-memory-privacy-invariant`,
  `s-personal-memory-namespace-guard`, `s-personal-memory-surfaces`,
  `s-personal-memory-ts-parity`; ADR `docs/adr/ADR-personal-memory.md`). A
  second, orthogonal memory axis keyed on the durable human identity (the
  verified `oid`), private per-user and portable across workspaces AND AI
  clients — distinct from today's shared workspace memory.
  - **Selector, `workspace` default.** Every memory verb takes an explicit
    `memory_scope ∈ {workspace, personal}`; `workspace` is the default, so every
    existing call is unchanged (personal is strictly additive). CLI:
    `dna memory remember/recall --personal` (identity from `DNA_PERSONAL_ID`).
    MCP: a `personal: true` flag on `recall`/`remember` (identity from the
    verified token's `oid` claim, via the new `enforce_oid_from_context` — the
    seam that was previously discarded). The `oid` is ALWAYS resolved
    server-side, never a caller argument.
  - **Zero migration.** Personal memory is a reserved value-namespace inside the
    EXISTING tenant partition — `personal:<oid>` — reusing the same filesystem
    path segment (the `:` percent-encoded on disk for portability) and Postgres
    `tenant` column. `personal:<oid>` is literally the SAME partition in every
    workspace and client, so "your memory follows you" becomes a primary-key
    value. A personal recall unions your partition with the base `_lib` defaults,
    never a workspace.
  - **Privacy (INV-PERSONAL), fail-closed, defense-in-depth.** A personal memory
    of X is never readable by any other identity, nor by any workspace query
    (owner/admin included). Enforced by four independent layers: server-derived
    `oid`; the `tenant IN ('', <workspace_id>)` read predicate provably cannot
    select `personal:*`; the `personal:` scheme is reserved in
    `validate_tenant_slug` so no workspace can alias it; and a raw
    `tenant=personal:<victim>` override is rejected at the surface. Guard suites
    in Python (`test_personal_memory_privacy.py`) and a TypeScript parity twin.
  - **Deferred (follow-on stories):** personal-insights LLM consolidation, the
    Portal Memory-tab UI, and REST personal parity (blocked on the REST
    token→identity bridge).

## [0.15.1] - 2026-07-15

### Added

- **Workspace owner bootstrap + member revoke — closing the Model B production
  gap** (`f-ws-owner-provision`, stories `s-ws-provision-owner-endpoint` +
  `s-ws-revoke-endpoint`, issue `i-033`). The deployed portal auto-provisioned a
  Model-A `TenantMembership` on first login, but the Members panel checks a
  Model-B owner `WorkspaceMembership` that nothing created in production — so the
  founding user was `403`'d and could not invite. Two REST endpoints close it:
  - **`POST /v1/workspaces/{id}/provision-owner`** — the Model B twin of
    `POST /v1/tenants/{tid}/provision-owner`. On first authenticated access the
    portal calls it so the signed-in user becomes **owner of their own
    workspace**: it creates the `Workspace` (id == the verified `tid`, so every
    existing row keyed `tenant==tid` is already this workspace's data — **zero
    migration**) if absent, then an owner `WorkspaceMembership` **bound to the
    verified identity** (oid + email + tid), `active`. **Idempotent + first-owner
    only**: a re-call by the same identity is a no-op returning the membership; a
    later *different* user does not auto-escalate (`owner_exists` no-op). The path
    id **must** equal the verified `tid` — a cross-`tid` caller is `403`'d, so a
    verified identity from another org can never seize a `tid`-workspace by racing
    the founder's first login.
  - **`POST /v1/workspaces/{id}/members/revoke`** — Owner/Admin removes a member
    (pending invite or active member; target named by `target_email` or
    `target_oid`). RBAC is checked **before** the target is revealed (no
    membership-existence oracle). **Policy: the last remaining active owner can
    never be revoked** (`409`, fail-closed — a workspace is never orphaned); a
    non-Owner/Admin is `403`; an unknown target is `404` (clear no-op).
  - The RBAC + last-owner + first-owner decisions are the pure
    `dna.tenancy.ownership` policy with a 1:1 TypeScript twin, gated by shared
    parity fixtures (`tests/parity-fixtures/workspace-ownership/`).

## [0.15.0] - 2026-07-15

### Added

- **Cross-org workspace invites — the identity→workspace join** (`f-ws-invites`,
  ADR *ADR-workspace-tenancy* F3). A workspace Owner/Admin invites a collaborator
  from **any** organization **by email**; the invitee's first verified sign-in
  binds their durable identity and joins them — the GitHub/Slack shape, on top of
  the Model B tenancy from `f-ws-resolution`.
  - **Invite → accept, two-phase bind.** `invite` writes a `pending`
    `WorkspaceMembership` (`identity_oid` null, keyed by the invited email); the
    invitee's first sign-in matches the **verified** email claim, binds the durable
    `oid` (+ `tid` provenance), and flips it `active`. RBAC: only an Owner/Admin of
    that workspace may invite/list; only an Owner may invite an Owner.
  - **Impersonation-proof by construction.** Matching is only ever on a verified
    email claim (`email`+`email_verified`, or the Entra `preferred_username`/`upn`
    UPN) — never a caller field; an unverified email accepts nothing. The bind key
    is the durable `oid`: a grant already bound to an `oid` can **not** be hijacked
    by a different identity sharing the email, and a token with no `oid` binds
    nothing. The decision is the pure `dna.tenancy.invites` policy with a 1:1
    TypeScript twin, gated by shared parity fixtures.
  - **REST surface** (`s-ws-invite-rest`): `POST /v1/workspaces/{id}/invites`,
    `GET /v1/workspaces/{id}/members` (both Owner/Admin), and
    `POST /v1/workspaces/accept` (the verified invitee — exempt from the workspace
    bind, since a pending invitee holds no active membership yet).
- **Per-workspace MCP URL + REST `--auth config` binding** (`f-ws-resolution`
  follow-ups `s-ws-res-mcp-url` / `s-ws-res-rest-config`, ADR §2.2). An MCP client
  picks its workspace **by URL** — `…/w/<workspace-id>/mcp` names it in the path
  (the bare `/mcp` falls back to the sole/default membership); the selector is
  re-verified against membership, never trusted blind. `dna mcp serve --transport
  http` now serves both the bare and per-workspace URLs. The REST face gains
  `dna api serve --auth config`: a verified bearer JWT is resolved to a workspace by
  membership, which **overwrites** the request's `tenant` argument (so a caller can
  no longer forge it) — mirroring the MCP guard, fail-closed on no/cross-workspace
  membership.
- **`dna specify` — the bidirectional GitHub Spec Kit ↔ DNA bridge**
  (`f-spec-kit-adoption`, ADR *ADR-spec-kit-adoption*). DNA officially names
  [GitHub Spec Kit](https://github.com/github/spec-kit) as the supported
  spec-driven flow and composes *underneath* it — Spec Kit runs untouched.
  - **`dna specify import <path>`** ingests a `.specify/` toolkit (or one
    `specs/<feature>/` run) into durable Kinds (ADR §4): `constitution.md` → a
    live **Guardrail** *and* a **Soul** (`--constitution-as`, default `both`);
    `spec.md` → **Spec** (`pattern="spec-kit"`); `plan.md` → **Plan**
    (`methodology="spec-kit"`); `research`/`data-model`/`quickstart`/`contracts`
    → **Reference** docs via `Plan.produces[]`; each `tasks.md` item → a **Story**
    under the **Feature** (`[P]` → a `parallel` label). Every write goes through
    `kernel.write_document`, so the constitution *becomes* enforced governance.
    `--dry-run --json` previews the full mapping without writing.
  - **`dna specify export <feature>`** projects a DNA-stored run back to a
    byte-faithful `.specify/` tree from the Feature's `specify_run` manifest —
    the same "one source → N projections" philosophy as `dna init`/`dna emit`.
    **Round-trip fidelity** (`import` then `export` = byte-identical `.specify/`)
    is an acceptance test.
  - The derived **journey** auto-fills `specify → plan → build` from the created
    Spec/Plan/Story refs, plus a `WorkflowEvent(methodology="spec-kit")` overlay
    that pins each phase to its `.specify/` artifact. `spec-kit` joins
    `superpowers` as an artifact-gated methodology (spec/plan must exist to leave
    the phase).
- **`dna specify wire` — DNA feeds Spec Kit's agent live over MCP**
  (`f-speckit-live-feed`, ADR *ADR-spec-kit-adoption* **Layer 2**). Where
  `import`/`export` capture a run *after* it happens, `wire` feeds DNA *into* a
  run *while* it happens: it projects the **DNA MCP server block** into each
  agent's *own* MCP config file — the same "one source → N projections"
  philosophy as `dna init`'s skill projection — so a Spec-Kit-driven agent
  reaches the live DNA over MCP mid-run: **memory** (`recall`/`remember`),
  **soul** (`compose_prompt` = Soul + Guardrails, composed live + tenant-aware)
  and the **board** (`sdlc_digest`/`list_stories`) — the *same* context whether
  Spec Kit drives Copilot or Claude.
  - Projects the correct per-agent shape: `claude`/`cursor` → `mcpServers` in
    `.mcp.json`/`.cursor/mcp.json`; `copilot` → `servers` (`type: stdio`) in
    `.vscode/mcp.json`; `opencode` → `mcp` (`type: local`) in `opencode.json`.
    The stdio block pins `DNA_SOURCE_URL` to the source the `dna` CLI already
    reads. `--http <url>` wires a hosted remote `dna mcp serve` instead.
  - Non-destructive + idempotent: other MCP servers are preserved; a re-run
    leaves an existing `dna` entry byte-identical unless `--force`. `--dry-run
    --json` previews. Skills continue to travel via `dna init` (byte-faithful
    into the agent's skill dir) — the two commands together fully ground a run.
  - Guide: [Spec Kit + DNA's live memory over MCP](docs/guides/spec-kit-live-memory.md).
- **`dna specify install-templates` / `export-templates` — serve the Spec Kit
  *toolkit* as DNA Kinds over MCP** (`f-speckit-templates`, ADR
  *ADR-spec-kit-adoption* §5, **Layer 3**). Where `import`/`export` bridge a
  *run*, this bridges the toolkit itself — templates, slash-commands, scripts,
  constitution — so it becomes versioned, governed, portable policy instead of
  per-repo files.
  - **`dna specify install-templates <path>`** ingests `.specify/templates/*.md`
    → **PromptTemplate** `speckit-<stem>`; the slash-command definitions
    (`.specify/templates/commands/*.md` or a projected `.claude/commands/`) →
    **Skill** `speckit-<cmd>` (verbatim); `.specify/scripts/**` → a **Skill**
    bundle `speckit-scripts`; `constitution.md` → a servable **PromptTemplate**
    `speckit-constitution-template` **and** a live **Guardrail**. Each Kind
    carries its `.specify/`-relative `origin`, so **`export-templates`** replays
    the tree **byte-for-byte** (round-trip acceptance test). No new Kinds —
    reuses PromptTemplate/Skill/Guardrail (all with TS twins).
  - **Served live over `dna mcp serve`** via four new tenant-aware tools —
    `list_templates` / `get_template` / `list_skills` / `get_skill` — so any MCP
    client (Claude/Copilot/Cursor) reaches the toolkit, and a **per-workspace/
    tenant overlay wins with zero redeploy** (PromptTemplate + Skill are
    inheritable — the kernel's existing overlay machinery).
  - **Live constitution governance** — a `speckit-constitution` Guardrail with
    `severity: hard` is enforced at **write time** by a new `pre_save` veto: a
    governed spec-kit `Story`/`Plan` must trace to a Spec, else the write is
    refused. Flip the severity (`warn` ⇄ `hard`) and the next write is governed
    differently — no restart, no deploy.
  - **Docs:** the [Spec Kit guide](guides/spec-kit.md) now documents installing
    the real `specify` CLI (`uv tool install specify-cli`) and makes the
    compose boundary explicit (DNA never invokes the `specify` binary), plus a
    new [Spec Kit templates, served by DNA](guides/spec-kit-templates.md) guide.
- **Workspace tenancy foundation — `Workspace` + `WorkspaceMembership` Kinds**
  (ADR "Model B", `f-ws-kinds` F1). Two GLOBAL record Kinds that make cross-org
  collaboration expressible (the GitHub/Slack shape): a DNA-native **workspace**
  is the tenancy unit, and Entra authenticates the *identity* while *membership*
  decides what it sees. Shipped as byte-identical Py↔TS descriptors (F3 — record
  Kinds are data, not classes), registered by the `tenant` extension; the
  auth→workspace *resolution* rework is a later feature (F2) and is untouched
  here.
  - **`Workspace` (`tenant-workspace`)** — the tenancy root: an opaque, immutable
    `workspace_id` (the physical `tenant` column value on every row it owns; the
    name/slug are editable, the id never changes), plus `name`, `slug`,
    `created_by`, `created_at`, `plan_ref`.
  - **`WorkspaceMembership` (`tenant-workspace-membership`)** — the
    identity→workspace boundary (the platform-level Kind the ADR calls the
    missing `TenantMembership`): `workspace_id`, `identity_email` (the invite
    handle), nullable `identity_oid` (the durable key, bound on accept),
    `identity_tid` (provenance), `role` (owner/admin/member/guest), `status`
    (pending→active), and invite audit. Distinct from the class-based
    `TenantMembership` (Model-A) and the portfolio `Membership` (intra-workspace
    RBAC), both untouched.
  - **Seed workspace #1 (`scripts/seed_workspace_one.py`)** — a documented,
    idempotent seed (NOT a data-moving migration): declares a `Workspace` whose
    id **equals the founder's live Azure tid**, so every existing row is already
    that workspace's data → **zero migration**. Plus an owner
    `WorkspaceMembership` for his identity.
- **Workspace tenancy resolution — the tenant is resolved from membership, not
  the org id** (ADR "Model B", `f-ws-resolution` F2). The heart of Model B: the
  DNA tenancy dimension (a `workspace_id`) now resolves from the caller's
  **verified identity → active `WorkspaceMembership`**, never from the Azure `tid`
  (which becomes provenance only). A read/write is served only if the verified
  identity holds an active membership in the resolved workspace — resolved
  **before** the source is touched; otherwise it is denied (fail-closed).
  - **The pure resolver (`dna.tenancy.resolution`, Py + TS twin)** — a
    transport-agnostic policy: `identity_from_token` (verified Entra
    `oid`/`email`/`preferred_username`/`upn`/`tid` claims only) →
    `workspace_for_identity`. An active grant matches on the durable `oid` when
    bound, else on the **verified email** while still unbound (the F1 founder
    seed); a `pending` invite authorizes nothing. No membership → deny; a
    requested workspace the identity is not a member of → deny; a sole membership
    resolves by default; multiple with no selector → deny (ambiguous). Guarded by
    shared fixtures (`tests/parity-fixtures/workspace-resolution/`) that gate
    Py↔TS parity.
  - **MCP wiring (`dna_cli._mcp_auth` / `_mcp_server`)** — the `tid → tenant` step
    is replaced by `enforce_workspace_from_context` (identity + membership). A
    source with **no `WorkspaceMembership` grants configured** falls back to the
    legacy `tid` tenancy, so OSS / self-host / stdio deployments are untouched;
    Model B engages only once workspaces exist. `kernel.workspace_memberships()`
    reads the GLOBAL grants `_lib`-direct (mirrors `tenant_plan`).
  - **Physical isolation (`LiveDna.default_scope` / `scope_is_bound`)** — the
    `(scope, tenant=workspace_id)` source keys per workspace: a scope-less read
    resolves to a per-workspace default (vendor workspace #1 → the base scope,
    every other → `tenant-<workspace_id>`), and a resolved workspace may name
    only its own scope (a cross-workspace `scope=` is denied). Enabled by
    `DNA_VENDOR_WORKSPACE` (unset = single-tenant, unchanged). A no-cross-workspace-
    leakage e2e over real JWT + HTTP is an acceptance test.
- **`WorkspacePlan` Kind + `PUT /v1/workspace-plan` — billing keys on the
  workspace** (`f-ws-billing` F4, ADR *Model B* §2.6). Billing now attaches to a
  workspace, not to an identity or Azure org: the `cloud-workspace-plan` record
  Kind maps a `workspace_id` → `Tier`, and the Stripe → runtime bridge
  (`PUT /v1/workspace-plan`, delegating to the core `set_workspace_plan_impl`)
  writes it. The MCP quota guard reads it via `kernel.workspace_plan(workspace_id)`
  — the same resolved workspace id F2 already keys on (identity → membership), so
  the full quota chain (claim → store → Free floor) now resolves tier by
  workspace. Byte-identical Py↔TS descriptor + `kernel.workspacePlan` twin.

### Changed

- **`TenantPlan` → `WorkspacePlan`; `kernel.tenant_plan` → `kernel.workspace_plan`**
  (`f-ws-billing` F4). The billing→enforcement bridge Kind, its `_lib`-direct
  accessor, and the quota guard are re-keyed from the Azure `tid` to the opaque
  `workspace_id` (field `tenant` → `workspace_id`, container `tenant-plans` →
  `workspace-plans`, alias `cloud-tenant-plan` → `cloud-workspace-plan`). **Zero
  migration:** the founding workspace's id equals the founder's old `tid`, so an
  existing assignment keyed on that string resolves unchanged (mirrors F1/F2).

### Deprecated

- **`PUT /v1/tenant-plan`** — superseded by `PUT /v1/workspace-plan`. Kept as a
  back-compat alias that forwards its legacy `{tenant}` body to `workspace_id`
  (they are the same opaque string post-Model-B), so an already-deployed Stripe
  webhook keeps working. Remove once dna-cloud has cut over.

## [0.14.0] - 2026-07-13

### Added

- **`POST /v1/tenants/{tid}/provision-owner` — first-login tenant-Owner
  bootstrap** (C3, #111). Closes the DNA Cloud gap where a brand-new tenant had
  zero `Membership` docs, so its first signed-in user hit a `403` on every
  membership write and nothing ever made them Owner of their own tenant.
  - **`provision_tenant_owner_impl`** (core `dna.application.runtime`) grants the
    user an org-scope Owner `Membership` for every referenced org (+ a
    project-scope Owner for any orgless project), keyed by the tenant (`tid`).
  - **Idempotent + first-owner-only**: a no-op once any Owner exists, so it is
    safe to call on every render and a later joiner never auto-escalates.
  - The hosted portal calls it (best-effort, shared-bearer) before the first
    member read, so the founder resolves `can_manage: true` and can add members.

## [0.13.0] - 2026-07-13

### Added

- **`PUT /v1/tenant-plan` — the billing→runtime bridge write** (C4, #109).
  Closes the DNA Cloud gap where a paying **Pro** subscriber was still
  throttled at **Free** on the MCP: the Stripe webhook wrote the plan to the
  portal's `tenant_plans` SQL table (the dashboard) but never to the
  `TenantPlan` Kind the MCP runtime reads for quota
  (`kernel.tenant_plan(tenant)`), so the two stores disagreed.
  - **`set_tenant_plan_impl`** (core `dna.application.runtime`) upserts the
    `TenantPlan` Kind into `_lib` (GLOBAL; doc name == tenant == the `tid` the
    MCP token carries), stamping `tier_id`/`source`/`status`/Stripe ids +
    `updated_at`. Only schema-allowed keys are written (the descriptor is
    `additionalProperties: false`) and optional refs are omitted when absent, so
    a status-only transition never nulls a stored id. Idempotent under Stripe's
    at-least-once retries (`write_document` upserts on name).
  - **`PUT /v1/tenant-plan`** on the REST face (`dna_cli._rest_api`) is a
    bearer-guarded (the shared `DNA_API_TOKEN` the portal already holds) thin
    delegate to the core impl, keeping DNA-source writes inside the DNA runtime
    (the Node portal never opens the DNA source directly).
  - End-to-end: Stripe Pro event → portal webhook → this endpoint → `TenantPlan`
    Kind in `_lib` → `kernel.tenant_plan(tid)` resolves `pro` → the MCP quota
    guard lifts the caps. Python-only runtime face (no TS parity surface); the
    parity-critical `tenant-plan.kind.yaml` descriptor is unchanged.

## [0.12.0] - 2026-07-13

### Added

- **Console REST — the portfolio/board read+write surface** the hosted DNA
  Cloud console renders. A `/v1` REST face over the kernel, tenant-aware:
  - **Portfolio read-endpoints + demo seed** (`s-console-rest-seed`, #103) —
    the console's portfolio/orgs/projects/board listings, backed by the
    `portfolio-console` record Kinds (#96), with a demo seed so the console has
    data to render out of the box.
  - **`GET /v1/board/item`** (#105) — the full work-item document (the console
    drawer's detail view), not just the board summary row.
  - **`POST /v1/memories`** (#106) — the portal's remember/add affordance:
    write a memory engram through the REST face.
  - **Project members RBAC** (`s-members-panel-functional`, #107) — read + write
    of project membership with role-based access control, powering the console's
    Membros panel.
- **MCP `scopes_supported` advertisement** — the deployed MCP (`--auth jwt` and
  the multi-provider `--auth config` path) now advertises its OAuth scope in the
  Protected-Resource-Metadata (RFC 9728) via the new `DNA_MCP_SCOPES_SUPPORTED`
  env (comma-separated). Without it an MCP client (e.g. VS Code) reaches the IdP
  with no scope to request and stalls. Per the Azure scope-format nuance
  (PrefectHQ/fastmcp#3002) the FULL scope (`api://…/user_impersonation`) is
  advertised in PRM only — never added to the verifier's `required_scopes`, so
  the token's SHORT `scp` claim (`user_impersonation`) is not rejected.

### Changed

- **Skills compose into `build_prompt`** (`i-031`, `s-dna-explain-provenance`,
  #102) — Skills now participate in prompt composition, and `dna explain` shows
  their provenance.
- **Kind schema emits enums + validates on read/dry-run** (`i-validation-shallow`,
  #101) — generated schemas carry enum constraints and are validated when a
  document is read or dry-run applied.

### Fixed

- **`DeclarativeKindPort.canonical_digest`** (`i-030`, #98) — unblocks
  FS→Postgres source-sync. Combined with the Postgres-substrate spike
  (`sp-postgres-substrate`, #97), DNA runs end-to-end on a Postgres source
  (asyncpg driver; set `sslmode`/`ssl` on `DNA_SOURCE_URL` for a TLS-required
  managed Postgres such as the hosted DNA Cloud).

## [0.11.0] - 2026-07-12

### Added

- **The intelligence layer** (feature `f-dna-cloud-intelligence`) — DNA turns
  from passive storage into a proactive *intelligence cycle* over a portfolio
  of sources. Two new record Kinds and a transport-agnostic engine, with thin
  CLI and REST faces:
  - **`IntelSource`** (`intel-source`) and **`IntelInsight`** (`intel-insight`)
    — per-tenant record Kinds (byte-identical Py↔TS descriptors): the watched
    portfolio source (with its Priority Intelligence Requirements, cadence and
    actionability threshold) and the ranked, actionable insight it produces.
  - **Engine** (`dna/extensions/intel/`, transport-agnostic) — `run_pass`
    researches a source, **ranks** each candidate by actionability and
    **suppresses** those below the source's threshold (the anti-noise core),
    **dedups** semantically against already-surfaced insights via the memory
    co-pillar, and writes the survivors. A **feedback loop** turns
    `dismissed`/`actioned` dispositions into memory engrams that tune the
    ranker, with a `precision` / `noise_rate` metric.
  - **`LLMAnalyzer`** — researches *arbitrary* sources via a live LLM (reads a
    repo's README/docs, a scope's documents, or an external hint), selectable
    with `dna intel run --analyzer [auto|llm|seed]`; the deterministic
    `SeedAnalyzer` stays the offline default.
  - **Faces** — CLI `dna intel run` / `list` / `metrics`; REST `GET /v1/sources`,
    `GET /v1/insights`, `GET /v1/insights/metrics`, `PATCH /v1/insights/{name}/state`.

### Changed

- **Faces reorg — move #1 (`adr-faces-reorg`).** The transport-agnostic
  application/use-case layer (the `*_impl` both the MCP server and the REST API
  call) moved out of the CLI package into the core as `dna.application`, so
  `dna mcp serve` and `dna api serve` are now thin adapters over a shared core.
  Behaviour is preserved (the incremental first step; splitting the server
  faces into separate distributions is a later move).

## [0.10.0] - 2026-07-11

### Added

- **DNA hosted — the MCP server on Azure Container Apps + Microsoft Entra**
  (feature `f-dna-hosting`, story `s-mcp-deploy-aca`; epic `e-dna-portability`).
  Phase A of DNA-hosted: a one-command (`azd up`) self-host recipe under
  [`deploy/azure/`](deploy/azure/README.md) that runs `dna mcp serve --transport
  http --auth jwt` on **Azure Container Apps**, behind an HTTPS ingress,
  authenticated with **Microsoft Entra** — the base the multi-tenant DNA Cloud
  offering builds on:
  - **`Dockerfile` + `entrypoint.sh`** — containerize `dna mcp serve --transport
    http` on `python:3.12-slim` (non-root, port 8080, `dna-cli[mcp]` installed
    from source). One image runs authenticated or open by flipping `DNA_MCP_AUTH`.
  - **azd/bicep** (`azure.yaml` + `main.bicep` + `resources.bicep`) — a **keyless**
    stack: Container App (external HTTPS ingress) + **user-assigned Managed
    Identity** (ACR pull, no registry secret) + Log Analytics + ACR + an Azure
    Files share mounted read-only as the DNA source (`/mnt/dna`). The Entra-JWT
    env (`DNA_MCP_JWKS_URI`/`_ISSUER`/`_AUDIENCE`/`_RESOURCE_URL`/`_AUTH_SERVERS`
    + `DNA_MCP_TENANT_CLAIM`) is derived from the tenant id via `environment()`
    (correct across Azure clouds); Entra tokens are validated against the public
    JWKS, so **no secret** lives in the template or the container.
  - **Runbook + guide** — `deploy/azure/README.md` (Entra app registration, `azd
    up`, `scripts/push-scope.sh` to seed the source, and a post-deploy smoke:
    PRM 200 / unauth 401 / authed `initialize` 200) and a new site guide *Hosting
    the MCP server on Azure (ACA + Entra)*. Auth code is untouched — the deploy
    wires the existing `--auth jwt` provider; a declarative `auth.providers:
    [entra]` front-end is sketched in `dna.config.sample.yaml`.

- **The `EmitterPort` as a first-class, documented DNA port + the scaffold
  mechanism for code-first runtimes** (epic `e-dna-portability`, feature
  `f-dna-emitters`, story `s-emit-port-contract`). Elevates the emit layer to a
  documented contract on the same footing as the kernel's ports, and lays the
  base the next code-first emitters (langgraph / agno / deepagents) are built on:
    - **The port contract, made explicit.** `EmitterPort` is a documented
      Protocol/interface with two surfaces — `build_emit_context(mi, agent)` (the
      kernel-facing half: compose + project to the neutral `EmitContext`) and
      `emit(ctx) -> EmitResult` (the runtime-facing half a target implements) —
      plus `target` / `file_extension`. Py↔TS parity of the contract.
    - **The byte-equal invariant, made inheritable.** The composed instruction in
      an emitted artifact MUST be byte-equal to `build_prompt`. A new contract
      hook, `extract_instructions(artifact)`, recovers it from any target's own
      artifact, and one generic test (`test_emit_contract` /
      `emit-contract.test.ts`) runs the byte-equal assertion over **every**
      registered target — so a new emitter inherits the check the moment it
      registers. Implemented on all three existing config emitters.
    - **Two emitter flavors.** *config-declarative* (map onto a runtime's
      published YAML/JSON schema — the shipped agent-framework / bedrock / vertex)
      and *scaffold-code* (fill a curated template for a code-first runtime).
    - **The scaffold mechanism (`ScaffoldEmitter`).** A code-first runtime has no
      schema to map onto, so the emitter emits *source code* by **filling a
      curated template, never generating code ad-hoc**. The template library is
      indexed by `{framework × case}` (`emit/scaffolds/<framework>/<case>.py.tmpl`)
      and a case classifier (`select_scaffold`) routes from the DNA signals in the
      context — no tools → `prompt-only`; tools → `with-tools`; `output_schema` →
      `structured-output` — falling back down a generality chain (and recording
      the fallback as a loss) when a framework does not ship a case. A subclass
      stays thin: template + variable mapping; selection, fill, and the byte-equal
      hook are inherited. Templates are read through an abstract resolution seam
      (`resolve_scaffold` / `ScaffoldResolver`), NOT a hardcoded path — the MVP
      resolver reads package-data, but a host can swap in another source with no
      emitter change. That is where the future first-class **Scaffold Kind**
      (declarative, versioned, tenant-overridable — story `s-scaffold-as-kind`)
      plugs in: the DNA thesis applied to DNA's own de-para.
    - **First code-first target: `openai-agents`** (OpenAI Agents SDK). Ships two
      case templates (`prompt-only`, `with-tools`) proving selection + the
      byte-equal instruction + syntactically valid (`py_compile`) output. The next
      three code-first emitters are then just "a couple of templates + a small
      mapping".
    - **Docs.** New guide *How to write an emitter* (both flavors + the *Passo 0*
      decision + how to add a case), the EmitterPort documented alongside the
      kernel ports in *The microkernel and its ports*, and the OpenAI Agents
      scaffold added to *Emitting to a runtime*.
- **`dna mcp serve` — pluggable N-provider IdP layer (config-driven auth)**
  (feature `f-dna-mcp-server`, story `s-mcp-idp-pluggable`; ADR
  `adr-dna-mcp-runtime-face`). The OAuth 2.1 auth on the MCP runtime face is now
  **N-provider without lock-in** — a provider is a **block of config, not code**:
  - **Provider registry in `dna.config.yaml`** — declare `auth.providers[]` (each
    `{type, issuer, audience, jwks_uri?, public_key?, tenant_claim?, scope_prefix?}`)
    and run `dna mcp serve --transport http --auth config`. Supported types:
    `entra`, `clerk`, `workos`, `auth0`, `oidc` (generic). Per-type defaults
    (Entra→`tid`, Clerk/WorkOS/Auth0→`org_id`) + JWKS derived from the issuer, so
    an Entra/Clerk/WorkOS block is `{type, issuer, audience}`. The SDK config
    (`dna/config.py` + `config.ts`) carries `auth` as an opaque passthrough
    (Py↔TS parity); the CLI owns the provider schema.
  - **Multi-issuer routing** — one `JWTVerifier` per provider composed into a
    verifier that accepts a token from ANY configured IdP, routes it by `iss`, and
    binds **that provider's** `tenant_claim` to the token, so `claim→tenant` is
    per-provider. The fail-closed tenancy policy (cross-tenant / tenant-less
    denied; no-auth identity) is unchanged; PRM (RFC 9728) advertises every
    configured issuer.
  - **Azure Entra ID as the first concrete provider** — `tid`→DNA tenant;
    per-tenant issuer validated strictly, multi-tenant `common`/`organizations`
    relaxed to audience+signature. The single-IdP `--auth jwt` (env) path stays for
    back-compat. Auth remains an optional, HTTP-only extra. The real Entra
    login→token→server check is deferred to the owner's `azd up` (a documented step
    + `requires_azure` skip); locally proven with two emulated OIDC issuers. Guide:
    *The MCP server → Multi-provider auth*.
- **Three more code-first emitters — `dna emit --target {langgraph,agno,deepagents}`**
  (feature `f-dna-emitters`, stories `s-emit-langgraph` / `s-emit-agno` /
  `s-emit-deepagents`). Built entirely on the shipped `ScaffoldEmitter` contract —
  each is a thin emitter class (Py + TS twin) plus a `prompt-only` and a
  `with-tools` template, registered in the builtins; no change to the emit core.
    - **`langgraph`** — `create_react_agent(model, tools=[...], prompt=INSTRUCTIONS)`
      (`langgraph.prebuilt`); with-tools emits `@tool` stubs. **`agno`** —
      `Agent(name, model, instructions=INSTRUCTIONS, tools=[...])` (`agno.agent`);
      Agno auto-wraps plain callables as tools. **`deepagents`** —
      `create_deep_agent(model, tools=[...], system_prompt=INSTRUCTIONS)` (LangChain
      DeepAgents).
    - **Model coordinate preserved.** Unlike `openai-agents` (which strips the
      provider token), all three resolve a `provider:model` string
      (`init_chat_model` / Agno string models), so the DNA coordinate is carried
      **verbatim** — a smaller loss. Each emitter reports its own de-para honestly
      (tool-body stubs; the `init_chat_model` provider-prefix convention; for
      deepagents the DNA prompt is a *prefix* of the harness system prompt and there
      is no name slot).
    - **One source → seven runtimes.** With these three, the `emitting-to-a-runtime`
      example emits the same `concierge` agent to **seven** runtimes (agent-framework
      / bedrock / vertex / openai-agents / langgraph / agno / deepagents) with the
      composed instruction **byte-identical** in every artifact — pinned by a new
      portability proof (`test_emit_portability.py` / `emit-portability.test.ts`) and
      inherited automatically by the generic `test_emit_contract` over every target.
      The three targets are documented with mapping tables in *Emitting to a runtime*.
- **`dna mcp serve` Phase 2 — remote transport + OAuth 2.1 auth bound to DNA
  tenancy** (feature `f-dna-mcp-server`, stories `s-mcp-remote-transport` +
  `s-mcp-oauth-auth`; ADR `adr-dna-mcp-runtime-face`). The *same* MCP server the
  MVP serves over stdio (local: Claude Code/Cursor/Copilot) is now hostable and
  authenticated for **remote/web** clients (Claude web, ChatGPT):
  - **Streamable HTTP transport** — `dna mcp serve --transport {stdio|http|sse}`
    with `--host/--port/--path`. FastMCP-native (MCP spec 2025-06-18) — a flag,
    not new transport code; the endpoint is `http://<host>:<port>/mcp/`.
  - **OAuth 2.1 Resource Server** — `--auth jwt` verifies signed bearer JWTs
    (env `DNA_MCP_JWT_PUBLIC_KEY` | `DNA_MCP_JWKS_URI` + issuer/audience) and
    advertises Protected Resource Metadata (RFC 9728) when wrapped as a Resource
    Server (`DNA_MCP_RESOURCE_URL` + `DNA_MCP_AUTH_SERVERS`). Conforms to the MCP
    Authorization spec revision 2025-11-25 (PKCE, RFC 9728/8707/8414/7591); a
    WorkOS/Auth0 `OAuthProxy` slots into the same provider seam.
  - **The auth↔tenancy bridge** (`dna_cli._mcp_auth`) — maps the verified token's
    claim (`tenant`, configurable) or scope (`tenant:<x>`) to a **DNA tenant** and
    enforces it: every tool (`compose_prompt`/`recall`/`list_stories`/…) is
    **tenant-scoped by the token**; a cross-tenant or tenant-less request is denied
    (fail closed); with no auth (stdio) the bridge is an identity, so the base path
    is untouched. Auth + multi-tenant in one mechanism. HTTP/auth are optional
    extras that never break the stdio/base install. Guide: *The MCP server — DNA as
    a live layer → Remote + authenticated*.

### Fixed

- **`dna-sdlc[bot]` is now a real, linkable committer** (SDLC git hook). The
  `Co-Authored-By` trailer used the plain noreply email
  (`dna-sdlc[bot]@users.noreply.github.com`), which GitHub renders as a gray
  identicon instead of linking to an account — GitHub links a noreply email only
  in the form `<user-id>+<login>@users.noreply.github.com`. With the `dna-sdlc`
  GitHub App created (bot user id `302582850`), the trailer emitted by
  `scripts/git-hooks/prepare-commit-msg`, its packaged copy under `dna_cli/data/`,
  and `dna_cli._git_symbiosis` now use
  `302582850+dna-sdlc[bot]@users.noreply.github.com` — hook-authored commits link
  to the bot (with its uploaded avatar) going forward. Forward-only; past commits
  keep their frozen trailer.

## [0.9.0] - 2026-07-11

### Added

- **`dna mcp serve` — the MCP runtime face (DNA as a live layer)** (epic
  `e-dna-portability`, feature `f-dna-mcp-server`, story `s-dna-mcp-server-mvp`;
  ADR `adr-dna-mcp-runtime-face`). The second face of DNA serving runtimes and
  the **inverse of `dna emit`**: where `emit` writes a *static* artifact (and
  drops composition structure, per-tenant overlay, and no-deploy change), the
  MCP server composes **live** on request — recovering exactly those axes. One
  thin server exposes **everything DNA stores** over the neutral MCP protocol,
  so any MCP client (Claude Code/Desktop, Cursor, GitHub Copilot,
  agent-framework, Bedrock AgentCore) can reach it: **definitions** —
  `compose_prompt(agent, scope?, tenant?)` (the killer surface: the live-composed
  Soul+Guardrail+instruction prompt, **tenant-aware**), `list_agents`,
  `list_tools`, `get_tool`; **SDLC** — `sdlc_digest` (reuses the same
  `build_digest` core), `list_stories`, `get_adr`; **memory** — `recall`,
  `remember`, `consolidate`; plus MCP **resources** (`dna://{scope}/manifest`,
  `dna://{scope}/agents`). The tools are thin adapters over already-tested pure
  cores — no new business logic. Built on **FastMCP** (the standalone `fastmcp`
  framework) for native stdio+HTTP transports and built-in OAuth 2.1 auth. The
  MVP is stdio (local clients); remote Streamable HTTP + OAuth-2.1-bound-to-DNA-
  tenancy are filed as Phase-2 stories (`s-mcp-remote-transport`,
  `s-mcp-oauth-auth`) — *enable + bridge*, not *build*, thanks to FastMCP. The
  `mcp` dependency is an **optional extra** (`pip install 'dna-cli[mcp]'`,
  imported lazily — the base install is unaffected). Guide: *The MCP server —
  DNA as a live layer*.
- **`dna sdlc gallery` — the board-native index of the HtmlArtifacts to review**
  (feature `f-sdlc-digest`, story `s-sdlc-gallery`). The sibling of `digest`:
  where the digest surfaces **events** ("what happened"), the gallery surfaces
  the visual **artifacts** ("the HtmlArtifacts to review"). `dna sdlc gallery
  [--html <out>] [--open] [--json] [--scope]` walks every work item's outputs
  (`produces[]` ∪ legacy back-refs) to find which work item produced each
  `HtmlArtifact`, then groups the artifacts by that work item's status —
  **👀 Precisa de avaliação** (Story in review / open PR), **🧭 Decisões**
  (produced by an ADR), **✅ Shipado** (terminal), **📈 Em andamento**, and
  **📎 Sem work item** (orphan). Because the index is generated from the board,
  it is always current — killing the "artifacts pasted into chat get lost"
  gap. `--html` writes **one self-contained** page (no CDN, theme-aware) with a
  card per artifact, a status chip, the producing work item, the published
  link, and open PRs; `--open` opens it. The aggregation core
  (`dna_cli._gallery.build_gallery` + `render_gallery_html`) is a pure,
  kernel-free function with 16 unit tests. CLI-only (Python). Guide: *Gallery —
  the artifacts you need to review*.
- **`HtmlArtifact` gains a `published_url`** — the canonical hosted location
  (e.g. a claude.ai artifact link), set via `dna sdlc artifact create
  --published-url <url>`, surfaced in `artifact show`, the Kind `summary()`
  (Py↔TS parity), and rendered as the clickable **Abrir artifact ↗** on each
  gallery card. Lives in `artifact_json` (free-form), so no schema break.
- **Third runtime emitter — `dna emit --target vertex`** (epic
  `e-dna-portability`, feature `f-dna-emitters`, story `s-emit-vertex`). The
  portability thesis, proven a *third* way: the **same** DNA agent that emits a
  Microsoft agent-framework `PromptAgent` and an AWS CloudFormation
  `AWS::Bedrock::Agent` now also emits a **Google ADK Agent Config** YAML — the
  declarative, code-free way to define an ADK `LlmAgent`
  (`config_agent_utils.from_config(<path>.yaml)`). The emitted `instruction` is
  **byte-equal** to `build_prompt(agent)` — and identical to the agent-framework
  `instructions` and the Bedrock `Instruction`: **one source → three runtimes**,
  the same composed prompt. The de-para maps `agent_class: LlmAgent`,
  `metadata.name` → `name` (snake_cased to a valid Python identifier),
  `metadata.description` → `description`, `spec.model`/Genome default → `model`
  (Gemini id; DNA provider token stripped), and `spec.tools[]` → `tools[].name`
  (ADK binds tools by *code reference*, not a declarative schema). The artifact
  leads with a `# yaml-language-server` header binding it to the real published
  `AgentConfig.json`, so it validates structurally in any editor **without a GCP
  credential**. Honest `losses` surface the ADK-specific drops (tool binding is a
  code reference so a Tool's schema/description have no declarative slot;
  `output_schema` is a Pydantic-class reference; a non-Gemini model coordinate
  needs `model_code`/LiteLlm) on top of the three DNA-only axes (composition
  structure / tenant overlay / eval-as-contract). Python + TypeScript parity
  (`dna/emit/vertex.py` + `src/emit/vertex.ts`); the shared
  `examples/emitting-to-a-runtime/` now proves all **three** runtimes. Guide:
  *Emitting to a runtime* (with the ADK mapping table).

### Changed

- **`dna sdlc produces add` now accepts an `ADR`** as a producer (not only
  Story/Spike/Feature/Epic/Issue) — an ADR legitimately produces its
  decision-visualization `HtmlArtifact`, which is what buckets it under
  **Decisões** in the gallery.

## [0.8.0] - 2026-07-11

### Added

- **`dna sdlc digest` — a retrospective "what happened while you were away"**
  (feature `f-sdlc-digest`, story `s-sdlc-delegator-digest`). The backward-
  looking mirror of `brief`/`next`/`current` (which point *forward*): the
  surface for whoever **delegates** work and reviews the board at the end
  instead of watching it live. `dna sdlc digest [--since <ref>] [--scope]
  [--save] [--json]` aggregates every work-item timeline event in a window and
  groups it — **Concluído / Decidido / Achado / Avançou / Releases / Artefatos**
  — leading with a first-class, **not-windowed** *"Precisa de você"* section:
  blocked items (with reason), Stories in review (with their open PR numbers
  matched from `gh`), owner decisions (ADRs still `proposed`), and open
  questions (unanswered Spikes), plus a PMO-style RAG status. `--since` accepts
  an ISO-8601 timestamp, a relative span (`90m`/`24h`/`3d`/`2w`), or
  `last-digest` (tiles the timeline gaplessly from the previous digest);
  default is the last 24h. `--save` persists the digest as a queryable
  `StatusReport` named `digest-<date>` (its `verdict` + `heuristic_explanation`
  are embedded, so `dna cognitive search` recalls past digests). The
  aggregation core (`dna_cli._digest.build_digest`) is a pure, kernel-free
  function with 23 unit tests. CLI-only (Python) — the `dna` binary has no TS
  twin. Guide: *Digest — what happened while you were away*.
- **Second runtime emitter — `dna emit --target bedrock`** (epic
  `e-dna-portability`, feature `f-dna-emitters`, story `s-emit-bedrock`). The
  portability thesis, *proven*: the **same** DNA agent that emits a Microsoft
  agent-framework `PromptAgent` now also emits an AWS **CloudFormation**
  `AWS::Bedrock::Agent` template — one definition, two runtimes, swapped without a
  rewrite. Target chosen after investigating AWS's three agent surfaces (Bedrock
  Agents / Strands / AgentCore): only **Bedrock Agents** has a published
  *declarative* schema, and a CloudFormation artifact is lintable + deployable
  with **no AWS credential**. The de-para is structural: `metadata.name`→
  `AgentName`, `metadata.description`→`Description`, the composed prompt
  (`build_prompt`)→`Instruction` (**byte-equal**, identical to the
  agent-framework `instructions`), `spec.model`/Genome `default_llm`→
  `FoundationModel` (DNA provider token stripped; Bedrock-native ids / ARNs pass
  through), `spec.tools[]`→`ActionGroups[].FunctionSchema.Functions[]` with a flat
  `Parameters{Type,Description,Required}` map and a `CustomControl: RETURN_CONTROL`
  executor (client-side tools, no Lambda). Honest `losses` add the Bedrock-specific
  drops: tool-parameter depth (`default`/`enum`/nested/`items`), `output_schema`,
  and the model coordinate. Plugged into the existing `EmitterPort` registry — the
  CLI core is unchanged. Python + TypeScript parity on the emitted template object;
  the `examples/emitting-to-a-runtime` example now documents both runtimes.
- **`dna sdlc cite` now cites _any_ citable Kind — not just `Reference`**
  (epic `e-dna-portability`, feature `f-dna-sdlc-expressiveness`, story
  `s-cite-any-citable-kind`). The cited target accepts `<Kind>/<name>` —
  `dna sdlc cite Research/<name> --from ADR/<name>` (or from an Epic, Spec,
  Story, …) — while a bare `<name>` still defaults to `Reference` for
  backwards-compat. The citation stays **bidirectional**: the cited doc gains
  `spec.cited_by` (the back-ref) and the caller gains `spec.references`. This
  encodes the semantic the model had to bridge by hand during the pivot —
  **`cite` = a source that _grounds_ the work; `produces` = an output the work
  _authored_.** The `Research` Kind gains an explicit `cited_by` field (Py↔TS)
  for discoverability; other SDLC Kinds inherit it via their flexible specs.
  `uncite` is symmetric across Kinds.

### Fixed

- **`dna sdlc epic show` now lists an Epic's features** (feature
  `f-dna-sdlc-expressiveness`, story `s-epic-show-forward-features`). It read
  the forward `Epic.spec.features[]` list, which `feature create --epic X`
  never populates (it maintains only the back-ref `Feature.spec.epic`), so a
  correctly-linked Epic still printed "(no features linked)". Features are now
  resolved by **reverse-lookup** on `Feature.spec.epic == <epic>` — the back-ref
  is the single source of truth, mirroring how `feature show` finds its stories
  by `Story.spec.feature`. The forward link is intentionally _not_ populated
  (no duplicate source of truth). `dna sdlc epic ship` had the identical
  latent bug in its cascade-close and is fixed the same way.

## [0.7.0] - 2026-07-11

### Added

- **Vendor-neutral emitters — `dna emit` + the `dna.emit` port/registry**
  (epic `e-dna-portability`, feature `f-dna-emitters`, story
  `s-emit-agent-framework`). The pivot's first concrete step: DNA is a
  vendor-neutral **definition** layer that authors an agent **once** (Agent +
  Soul + Guardrail + Tool Kinds) and **materializes the native artifact each
  runtime consumes** — "author once, emit per runtime". New CLI:
  `dna emit <agent> --target <t> [--scope --out --model --provider --json]` and
  `dna emit --list-targets`. First proven target: **Microsoft agent-framework**
  (`--target agent-framework`) — emits the declarative `PromptAgent` YAML that
  `AgentFactory` loads. The de-para is **structural**, not a string dump:
  `metadata.name`→`name` (CamelCase), `metadata.description`→`description`,
  the composed prompt (`build_prompt`: Soul + guardrails + instruction)→
  `instructions` (**byte-equal**), `spec.model`/Genome `default_llm`→
  `model.{id,provider}`, `spec.tools[]` (the `Tool` Kind)→`tools[]`
  (`kind: function`, carrying each tool's description + input JSON Schema),
  `spec.output_schema`→`outputSchema`. Axes with no target slot (composition
  structure, tenant overlay, eval-as-contract) are reported honestly in
  `EmitResult.losses`. Targets are a **pluggable registry** (`EmitterPort` +
  `register_emitter`) — a new one (bedrock/vertex/openai) is a class + one call,
  the CLI core never changes. Exposed from the package root on both runtimes
  (`dna.emit_agent` / `emitAgent`); the pure de-para is Py↔TS parity-checked.
  Committed example + fixture: `examples/emitting-to-a-runtime/`. Proof: the
  emitted `instructions` is byte-equal to `build_prompt` and the artifact loads
  into a live agent-framework `Agent` (a gated test that skips without the
  runtime). Guide: **How-to → Emitting to a runtime (the de-para)**.

## [0.6.0] - 2026-07-11

### Added

- **Tools as data — `load_tools` + the `Tool` Kind as a descriptor**
  (feature `f-dna-tools-as-data`). The agent-facing surface of a tool — the
  `description` a model reads to decide whether to call it, and the JSON Schema
  of its `parameters` — is now consumable as data, the twin of `load_prompts`:
  `dna.load_tools(scope)` / `loadTools(scope)` returns a `ToolLibrary` mapping a
  tool name to its `ToolSurface` (`{description, parameters}` =
  `{metadata.description, spec.input_schema}`), lazy + cached, exported from the
  package root on both runtimes. A miss raises the typed, exported
  `ToolNotFound` (a `LookupError`) — never an empty surface. New CLI: `dna new
  tool <name> [-d --type]` scaffolds a valid Tool through `kernel.write_document`
  (idempotent; `--force`). Overlay-aware: a tenant overlay of a tool's
  description/parameters wins for that tenant while the base stays intact.
  Cross-language dogfood under `examples/tools_as_data/` — the **same** Tool
  document read by Python and TypeScript yields **byte-identical** surfaces
  (asserted against one committed oracle by both suites): the first place the
  Py↔TS descriptor parity pays off in a real consumer. Guide: **How-to → Tools
  as data**.

### Changed

- **The `Tool` Kind migrated from a hand-written class to a record-plane
  descriptor** (`helix/kinds/tool.kind.yaml`, byte-identical Py↔TS), per the
  repo's own ratchet (record Kinds are data, not classes). The alias
  (`helix-tool`), storage (`tools/<name>.yaml`), schema, Studio UI metadata and
  agent references (`dep_filters.tools`) are unchanged. Because a Tool is not a
  prompt target, it now correctly lives on the **record** plane: writing a Tool
  no longer invalidates the composition schema cache, and an agent's `tools:`
  ref pointing at a not-yet-shipped Tool is resolved lazily (host-resolved)
  instead of being flagged as a missing composition input.
- **Ship a scope with your app — resolve a scope as PACKAGE DATA** (feature
  `f-dna-scope-packaging`; stories `s-scope-as-package-data`,
  `s-pkg-source-scheme`). A deployed app can now let its DNA scope TRAVEL inside
  the deployable, resolved from *inside* the installed package — no fragile
  `Path(__file__).resolve().parents[N] / ".dna"` navigation and no manual
  `COPY .dna` in the Dockerfile (the image is the app, not the repo; forget the
  copy and the app boots with no scope — a real pilot bug). Two surfaces, in
  Python↔TypeScript parity:
  - `load_prompts(scope, *, anchor="mypkg")` / `loadPrompts(scope, { anchor })`
    — `anchor` is a package name; the scope is resolved via
    `importlib.resources` (Py) / the package's own location (TS), so it works
    identically from a source checkout, an installed wheel, and a Docker image.
    Precedence: `base_dir` arg > `$DNA_BASE_DIR` > `anchor` (package data) >
    `.dna` (cwd).
  - A `pkg://<package>[/<subpath>]` **source scheme** for `dna.config.yaml` /
    `Kernel.from_config` (subpath defaults to `.dna`), resolving the embedded
    scope to a **read-only** filesystem source. Both surfaces fail loud with a
    packaging-oriented message on a missing package/subpath.
  - New helper `dna.anchor_scopes_root` / `anchorScopesRoot` (+
    `PackageScopeNotFound`) exposes the resolution directly.
  - New guide **"How to ship a scope with your app"** (Hatch / setuptools / npm
    packaging + the Docker contrast) and a runnable example
    (`examples/shipping-a-scope/`) with a test that installs the example and
    resolves the scope from a DIFFERENT working directory — the Docker scenario.

### Fixed

- **CLI boot now wires the `LocalResolver` — `dna eval run` resolves `local:`
  deps identically to the SDK** (s-cli-localresolver-consistency, kaizen
  `kz-001`; feature `f-dna-dx-configure`). The `dna` CLI built its kernel via
  `Kernel.auto()` **without a source** and attached the source afterwards, so
  `build_auto_kernel`'s resolver-wiring branch (guarded by `source is not None`)
  never ran — the CLI kernel had **zero resolvers**. A dependency declared as
  `local:<scope>` therefore resolved through `Kernel.quick` (which wires the
  resolvers) but silently **failed to resolve** through `dna eval run` and every
  other CLI command: same composition, two results. The resolver set is now
  wired by one shared recipe (`kernel_bootstrap.wire_filesystem_resolvers`) used
  by `Kernel.quick`, `Kernel.auto`/`Kernel.from_config` (filesystem source), and
  the CLI boot path. Non-filesystem sources (SQLite/Postgres) have no
  scopes-root directory, so `LocalResolver` is a documented no-op there. As a
  side benefit, the `auto`/`from_config` path now also registers the `github` /
  `http` / `https` / `registry` / `helix` resolvers (previously `local`-only),
  matching `Kernel.quick` and the TypeScript `fromConfig`. The `dna` CLI is
  Python-only; the TypeScript `quickInstance` / `fromConfig` already wired their
  resolvers, so there was no TS-side gap to fix.

## [0.5.0] - 2026-07-11

### Added

- **`HtmlArtifact` Kind — an HTML page as a first-class work-item output**
  (s-dx-html-artifact-kind, epic `e-dna-dx`). A bundle Kind (record plane,
  alias `sdlc-html-artifact`) registered by the `sdlc` extension in both
  runtimes: `ARTIFACT.html` stores the raw HTML **byte-faithful** (the writer
  never injects frontmatter or re-escapes — a design doc / roteiro / rendered
  report round-trips untouched), plus an optional `artifact.json` companion
  with structured metadata (`title`, `description`, `source`, `created_at`) —
  the same mechanic as a Soul's `SOUL.md` + `soul.json`. Custom reader/writer
  with proven Py↔TS round-trip parity. New CLI: `dna sdlc artifact create
  <name> --from <file.html> [--title --description --source]`, plus `artifact
  list` / `artifact show [--html]`. Attach one to the board with `dna sdlc
  produces add <WiKind>/<wi> HtmlArtifact/<name>`. DNA dogfoods it — the
  `e-dna-dx` epic **produces** its own design doc as
  `HtmlArtifact/ha-e-dna-dx-design`. Guide: **SDLC → Work items produce
  artifacts**.
- **Named composition layouts — order the persona by name, no Mustache**
  (s-dx-named-layouts, epic `e-dna-dx` / feature `f-dna-dx-author`). An Agent
  spec now accepts a `layout:` field: `persona-first` puts the Soul before the
  instruction, `instruction-first` (a.k.a. `default`, the historic order) keeps
  it after. The kernel resolves the name to an embedded template via a new
  KindPort extension point (`layout_template()` / `layoutTemplate()`), so the
  common case never hand-writes `{{{soul_content}}}` / `{{#guardrails-guardrail}}`.
  A raw `promptTemplate` still wins over `layout` (the poweruser escape hatch);
  an unknown layout fails loud with the new `UnknownLayout` error (exported from
  the package root, Py + TS). Guardrails always compose last. Py↔TS 1:1. Guide:
  **Authoring agents**.
- **`dna new agent|soul|guardrail <name>` — scaffold a valid skeleton**
  (s-dx-new-scaffolding). Writes the correct envelope + bundle shape into a
  scope through `kernel.write_document` (every write guard runs), leaving only
  the prose to fill in. `dna new agent` pre-fills `--soul` / `--guardrails` /
  `--layout` / `--model`; `dna new soul` emits a single-file `SOUL.md`. Idempotent
  (never clobbers without `--force`). Guide: **Authoring agents**.

### Changed

- **Single-file souls are a first-class authoring path** (s-dx-single-file-soul).
  A Soul authored as a lone `SOUL.md` (minimal frontmatter or none) reads and
  composes — `soul.json` is now optional, not required. The two-file
  soulspec.org bundle (`SOUL.md` + `soul.json` manifest) stays fully supported
  and byte-faithful on round-trip (market-conformance suite unchanged); the
  single-file form is the convenience on-ramp. Py↔TS 1:1.
- **TS composition now includes the guardrails block** (aligns the TypeScript
  Agent default template to Python, which was the semantic reference — closing
  the latent i-213/i-011 divergence where TS `promptTemplate()` omitted it).
  Composed prompts in the TS SDK now carry the same guardrail policy section as
  Python.

## [0.4.0] - 2026-07-11

### Added

- **`dna.load_prompts(scope, base_dir=None)` — compose prompts in one line**
  (s-dx-load-prompts-helper, epic `e-dna-dx`). Returns a `PromptLibrary`, a
  lazy/cached read-only mapping from agent name to its composed, already-clean
  system prompt; a missing agent raises `AgentNotFound`. Collapses the
  ~166-line defensive prompt shim a real consumer wrote (boot kernel + resolve
  base dir + `mi.one("Agent", x) is None` guard + `.rstrip("\n")`) down to
  `prompts = load_prompts(scope); TRIAGE = prompts["triage"]`. TS twin
  `loadPrompts` / `PromptLibrary` (composition is async, so `await
  prompts.get("triage")`). Guide: **Consuming prompts**.
- **`dna.config.yaml` + `Kernel.from_config(path=None)` — declarative port
  wiring** (s-dx-kernel-from-config). A language-agnostic config file selects
  the `source` (`file://` / `sqlite://` / `postgresql://`), and optionally the
  `search` (`pgvector` / `sqlite-vec` / `off`) and `embedding` (`onnx` /
  `fake` / `off`) providers; `Kernel.from_config` resolves every port to its
  adapter and returns the wired kernel. No config present → the current
  filesystem `.dna` behavior, unchanged. TS twin `fromConfig`. The URL→source
  factory is now a **public** surface (`dna.adapters.source_from_url` /
  `sourceFromUrl`) that actually supports `sqlite://` / `postgresql://` via the
  existing `SqlAlchemySource`; the `dna` CLI consumes the same factory (so
  `DNA_SOURCE_URL=sqlite://…` / `postgresql://…` now Just Works). `sqlite://`
  is Python-only in the TS runtime and fails loud there. Guide: **Configuring
  ports**.
- **`dna sdlc epic create <name>`** (s-dx-epic-create) — closes the last CRUD
  gap in the SDLC CLI. Story and Feature had `create`; an Epic previously had
  to be hand-authored via `dna doc apply`. Mirrors `feature create` (same
  flags, same `kernel.write_document` path, same initial timeline event).

### Changed

- **BREAKING — `build_prompt` fails loud on a missing agent**
  (s-dx-build-prompt-fail-loud). `mi.build_prompt(agent=X)` (and its async /
  record-plane twins, and the TS `mi.buildPrompt`) now **raise**
  `AgentNotFound` (Python: a `LookupError`; TS: an `Error` with `.agent`)
  instead of RETURNING the string `"Agent 'X' not found"`. The old behavior
  let a missing/renamed agent sail through an `if not text` check and become
  the literal instruction — every consumer wrote the same `mi.one("Agent", x)
  is None` guard to defend against it. `AgentNotFound` is exported from the
  package root. Migration: replace the guard + `.rstrip` shim with a
  `try/except AgentNotFound` (or just let it propagate) — or adopt
  `load_prompts`, which does it for you.
- **BREAKING — `build_prompt` returns clean output**
  (s-dx-clean-composition-output). Composed prompts no longer carry trailing
  newlines leaked from template sections; the builder strips them. Consumers
  that hand-wrote `.rstrip("\n")` can drop it. If you pinned an exact composed
  string that ended in `\n`, update the expectation.

## [0.3.1] - 2026-07-10

### Fixed

- **`dna install` no longer hides sibling documents when a reader claims the
  tree root** (s-install-scan-fixes, closes i-016). A claim now consumes its
  *bundle* — whose authoritative extent is the paired writer's
  `serialize()` — instead of the whole subtree, so a root `AGENTS.md`
  coexists with `skills/` (mixed trees install completely) while Skill
  bundles still yield exactly one document. Claims without a paired writer
  keep the old conservative subtree semantics. `dna init --from` now
  delegates to the fixed scan (its PR #41 workaround was removed), and a
  `requires_network` test consumes the public `examples/onboarding-pack`
  from the default branch (closes i-017).

## [0.3.0] - 2026-07-10

### Added

- **`dna init --from` — distributed onboarding packs**
  (s-onboarding-genome-install, closes i-015). `dna init` can now source its
  assets from a remote pack instead of the embedded Genome:
  `dna init --from github:owner/repo[/subdir][@ref]` (or a local path). Every
  valid Skill in the pack is projected per `--tools`; a root `AGENTS.md`
  replaces the embedded one (absent → embedded fallback, noted). `--from`
  only projects to tool directories — `dna install` remains the channel that
  writes documents to the source; the two compose over the same ref. Pack
  content is untrusted and goes through the same install defenses
  (registered Kinds, JSON Schema, slug-only names). A public example pack
  ships in `examples/onboarding-pack/`.
- **Memory conformance kit** (s-memory-conformance-kit). `dna.testing` now
  ships a public conformance suite for memory: 10 verb invariants
  (remember→recall roundtrip, bi-temporal forget with no hard deletes,
  idempotent consolidate, strictly decreasing Ebbinghaus retention under
  simulated time, text-hash-idempotent backfill, honest lexical fallback)
  plus 7 pure scoring invariants mirrored 1:1 in `dna-sdk/testing` for
  TypeScript (ecphory weights/threshold, RRF fusion, cosine ordering).
  Runs against the builtin providers (filesystem, sqlite-vec, pgvector)
  and against custom `RecordSearchProvider`/`EmbeddingPort` implementations
  via the public factory API.

### Changed

- `dna-cli` now depends on `dna-sdk>=0.3,<0.4`.

## [0.2.0] - 2026-07-10

### Added

- **`dna init` — multi-tool agent-ready onboarding** (s-dna-init-agent-ready).
  One command scaffolds a consumer project for AI-assisted development: a
  `.dna/<scope>` board, a canonical `AGENTS.md` (agents.md/v1), the
  `dna-sdlc-cli` skill materialized per tool directory
  (`--tools claude,copilot,cursor,opencode`, default `claude,copilot`,
  `all` supported), and the `Work-Item:` git hooks. The skill ships inside
  the package as a real Kind and is projected byte-faithfully by the
  agentskills writer — one Kind, N projections. Idempotent: existing files
  are never overwritten without `--force`; the board is never rewritten.
  See the [agent onboarding guide](docs/getting-started/agent-onboarding.md).
- **Semantic recall in memory** (s-memory-semantic-recall). `recall` now
  feeds the previously inert semantic path of the ecphory scorer: when an
  `EmbeddingPort` + `RecordSearchProvider` are configured, results blend the
  existing hybrid retrieval with ecphory×cosine ranking via RRF. Opt-out
  with `--no-semantic`; without a provider the behavior is byte-identical
  to previous releases (offline-first, no schema migration — lazy backfill
  indexes older memories on demand). See the
  [semantic recall guide](docs/guides/semantic-recall.md).

### Changed

- `dna-cli` now depends on `dna-sdk>=0.2,<0.3`.

## [0.1.0] - 2026-07-10

The first tagged release — the extracted public core, published to the
registries: **PyPI** ([`dna-sdk`](https://pypi.org/project/dna-sdk/),
[`dna-cli`](https://pypi.org/project/dna-cli/)) and **npm**
([`dna-sdk`](https://www.npmjs.com/package/dna-sdk)).

### Added

- **Published packages** (s-publish-registries). `pip install dna-sdk dna-cli`
  and `npm install dna-sdk` are now the primary install paths (the repo
  remains the pre-release/exact-pin alternative). The TypeScript package was
  renamed `@dna/sdk` → `dna-sdk` (unscoped, mirroring PyPI) and gained a
  publication build — compiled ESM JS + type declarations in `dist/`,
  including the runtime `*.kind.yaml` descriptors and `DOCS*.md` kind docs
  that the extensions load relative to their own compiled modules. `dna-cli`
  now depends on `dna-sdk>=0.1,<0.2` (resolved from PyPI in published
  artifacts; the dev workspace keeps the editable path source). Releases are
  cut by pushing a `vX.Y.Z` tag: tag-triggered workflows (`release.yml` +
  `release-cli.yml` — one PyPI project per workflow file, a PyPI
  pending-publisher dedup constraint) build sdist+wheel for both Python
  packages and publish them via PyPI trusted publishing (OIDC, no long-lived
  token), and publish the npm package with provenance via npm OIDC trusted
  publishing (no token; the first npm publish is manual). See `RELEASING.md`.
- **Write-path schema validation** (i-008). `write_document` /
  `writeDocument` now validate the doc's `spec` against the Kind's declared
  `schema()` **before persisting** — previously schemas were only checked at
  scan/read (fail-soft), so a shape-broken doc persisted and exploded later,
  far from the author. Kinds without a schema stay permissive; descriptor
  `spec_defaults` fill before validation; the veto error is didactic (field,
  violation, `dna kind show <Kind>` hint). Escape hatches:
  `DNA_WRITE_VALIDATION=warn|off` (default `enforce`). The Automation write
  guard dropped its now-redundant local shape check and keeps only its
  Kind-specific cures (YAML-1.1 `on:` heal, cron/hook semantics).
- **Microkernel + extensions core.** A kernel that mediates five ports —
  source, cache, resolver, reader/writer, and kind — and knows no Kinds
  itself; extensions register Kinds onto it via `kernel.load(ext)`.
- **Dual SDK, one behavior.** Python (`packages/sdk-py`, `import dna`) and
  TypeScript (`packages/sdk-ts`, `dna-sdk`) implementing the same kernel 1:1,
  with a test-enforced Python↔TypeScript parity contract (port-surface parity,
  descriptor hash parity, kind-registry parity, composition parity).
- **Core Kinds** under `github.com/ruinosus/dna/...` — `Genome`, `Agent`,
  `Guardrail`, `Actor`/`UseCase`, `Tool`, `Hook`, `SafetyPolicy`, `Theme`,
  `Setting`, `LayerPolicy`, `Tenant`/`TenantMembership`, and governance Kinds
  (`Evidence`, `AuditLog`, `Comment`, `MCPFederation`, `Recognizer`).
- **`KindDefinition`** — a Kind that defines Kinds: register new record Kinds
  with a `*.kind.yaml` descriptor and no code. Descriptors are byte-identical
  across the two SDKs (hash-enforced).
- **Market-format fidelity.** Byte-faithful readers/writers for standards DNA
  did not invent, consumed under their owners' namespaces — Agent Skills
  (`agentskills.io/v1`, `SKILL.md` bundles), Souls (`soulspec.org/v1`,
  `SOUL.md` + companions), and `AGENTS.md` (`agents.md/v1`). Enforced by a
  conformance suite over real marketplace fixtures with byte-identical
  round-trip.
- **Source adapters** — filesystem (the default for development) and SQL
  (`SqlAlchemySource`: sqlite + postgres dialects, one adapter) — behind a
  capability-aware `SourcePort`.
- **Multi-tenancy and layer composition** — tenants as a first-class kernel
  dimension orthogonal to layers, with `LayerPolicy` governing which layers
  may override which Kinds.
- **The `dna` CLI** (`packages/cli`) — document CRUD (`dna doc`, `dna kind`,
  `dna scope`, `dna source`) plus a declarative, story-first SDLC
  (`dna sdlc`): Stories/Features/Issues tracked as DNA documents, versioned
  `prepare-commit-msg` commit-trailer hooks, and `dna sdlc story pr` that
  assembles a pull request from the Story.
- **The Research Kind** (`github.com/ruinosus/dna/research/v1`) — curated,
  multi-finding syntheses stored as documents, authored via `dna research`.
- **The public conformance kit** (`dna.testing`) — ship-with-the-SDK source
  and reader/writer compliance suites for adapter authors, in the spirit of
  the DB-API compliance suite.
- **Community-health baseline** — this CHANGELOG, plus `CONTRIBUTING`,
  `SECURITY`, `CODE_OF_CONDUCT`, issue forms, and a PR template.

### Changed

- **Python floor lowered to 3.12** (`requires-python = ">=3.12,<3.14"` for
  `dna-sdk` and `dna-cli`, s-py312-floor). The first real consumer of the
  SDK — a backend on Azure Container Apps pinned to `>=3.12,<3.13` — could
  not install it under the previous 3.13-only floor, a convenience decision
  from PR #1 whose single deliberate 3.13-ism was PEP 696
  `TypeVar(default=...)` in `dna/kernel/document.py`. That import is now
  version-gated: stdlib `typing` on 3.13+, `typing_extensions>=4.4` on 3.12
  (an env-markered dependency — zero cost on 3.13+ installs). A full-suite
  sweep under 3.12 found no other accidental 3.13-isms, and the CI matrix
  now runs sdk-py + cli on {3.12, 3.13} so the floor cannot regress
  silently. Ecosystem libraries support N-1.

### Removed

- **The raw Python SQL adapters** (`s-retire-raw-sql-adapters`). The
  asyncpg-based `PostgresSource` and the aiosqlite-based `SqliteSource` are
  gone; `SqlAlchemySource` (`dna.adapters.sqlalchemy_`) is the Python SDK's
  only SQL source. It binds to the **exact same tables and migrations** the
  raw adapters created, so **switching is pure instantiation — zero data
  migration**:

  ```python
  # before                                   # after
  SqliteSource(db_path="app.db")             SqlAlchemySource("sqlite+aiosqlite:///app.db")
  PostgresSource(pool, schema="public")      SqlAlchemySource("postgresql+asyncpg://…", schema="public")
  ```

  The `postgres` / `sqlite` extras keep their names and now install
  `sqlalchemy[asyncio]` plus that dialect's driver (`sql` is the umbrella
  for both); nothing in the default install imports sqlalchemy. The
  `PostgresEventBus` subscriber is unchanged (the pg dialect emits the same
  outbox + `kernel_writes` NOTIFY contract, now homed in
  `dna.kernel.eventbus`), and the pg dialect keeps the native COUNT
  push-down. Retiring the raw PG adapter also retires its two known
  defects (i-001 `_acquire_safe` connection leak, i-002 asyncpg
  pool-close hang) — the SQLAlchemy pool does not exhibit them. The
  TypeScript SDK is untouched: its raw `PostgresSource` remains the single
  TS SQL adapter (documented asymmetry — TS has no SQLAlchemy to
  consolidate onto).

### Fixed

- **`dna source diff`/`push` were blind to base-layer content** (i-006).
  `digest_manifest` read the base via `load_layer(scope, "tenant",
  "__base__")`, which real adapters treat strictly as a tenant-overlay
  read — both sides digested `{}` and every diff reported "in sync".
  The base now digests through `load_all` (the canonical base-read
  path); explicit `--tenant` overlays keep using `load_layer`. `push`
  additionally publishes drafts on draft-staged targets (SQLite) so
  pushed docs become visible, and relative `fs://./path` URLs resolve
  correctly instead of silently pointing at an absolute path. The
  source conformance kit now pins the contract: base content is served
  by `load_all`, never by a `load_layer` sentinel.

[Unreleased]: https://github.com/ruinosus/dna/compare/v0.17.0...HEAD
[0.17.0]: https://github.com/ruinosus/dna/compare/v0.16.0...v0.17.0
[0.13.0]: https://github.com/ruinosus/dna/compare/v0.12.0...v0.13.0
[0.12.0]: https://github.com/ruinosus/dna/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/ruinosus/dna/compare/v0.9.0...v0.11.0
[0.9.0]: https://github.com/ruinosus/dna/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/ruinosus/dna/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/ruinosus/dna/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/ruinosus/dna/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/ruinosus/dna/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/ruinosus/dna/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/ruinosus/dna/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/ruinosus/dna/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ruinosus/dna/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ruinosus/dna/releases/tag/v0.1.0
