from __future__ import annotations

import sys
from types import ModuleType

import pytest
from dna.definitions import ResolvedAgent, ResolvedMcpServer
from dna.integrations.github_copilot import build_github_copilot_agent


class _FakeAgent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.fixture(autouse=True)
def fake_provider(monkeypatch):
    module = ModuleType("agent_framework.github")
    module.GitHubCopilotAgent = _FakeAgent
    module.GitHubCopilotOptions = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "agent_framework.github", module)


def test_binding_maps_definition_without_owning_runtime(monkeypatch):
    monkeypatch.setenv("DNA_MCP_TOKEN", "secret")
    permission_handler = object()
    definition = ResolvedAgent(
        name="reviewer",
        description="Repository reviewer",
        instructions="Composed live by DNA",
        model="azure/gpt-4o",
        mcp_servers=(ResolvedMcpServer(
            ref="dna-mcp",
            transport="streamable-http",
            url="https://mcp.example/mcp",
            auth={"kind": "bearer_env", "env": "DNA_MCP_TOKEN"},
            allowed_tools=("recall", "forget"),
        ),),
        tools_requiring_confirmation=frozenset({"forget"}),
    )

    agent = build_github_copilot_agent(
        definition,
        tools=["local-tool"],
        on_permission_request=permission_handler,
        instruction_directories=[".copilot/instructions"],
    )

    assert agent.kwargs["instructions"] == definition.instructions
    assert agent.kwargs["tools"] == ["local-tool"]
    options = agent.kwargs["default_options"]
    assert options["model"] == "gpt-4o"
    assert options["on_permission_request"] is permission_handler
    assert options["mcp_servers"]["dna-mcp"]["headers"] == {
        "Authorization": "Bearer secret"
    }
    assert options["on_pre_tool_use"](
        {"toolName": "forget"}, {}
    )["permissionDecision"] == "ask"


def test_binding_fails_when_declared_auth_is_missing(monkeypatch):
    monkeypatch.delenv("MISSING_TOKEN", raising=False)
    definition = ResolvedAgent(
        name="reviewer",
        instructions="DNA",
        mcp_servers=(ResolvedMcpServer(
            ref="private",
            transport="streamable-http",
            url="https://mcp.example/mcp",
            auth={"env": "MISSING_TOKEN"},
        ),),
    )

    with pytest.raises(ValueError, match="MISSING_TOKEN"):
        build_github_copilot_agent(definition)


def test_binding_maps_stdio_mcp_process_configuration():
    definition = ResolvedAgent(
        name="filesystem-agent",
        instructions="DNA",
        mcp_servers=(ResolvedMcpServer(
            ref="filesystem",
            transport="stdio",
            command="npx",
            args=("-y", "@modelcontextprotocol/server-filesystem", "."),
            env={"LOG_LEVEL": "error"},
            cwd="/workspace",
        ),),
    )

    agent = build_github_copilot_agent(definition)

    assert agent.kwargs["default_options"]["mcp_servers"]["filesystem"] == {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
        "tools": ["*"],
        "env": {"LOG_LEVEL": "error"},
        "cwd": "/workspace",
    }