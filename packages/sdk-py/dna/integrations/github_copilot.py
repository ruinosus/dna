"""Pure binding from a resolved DNA definition to GitHub Copilot SDK."""
from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from typing import Any

from dna.definitions import ResolvedAgent


def _model_id(model: str | None) -> str | None:
    if not model:
        return None
    identifier = model.strip()
    for separator in (":", "/"):
        if separator in identifier:
            return identifier.split(separator, 1)[1].strip()
    return identifier


def _mcp_servers(definition: ResolvedAgent) -> dict[str, dict[str, Any]]:
    servers: dict[str, dict[str, Any]] = {}
    for server in definition.mcp_servers:
        if server.transport == "stdio":
            if not server.command:
                raise ValueError(f"MCP server {server.ref!r} has no stdio command")
            config: dict[str, Any] = {
                "type": "stdio",
                "command": server.command,
                "args": list(server.args),
                "tools": sorted(server.allowed_tools) or ["*"],
            }
            if server.env:
                config["env"] = dict(server.env)
            if server.cwd:
                config["cwd"] = server.cwd
        else:
            if not server.url:
                raise ValueError(f"MCP server {server.ref!r} has no URL")
            config = {
                "type": "http",
                "url": server.url,
                "tools": sorted(server.allowed_tools) or ["*"],
            }
        env_name = server.auth.get("env")
        if env_name:
            value = os.environ.get(str(env_name))
            if not value:
                raise ValueError(
                    f"MCP server {server.ref!r} requires environment variable "
                    f"{env_name!r} for authentication"
                )
            if server.auth.get("kind") == "bearer_env":
                value = f"Bearer {value}"
            header = str(server.auth.get("header") or "Authorization")
            config["headers"] = {header: value}
        servers[server.ref] = config
    return servers


def _confirmation_hook(
    confirm_tools: frozenset[str],
    host_hook: Callable[..., Any] | None,
) -> Callable[..., Any] | None:
    if not confirm_tools and host_hook is None:
        return None

    def handle(hook_input: dict[str, Any], context: dict[str, str]) -> Any:
        tool_name = hook_input.get("toolName")
        if tool_name in confirm_tools:
            return {
                "permissionDecision": "ask",
                "permissionDecisionReason": (
                    f"DNA requires human confirmation for tool {tool_name!r}."
                ),
            }
        return host_hook(hook_input, context) if host_hook is not None else None

    return handle


def build_github_copilot_agent(
    definition: ResolvedAgent,
    *,
    tools: Sequence[Any] = (),
    on_permission_request: Callable[..., Any] | None = None,
    on_pre_tool_use: Callable[..., Any] | None = None,
    instruction_directories: Sequence[str] = (),
    **option_overrides: Any,
) -> Any:
    """Convert data into an agent while leaving lifecycle to the caller."""
    try:
        from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
    except ImportError as error:
        raise ImportError(
            "GitHub Copilot binding requires `dna-sdk[github-copilot]`"
        ) from error

    options = dict(option_overrides)
    model = _model_id(definition.model)
    if model:
        options.setdefault("model", model)
    mcp_servers = _mcp_servers(definition)
    if mcp_servers:
        options.setdefault("mcp_servers", mcp_servers)
    confirmation = _confirmation_hook(
        definition.tools_requiring_confirmation, on_pre_tool_use,
    )
    if confirmation is not None:
        options.setdefault("on_pre_tool_use", confirmation)
    if on_permission_request is not None:
        options.setdefault("on_permission_request", on_permission_request)
    if instruction_directories:
        options.setdefault("instruction_directories", list(instruction_directories))

    return GitHubCopilotAgent(
        name=definition.name,
        description=definition.description,
        instructions=definition.instructions,
        tools=list(tools),
        default_options=GitHubCopilotOptions(**options),
    )


__all__ = ["build_github_copilot_agent"]