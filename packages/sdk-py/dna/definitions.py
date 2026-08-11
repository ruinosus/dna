"""Public, runtime-neutral projections of resolved DNA definitions.

These values are the hand-off between DNA's declarative kernel and a
consumer-owned runtime.  They contain data only: importing this module never
starts a server, creates a runtime session, or invokes a model.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class ResolvedMcpServer:
    """One MCP federation resolved for an agent."""

    ref: str
    transport: str
    url: str | None = None
    command: str | None = None
    args: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    cwd: str | None = None
    auth: Mapping[str, Any] = field(default_factory=dict)
    allowed_tools: tuple[str, ...] = ()
    propagate_tenant: bool = True


@dataclass(frozen=True)
class ResolvedTool:
    """A complete, runtime-neutral ``Tool`` definition."""

    name: str
    description: str = ""
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    output_schema: Mapping[str, Any] = field(default_factory=dict)
    invocation_type: str | None = None
    endpoint: str | None = None
    method: str | None = None
    mcp_server: str | None = None
    mcp_tool: str | None = None
    python_module: str | None = None
    python_callable: str | None = None
    shell_command: str | None = None
    auth_type: str | None = None
    auth_env_var: str | None = None
    read_only: bool = False
    requires_confirmation: bool = False
    tags: tuple[str, ...] = ()
    examples: tuple[Mapping[str, Any], ...] = ()

    @classmethod
    def from_instance(cls, raw: Mapping[str, Any]) -> ResolvedTool:
        """Project a kernel instance envelope without resolving credentials."""
        metadata = raw.get("metadata") or {}
        spec = raw.get("spec") or {}
        return cls(
            name=str(metadata.get("name") or raw.get("name") or ""),
            description=str(metadata.get("description") or ""),
            input_schema=dict(spec.get("input_schema") or {}),
            output_schema=dict(spec.get("output_schema") or {}),
            invocation_type=spec.get("type"),
            endpoint=spec.get("endpoint"),
            method=spec.get("method"),
            mcp_server=spec.get("mcp_server"),
            mcp_tool=spec.get("mcp_tool"),
            python_module=spec.get("python_module"),
            python_callable=spec.get("python_callable"),
            shell_command=spec.get("shell_command"),
            auth_type=spec.get("auth_type"),
            auth_env_var=spec.get("auth_env_var"),
            read_only=bool(spec.get("read_only", False)),
            requires_confirmation=bool(spec.get("requires_confirmation", False)),
            tags=tuple(spec.get("tags") or ()),
            examples=tuple(dict(item) for item in (spec.get("examples") or ())),
        )


@dataclass(frozen=True)
class ResolvedAgent:
    """A composed Agent or Copilot definition, independent of any runtime."""

    name: str
    instructions: str
    description: str = ""
    model: str | None = None
    tools: tuple[ResolvedTool, ...] = ()
    output_schema: Mapping[str, Any] | None = None
    scope: str | None = None
    mcp_servers: tuple[ResolvedMcpServer, ...] = ()
    tools_requiring_confirmation: frozenset[str] = frozenset()
    tenant_propagate: bool = False
    knowledge: tuple[str, ...] = ()
    workflow: tuple[str, ...] = ()
    source_kind: str = "Agent"
    source_name: str | None = None

    def with_tools(self, tools: tuple[ResolvedTool, ...]) -> ResolvedAgent:
        """Return a copy enriched with complete Tool definitions."""
        return replace(self, tools=tools)


@dataclass(frozen=True)
class RuntimePolicy:
    """Runtime behavior requested by a binding, without transport state."""

    sessions: str | None = None
    reconnect: str | None = None
    confirmations: str | None = None


@dataclass(frozen=True)
class ResolvedRuntimeBinding:
    """A portable runtime target resolved without endpoints or credentials."""

    name: str
    agent: str
    protocol: str
    host_ref: str
    provider: str | None = None
    policy: RuntimePolicy = field(default_factory=RuntimePolicy)
    scope: str | None = None

    @classmethod
    def from_instance(
        cls, raw: Mapping[str, Any], *, scope: str | None = None,
    ) -> ResolvedRuntimeBinding:
        metadata = raw.get("metadata") or {}
        spec = raw.get("spec") or {}
        runtime = spec.get("runtime") or {}
        host = spec.get("host") or {}
        policy = spec.get("policy") or {}
        required = {
            "metadata.name": metadata.get("name"),
            "spec.agent": spec.get("agent"),
            "spec.runtime.protocol": runtime.get("protocol"),
            "spec.host.ref": host.get("ref"),
        }
        missing = [path for path, value in required.items() if not value]
        if missing:
            raise ValueError(
                "RuntimeBinding is missing required fields: " + ", ".join(missing)
            )
        host_ref = str(host["ref"])
        if "://" in host_ref:
            raise ValueError(
                "RuntimeBinding spec.host.ref must name a deployment host, "
                "not contain a raw endpoint"
            )
        return cls(
            name=str(metadata["name"]),
            agent=str(spec["agent"]),
            protocol=str(runtime["protocol"]),
            provider=(str(runtime["provider"]) if runtime.get("provider") else None),
            host_ref=host_ref,
            policy=RuntimePolicy(
                sessions=policy.get("sessions"),
                reconnect=policy.get("reconnect"),
                confirmations=policy.get("confirmations"),
            ),
            scope=scope,
        )


@dataclass(frozen=True)
class ResolvedGenUIComponent:
    """A portable GenUI contract resolved without executable renderer code."""

    name: str
    tool_name: str
    description: str
    input_schema: Mapping[str, Any]
    renderer_ref: str
    protocols: tuple[str, ...]
    required_capabilities: frozenset[str]
    fallback_type: str
    fallback_message: str | None = None
    contract_version: int = 1
    scope: str | None = None

    @classmethod
    def from_instance(
        cls, raw: Mapping[str, Any], *, scope: str | None = None,
    ) -> ResolvedGenUIComponent:
        metadata = raw.get("metadata") or {}
        spec = raw.get("spec") or {}
        fallback = spec.get("fallback") or {}
        required = {
            "name": metadata.get("name") or raw.get("name"),
            "spec.tool_name": spec.get("tool_name"),
            "spec.description": spec.get("description"),
            "spec.input_schema": spec.get("input_schema"),
            "spec.renderer_ref": spec.get("renderer_ref"),
            "spec.protocols": spec.get("protocols"),
            "spec.fallback.type": fallback.get("type"),
        }
        missing = [path for path, value in required.items() if not value]
        if missing:
            raise ValueError(
                "GenUIComponent is missing required fields: " + ", ".join(missing)
            )
        renderer_ref = str(spec["renderer_ref"])
        if "://" in renderer_ref or "/" in renderer_ref:
            raise ValueError(
                "GenUIComponent spec.renderer_ref must be a symbolic host key, "
                "not code, a path, or a remote URL"
            )
        return cls(
            name=str(metadata.get("name") or raw["name"]),
            tool_name=str(spec["tool_name"]),
            description=str(spec["description"]),
            input_schema=dict(spec["input_schema"]),
            renderer_ref=renderer_ref,
            protocols=tuple(str(item) for item in spec["protocols"]),
            required_capabilities=frozenset(
                str(item) for item in spec.get("required_capabilities") or ()
            ),
            fallback_type=str(fallback["type"]),
            fallback_message=(
                str(fallback["message"]) if fallback.get("message") else None
            ),
            contract_version=int(spec.get("contract_version", 1)),
            scope=scope,
        )


@dataclass(frozen=True)
class ResolvedGenUIBinding:
    """An explicit assignment of GenUI components to one DNA Agent."""

    name: str
    agent: str
    components: tuple[str, ...]
    scope: str | None = None

    @classmethod
    def from_instance(
        cls, raw: Mapping[str, Any], *, scope: str | None = None,
    ) -> ResolvedGenUIBinding:
        metadata = raw.get("metadata") or {}
        spec = raw.get("spec") or {}
        name = metadata.get("name") or raw.get("name")
        required = {
            "name": name,
            "spec.agent": spec.get("agent"),
            "spec.components": spec.get("components"),
        }
        missing = [path for path, value in required.items() if not value]
        if missing:
            raise ValueError(
                "GenUIBinding is missing required fields: " + ", ".join(missing)
            )
        return cls(
            name=str(name),
            agent=str(spec["agent"]),
            components=tuple(str(item) for item in spec["components"]),
            scope=scope,
        )


@dataclass(frozen=True)
class KindDescriptor:
    """Stable public description of a Kind active in one scope."""

    kind: str
    api_version: str
    alias: str | None = None
    origin: str | None = None
    registration_status: str = "builtin"
    family: str | None = None
    plane: str = "composition"
    display_label: str | None = None
    tenant_scope: str | None = None
    storage_pattern: str | None = None
    traits: tuple[str, ...] = ()
    schema: Mapping[str, Any] = field(default_factory=dict)
    ui_schema: Mapping[str, Any] = field(default_factory=dict)
    docs: str | None = None
    writable: bool = False
    write_refusal: str | None = None
    deletable: bool = False
    delete_refusal: str | None = None


def _from_emit_context(
    context: Any, *, source_kind: str, source_name: str,
) -> ResolvedAgent:
    """Compatibility projection while emitters migrate to this contract."""
    return ResolvedAgent(
        name=context.name,
        description=context.description,
        instructions=context.instructions,
        model=context.model,
        tools=tuple(
            ResolvedTool(
                name=str(tool.get("name", "")),
                description=str(tool.get("description", "")),
                input_schema=dict(tool.get("parameters") or {}),
            )
            for tool in context.tools
        ),
        output_schema=(
            dict(context.output_schema) if context.output_schema is not None else None
        ),
        scope=context.scope,
        mcp_servers=tuple(
            ResolvedMcpServer(
                ref=server.ref,
                transport=server.transport,
                url=server.url,
                command=server.command,
                args=tuple(server.args),
                env=dict(server.env),
                cwd=server.cwd,
                auth=dict(server.auth),
                allowed_tools=tuple(server.allowed_tools),
                propagate_tenant=server.propagate_tenant,
            )
            for server in context.mcp_servers
        ),
        tools_requiring_confirmation=frozenset(
            context.tools_requiring_confirmation
        ),
        tenant_propagate=context.tenant_propagate,
        knowledge=tuple(context.knowledge),
        workflow=tuple(context.workflow),
        source_kind=source_kind,
        source_name=source_name,
    )


def resolve_agent(
    manifest: Any,
    name: str | None = None,
    *,
    model: str | None = None,
    provider: str | None = None,
) -> ResolvedAgent:
    """Resolve an explicit Agent or the Genome's ``default_agent``."""
    from dna.emit import build_emit_context, project_agent_mcp_servers
    from dna.kernel.errors import AgentNotFound

    resolved_name = name
    if resolved_name is None:
        default = manifest.default_agent()
        resolved_name = getattr(default, "name", None) if default is not None else None
    if not resolved_name:
        raise AgentNotFound(
            "no Agent was selected and the scope's Genome declares no default_agent"
        )

    context = build_emit_context(
        manifest, resolved_name, model=model, provider=provider,
    )
    agent = manifest._one("Agent", resolved_name)
    if agent is not None:
        context.mcp_servers = project_agent_mcp_servers(manifest, agent.spec)
        context.tenant_propagate = any(
            server.propagate_tenant for server in context.mcp_servers
        )
    return _from_emit_context(
        context, source_kind="Agent", source_name=resolved_name,
    )


def resolve_copilot(
    manifest: Any,
    name: str,
    *,
    model: str | None = None,
    provider: str | None = None,
) -> ResolvedAgent:
    """Resolve one Copilot and its mounted Agent through a live manifest."""
    from dna.emit import build_copilot_context

    context = build_copilot_context(manifest, name, model=model, provider=provider)
    return _from_emit_context(context, source_kind="Copilot", source_name=name)


__all__ = [
    "KindDescriptor",
    "ResolvedAgent",
    "ResolvedGenUIBinding",
    "ResolvedGenUIComponent",
    "ResolvedMcpServer",
    "ResolvedRuntimeBinding",
    "ResolvedTool",
    "RuntimePolicy",
    "resolve_agent",
    "resolve_copilot",
]
