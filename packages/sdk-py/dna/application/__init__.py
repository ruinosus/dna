"""``dna.application`` — the DNA transport-agnostic application / use-case layer.

Per ``adr-faces-reorg`` (move #1, load-bearing): the shared ``*_impl`` use-cases
that the three DNA faces (CLI, MCP server, REST API) call live HERE, in the core,
so a face is a thin adapter over them — never a re-implementation and never a home
for business logic. Each use-case takes a :class:`LiveDna` handle and drives the
kernel directly; nothing here imports HTTP / Click / FastMCP.

Faces boot a ``LiveDna`` (the CLI's ``boot_live`` composition root) and delegate:
the MCP server (``dna_cli._mcp_server``) and the REST API (``dna_cli._rest_api``)
both import these use-cases and only translate transport + edge validation
(auth/quota, request/response shaping, JSON-RPC).
"""
from dna.application.live import LiveDna
from dna.application.runtime import (
    BoardItemNotFound,
    ProjectNotFound,
    board_item_impl,
    board_summary_impl,
    compose_prompt_impl,
    consolidate_impl,
    forget_impl,
    get_adr_impl,
    get_project_impl,
    get_tool_impl,
    list_agents_impl,
    list_memories_impl,
    list_orgs_impl,
    list_projects_impl,
    list_repos_impl,
    list_stories_impl,
    list_tools_impl,
    recall_impl,
    remember_impl,
)

__all__ = [
    "LiveDna",
    "compose_prompt_impl",
    "list_agents_impl",
    "list_tools_impl",
    "get_tool_impl",
    "list_stories_impl",
    "get_adr_impl",
    "recall_impl",
    "remember_impl",
    "consolidate_impl",
    "list_memories_impl",
    "forget_impl",
    # portfolio (the DNA Cloud console read model)
    "list_orgs_impl",
    "list_projects_impl",
    "get_project_impl",
    "list_repos_impl",
    "board_summary_impl",
    "board_item_impl",
    "ProjectNotFound",
    "BoardItemNotFound",
]
