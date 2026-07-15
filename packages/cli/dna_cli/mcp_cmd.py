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
@click.option("--auth", type=click.Choice(["none", "jwt", "config"]), default="none",
              show_default=True,
              help="Auth provider for the HTTP transport. `jwt` = a single bearer-JWT "
                   "Resource Server from env (DNA_MCP_JWT_*). `config` = the pluggable "
                   "N-provider IdP layer read from dna.config.yaml's `auth.providers[]` "
                   "(Entra/Clerk/WorkOS/OIDC — a provider is a config block; multi-issuer, "
                   "claim→tenant per provider). Both bridge the token to DNA tenancy; both "
                   "are HTTP-only. stdio stays local/unauthenticated.")
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
      # add --auth jwt (single env IdP) or --auth config (the pluggable N-provider
      # layer from dna.config.yaml — Entra/Clerk/WorkOS/OIDC) to require a bearer
      # token whose tenant claim scopes every tool to that tenant (see the auth guide).

    Either way the client calls compose_prompt / sdlc_digest / recall and reads the
    dna://{scope}/manifest resource — all against your live DNA.
    """
    from dna_cli._mcp_server import build_server

    # Microsoft On-Behalf-Of (OBO) enablement — the `graph:` block of
    # dna.config.yaml, off by default. HTTP-only (like --auth): a bearer token is
    # the assertion OBO exchanges, so stdio (no token) never registers graph tools.
    graph_config = None
    if transport != "stdio":
        try:
            from dna.config import load_config
            from dna_cli.graph._config import parse_graph_config

            cfg = load_config()
            graph_config = parse_graph_config(cfg.graph if cfg else None)
        except ValueError as exc:
            raise click.ClickException(f"graph: config error — {exc}") from None
        if graph_config is not None and graph_config.active_groups():
            click.echo(
                "graph (OBO): active groups — "
                + ", ".join(graph_config.active_groups()),
                err=True,
            )

    auth_provider = None
    if auth in ("jwt", "config"):
        if transport == "stdio":
            raise click.ClickException(
                f"--auth {auth} is HTTP-only (there is no bearer token over stdio); "
                "run with --transport http."
            )
        try:
            if auth == "jwt":
                from dna_cli._mcp_auth import jwt_provider_from_env

                auth_provider = jwt_provider_from_env()
            else:  # config — the pluggable N-provider IdP layer
                from dna_cli._mcp_auth import (
                    build_auth_from_config,
                    providers_from_config,
                )

                providers = providers_from_config()
                click.echo(
                    "auth: multi-provider layer — "
                    + ", ".join(f"{p.label}({p.tenant_claim})" for p in providers),
                    err=True,
                )
                auth_provider = build_auth_from_config(providers)
        except (RuntimeError, ValueError) as exc:
            raise click.ClickException(str(exc)) from None

    try:
        server = build_server(
            scope=scope, base_dir=base_dir, auth=auth_provider,
            graph_config=graph_config,
        )
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from None

    # FastMCP owns the event loop; the kernel handle is built lazily on it.
    if transport == "stdio":
        server.run(transport=transport)
    else:
        # HTTP transports also accept the per-workspace URL `/w/<id>/mcp` (Model B
        # S2.3) beside the bare `/mcp`: build the multi-mount Starlette app and run
        # it under uvicorn (FastMCP's own dependency), so a client can pick its
        # workspace by URL. The auth bridge reads the id from the request path.
        from dna_cli._mcp_server import build_http_app

        try:
            import uvicorn
        except ModuleNotFoundError as exc:  # pragma: no cover — exercised via CLI
            raise click.ClickException(
                "the HTTP transport needs 'uvicorn' — install with:  pip install "
                "'dna-cli[mcp]'"
            ) from exc

        http_transport = "sse" if transport == "sse" else "http"
        app = build_http_app(server, path=path or "/mcp", transport=http_transport)
        click.echo(
            f"DNA MCP over HTTP — bare /mcp and per-workspace /w/<id>/mcp "
            f"(ADR Model B) on {host}:{port}",
            err=True,
        )
        uvicorn.run(app, host=host, port=port, log_level="info")
