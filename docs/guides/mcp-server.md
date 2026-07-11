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
WorkOS/Auth0, and JWT token verification with scope enforcement). So the MVP is
stdio-only, and the remote + authenticated phase is *enable + bridge* — not
*build* (see the Roadmap below).

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

## Why this completes the thesis

DNA is a **vendor-neutral intelligence layer with no runtime**. `emit` proved
one face (author once, materialize per runtime). The MCP server is the other:
the *live* layer any client consumes over the market's neutral protocol —
preserving composition, per-tenant overlay, and no-deploy change, the exact axes
a static artifact drops.

## Roadmap

The MVP ships **stdio** (local clients). Because the server is on FastMCP —
which provides the transport and auth natively — the two Phase-2 stories (design
+ owner approval) are *enablement + a bridge*, not a build:

- **Remote transport** (`s-mcp-remote-transport`) — enable FastMCP's native
  Streamable HTTP transport (`run(transport="http")`) so the same server is
  hostable, unblocking WEB clients (Claude web, ChatGPT) that cannot spawn a
  local stdio process.
- **OAuth 2.1 + tenancy** (`s-mcp-oauth-auth`) — enable FastMCP's built-in OAuth
  2.1 auth (DCR servers / OAuth proxy for WorkOS/Auth0 / JWT scope enforcement)
  and **bridge the token scopes/claims to DNA tenancy** (the `Tenant` Kind +
  inheritance) — a client/tenant token composes and reads only what is theirs.
  The real work is the auth↔tenancy bridge, not building OAuth.

See the ADR `adr-dna-mcp-runtime-face` for the decision and phasing.
