# `dna mcp`

Expose the live DNA (definitions + SDLC + memory) over MCP.

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna mcp --help`.

## `dna mcp serve`

Run the DNA MCP server (stdio local, or Streamable HTTP for remote/web clients).


LOCAL (stdio) — wire it into Claude Code / Cursor / Copilot (mcp config JSON):
  {
    "mcpServers": {
      "dna": {
        "command": "dna",
        "args": ["mcp", "serve"],
        "env": { "DNA_SOURCE_URL": "`file:///abs/path/to/.dna"` }
      }
    }
  }


REMOTE (Streamable HTTP) — host it so WEB clients (Claude web, ChatGPT) reach it:
  $ dna mcp serve --transport http --host 0.0.0.0 --port 8000
  # endpoint: `http://<host>:8000/mcp/`  — point a remote/web MCP client at that URL.
  # add --auth jwt (single env IdP) or --auth config (the pluggable N-provider
  # layer from dna.config.yaml — Entra/Clerk/WorkOS/OIDC) to require a bearer
  # token whose tenant claim scopes every tool to that tenant (see the auth guide).

Either way the client calls compose_prompt / sdlc_digest / recall and reads the
`dna://{scope}/manifest` resource — all against your live DNA.

```text
dna mcp serve [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--auth` | Auth provider for the HTTP transport. `jwt` = a single bearer-JWT Resource Server from env (DNA_MCP_JWT_*). `config` = the pluggable N-provider IdP layer read from dna.config.yaml's `auth.providers[]` (Entra/Clerk/WorkOS/OIDC — a provider is a config block; multi-issuer, claim→tenant per provider). `azure` = the Lane A Entra FACADE (AzureProvider/OAuthProxy from DNA_MCP_AZURE_*) — gives Claude zero-config DCR/CIMD/PKCE while preserving the Entra assertion for OBO. All bridge the token to DNA tenancy; all are HTTP-only. stdio stays local/unauthenticated. _(default: `none`)_ |
| `--base-dir` | Source directory override (else DNA_SOURCE_URL / DNA_BASE_DIR / ./.dna). |
| `--help` | Show this message and exit. |
| `--host` | Bind host for the HTTP/SSE transports (ignored for stdio). _(default: `127.0.0.1`)_ |
| `--lane-b` | Consumer lane (identity front-door Option X). `workos` mounts a SECOND MCP surface at /consumer authenticated by WorkOS AuthKit (DNA_MCP_WORKOS_*) — for Gmail/consumer sign-up — beside the primary Lane A. HTTP-only; requires --transport http. _(default: `none`)_ |
| `--path` | URL path the MCP endpoint is mounted at (HTTP/SSE; FastMCP default /mcp). |
| `--port` | Bind port for the HTTP/SSE transports (ignored for stdio). _(default: `8000`)_ |
| `--scope` | Default scope for tools that omit one (else the sole/first scope). |
| `--transport` | MCP transport. `stdio` = local clients (Claude Code/Cursor/Copilot). `http` (Streamable HTTP, MCP spec 2025-06-18) = REMOTE/web clients (Claude web, ChatGPT) that cannot spawn a local process. Same server, both transports (FastMCP native — story s-mcp-remote-transport). _(default: `stdio`)_ |

