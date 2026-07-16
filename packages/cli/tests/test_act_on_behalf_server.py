"""Story ``s-aob-neutral-calendar`` (server integration) — neutral ``calendar_list``
on the real FastMCP protocol surface, ALONGSIDE the shipped ``ms_*`` tools.

Mirrors ``test_mcp_graph.py``'s registration-gating style (real FastMCP ``Client``,
in-memory, no live Entra/Graph). Proves: the neutral tool registers when calendar is
active; ``ms_calendar_list`` stays present (the Microsoft binding/alias); with no
inbound identity the neutral tool is an honest capability ``ToolError``; and with OBO
off nothing registers (OSS/stdio untouched).
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

from dna_cli.graph import _config as C

pytest.importorskip("fastmcp", reason="the MCP runtime face needs the optional 'fastmcp' extra")

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_DNA_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"


def _cfg(**over):
    base = {
        "enabled": True,
        "client_id_env": "DNA_MCP_CLIENT_ID",
        "credential_env": "DNA_MCP_CLIENT_SECRET",
        "groups": {"calendar": {"enabled": True, "scopes": ["Calendars.Read"]}},
    }
    base.update(over)
    return base


def _build(dst, graph_cfg):
    from dna_cli._mcp_server import build_server

    return build_server(base_dir=str(dst), graph_config=graph_cfg)


def test_neutral_calendar_list_registered_alongside_ms_alias(tmp_path, monkeypatch):
    from fastmcp import Client
    from fastmcp.exceptions import ToolError

    dst = tmp_path / ".dna"
    shutil.copytree(_DNA_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    gc = C.parse_graph_config(_cfg())

    async def scenario():
        server = _build(dst, gc)
        async with Client(server) as client:
            names = {t.name for t in await client.list_tools()}
            assert "calendar_list" in names          # the neutral tool …
            assert "ms_calendar_list" in names       # … and its Microsoft alias.
            # No inbound identity (in-memory client has no token) → honest gap.
            with pytest.raises(ToolError):
                await client.call_tool("calendar_list", {})

    asyncio.run(scenario())


def test_neutral_calendar_list_absent_when_obo_off(tmp_path, monkeypatch):
    from fastmcp import Client

    dst = tmp_path / ".dna"
    shutil.copytree(_DNA_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))

    async def scenario():
        server = _build(dst, None)
        async with Client(server) as client:
            names = {t.name for t in await client.list_tools()}
            assert "calendar_list" not in names
            assert "compose_prompt" in names  # base tools untouched (OSS/stdio path).

    asyncio.run(scenario())


def test_neutral_absent_when_calendar_group_disabled(tmp_path, monkeypatch):
    from fastmcp import Client

    dst = tmp_path / ".dna"
    shutil.copytree(_DNA_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    gc = C.parse_graph_config(
        _cfg(groups={"calendar": {"enabled": False, "scopes": ["Calendars.Read"]}})
    )

    async def scenario():
        server = _build(dst, gc)
        async with Client(server) as client:
            names = {t.name for t in await client.list_tools()}
            assert "calendar_list" not in names

    asyncio.run(scenario())
