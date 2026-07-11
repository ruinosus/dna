# The MCP server — DNA as a live layer

DNA stores the neutral **definitions** (`Agent` / `Soul` / `Guardrail` / `Tool`),
its self-describing **SDLC** board, and its declarative **memory** — and has no
runtime of its own. There are two ways to serve that to a runtime:

| | **`dna emit`** | **`dna mcp serve`** |
|---|---|---|
| When | build-time | runtime |
| Output | a **static** native artifact (a file) | a **live** answer to a query |
| Composition structure | flattened to one string | composed **on request** |
| Per-tenant overlay | dropped (needs a fork) | **preserved** (`compose_prompt(tenant=…)`) |
| No-deploy change | frozen at emit time | **live** (edit the source, next call reflects it) |
| Reaches | one runtime's loader | **any** MCP client |
| Protocol | the target's file format | the neutral **MCP** protocol |

`emit` is the *static* de-para (see [Emitting to a runtime](emitting-to-a-runtime.md)).
The MCP server is the *dynamic* face — and it **recovers exactly what emit
loses**: a client asks *"compose the ACME concierge **now**"* and the server
composes it live, tenant-aware, with zero deploy.

DNA already *consumes* MCP (the `MCPFederation` Kind pulls external MCP tools
into a scope). This is the **inverse**: DNA *exposing itself* over MCP, so that
Claude Code/Desktop, Cursor, GitHub Copilot, agent-framework, Bedrock AgentCore —
any MCP client — can reach everything DNA stores.

## One server exposes everything

`dna mcp serve` boots a single server against the **configured source**
(`DNA_SOURCE_URL` / `DNA_BASE_DIR` / `./.dna` — the same source every `dna`
command reads) and speaks MCP over **stdio**. It surfaces three faces of what
DNA stores, plus resources:

**Definitions** — recover what emit drops:

- `compose_prompt(agent, scope?, tenant?)` → the **live-composed** system prompt
  (Soul + Guardrails + instruction). Pass `tenant` for the per-tenant overlay —
  the composition a flat artifact cannot express.
- `list_agents(scope?)` · `list_tools(scope?)` · `get_tool(name, scope?)`.

**SDLC** — the self-describing board:

- `sdlc_digest(since?, scope?)` · `list_stories(status?, scope?)` · `get_adr(name, scope?)`.

**Memory** — declarative recall:

- `recall(query, scope?, k?)` · `remember(summary, …)` · `consolidate(apply?)`.

**Resources** (beyond tools):

- `dna://{scope}/manifest` — the scope's Kinds → document names.
- `dna://{scope}/agents` — the agent roster.

## Built on FastMCP

The server is built on **FastMCP** (the standalone `fastmcp` framework — the
leading MCP framework, from which the official MCP Python SDK's FastMCP 1.0 was
derived). That is a deliberate choice about the *phasing*: FastMCP ships **native
transports** (stdio + Streamable HTTP) and **built-in auth** (OAuth 2.1 with
Dynamic Client Registration, an OAuth proxy for providers without DCR like
WorkOS/Auth0, and JWT token verification with scope enforcement). So the local
face is stdio, and the remote + authenticated face is *enable + bridge* — not
*build* (see [Remote + authenticated](#remote-authenticated-phase-2) below).

## Install

The MCP dependency is an **optional extra** (`fastmcp`, imported lazily, so the
base `dna` install never carries it):

```console
$ pip install 'dna-cli[mcp]'
```

## Run it

```console
$ DNA_SOURCE_URL=file:///abs/path/to/.dna dna mcp serve
```

## Connect a client

Point any MCP client at the command. For **Claude Code** / **Cursor**
(`mcp` config JSON):

```json
{
  "mcpServers": {
    "dna": {
      "command": "dna",
      "args": ["mcp", "serve"],
      "env": { "DNA_SOURCE_URL": "file:///abs/path/to/.dna" }
    }
  }
}
```

Now the client can call the tools and read the resources against your **live**
DNA. For example, composing an agent's prompt live and tenant-aware:

```jsonc
// tool: compose_prompt
{ "agent": "concierge", "scope": "concierge", "tenant": "acme" }
// → { "scope": "concierge", "agent": "concierge", "tenant": "acme",
//     "model": "azure/gpt-4o", "prompt": "You are the Helpdesk Concierge …" }
```

The same server answers `sdlc_digest`, `list_stories`, `get_adr` (the board) and
`recall` (the memory) — one server, everything DNA stores.

## Remote + authenticated (Phase 2)

The stdio server above is the LOCAL face — a client on your machine spawns it as
a child process. A **web** client (Claude web, ChatGPT) cannot spawn a local
process; it needs a URL. Because the server is on FastMCP — which ships both the
transport and the auth natively — the remote face is *enable + bridge*, not a
rebuild. It is the **same server**, the same tools, reached over HTTP:

| | **local — stdio** | **remote — Streamable HTTP + OAuth** |
|---|---|---|
| Transport | stdio (child process) | Streamable HTTP (MCP spec 2025-06-18) |
| Clients | Claude Code, Cursor, Copilot | Claude web, ChatGPT, any hosted client |
| Reachability | your machine only | hostable / networked |
| Auth | none (local trust) | OAuth 2.1 bearer JWT — one IdP (`--auth jwt`) or the pluggable **N-provider layer** (`--auth config`) |
| Tenancy | caller-supplied `tenant` arg | **bound to the token** (the bridge; the claim is per-provider under `--auth config`) |
| Command | `dna mcp serve` | `dna mcp serve --transport http --auth config` |

### Serve it over HTTP

```console
$ dna mcp serve --transport http --host 0.0.0.0 --port 8000
# → the MCP endpoint is http://<host>:8000/mcp/
```

Point a remote/web MCP client at that URL. FastMCP serves the Streamable HTTP
transport — no transport code is written, it is a flag.

> **Hosting it for real?** [Host the MCP server on Azure Container Apps +
> Microsoft Entra](hosting-mcp-aca.md) is the one-command (`azd up`) recipe —
> Dockerfile + bicep + runbook — that runs this HTTP server behind an HTTPS
> ingress, keyless (Managed Identity), with Entra as the OAuth IdP.

### Connect a web client

A web MCP client takes a URL (and, when auth is on, drives the OAuth flow):

```jsonc
// a hosted/remote MCP client's server entry
{ "type": "http", "url": "https://dna.example.com/mcp/" }
```

### Authenticate — OAuth 2.1 with a JWT Resource Server

Add `--auth jwt` (HTTP-only — there is no bearer token over stdio). The server
becomes an OAuth 2.1 **Resource Server**: it validates signed bearer JWTs and
advertises **Protected Resource Metadata** (RFC 9728) at
`/.well-known/oauth-protected-resource/mcp`, so a client discovers where to
authorize. Configure it from the environment:

| Env var | Meaning |
|---|---|
| `DNA_MCP_JWT_PUBLIC_KEY` | PEM public key (static key), **or** |
| `DNA_MCP_JWKS_URI` | a JWKS endpoint (a real IdP / rotating keys) |
| `DNA_MCP_JWT_ISSUER` | expected `iss` (optional) |
| `DNA_MCP_JWT_AUDIENCE` | expected `aud` (optional) |
| `DNA_MCP_RESOURCE_URL` + `DNA_MCP_AUTH_SERVERS` | set both to advertise PRM (RFC 9728) |

```console
$ DNA_MCP_JWKS_URI=https://idp.example.com/.well-known/jwks.json \
  DNA_MCP_JWT_ISSUER=https://idp.example.com/ \
  DNA_MCP_JWT_AUDIENCE=dna-mcp \
  DNA_MCP_RESOURCE_URL=https://dna.example.com \
  DNA_MCP_AUTH_SERVERS=https://idp.example.com/ \
  dna mcp serve --transport http --auth jwt --host 0.0.0.0 --port 8000
```

FastMCP conforms to the current MCP Authorization spec (revision 2025-11-25):
OAuth 2.1 Resource Server, mandatory PKCE, Protected Resource Metadata (RFC
9728), Resource Indicators (RFC 8707), Authorization Server Metadata (RFC 8414),
Dynamic Client Registration (RFC 7591).

`--auth jwt` is the **single-IdP** shortcut (one Resource Server from env). For
**more than one IdP at once** — and for a config-driven setup where adding a
provider is a config block, not code — use the **multi-provider layer** below.

### Multi-provider auth — a provider is a config block, not code

A serious IdP always exposes **JWKS + OIDC discovery**, so DNA treats a provider
as a **block of config**, not a code path. Declare `auth.providers[]` in
`dna.config.yaml` and run `dna mcp serve --transport http --auth config`. The
server accepts a token from **any** configured provider, routes it to that
provider by its issuer, and scopes every tool to the tenant the provider's own
claim names. Adding an IdP is one more block — no new code.

```yaml
# dna.config.yaml
source: postgresql://user:pass@host/db

auth:
  providers:
    # Azure Entra ID — the reference provider (see below).
    - type: entra
      issuer: https://login.microsoftonline.com/<tenant-id-or-common>/v2.0
      audience: <app-id>          # your Entra app registration (client) ID
      # tenant_claim defaults to `tid` (the Azure tenant → the DNA tenant)

    # Any OIDC-generic IdP.
    - type: oidc
      issuer: https://idp.example.com
      jwks_uri: https://idp.example.com/.well-known/jwks.json   # optional; derived if omitted
      audience: dna-mcp
      tenant_claim: org           # REQUIRED for `oidc` (no default)

    - type: clerk                 # tenant_claim defaults to `org_id`
      issuer: https://clerk.acme.dev

    - type: workos                # tenant_claim defaults to `org_id`
      issuer: https://api.workos.com
      audience: dna-mcp
```

**The provider table.**

| `type` | default `tenant_claim` | JWKS (when `jwks_uri` omitted) | issuer notes |
|---|---|---|---|
| `entra` | `tid` | `…/<tenant>/discovery/v2.0/keys` (derived) | `common`/`organizations`/`consumers` → issuer relaxed, `audience` required |
| `clerk` | `org_id` | `<issuer>/.well-known/jwks.json` | Clerk Frontend API origin |
| `workos` | `org_id` | `<issuer>/.well-known/jwks.json` | organization-based |
| `auth0` | `org_id` | `<issuer>/.well-known/jwks.json` | no DCR → `OAuthProxy` seam |
| `oidc` | *(required — you name it)* | `<issuer>/.well-known/jwks.json` | any OIDC IdP |

Each block accepts `issuer`, `audience`, `jwks_uri`, `public_key` (static PEM,
in place of a JWKS), `algorithm`, `tenant_claim`, `scope_prefix`, and `name`. A
provider needs a key source: `jwks_uri`, a `public_key`, or an `issuer` to derive
the JWKS from.

**Multi-issuer routing.** DNA builds one FastMCP `JWTVerifier` per provider
(each aimed at its own JWKS + issuer + audience) and composes them: a token is
verified by the **one** provider whose issuer + audience + signature match, so it
is routed by `iss` for free. The composite then stamps *that* provider's
`tenant_claim` onto the verified token, so the tenancy bridge reads the right
claim **per provider** — no global state, and it survives Entra `common` (where
the token's `iss` carries the real Azure tenant, not the literal `common`).

**PRM lists every provider.** Wrap the layer as a Resource Server
(`DNA_MCP_RESOURCE_URL` + `DNA_MCP_AUTH_SERVERS`, or the per-provider issuers by
default) and it advertises Protected Resource Metadata (RFC 9728) naming **all**
configured authorization servers — one discovery document, N providers.

**Providers without DCR (WorkOS, Auth0).** FastMCP's `OAuthProxy` bridges an IdP
that lacks Dynamic Client Registration to MCP's DCR-compliant flow. It slots into
the same `dna_cli._mcp_auth.resource_server(...)` seam; the tenancy bridge is
provider-agnostic (it reads the stamped claim off whatever verified token comes
back), so nothing downstream changes.

### Entra as the reference provider (+ the `azd up` step)

Azure Entra ID maps onto DNA cleanly: the **Azure tenant is the `tid` claim**,
and that is the DNA tenant — so `type: entra` defaults `tenant_claim: tid`.

- **Per-tenant** (`issuer: …/<tenant-guid>/v2.0`) — the token's `iss` is a
  concrete match, validated **strictly**; the derived JWKS is that tenant's keys.
- **Multi-tenant** (`issuer: …/common/v2.0` or `…/organizations/v2.0`) — Entra
  mints a *per-caller* issuer, so strict `iss` validation is impossible. DNA
  relaxes the issuer and validates by **audience + signature** (your app-id
  audience is the security boundary — it is **required** here), then reads the
  Azure tenant from `tid`.

**Real end-to-end validation is done on the owner's `azd up`.** The Foundry
already carries `entraTenantId` / `entraApiClientId`; a full login → Azure token →
Resource Server check needs a live Entra app registration and is therefore run at
deploy time, not in CI. The step:

1. `azd up` — provision the Entra app registration (audience = its client ID) and
   host the server with `--transport http --auth config`.
2. From a client, sign in against Entra and call a tool with the issued bearer
   token; confirm `compose_prompt` returns the tenant matching the token's `tid`,
   and that a token for another Azure tenant cannot reach it.

Locally this is covered by an emulated multi-provider test (two OIDC issuers with
distinct tenant-claim keys) plus a `requires_azure` placeholder
(`DNA_MCP_ENTRA_E2E`) that documents the real check without needing a credential.

### The tenancy bridge — a token composes only what is its tenant's

This is the DNA-specific value. FastMCP verifies the token; it does **not** know
DNA tenancy. The bridge (`dna_cli._mcp_auth`) maps the verified token's
**claims/scopes → a DNA tenant** and enforces it, so every tool becomes
**tenant-scoped by the token**, not by a caller argument:

- A token with claim `{"tenant": "acme"}` (or a scope `tenant:acme`) makes
  `compose_prompt` / `recall` / `list_stories` compose and read **only ACME's**
  layer — the token's tenant is injected into every data access.
- A caller that also passes a *different* `tenant` argument is **denied**
  (cross-tenant). Omitting it resolves to the token's tenant.
- A token with **no** tenant claim/scope is **denied** — fail closed; an
  authenticated request with no tenant binding never falls back to "all tenants".
- With **no** auth (stdio / local) the bridge is an identity: the caller-supplied
  `tenant` passes through unchanged, so the base/stdio path is untouched.

Under `--auth jwt` (single IdP) the claim key is configurable via env
(`DNA_MCP_TENANT_CLAIM`, default `tenant`; scope prefix
`DNA_MCP_TENANT_SCOPE_PREFIX`, default `tenant:`). Under `--auth config` (the
multi-provider layer) the claim key is **per provider** — each block's
`tenant_claim` (Entra `tid`, Clerk/WorkOS `org_id`, an `oidc` block's own) — and
the composite verifier binds the right one to each token automatically. Either
way: auth + multi-tenant in one mechanism — the token IS the tenancy.

## Why this completes the thesis

DNA is a **vendor-neutral intelligence layer with no runtime**. `emit` proved
one face (author once, materialize per runtime). The MCP server is the other:
the *live* layer any client consumes over the market's neutral protocol —
preserving composition, per-tenant overlay, and no-deploy change, the exact axes
a static artifact drops. Locally over stdio, or **remotely over authenticated,
multi-tenant HTTP** — the same server, the token scoping each client to its own
tenant.

See the ADR `adr-dna-mcp-runtime-face` for the decision, the phasing, and the
auth↔tenancy bridge design.
