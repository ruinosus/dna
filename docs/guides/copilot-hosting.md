# Copilot hosting — the hosted variant (Foundry first-class)

A servable `Copilot` already emits a **self-hosted** AG-UI app (the per-user
copilot backend + its CopilotKit console). The `hosting` block adds a second
deployment shape: a **hosted** variant — a container image + a managed-runtime
manifest deployed to a managed service.

`hosting.mode` is a **variant selector over ONE agent definition**: the same
agent emits BOTH the per-user AG-UI app AND the single-identity hosted agent. The
hosted variant **degrades** — it strips the per-user concerns that don't fit a
hosted, single-identity, request/response model.

```yaml
Copilot:
  hosting:
    mode: hosted            # self-hosted (the AG-UI app) | hosted
    target: foundry         # foundry | langgraph-platform | agentos
    resources: { cpu: "0.5", memory: 1Gi }
    image:
      registry_hint: acr     # acr | ghcr | ecr | dockerhub
      remote_build: true      # Foundry ACR remoteBuild; else local
      base_image: null        # null → framework default
      port: null              # null → framework default (8088 / 8123 / 7777)
    stores: { postgres: required, redis: required }   # langgraph/agentos only
```

## The one command

```console
$ dna emit hosted-copilot --hosting --scope concierge --out hosted/
Emitted hosted-copilot hosted → foundry-hosted: 4 files under hosted/
```

`--hosting` treats the positional argument as a **Copilot** (not an Agent), reads
its `hosting` block (which must declare `mode: hosted`), and writes the hosted
variant. A `mode: self-hosted` copilot has no hosted variant — the self-hosted
AG-UI emit is unchanged. SDK: `emit_hosting(build_copilot_context(mi, copilot))`.

## `target: foundry` — first-class (a true managed runtime)

Foundry is the only true managed hosted runtime, so it is emitted **first-class** —
four files:

| File | What it is |
| --- | --- |
| `Dockerfile` | `python:3.12-slim`, `EXPOSE 8088`, `linux/amd64` — the Responses-protocol container (built remotely by ACR). |
| `main.py` | `ResponsesHostServer(build_agent()).run()` — the MS-AF agent build reused from the self-hosted copilot scaffold, DEGRADED (see below). |
| `requirements.txt` | `agent-framework` + `agent-framework-foundry-hosting` (+ `agent-framework-postgres` when a pgvector knowledge store survives). |
| `azure.yaml` | the `host: azure.ai.agent` service block — the **non-deprecated** Foundry hosted-agent manifest (NOT the deprecated `agent.yaml`). |

The `azure.yaml` block carries `language: docker`, `docker.remoteBuild` (when
`image.remote_build`), `config.container.resources` (from `hosting.resources`), and
`startupCommand: python main.py`. Merge it into your azd `azure.yaml` and set
`project:` to the service directory.

### What the hosted variant degrades

The hosted agent is a **single service identity**. Compared with the self-hosted
AG-UI app for the same agent, it drops:

- **per-user OBO** — auth is the platform-injected **agent** identity
  (`DefaultAzureCredential`), not the signed-in user;
- **HITL approval** — the MCP mount carries no `approval_mode` (no approval card);
  write tools run under the agent identity;
- **per-user long-term memory** — Foundry hosting manages conversation history.

What **survives**: the composed instruction (carried byte-equal as `INSTRUCTIONS`),
the MCP tool mount (ungated), and single-identity RAG grounding
(`PostgresVectorStore` over the shared corpus — not per-user memory).

> The agent **version** is not built by this emit. `azd deploy` builds the image
> (remoteBuild via ACR) and publishes a new agent version — a deploy step, not an
> artifact. The Azure resources it needs (account / project / ACR / model
> deployment / RBAC) come from the infra binding — see
> [Copilot infra binding](copilot-infra-binding.md).

## `target: langgraph-platform` / `agentos` — documented

The abstraction leaks for the other two targets, so they are emitted **documented,
lower priority** — honest about what "hosted" does and does not mean:

- **`langgraph-platform`** is a stateful **server**, not a Foundry-style managed
  agent. The emit writes `langgraph.json` (graphs + dependencies + env) + a
  `HOSTING.md` note. `langgraph build` (not this emit) produces the image, and
  `identity` / `protocol` don't map cleanly.
- **`agentos`** has **no managed runtime** at all. `mode: hosted` there ≈
  self-host (the emitted `AgentOS(...)` app + a thin `compose.yaml` on port 7777)
  + an optional control-plane registration step. The emit writes those + a
  `HOSTING.md` note.

Both still route their managed Postgres / Redis / secrets through the infra
binding (the Terraform closure lives downstream in the dna-cloud repository).

## Where it sits

`hosting` is one of the three infra-shaped Copilot dimensions
(`persistence`, `knowledge.store`, `hosting`). The **artifacts** are this guide;
the **infrastructure** those artifacts run on is the
[Copilot infra binding](copilot-infra-binding.md) — declarative all the way down.
