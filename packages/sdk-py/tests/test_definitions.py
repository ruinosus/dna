from __future__ import annotations

import pathlib

import pytest
from dna import DnaClient
from dna.definitions import resolve_agent, resolve_copilot
from dna.kernel import Kernel

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = str(_ROOT / "examples" / "emitting-to-a-runtime" / ".dna")
_SCOPE = "concierge"


@pytest.fixture(scope="module")
def manifest():
    return Kernel.quick(_SCOPE, base_dir=_BASE)


def test_resolve_agent_preserves_live_composed_prompt(manifest):
    definition = resolve_agent(manifest)

    assert definition.instructions == manifest.build_prompt("concierge")
    assert definition.scope == _SCOPE
    assert definition.source_kind == "Agent"
    assert definition.source_name == "concierge"


def test_resolve_agent_explicit_name_overrides_genome_default(manifest):
    definition = resolve_agent(manifest, "memory-agent")

    assert definition.name == "memory-agent"
    assert definition.source_name == "memory-agent"
    assert definition.mcp_servers[0].ref == "dna-mcp"


def test_resolve_copilot_preserves_mcp_and_confirmation_policy(manifest):
    definition = resolve_copilot(manifest, "memory-copilot")

    assert definition.instructions == manifest.build_prompt("memory-agent")
    assert definition.source_kind == "Copilot"
    assert definition.source_name == "memory-copilot"
    assert definition.mcp_servers[0].ref == "dna-mcp"
    assert definition.mcp_servers[0].allowed_tools
    assert definition.tools_requiring_confirmation


@pytest.mark.asyncio
async def test_client_exposes_registered_kind_catalog_and_schema():
    async with await DnaClient.from_env(
        scope=_SCOPE, base_dir=_BASE,
    ) as client:
        kinds = await client.kinds.list()
        tool = await client.kinds.describe("Tool")

    assert "Tool" in {descriptor.kind for descriptor in kinds}
    assert tool.plane == "record"
    assert tool.registration_status == "builtin"
    assert "input_schema" in tool.schema["properties"]


@pytest.mark.asyncio
async def test_client_resolves_complete_tool_definitions():
    async with await DnaClient.from_env(
        scope=_SCOPE, base_dir=_BASE,
    ) as client:
        definition = await client.resolve_copilot("memory-copilot")
        tools_page = await client.instances.list("Tool", limit=20)

    tools = {tool.name: tool for tool in definition.tools}
    assert definition.instructions
    assert tools["remember"].invocation_type == "builtin"
    assert tools["remember"].requires_confirmation is True
    assert tools["remember"].input_schema["type"] == "object"
    assert "remember" in {row["name"] for row in tools_page["instances"]}