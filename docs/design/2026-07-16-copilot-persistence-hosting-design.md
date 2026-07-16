# Design: Copilot Persistence + Hosting (Copilot Kind extension for 0.17.0)

**Date:** 2026-07-16 · **Status:** Accepted (owner-approved design; pre-implementation)
**Epic:** `e-dna-copilot-absorption`
**Features:** `f-copilot-persistence` · `f-copilot-hosting` · `f-copilot-infra-binding`
**Inputs:** the storage/state research + the hosted-agent research (2026-07-16); owner decisions.

Two new dimensions extend the `Copilot` Kind so a declarative definition controls
(a) the agent's **storage/state backends** and (b) its **deployment/hosting model** —
and both flow to the **Terraform** migration modules. Ships in the **0.17.0** release
BEFORE the DNA Cloud consumer, so the consumer is born with real persistence (not the
current hardcoded `InMemoryDb()`).

---

## 1. Persistence (`f-copilot-persistence`)

Every framework separates the same axes: **checkpoint/thread-state** (short-term),
**long-term memory** (cross-session), **vectors** (RAG), + a LangGraph-only **cache**.

### The block
```yaml
Copilot:
  persistence:
    checkpoint: { backend: postgres, ref: primary-pg }   # thread/run state — survives restart/resume
    memory:     { backend: postgres, ref: primary-pg }   # cross-session long-term memory
    cache:      { backend: null }                         # LangGraph-only; null elsewhere
  knowledge:                                              # existing field, extended:
    collections: [rfp-corpus]                             #   WHAT (the corpus)
    store: { backend: pgvector, ref: primary-pg,          #   WHERE (the vector store — DECIDED: inside knowledge)
             embed: { model: text-embedding-3-small, dims: 1536 } }
```
Each slot = `{backend, ref}`; `ref` points at an infra resource. **Multiple slots may
share one `ref`** (one physical Postgres — distinct tables/objects per framework). The
vector store lives **inside `knowledge`** (owner decision — corpus + its store cohesive).

### Emit map (backend → framework class)
| slot=backend | LangGraph | Agno | MS-AF |
|---|---|---|---|
| checkpoint=postgres | `PostgresSaver` | `PostgresDb` | *serialize → PG column* |
| checkpoint=mongo | `MongoDBSaver` | `MongoDb` | Cosmos (.NET) / serialize |
| memory=postgres | `PostgresStore` | `db=` + `enable_user_memories` | mem0 / VectorStore |
| memory=mongo | **null (gap)** | `MongoDb` | mem0 |
| vectors=pgvector | Store `index=` / `PGVector` | `PgVector` | `PostgresVectorStore` |
| vectors=mongo-atlas | `MongoDBAtlasVectorSearch` | `MongoVectorDb` (Atlas-only) | `CosmosMongoCollection` (vCore) |

Where a framework can't express a slot → emit **null** + document it (honest config,
never broken). This **kills the hardcoded `InMemoryDb()`**.

### v1 scope (owner decision)
- **Postgres FUNCTIONAL** across all 3 (one `DB_URI` → checkpoint + memory + pgvector).
- **Mongo DOCUMENTED** — a `docs/guides/copilot-persistence-mongo.md` guide with the
  per-framework Mongo config + the honest gaps (LangGraph has no Mongo memory Store;
  MS-AF is lopsided — Redis Python-only, Cosmos .NET-only, no Postgres thread-store).
  The `backend` enum is **open** (`mongo|redis|cosmos|azure-ai-search`) — emit when built.
- **v2→v1 hazards to pin at build:** Agno v2 `agno.db.*` surface (not v1 `agno.storage.*`);
  `MongoVectorDb` class name (not `MongoDb`); MS-AF `AgentThread`↔`AgentSession` rename;
  LangGraph community `redis` package.

---

## 2. Hosting (`f-copilot-hosting`)

Beyond the self-hosted AG-UI app we already emit, emit the **hosted** variant — a
container image + manifest deployed to a managed service. **`hosting.mode` is a variant
selector over ONE agent def** (owner-confirmed): the same agent emits BOTH the per-user
AG-UI app AND the single-identity hosted agent; the hosted variant **degrades** (strips
per-user OBO / per-user memory / HITL).

### The block
```yaml
Copilot:
  hosting:
    mode: self-hosted        # self-hosted (the AG-UI app) | hosted
    target: foundry          # foundry | langgraph-platform | agentos
    resources: { cpu: "0.5", memory: 1Gi }
    image:
      registry_hint: acr     # acr | ghcr | ecr | dockerhub
      remote_build: true      # Foundry ACR remoteBuild; else local
      base_image: null        # null → framework default
      port: null              # null → framework default (8088 / 8123 / 7777)
    env: {...}               # non-secret config
    stores: { postgres: required, redis: required }   # langgraph/agentos only
```

### The asymmetry (shapes the design)
| | **Foundry (MS-AF)** | **LangGraph Platform** | **Agno AgentOS** |
|---|---|---|---|
| Managed runtime? | **Yes** (true managed) | Yes (SaaS)/self-host | **No** — self-host only |
| Manifest | `azure.yaml` (`host: azure.ai.agent`) | `langgraph.json` | none (Python `AgentOS(...)`) |
| Dockerfile | you write (8088, linux/amd64) | generated from config | thin compose |
| Protocol | **Responses** | LangGraph Server API | REST / AG-UI |
| Identity | **per-agent Entra ID** (single-service) | shared server | single-service JWT |

### v1 scope (owner decision — Foundry first-class, others documented)
- **`target: foundry` = FIRST-CLASS.** Emit `Dockerfile` (port 8088, `linux/amd64`),
  `main.py` (`agent_framework_foundry_hosting.ResponsesHostServer`), `requirements.txt`,
  and the **`azure.ai.agent` service block in `azure.yaml`** (NOT the deprecated
  `agent.yaml` — optional legacy only). `resources` → sandbox tier; `identity: service`
  native. The hosted variant strips per-user concerns.
- **`langgraph-platform` + `agentos` = DOCUMENTED** as "self-host + optional control
  plane" — the abstraction leaks (LangGraph is a stateful server; Agno has no managed
  runtime). Emit the self-host artifacts + document; lower v1 priority. Honest about it.
- **Coexistence:** the same Copilot emits self-hosted AG-UI **and** hosted-foundry.

---

## 3. Infra binding (`f-copilot-infra-binding`) — the Terraform closure

Each `{backend, ref}` (persistence) and each hosting target becomes **input to the
Terraform migration modules** (the accepted Terraform migration ADR). The Copilot
definition drives the infra — declarative all the way down.

| Declared | Terraform/Bicep provisions |
|---|---|
| **persistence postgres/pgvector** | Postgres server + db + secret + `CREATE EXTENSION vector` (Azure Flex: `vector` in `azure.extensions`). Tables auto-create via each framework's `.setup()` → TF provisions server+db+extension, not tables. |
| **persistence mongo/atlas** | `mongodbatlas_cluster` + user + IP list + `mongodbatlas_search_index` (vectorSearch). Self-hosted Mongo ≠ Atlas `$vectorSearch`. |
| **persistence redis** | Managed Redis (RediSearch) + secret. |
| **hosting: foundry** | CognitiveServices `accounts` + `accounts/projects` (SystemAssigned MI) + `accounts/deployments` (model) + `ContainerRegistry/registries` + AppInsights + Log Analytics + `accounts/connections` + RBAC (project MI → **AcrPull**; agent → **Azure AI User**). The **agent version is NOT an ARM resource** — a post-provision `azd deploy` / SDK step. |
| **hosting: langgraph** | compute (Container App/ECS/K8s via Helm) + managed **Postgres + Redis** + registry + secrets (`LANGGRAPH_CLOUD_LICENSE_KEY`, …). |
| **hosting: agentos** | compute + managed **Postgres/pgvector** + registry + JWT secrets + ingress. |

`ref` → the TF module's output (connection string/endpoint + secret) injected into the
emitted copilot's env.

---

## 4. Copilot Kind schema additions

Add to `copilot.kind.yaml` (Py + TS byte-identical twin, `test_descriptor_hash_parity`):
- `persistence: {checkpoint?, memory?, cache?}` each `{backend: enum, ref: string}`.
- `knowledge.store: {backend: enum, ref: string, embed: {model, dims}}` (extend existing `knowledge`).
- `hosting: {mode: enum, target: enum, resources?, image?, env?, stores?}`.
All optional (a self-hosted, in-memory, no-RAG copilot declares none — back-compat).
Projected into `EmitContext` (new fields) via `build_copilot_context`.

---

## 5. Build order (one coherent pass, after #8 langgraph merges)

1. **Kind + EmitContext** — the `persistence`/`knowledge.store`/`hosting` fields + projection (Py+TS twin).
2. **Persistence emit** — the 3 scaffolds (Agno/MS-AF/LangGraph) read persistence → real config (Postgres); the Mongo guide.
3. **Hosting emit** — the Foundry hosted variant (Dockerfile/main.py/requirements/azure.yaml) first-class; langgraph/agentos documented.
4. **Infra binding** — the `ref`/target → Terraform module inputs (`f-copilot-infra-binding`).
5. **Regenerate goldens + reference; brand-guard clean; Py+TS green.**

All three features land in **0.17.0** (before the DNA Cloud consumer).

---

## 6. Honest gaps (documented, not hidden)

- **Persistence:** LangGraph no Mongo memory Store / no SQLite Store; Agno no first-class
  cache; MS-AF no Postgres thread-store (serialize-yourself). Emit null + document.
- **Hosting:** only Foundry is a true managed hosted runtime; LangGraph is a stateful
  server (abstraction bends — `identity`/`protocol` don't map); Agno has no managed
  runtime (`mode: hosted` ≈ `self-hosted` + control-plane registration).
- **MCP RBAC role floors** (`f-copilot-mcp-rbac-emit`, from the retrofit) — a separate
  follow-up, not in this release.
