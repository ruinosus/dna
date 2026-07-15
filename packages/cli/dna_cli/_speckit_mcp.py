"""Pure planner for ``dna specify wire`` — project the DNA MCP server block into
the per-agent MCP config a Spec-Kit-driven agent reads (ADR ``ADR-spec-kit-adoption``
Layer 2: "DNA feeds Spec Kit's agent").

Spec Kit is agent-agnostic: at ``specify init --integration <agent>`` it projects
one command set into ~30 agents. DNA is agent-agnostic the same way (``dna init``
projects one Skill Kind into ``.claude/skills`` / ``.github/skills`` / … — "one
source, N projections"). Layer 2 applies that exact philosophy to the **MCP
server block**: one DNA MCP endpoint, projected into each agent's OWN MCP config
file, so a Spec Kit run — whichever of the 30+ agents it drives — is grounded in
DNA's live layer: **memory** (recall/remember/list_memories), **soul**
(compose_prompt = Soul + Guardrails, composed live + tenant-aware), and the
**board** (sdlc_digest/list_stories/get_adr). The context is the SAME whether
Spec Kit drives Copilot or Claude.

Each agent reads MCP servers from a DIFFERENT file in a DIFFERENT JSON shape.
This module is the pure, byte-checked planner over those shapes; the thin CLI
wrapper lives in ``specify_cmd.py``. It writes NOTHING and touches no kernel — so
it is trivially testable and never forks the (untrusted) I/O defenses.

The three real schema families (current as of 2026-07):

    claude   .mcp.json          key ``mcpServers``  stdio: command/args/env
    cursor   .cursor/mcp.json    key ``mcpServers``  (identical schema to claude)
    copilot  .vscode/mcp.json    key ``servers``     stdio: type=stdio + command/args/env
    opencode opencode.json       key ``mcp``         local: type=local + command[]/environment/enabled

Remote (Streamable HTTP) variants — for a hosted ``dna mcp serve --transport http``:

    claude/cursor  {"type": "http", "url": …}
    copilot        {"type": "http", "url": …}
    opencode       {"type": "remote", "url": …, "enabled": true}
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: The server id injected under each agent's server map. Stable so re-running is
#: idempotent (the same key is found + skipped, or replaced with ``--force``).
SERVER_KEY = "dna"


@dataclass(frozen=True)
class AgentMcpTarget:
    """Where + how one agent reads its MCP servers.

    ``config_rel`` is the project-root-relative config path; ``servers_key`` is
    the top-level object the server map hangs off; ``schema`` selects the
    per-agent server-block shape.
    """

    tool: str
    config_rel: str
    servers_key: str
    schema: str


#: Tool → its MCP config location + shape. The SET matches ``dna init``'s
#: ``TOOL_SKILL_DIRS`` (claude/copilot/cursor/opencode) so the two projections
#: cover the same agents; only the file + JSON shape differ per agent.
TOOL_MCP_TARGETS: dict[str, AgentMcpTarget] = {
    "claude": AgentMcpTarget("claude", ".mcp.json", "mcpServers", "claude"),
    "cursor": AgentMcpTarget("cursor", ".cursor/mcp.json", "mcpServers", "claude"),
    "copilot": AgentMcpTarget("copilot", ".vscode/mcp.json", "servers", "vscode"),
    "opencode": AgentMcpTarget("opencode", "opencode.json", "mcp", "opencode"),
}

#: Sensible default — Claude Code + GitHub Copilot cover the two biggest agent
#: populations (mirrors ``dna init``'s DEFAULT_TOOLS).
DEFAULT_TOOLS = ("claude", "copilot")

#: opencode requires a ``$schema`` pointer at the config root; we seed it when
#: creating a fresh opencode.json so the file validates in the editor.
_OPENCODE_SCHEMA = "https://opencode.ai/config.json"


def build_server_block(
    schema: str, *, source_url: str | None = None, http_url: str | None = None
) -> dict[str, Any]:
    """Build the DNA MCP server block for one agent ``schema``.

    ``http_url`` (a hosted ``dna mcp serve --transport http`` endpoint) wins over
    stdio when set. Otherwise the block spawns the local ``dna mcp serve`` (stdio)
    and — when ``source_url`` is known — pins ``DNA_SOURCE_URL`` so the agent's
    server reads the SAME DNA the developer's ``dna`` CLI reads.
    """
    if http_url:
        if schema == "opencode":
            return {"type": "remote", "url": http_url, "enabled": True}
        # claude / cursor / vscode all accept the Streamable-HTTP form.
        return {"type": "http", "url": http_url}

    if schema == "opencode":
        block: dict[str, Any] = {
            "type": "local",
            "command": ["dna", "mcp", "serve"],
            "enabled": True,
        }
        if source_url:
            block["environment"] = {"DNA_SOURCE_URL": source_url}
        return block

    if schema == "vscode":
        block = {"type": "stdio", "command": "dna", "args": ["mcp", "serve"]}
        if source_url:
            block["env"] = {"DNA_SOURCE_URL": source_url}
        return block

    # claude / cursor
    block = {"command": "dna", "args": ["mcp", "serve"]}
    if source_url:
        block["env"] = {"DNA_SOURCE_URL": source_url}
    return block


# Outcome labels (mirror init_cmd's vocabulary).
CREATED = "created"   # a new config file was born
MERGED = "merged"     # an existing file gained the dna server (others preserved)
UPDATED = "updated"   # the dna server already existed and was replaced (--force)
SKIPPED = "skipped"   # the dna server already existed; left as-is (no --force)


def merge_config(
    existing: dict[str, Any] | None,
    target: AgentMcpTarget,
    block: dict[str, Any],
    *,
    force: bool,
) -> tuple[dict[str, Any], str]:
    """Merge the DNA server ``block`` into an agent config non-destructively.

    Returns ``(new_config, outcome)``. Every other server the file already
    declares is preserved; only the ``dna`` entry is written. Idempotent: if
    ``dna`` is already present and ``force`` is false, the config is returned
    untouched with ``SKIPPED``.
    """
    cfg: dict[str, Any] = dict(existing or {})
    servers: dict[str, Any] = dict(cfg.get(target.servers_key) or {})
    already = SERVER_KEY in servers

    if already and not force:
        outcome = SKIPPED
    else:
        servers[SERVER_KEY] = block
        outcome = UPDATED if already else (MERGED if existing else CREATED)

    cfg[target.servers_key] = servers
    if target.schema == "opencode":
        cfg.setdefault("$schema", _OPENCODE_SCHEMA)
    return cfg, outcome


def parse_tools(value: str) -> list[str]:
    """Parse ``--tools`` into a validated, order-preserving tool list.

    ``"all"`` expands to every supported agent. Unknown tools raise ``ValueError``
    (the CLI wraps it in a clean ``click`` failure).
    """
    if value.strip().lower() == "all":
        return list(TOOL_MCP_TARGETS)
    tools: list[str] = []
    for part in value.split(","):
        tool = part.strip().lower()
        if not tool:
            continue
        if tool not in TOOL_MCP_TARGETS:
            raise ValueError(
                f"unknown tool {tool!r} — pick from "
                f"{', '.join(TOOL_MCP_TARGETS)} (or 'all')"
            )
        if tool not in tools:
            tools.append(tool)
    if not tools:
        raise ValueError("no tools selected")
    return tools
