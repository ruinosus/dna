# Copilot infra binding (the Terraform closure)

A servable `Copilot` declares three infra-shaped dimensions —
`persistence` (checkpoint / memory / cache), `knowledge.store` (the vector store),
and `hosting` (the deployment target). This guide documents how DNA turns those
declarations into **Terraform module inputs**: the `dna emit <copilot> --infra`
command renders a `<agent>.tfvars.json` that the DNA Cloud Terraform modules
(the accepted [Terraform migration ADR][adr]) consume to provision the exact
resources the emitted copilot needs — and how each resource's Terraform **output**
(a connection string / endpoint + secret) is injected back into the copilot's env.

This is the last link in *"DNA as the Terraform of agents"*: the same declarative
source that emits the agent, the serving app, and the console also drives the
**infrastructure** — declarative all the way down. It closes the loop the design's
§3 opened.

> **This emit produces the module INPUTS, not the modules.** The `.tf` module
> implementations live downstream in `dna-cloud` (the Terraform-ADR execution).
> This guide is the **contract** those modules implement: the input shape they
> accept and the output shape they must expose.

## The one command

```console
$ dna emit memory-copilot --infra --scope concierge --out infra/
Emitted memory-copilot infra → terraform: memory_agent.tfvars.json
```

`--infra` treats the positional argument as a **Copilot** (not an Agent), reads
its `persistence` / `knowledge.store` / `hosting`, and writes a Terraform-native
`.tfvars.json`. `--json` emits the machine-readable `{artifacts, mapping, losses}`
envelope, exactly like the agent path. A copilot that declares none of the three
(an in-memory, no-RAG, self-hosted copilot) has no infra to provision and the
emit is a no-op error — back-compat.

## Worked example — a Postgres + Foundry copilot

`memory-copilot` binds Postgres for both checkpoint and long-term memory, a
pgvector knowledge store on the **same** physical Postgres, and hosts on Foundry:

```yaml
persistence:
  checkpoint: { backend: postgres, ref: primary-pg }
  memory:     { backend: postgres, ref: primary-pg }
  cache:      { backend: null }
knowledge:
  store: { backend: pgvector, ref: primary-pg, embed: { model: text-embedding-3-small, dims: 1536 } }
hosting:
  mode: self-hosted
  target: foundry
  image: { registry_hint: acr, remote_build: true }
```

emits:

```jsonc
{
  "dna_agent": "memory-agent",
  "scope": "concierge",
  "postgres": [
    {
      "ref": "primary-pg",
      "database": "dna",
      "pgvector": true,                      // knowledge.store shares this ref
      "used_by": ["knowledge.store", "persistence.checkpoint", "persistence.memory"],
      "output_env": "DNA_PG_URI_PRIMARY_PG", // the env var the copilot reads
      "secret": true
    }
  ],
  "mongo": [],
  "redis": [],
  "hosting": {
    "target": "foundry",
    "mode": "self-hosted",
    "resources": { "cpu": "0.5", "memory": "1Gi" },
    "image": { "registry_hint": "acr", "remote_build": true, "base_image": null, "container_port": 8088 },
    "foundry": {
      "account": true, "project": true, "acr": true,
      "app_insights": true, "log_analytics": true, "connections": true,
      "identity": "system_assigned",
      "model_deployment": "azure/gpt-4o",
      "rbac": [
        { "principal": "project_identity", "role": "AcrPull" },
        { "principal": "agent_identity",   "role": "Azure AI User" }
      ]
    },
    "note": "the agent version is NOT an ARM resource — post-provision azd deploy / SDK step"
  },
  "env_injection": {
    "DNA_PG_URI_PRIMARY_PG": { "from": "postgres['primary-pg'].connection_string", "secret": true }
  }
}
```

### The two rules (design §3)

1. **`ref` → the TF output injected into the copilot's env.** Every store
   resource carries an `output_env`, and `env_injection` maps that env var to the
   Terraform module output (`postgres['primary-pg'].connection_string`, `secret`).
   The scaffold emitters (agno / MS-AF / LangGraph) bind their state stores from
   this env var — the seam between "what Terraform provisions" and "what the agent
   reads."
2. **Dedup by `ref`.** `checkpoint`, `memory`, and the pgvector `knowledge.store`
   all point at `primary-pg` → **one** Postgres resource (distinct tables/objects
   per framework, one physical server). `used_by` records every slot the resource
   backs, and `pgvector: true` is coalesced on if **any** contributor needs the
   vector extension.

## The module contract — backend / target → what Terraform provisions

Each row is a resource the corresponding `dna-cloud` Terraform module implements
against the `azurerm` + `azuread` provider conventions the [ADR §8][adr] fixes.
The **outputs** column is the seam: the module must expose these so `env_injection`
can inject them.

| Declared | `.tfvars.json` input | TF module provisions | Outputs (→ `env_injection`) |
|---|---|---|---|
| `persistence.*.backend: postgres` | `postgres[]` entry (deduped by `ref`) | `azurerm_postgresql_flexible_server` + `_database` (`dna`) + `_firewall_rule` (AllowAllAzureServices) | `connection_string` (secret) → `DNA_PG_URI_<REF>` |
| `knowledge.store.backend: pgvector` | `postgres[].pgvector = true` | + `azurerm_postgresql_flexible_server_configuration` (`azure.extensions = VECTOR`). Tables auto-create via each framework's `.setup()` — TF provisions **server+db+extension, not tables**. | (shares the postgres `connection_string`) |
| `*.backend: mongo` / `knowledge.store.backend: mongo-atlas` | `mongo[]` entry; `vector_search: true` when a store contributes | `mongodbatlas_cluster` + `_database_user` + `_project_ip_access_list` + `mongodbatlas_search_index` (vectorSearch) | `connection_string` (secret) → `DNA_MONGO_URI_<REF>` |
| `*.backend: redis` (LangGraph cache) | `redis[]` entry | managed Redis (RediSearch) + secret | `connection_string` (secret) → `DNA_REDIS_URL_<REF>` |
| `hosting.target: foundry` | `hosting.foundry` | CognitiveServices `accounts` + `accounts/projects` (SystemAssigned MI) + `accounts/deployments` (model) + `ContainerRegistry/registries` + AppInsights + Log Analytics + `accounts/connections` + RBAC (project MI → **AcrPull**; agent → **Azure AI User**). The **agent version is NOT an ARM resource** — a post-provision `azd deploy` / SDK step. | ACR login server, project endpoint (non-secret); model endpoint |
| `hosting.target: langgraph-platform` | `hosting.langgraph_platform` + synthesized `postgres[]`/`redis[]` from `stores` | compute (Container App / ECS / K8s via Helm) + managed **Postgres + Redis** + registry + secrets | `LANGGRAPH_CLOUD_LICENSE_KEY` (secret) → `env_injection` |
| `hosting.target: agentos` | `hosting.agentos` + synthesized `postgres[]` (pgvector) from `stores` | compute + managed **Postgres/pgvector** + registry + JWT secrets + ingress | `AGENTOS_JWT_SECRET` (secret) → `env_injection` |

### The env-injection contract

`env_injection` is a map `{ <ENV_VAR>: { from: "<kind>['<ref>'].<output>", secret } }`.
It names, per resource, **which Terraform module output feeds which copilot env
var**. The env-var naming is deterministic: `DNA_PG_URI_<REF>` / `DNA_MONGO_URI_<REF>`
/ `DNA_REDIS_URL_<REF>`, where `<REF>` is the declared `ref` upper-snake-cased
(`primary-pg` → `PRIMARY_PG`). A copilot binding two physical Postgres servers gets
two disambiguated env vars — the scaffold reads the one matching the store's `ref`.

## Honest gaps (documented, not hidden)

- **Foundry ignores `hosting.stores`.** Foundry is a true managed runtime that
  provisions its own state — the `stores` block (`postgres`/`redis` required) is
  a **LangGraph/AgentOS-only** concern (design §2). When a Foundry copilot also
  declares `stores`, the emit records an honest de-para loss and ignores it. State
  a Foundry copilot needs still comes from its explicit `persistence` refs.
- **`langgraph-platform` / `agentos` are documented, not first-class.** Foundry is
  the first-class hosted target (design §2). For the other two the emit synthesizes
  a Postgres/Redis resource from the `hosting.stores` requirement **only when no
  `persistence` ref already declares one** — the ref is derived from the agent
  slug (`<agent>-pg` / `<agent>-redis`) because a `stores` requirement carries no
  `ref` of its own. If your copilot binds an explicit persistence Postgres AND
  declares `stores.postgres: required`, they are assumed to be the same server —
  declare the `ref` explicitly to be unambiguous.
- **Unmapped backends are a loss, never a silent drop.** A backend with no
  Terraform mapping (e.g. `cassandra`) produces no resource and is recorded in the
  emit's `losses` list — provision it out-of-band or extend this contract.
- **This emit does not run Terraform.** It produces the `.tfvars.json` inputs; the
  `apply` (and the module implementations) are the downstream Terraform-ADR
  execution in `dna-cloud`.

[adr]: ../../../dna-cloud/docs/adr/ADR-terraform-migration.md
