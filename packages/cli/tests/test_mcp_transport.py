"""Story ``s-mcp-remote-transport`` — the DNA MCP server over Streamable HTTP.

The MVP shipped stdio (local clients). This proves the SAME server, unchanged,
is reachable over **Streamable HTTP** (MCP spec 2025-06-18) — the transport a
WEB MCP client (Claude web, ChatGPT) uses because it cannot spawn a local stdio
process. FastMCP ships the transport natively, so the work is enablement; the
test drives it over a real socket via ``FastMCP Client`` pointed at an ``http://``
URL, and asserts a remote client reaches the same tools/resources as the stdio
MVP.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

pytest.importorskip("fastmcp", reason="the MCP runtime face needs the optional 'fastmcp' extra")

from dna_cli import _mcp_server as M  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_AGENT = "concierge"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def test_web_client_reaches_tools_over_http(dna_dir, http_server):
    """A remote/web-style MCP client connects over Streamable HTTP (no local
    stdio) and reaches the SAME tools/resources + composes a prompt live."""
    from fastmcp import Client

    server = M.build_server(base_dir=str(dna_dir))

    async def scenario(url: str):
        # A plain HTTP MCP client — exactly what Claude web / ChatGPT drive.
        async with Client(url) as client:
            names = {t.name for t in await client.list_tools()}
            assert {
                "compose_prompt", "list_agents", "list_tools", "get_tool",
                "sdlc_digest", "list_stories", "get_adr",
                "recall", "remember", "consolidate",
            } <= names

            templates = {
                str(r.uriTemplate) for r in await client.list_resource_templates()
            }
            assert "dna://{scope}/manifest" in templates

            # a real tool call over the wire — live composition survives HTTP.
            res = (await client.call_tool(
                "compose_prompt", {"agent": _AGENT, "scope": _SCOPE}
            )).structured_content
            assert "Helpdesk Concierge" in res["prompt"]

    with http_server(server) as url:
        assert url.startswith("http://")
        asyncio.run(scenario(url))


def test_serve_cli_accepts_http_transport_choice():
    """`dna mcp serve --transport http --host --port` is a valid invocation (the
    transport is a real FastMCP transport, not a stub)."""
    from click.testing import CliRunner

    from dna_cli.mcp_cmd import serve

    # --help renders the expanded transport choice + host/port/path/auth options.
    out = CliRunner().invoke(serve, ["--help"])
    assert out.exit_code == 0
    assert "http" in out.output
    assert "--host" in out.output and "--port" in out.output
    assert "--auth" in out.output
