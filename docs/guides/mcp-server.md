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
| Auth | none (local trust) | OAuth 2.1 bearer JWT (Resource Server) |
| Tenancy | caller-supplied `tenant` arg | **bound to the token** (the bridge) |
| Command | `dna mcp serve` | `dna mcp serve --transport http --auth jwt` |

### Serve it over HTTP

```console
$ dna mcp serve --transport http --host 0.0.0.0 --port 8000
# → the MCP endpoint is http://<host>:8000/mcp/
```

Point a remote/web MCP client at that URL. FastMCP serves the Streamable HTTP
transport — no transport code is written, it is a flag.

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
Dynamic Client Registration (RFC 7591). For a provider **without** DCR (WorkOS,
Auth0) FastMCP's `OAuthProxy` bridges it to MCP's DCR-compliant flow — it slots
into the same `dna_cli._mcp_auth.resource_server(...)` seam, and the tenancy
bridge below is provider-agnostic (it reads the tenant off whatever verified
token comes back).

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

The claim key is configurable (`DNA_MCP_TENANT_CLAIM`, default `tenant`; scope
prefix `DNA_MCP_TENANT_SCOPE_PREFIX`, default `tenant:`). Auth + multi-tenant in
one mechanism — the token IS the tenancy.

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
