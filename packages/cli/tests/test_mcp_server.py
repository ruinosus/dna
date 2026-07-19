"""Tests for the DNA **MCP runtime face** (``dna_cli._mcp_server`` + ``dna mcp``).

The thesis end-to-end: ONE thin MCP server exposes everything DNA stores — agent
DEFINITIONS composed live + tenant-aware, the self-describing SDLC board, and
declarative MEMORY — over the neutral MCP protocol. These tests instantiate the
real server in-process (no subprocess) against the committed
``examples/emitting-to-a-runtime`` concierge scope (copied to a tmp dir so the
tenant-overlay case can write into it) and drive the tools.

The behavioral assertions run against the pure impls (version-independent); a
couple go through the real ``FastMCP`` (``list_tools`` / ``call_tool``) to prove
the tools are actually wired into the protocol surface.
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
    """A writable copy of the concierge scope (so tenant overlays + SDLC/memory
    docs can be written into it), wired as the source via DNA_BASE_DIR."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


# ── definitions: compose_prompt recovers what emit loses ──────────────────


def test_compose_prompt_live(dna_dir):
    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        res = await M.compose_prompt_impl(live, _AGENT, scope=_SCOPE)
        return res

    res = asyncio.run(scenario())
    assert res["scope"] == _SCOPE
    assert res["agent"] == _AGENT
    # The Soul persona ("Helpdesk Concierge") is COMPOSED into the prompt — not
    # a copy in the one-line Agent instruction. That composition is exactly the
    # axis a static emit flattens.
    assert "Helpdesk Concierge" in res["prompt"]
    # ...and the Agent's own instruction line survives too.
    assert "runbook" in res["prompt"].lower()


def test_compose_prompt_unknown_agent_raises(dna_dir):
    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        await M.compose_prompt_impl(live, "nope", scope=_SCOPE)

    with pytest.raises(ValueError, match="not found"):
        asyncio.run(scenario())


def test_compose_prompt_tenant_overlay(dna_dir):
    """The killer feature: compose_prompt with a tenant returns the per-tenant
    overlay — the composition emit cannot express in a flat file."""
    sentinel = "ACME-ONLY escalation: page the on-call SRE before answering."

    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        # Write a per-tenant override of the concierge Agent (a different
        # instruction) through the kernel's tenant writer — the source stores it
        # as a tenant overlay, NOT a base fork.
        overlay = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": {"name": _AGENT},
            "spec": {
                "instruction": sentinel,
                "layout": "persona-first",
                "soul": "helpdesk-host",
                "guardrails": ["grounded-citation"],
                "tools": ["kb-search"],
                "model": "azure/gpt-4o",
            },
        }
        await live.kernel.with_tenant("acme").write_document(
            _SCOPE, "Agent", _AGENT, overlay
        )
        base = await M.compose_prompt_impl(live, _AGENT, scope=_SCOPE)
        tenant = await M.compose_prompt_impl(live, _AGENT, scope=_SCOPE, tenant="acme")
        return base, tenant

    base, tenant = asyncio.run(scenario())
    assert tenant["tenant"] == "acme"
    # The overlay changed the composition: the tenant prompt carries the
    # ACME-only instruction; the base prompt does NOT.
    assert sentinel in tenant["prompt"]
    assert sentinel not in base["prompt"]
    # Both still compose the shared Soul persona.
    assert "Helpdesk Concierge" in tenant["prompt"]


# ── definitions: list_agents / list_tools / get_tool ──────────────────────


def test_list_agents_and_tools(dna_dir):
    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        agents = await M.list_agents_impl(live, scope=_SCOPE)
        tools = await M.list_tools_impl(live, scope=_SCOPE)
        tool = await M.get_tool_impl(live, "kb-search", scope=_SCOPE)
        return agents, tools, tool

    agents, tools, tool = asyncio.run(scenario())
    assert _AGENT in [a["name"] for a in agents["agents"]]
    assert "kb-search" in [t["name"] for t in tools["tools"]]
    assert tool["name"] == "kb-search"
    assert "knowledge base" in tool["description"].lower()
    # The Tool's input JSON Schema is surfaced verbatim (what a model fills in).
    assert tool["parameters"]["properties"]["query"]["type"] == "string"


def test_get_tool_unknown_raises(dna_dir):
    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        await M.get_tool_impl(live, "no-such-tool", scope=_SCOPE)

    with pytest.raises(ValueError):
        asyncio.run(scenario())


# ── SDLC: digest / list_stories / get_adr ─────────────────────────────────


def test_sdlc_surface(dna_dir):
    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        # Seed one ADR + one Story into the scope so the SDLC surface returns
        # REAL data end-to-end (not just an empty-but-valid shape).
        await live.kernel.write_document(
            _SCOPE, "ADR", "adr-demo",
            {
                "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
                "kind": "ADR",
                "metadata": {"name": "adr-demo"},
                "spec": {"title": "Demo decision", "description": "demo", "status": "accepted",
                         "context": "why", "decision": "what"},
            },
        )
        await live.kernel.write_document(
            _SCOPE, "Story", "s-demo",
            {
                "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
                "kind": "Story",
                "metadata": {"name": "s-demo"},
                "spec": {"title": "Demo story", "description": "demo", "status": "todo"},
            },
        )
        digest = await M.sdlc_digest_impl(live, scope=_SCOPE)
        stories = await M.list_stories_impl(live, scope=_SCOPE)
        adr = await M.get_adr_impl(live, "adr-demo", scope=_SCOPE)
        return digest, stories, adr

    digest, stories, adr = asyncio.run(scenario())
    # digest is the aggregator's well-formed dict (buckets present).
    assert "completed" in digest and "attention" in digest
    assert "s-demo" in [s["name"] for s in stories["stories"]]
    assert adr["name"] == "adr-demo"
    assert adr["decision"] == "what"


def test_get_adr_unknown_raises(dna_dir):
    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        await M.get_adr_impl(live, "missing", scope=_SCOPE)

    with pytest.raises(ValueError, match="not found"):
        asyncio.run(scenario())


# ── memory: remember → recall round-trip ──────────────────────────────────


def test_memory_round_trip(dna_dir):
    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        out = await M.remember_impl(
            live,
            "the DNA pivot chose portability over prompt-management because "
            "runtimes proliferate in 2026",
            scope=_SCOPE,
            tags=["pivot", "portability"],
        )
        hits = await M.recall_impl(live, "why the pivot", scope=_SCOPE, k=5)
        return out, hits

    out, hits = asyncio.run(scenario())
    assert out["kind"] == "Engram"
    names = [h.get("name") for h in hits["hits"]]
    assert out["name"] in names


# ── the thesis smoke: ONE server, definitions + SDLC + memory ─────────────


def test_one_server_exposes_definitions_sdlc_and_memory(dna_dir):
    """A single MCP client reaches DEFINITIONS + SDLC + MEMORY from the SAME
    server, driven through the real FastMCP protocol via the in-memory Client."""
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))

        # Seed one Story so the SDLC surface returns real data (write on THIS
        # loop via a fresh boot — the server's own kernel is built lazily too).
        live = await M.boot_live(base_dir=str(dna_dir))
        await live.kernel.write_document(
            _SCOPE, "Story", "s-smoke",
            {"apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Story",
             "metadata": {"name": "s-smoke"},
             "spec": {"title": "smoke", "description": "smoke", "status": "todo"}},
        )

        async with Client(server) as client:
            # every advertised tool is on the protocol surface.
            names = {t.name for t in await client.list_tools()}
            assert {
                "compose_prompt", "list_agents", "list_tools", "get_tool",
                "sdlc_digest", "list_stories", "get_adr",
                "recall", "remember", "consolidate",
            } <= names

            # resources are advertised too (proving resources beyond tools).
            templates = {
                str(r.uriTemplate) for r in await client.list_resource_templates()
            }
            assert "dna://{scope}/manifest" in templates

            # DEFINITIONS
            defn = (await client.call_tool(
                "compose_prompt", {"agent": _AGENT, "scope": _SCOPE}
            )).structured_content
            assert "Helpdesk Concierge" in defn["prompt"]

            # SDLC
            sdlc = (await client.call_tool(
                "list_stories", {"scope": _SCOPE}
            )).structured_content
            assert "s-smoke" in [s["name"] for s in sdlc["stories"]]

            # MEMORY
            await client.call_tool(
                "remember",
                {"summary": "smoke memory: the MCP face is the live layer",
                 "scope": _SCOPE},
            )
            mem = (await client.call_tool(
                "recall", {"query": "live layer", "scope": _SCOPE}
            )).structured_content
            assert mem["hits"], "recall returned no memory from the same server"

    asyncio.run(scenario())


# ── the [mcp] extra stays optional (lazy import) ──────────────────────────


def test_base_import_never_pulls_mcp():
    """Importing the CLI package (and even the server module) must NOT import
    the optional `fastmcp`/`mcp` packages at module load — only build_server()
    does. Guards the promise that the base install carries no MCP requirement."""
    import importlib

    # dna_cli itself + the CLI command module: importable with no fastmcp/mcp in
    # the import chain (mcp_cmd defers the server import into serve(), and the
    # server module defers `from fastmcp import FastMCP` into build_server).
    importlib.import_module("dna_cli")
    importlib.import_module("dna_cli.mcp_cmd")
    mod = importlib.import_module("dna_cli._mcp_server")

    # The real guard: the ONLY fastmcp/mcp import is lazy (inside build_server);
    # no top-level `import fastmcp` / `from fastmcp ...` / `import mcp` at module
    # scope.
    src = pathlib.Path(mod.__file__).read_text()
    assert "from fastmcp import FastMCP" in src  # it IS imported, lazily
    top_level = [
        ln for ln in src.splitlines()
        if ln.startswith(("import fastmcp", "from fastmcp", "import mcp", "from mcp"))
    ]
    assert top_level == [], f"MCP deps must be imported lazily, found top-level: {top_level}"
