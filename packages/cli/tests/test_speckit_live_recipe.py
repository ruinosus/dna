"""The Layer 2 RECIPE, end-to-end (ADR ADR-spec-kit-adoption §5 Layer 2 +
s-speckit-live-recipe).

The claim Layer 2 makes: after `dna specify wire`, a Spec-Kit-driven agent —
whichever one Spec Kit projected into — reaches the LIVE DNA over MCP mid-run:
portable **memory** (recall), the **soul** (compose_prompt = Soul + Guardrails),
and the **board** (list_stories). This test proves the whole chain is real, not
a config that points at nothing:

  1. a project has a Spec Kit run (`.specify/` + `specs/<f>/`) AND a DNA board
     (`.dna/<scope>/` with a Soul + Agent + guardrail — the concierge example);
  2. `dna specify wire --tools claude` projects the DNA MCP block into `.mcp.json`;
  3. the block is exactly what launches the DNA MCP server (`dna mcp serve`) with
     `DNA_SOURCE_URL` pinned to THIS project's source;
  4. booting the DNA MCP server against that same source and driving it through
     the real FastMCP protocol, the agent reaches recall + compose_prompt +
     list_stories LIVE.

Step 4 uses the in-memory FastMCP Client (same technique as test_mcp_server.py)
against the source the wired block names — the honest stand-in for the agent
spawning `dna mcp serve` from the projected config.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import shutil

import pytest
from click.testing import CliRunner

pytest.importorskip("fastmcp", reason="the live recipe needs the optional 'fastmcp' extra")

from dna_cli import _mcp_server as M  # noqa: E402
from dna_cli.specify_cmd import specify  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_CONCIERGE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SPECKIT = pathlib.Path(__file__).resolve().parent / "fixtures" / "speckit"
_SCOPE = "concierge"
_AGENT = "concierge"


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project that has BOTH a Spec Kit run and a DNA board.

    - ``<proj>/.dna/concierge`` — the concierge scope (Soul + Agent + guardrail),
      so compose_prompt has a real persona to compose.
    - ``<proj>/.specify`` + ``<proj>/specs`` — the committed Spec Kit fixture run.

    ``DNA_BASE_DIR`` points at the board so ``dna specify wire`` pins the block's
    ``DNA_SOURCE_URL`` at exactly this project's source.
    """
    proj = tmp_path / "proj"
    proj.mkdir()
    shutil.copytree(_CONCIERGE, proj / ".dna")
    shutil.copytree(_SPECKIT / ".specify", proj / ".specify")
    shutil.copytree(_SPECKIT / "specs", proj / "specs")
    monkeypatch.setenv("DNA_BASE_DIR", str(proj / ".dna"))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return proj


def test_wired_config_points_at_a_live_dna_mcp(project):
    """wire → the projected .mcp.json → a working DNA MCP server serving
    memory + soul + board. The full Layer 2 chain, end-to-end."""
    runner = CliRunner()

    # 2. project the DNA MCP block into the agent's config.
    r = runner.invoke(
        specify, ["wire", "--dir", str(project), "--tools", "claude"],
        catch_exceptions=False,
    )
    assert r.exit_code == 0, r.output

    # 3. the block is exactly `dna mcp serve`, with DNA_SOURCE_URL pinned to THIS
    #    project's board — so the agent's server sees the same DNA the dev does.
    cfg = json.loads((project / ".mcp.json").read_text())
    block = cfg["mcpServers"]["dna"]
    assert block["command"] == "dna"
    assert block["args"] == ["mcp", "serve"]
    pinned = block["env"]["DNA_SOURCE_URL"]
    assert pinned.startswith("file://")
    assert str((project / ".dna").resolve()) in pinned

    # 4. boot the DNA MCP server against the source the block names, and drive
    #    it through the real MCP protocol — recall + compose_prompt + board.
    from fastmcp import Client

    source_dir = str((project / ".dna").resolve())

    async def scenario():
        server = M.build_server(base_dir=source_dir)

        # seed a memory + a board Story on the server's own source (fresh boot on
        # this loop — the server's kernel is lazy too).
        live = await M.boot_live(base_dir=source_dir)
        await live.kernel.write_document(
            _SCOPE, "Story", "s-speckit-live",
            {"apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Story",
             "metadata": {"name": "s-speckit-live"},
             "spec": {"title": "spec-kit live feed", "description": "x", "status": "todo"}},
        )

        async with Client(server) as client:
            names = {t.name for t in await client.list_tools()}
            # the exact tools Layer 2 promises the spec-kit agent, over ONE server.
            assert {"recall", "remember", "compose_prompt", "list_stories"} <= names

            # SOUL — the concierge persona is composed live (the axis a static
            # emit flattens; here it is served live to the spec-kit agent).
            defn = (await client.call_tool(
                "compose_prompt", {"agent": _AGENT, "scope": _SCOPE}
            )).structured_content
            assert "Helpdesk Concierge" in defn["prompt"]

            # MEMORY — the agent can remember + recall across the run.
            await client.call_tool(
                "remember",
                {"summary": "spec-kit run grounded in DNA's live memory over MCP",
                 "scope": _SCOPE},
            )
            mem = (await client.call_tool(
                "recall", {"query": "live memory", "scope": _SCOPE}
            )).structured_content
            assert mem["hits"], "recall returned nothing — memory is not live"

            # BOARD — the spec-kit run's tracking is reachable too.
            board = (await client.call_tool(
                "list_stories", {"scope": _SCOPE}
            )).structured_content
            assert "s-speckit-live" in [s["name"] for s in board["stories"]]

    asyncio.run(scenario())


def test_wire_is_idempotent_alongside_an_existing_run(project):
    """Re-wiring a project that already has the DNA server leaves the config
    byte-identical (a Spec Kit run can re-run `wire` safely)."""
    runner = CliRunner()
    args = ["wire", "--dir", str(project), "--tools", "claude"]
    assert runner.invoke(specify, args, catch_exceptions=False).exit_code == 0
    first = (project / ".mcp.json").read_text()
    r2 = runner.invoke(specify, args, catch_exceptions=False)
    assert r2.exit_code == 0
    assert "skipped" in r2.output
    assert (project / ".mcp.json").read_text() == first
