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

from typing import Any, Iterable, Mapping

from dna.kernel.protocols import ExtensionHost, StorageDescriptor
from dna.kernel.kind_base import KindBase

_API_VERSION = "github.com/ruinosus/dna/federation/v1"
_ORIGIN = "github.com/ruinosus/dna/federation"

# ── RBAC (absorption phase 6a, design §6.4) ──────────────────────────────────
# Read/write tool governance + per-tool role floors, mirroring
# foundry-assured's McpServer registry (apps/backend/app/agents/mcp/registry.py)
# adapted to DNA's role ladder. Foundry uses a flat named-grant set
# (Reader/Author/Approver/Admin); DNA's ladder is rank-based
# (portfolio Role Kind: guest < member < admin < owner, "highest-role-wins
# compares rank"), so the floor is a RANK comparison, not set membership.
#
# These are PURE functions (no network, no framework, no auth imports) so they
# unit-test in isolation and can be reused by the emitter and the harness
# mcp_tools resolver.
#
# Back-compat is SACRED: the flat ``allowed_tools`` allowlist is unchanged. The
# read/write split + role floors are ADDITIVE, OPTIONAL refinements — when the
# split is not declared (both read_tools and write_tools empty), RBAC is OFF and
# ``allowed_tools`` governs alone, exactly as before this extension existed.

# The standard DNA ladder ranks (higher = more access). A tenant may add custom
# rungs as Role docs; a runtime consumer with the tenant's ladder can inject
# ranks via the ``role_ranks`` param. The pure default is the standard ladder.
STANDARD_ROLE_RANKS: dict[str, int] = {
    "guest": 0,
    "member": 10,
    "admin": 20,
    "owner": 30,
}


def _rank(role_id: str, role_ranks: Mapping[str, int] | None) -> int:
    """Rank of a single role_id; unknown → -1 (below the whole ladder,
    fail-closed)."""
    ranks = role_ranks if role_ranks is not None else STANDARD_ROLE_RANKS
    return ranks.get(role_id, -1)


def _max_rank(roles: Iterable[str], role_ranks: Mapping[str, int] | None) -> int:
    """Highest-role-wins: the max rank among a caller's roles; no roles → -1."""
    ranks = [_rank(r, role_ranks) for r in roles]
    return max(ranks) if ranks else -1


def _satisfies(
    roles: Iterable[str], floor: str, role_ranks: Mapping[str, int] | None
) -> bool:
    """True if the caller's highest role meets the floor. Fail-closed on an
    unknown floor (rank -1 would let anyone in, so an unrecognized floor DENIES
    instead)."""
    floor_rank = _rank(floor, role_ranks)
    if floor_rank < 0:
        return False  # unknown floor → deny (better closed than silently open)
    return _max_rank(roles, role_ranks) >= floor_rank


def _spec_dict(spec: Any) -> dict[str, Any]:
    if isinstance(spec, dict):
        return spec
    return dict(spec) if spec else {}


def classify_tool(spec: Any, tool_name: str) -> str:
    """'read' | 'write'. Fail-closed: a tool on NEITHER list is a WRITE — an
    unclassified new tool can't slip through as an open read. Mirrors foundry's
    ``classify_tool``. (Only meaningful once the read/write split is declared;
    with no split every tool classifies as 'write'.)"""
    s = _spec_dict(spec)
    if tool_name in (s.get("read_tools") or []):
        return "read"
    return "write"


def visible_tools(
    spec: Any,
    roles: Iterable[str],
    *,
    role_ranks: Mapping[str, int] | None = None,
) -> tuple[list[str], list[str]]:
    """(read_tools, write_tools) this caller may see, gated by role. The caller
    never sees a tool above their grant, and a no-role caller sees nothing
    (fail-closed). Mirrors foundry's ``visible_tools``."""
    s = _spec_dict(spec)
    reads = list(s.get("read_tools") or [])
    writes = list(s.get("write_tools") or [])
    min_role = s.get("min_role") or "guest"
    min_role_write = s.get("min_role_write") or "member"
    visible_reads = reads if _satisfies(roles, min_role, role_ranks) else []
    visible_writes = writes if _satisfies(roles, min_role_write, role_ranks) else []
    return visible_reads, visible_writes


def resolve_tools(
    spec: Any,
    roles: Iterable[str] | None = None,
    *,
    role_ranks: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Effective tool governance for a caller against a federation doc.

    Returns ``{"rbac": bool, "reads": [...], "writes": [...], "allowed": [...]}``.

    - **rbac False (legacy / no split declared):** ``allowed_tools`` is returned
      untouched in ``allowed`` (empty = all, exactly as v2), ``reads``/``writes``
      are empty, and NO role gating is applied. This is the SACRED back-compat
      path — a legacy doc behaves exactly as before.
    - **rbac True (split declared):** ``reads``/``writes`` are the role-gated
      visible sets; if ``allowed_tools`` is non-empty it is an outer bound
      (stricter-of-both — it can only tighten, never loosen), mirroring foundry's
      registry ∧ connection min-role.
    """
    s = _spec_dict(spec)
    roles = set(roles or ())
    read_tools = s.get("read_tools") or []
    write_tools = s.get("write_tools") or []
    allowed = list(s.get("allowed_tools") or [])
    rbac_on = bool(read_tools or write_tools)
    if not rbac_on:
        return {"rbac": False, "reads": [], "writes": [], "allowed": allowed}
    reads, writes = visible_tools(s, roles, role_ranks=role_ranks)
    if allowed:
        aset = set(allowed)
        reads = [t for t in reads if t in aset]
        writes = [t for t in writes if t in aset]
    return {"rbac": True, "reads": reads, "writes": writes, "allowed": allowed}


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
                "read_tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "RBAC read set (§6.4): non-mutating tool names callable by roles at or above min_role. ADDITIVE optional refinement over allowed_tools — when read_tools and write_tools are both empty the split is undeclared, RBAC is OFF, and allowed_tools governs alone (back-compat). When declared, a tool in NEITHER read_tools nor write_tools is not exposed (fail-closed).",
                },
                "write_tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "RBAC write set (§6.4): mutating tool names callable by roles at or above min_role_write. These are the tools routed through HITL confirmation. An unclassified tool is treated as a write (fail-closed).",
                },
                "min_role": {
                    "type": "string",
                    "default": "guest",
                    "description": "Role floor for read_tools — the lowest ladder rung (guest<member<admin<owner; highest-role-wins compares rank) whose members may call read tools.",
                },
                "min_role_write": {
                    "type": "string",
                    "default": "member",
                    "description": "Role floor for write_tools — the lowest ladder rung whose members may call write (mutating) tools.",
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

    def register(self, kernel: ExtensionHost) -> None:
        kernel.kind(MCPFederationKind())
