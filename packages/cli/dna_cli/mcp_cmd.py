"""``dna mcp`` — expose the LIVE DNA over the Model Context Protocol.

``dna mcp serve`` boots a single MCP server against the configured source
(``DNA_SOURCE_URL`` / ``DNA_BASE_DIR`` — the same source every ``dna`` command
reads) and speaks the neutral MCP protocol over stdio, so any MCP client (Claude
Code/Desktop, Cursor, GitHub Copilot, agent-framework, Bedrock AgentCore) can
reach everything DNA stores — definitions (composed live + tenant-aware), the
SDLC board, and declarative memory.

It is the runtime counterpart of ``dna emit``: emit writes a STATIC artifact
(and drops composition/tenant/no-deploy); this composes LIVE on request.

The ``mcp`` SDK is an optional extra (``pip install 'dna-cli[mcp]'``); it is
imported lazily so the base ``dna`` install never requires it.
"""
from __future__ import annotations

import click


@click.group(name="mcp")
def mcp() -> None:
    """Expose the live DNA (definitions + SDLC + memory) over MCP."""


@mcp.command("serve")
@click.option("--scope", default=None,
              help="Default scope for tools that omit one (else the sole/first scope).")
@click.option("--base-dir", default=None,
              help="Source directory override (else DNA_SOURCE_URL / DNA_BASE_DIR / ./.dna).")
@click.option("--transport", type=click.Choice(["stdio", "http", "sse", "streamable-http"]),
              default="stdio", show_default=True,
              help="MCP transport. `stdio` = local clients (Claude Code/Cursor/Copilot). "
                   "`http` (Streamable HTTP, MCP spec 2025-06-18) = REMOTE/web clients "
                   "(Claude web, ChatGPT) that cannot spawn a local process. Same server, "
                   "both transports (FastMCP native — story s-mcp-remote-transport).")
@click.option("--host", default="127.0.0.1", show_default=True,
              help="Bind host for the HTTP/SSE transports (ignored for stdio).")
@click.option("--port", type=int, default=8000, show_default=True,
              help="Bind port for the HTTP/SSE transports (ignored for stdio).")
@click.option("--path", default=None,
              help="URL path the MCP endpoint is mounted at (HTTP/SSE; FastMCP default /mcp).")
@click.option("--auth", type=click.Choice(["none", "jwt"]), default="none", show_default=True,
              help="Auth provider for the HTTP transport. `jwt` verifies bearer JWTs and "
                   "bridges the tenant claim to DNA tenancy (env DNA_MCP_JWT_*; HTTP-only, "
                   "story s-mcp-oauth-auth). stdio stays local/unauthenticated.")
def serve(scope: str | None, base_dir: str | None, transport: str,
          host: str, port: int, path: str | None, auth: str) -> None:
    """Run the DNA MCP server (stdio local, or Streamable HTTP for remote/web clients).

    \b
    LOCAL (stdio) — wire it into Claude Code / Cursor / Copilot (mcp config JSON):
      {
        "mcpServers": {
          "dna": {
            "command": "dna",
            "args": ["mcp", "serve"],
            "env": { "DNA_SOURCE_URL": "file:///abs/path/to/.dna" }
          }
        }
      }

    \b
    REMOTE (Streamable HTTP) — host it so WEB clients (Claude web, ChatGPT) reach it:
      $ dna mcp serve --transport http --host 0.0.0.0 --port 8000
      # endpoint: http://<host>:8000/mcp/  — point a remote/web MCP client at that URL.
      # add --auth jwt to require a bearer token whose tenant claim scopes every
      # tool to that tenant (see `dna mcp serve --help` / the auth guide).

    Either way the client calls compose_prompt / sdlc_digest / recall and reads the
    dna://{scope}/manifest resource — all against your live DNA.
    """
    from dna_cli._mcp_server import build_server

    auth_provider = None
    if auth == "jwt":
        if transport == "stdio":
            raise click.ClickException(
                "--auth jwt is HTTP-only (there is no bearer token over stdio); "
                "run with --transport http."
            )
        from dna_cli._mcp_auth import jwt_provider_from_env

        try:
            auth_provider = jwt_provider_from_env()
        except (RuntimeError, ValueError) as exc:
            raise click.ClickException(str(exc)) from None

    try:
        server = build_server(scope=scope, base_dir=base_dir, auth=auth_provider)
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from None

    # FastMCP owns the event loop; the kernel handle is built lazily on it.
    if transport == "stdio":
        server.run(transport=transport)
    else:
        kwargs: dict[str, object] = {"host": host, "port": port}
        if path:
            kwargs["path"] = path
        server.run(transport=transport, **kwargs)
