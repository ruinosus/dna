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
@click.option("--transport", type=click.Choice(["stdio"]), default="stdio",
              show_default=True,
              help="MCP transport. The MVP ships stdio (local clients); remote "
                   "Streamable HTTP is Phase 2 (story s-mcp-remote-transport).")
def serve(scope: str | None, base_dir: str | None, transport: str) -> None:
    """Run the DNA MCP server (stdio).

    \b
    Wire it into a client (e.g. Claude Code / Cursor mcp config):
      {
        "mcpServers": {
          "dna": {
            "command": "dna",
            "args": ["mcp", "serve"],
            "env": { "DNA_SOURCE_URL": "file:///abs/path/to/.dna" }
          }
        }
      }
    Then the client can call compose_prompt / sdlc_digest / recall, and read the
    dna://{scope}/manifest resource — all against your live DNA.
    """
    from dna_cli._mcp_server import build_server

    try:
        server = build_server(scope=scope, base_dir=base_dir)
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from None
    # FastMCP owns the event loop; the kernel handle is built lazily on it.
    server.run(transport=transport)
