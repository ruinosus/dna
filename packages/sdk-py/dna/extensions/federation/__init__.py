"""Phase 14r — MCP Federation extension (schema v2, 2026-07-07).

Declares the ``MCPFederation`` Kind: a declarative description of an
external MCP server whose tools are consumed by DNA agents.

This is graphify-inspired but tool-agnostic — any MCP-compliant server
that speaks JSON-RPC over stdio or Streamable HTTP (Sourcegraph MCP,
ast-grep, mcp.draw.io, custom domain-specific servers, etc.) plugs in
via the same Kind.

The Kind itself only declares the configuration; connection lifecycle
lives in the harness so the SDK core stays runtime-free:

  - agent runtime (primary, s-mcp-servers-on-agent):
    ``dna_shared/manifest_tools/mcp_tools.py`` resolves
    ``Agent.spec.mcp_servers`` refs to these docs and loads the
    remote tools as first-class LangChain StructuredTools.
  - DNA-as-MCP-server proxy (legacy Phase 14r direction):
    ``dna_shared/mcp_server/federation.py``.

Schema v2 (spec 2026-07-07-mcp-first-tools-design.md, §5.1) is fully
backward-compatible with v1 docs: ``transport`` defaults to ``stdio``
and every new field is optional. Secrets NEVER live in the doc — the
``auth`` block carries env-var *names* only, read at connect time.

Tenancy máxima: MCPFederation docs are shared infra defaults inherited
from ``_lib`` (herdável ⇒ nunca TENANTED) — permissive tenancy: base +
per-tenant override.
"""
from __future__ import annotations

from typing import Any

from dna.kernel.protocols import StorageDescriptor
from dna.kernel.kind_base import KindBase

_API_VERSION = "github.com/ruinosus/dna/federation/v1"
_ORIGIN = "github.com/ruinosus/dna/federation"


class MCPFederationKind(KindBase):
    api_version = _API_VERSION
    kind = "MCPFederation"
    alias = "federation-mcp"
    model = dict
    origin = _ORIGIN
    storage = StorageDescriptor.yaml("federations")
    graph_style = {"fill": "#F97316", "stroke": "#EA580C", "text_color": "#fff"}
    ascii_icon = "🛰️"
    display_label = "MCP Federations"
    is_prompt_target = False
    prompt_target_priority = 0
    flatten_in_context = False
    docs = (
        "An MCPFederation declares an external MCP server whose tools DNA "
        "agents consume: a Agent lists the doc's name in "
        "spec.mcp_servers and the harness loads the remote tools as "
        "first-class agent tools (zero code, zero deploy). Transports: "
        "stdio (command/args/env/cwd) or streamable_http (url). Auth "
        "carries env-var NAMES only — never secret values. allowed_tools "
        "bounds what any agent can get; enabled: false is the declarative "
        "kill-switch. Docs in _lib/federations/ are inherited by every "
        "scope. Also consumed by the DNA-as-MCP-server proxy (Phase 14r)."
    )

    def schema(self) -> dict[str, Any] | None:
        # v2 (spec 2026-07-07-mcp-first-tools-design.md §5.1). Back-compat:
        # every v1 doc (required command, stdio implied) stays valid —
        # ``transport`` defaults to stdio and ``command`` is enforced for
        # stdio (resp. ``url`` for streamable_http) via allOf/if-then
        # instead of a top-level ``required: [command]``.
        return {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "transport": {
                    "type": "string",
                    "enum": ["stdio", "streamable_http"],
                    "default": "stdio",
                    "description": "How to reach the server: stdio subprocess (default, v1) or Streamable HTTP.",
                },
                "url": {
                    "type": "string",
                    "description": "Server endpoint. Required when transport=streamable_http.",
                },
                "command": {
                    "type": "string",
                    "description": "Executable to run (resolved via PATH). Required when transport=stdio.",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
                "env": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "default": {},
                    "description": "Extra env vars merged onto os.environ for the subprocess.",
                },
                "cwd": {
                    "type": ["string", "null"],
                    "description": "Working directory; null = scope dir.",
                },
                "tool_prefix": {
                    "type": "string",
                    "description": "Prepended to every proxied tool name (e.g. 'graphify_').",
                    "default": "",
                },
                "enabled": {
                    "type": "boolean",
                    "default": True,
                    "description": "Disable without deleting the doc — declarative kill-switch, no deploy.",
                },
                "allowed_tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Server-level allowlist of remote tool names (pre-prefix). Empty = all.",
                },
                "timeout_s": {
                    "type": "integer",
                    "default": 30,
                    "description": "Per-call timeout default (seconds). Per-agent entry may override.",
                },
                "auth": {
                    "type": "object",
                    "additionalProperties": False,
                    "description": "Auth by env-var NAME — the value is read from the process env at connect time and never stored in docs, logs, or events.",
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": ["none", "bearer_env", "header_env"],
                            "default": "none",
                        },
                        "env": {
                            "type": "string",
                            "description": "Name of the env var holding the secret value.",
                        },
                        "header": {
                            "type": "string",
                            "description": "Header to carry the value (header_env only; bearer_env implies Authorization: Bearer).",
                        },
                    },
                },
                "propagate_tenant": {
                    "type": "boolean",
                    "default": True,
                    "description": "HTTP transport: stamp X-DNA-Tenant-Effective / X-DNA-Scope / X-DNA-Agent headers.",
                },
                "health_check": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {
                        "interval_s": {"type": "integer", "default": 30},
                        "timeout_s": {"type": "integer", "default": 5},
                    },
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
            },
            "allOf": [
                {
                    # NOTE: ``required: [transport]`` inside the ``if`` is
                    # load-bearing — without it an absent ``transport``
                    # matches the const vacuously and v1 docs would be
                    # forced to carry ``url``.
                    "if": {
                        "properties": {"transport": {"const": "streamable_http"}},
                        "required": ["transport"],
                    },
                    "then": {"required": ["url"]},
                    "else": {"required": ["command"]},
                },
            ],
        }

    def describe(self, doc: Any) -> str | None:
        spec = getattr(doc, "spec", None) or {}
        if not isinstance(spec, dict):
            spec = dict(spec) if spec else {}
        transport = spec.get("transport") or "stdio"
        target = (
            spec.get("url") if transport == "streamable_http" else spec.get("command")
        ) or "?"
        prefix = spec.get("tool_prefix") or ""
        return f"{target} ({prefix or 'no-prefix'})"

    def summary(self, doc: Any) -> dict[str, Any] | None:
        spec = getattr(doc, "spec", None) or {}
        if not isinstance(spec, dict):
            spec = dict(spec) if spec else {}
        return {
            "transport": spec.get("transport") or "stdio",
            "url": spec.get("url", ""),
            "command": spec.get("command", ""),
            "tool_prefix": spec.get("tool_prefix", ""),
            "enabled": bool(spec.get("enabled", True)),
            "tags": spec.get("tags") or [],
        }


class FederationExtension:
    name = "federation"
    version = "1.0.0"

    def register(self, kernel: Any) -> None:
        kernel.kind(MCPFederationKind())
