"""Minimal FastMCP server for Spike 0A — one WRITE tool `remember`, streamable-http.

Run: python mcp_server.py  (serves at http://127.0.0.1:8199/mcp)

The tool writes a line to remembered.log so we can PROVE, on HITL resume, that the
underlying MCP write actually executed (not just that the run resumed).
"""
from __future__ import annotations

import pathlib

from fastmcp import FastMCP

LOG = pathlib.Path(__file__).parent / "remembered.log"

mcp = FastMCP("dna-memory-spike")


@mcp.tool
def remember(text: str) -> str:
    """Persist a memory. This is the WRITE that HITL must gate."""
    with LOG.open("a") as fh:
        fh.write(text + "\n")
    return f"remembered: {text}"


if __name__ == "__main__":
    # FastMCP 3.x: transport="http" == streamable-http
    mcp.run(transport="http", host="127.0.0.1", port=8199)
