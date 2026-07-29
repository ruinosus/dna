"""The PORTFOLIO door at the MCP face — workspaces, projects, repos, orgs.

WHY THIS MODULE EXISTS, stated plainly, because the answer is not "a feature
was missing":

``Project`` / ``Organization`` / ``Repo`` are Kinds — builtin descriptors from
the ``portfolio`` extension, registered globally, present in every store's
catalog. Every one of them was already reachable over MCP through the GENERIC
document door (``list_documents(kind="Project")``). The application seams were
already written and already served the REST face. Nothing was missing except a
name.

And a catalog of 78 Kinds with no named tool is discoverable only by luck: a
model finds what it was told exists, not what it could reach if it guessed the
right ``kind=`` string. The gap this module closes is DISCOVERY, and the fix
is not new capability — it is a door with a sign on it.

THE BOARD BRIDGE, which is the whole point of :func:`list_projects`:

    a project carries ``board_scope``; ``board_summary(scope=<board_scope>)``
    is that project's board.

That sentence is in the tool's own description, deliberately. A model that
reads the roster then holds the key to every board in the tenant, without
being told separately. Before it, the two halves existed and nothing joined
them — which is exactly how a user ends up reporting "I cannot find the
boards" about a system that has served them all along.

AUTHORIZATION is unchanged and is not ours to relax. Reads go through the same
``guard`` every other tool uses. ``create_project`` carries the caller's
VERIFIED claims from the request token (never a tool argument) into
``create_project_impl``, which requires an ACTIVE ``WorkspaceMembership`` in
the target workspace and DERIVES both the write scope and ``board_scope`` from
(workspace, slug). A caller-chosen scope would be a cross-workspace write
vector; the impl refuses to take one and this door does not offer it.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

#: The signature ``_mcp_server`` injects: ``guard(family, tenant, scope=…,
#: family_op=…)`` → the resolved workspace (or None). Raises ``ToolError`` on
#: denial. Same contract ``_mcp_kinds`` documents.
GuardFn = Callable[..., Awaitable[Any]]


def register_portfolio_tools(
    server: Any,
    *,
    live: Callable[[], Awaitable[Any]],
    guard: GuardFn,
) -> list[str]:
    """Register the portfolio tools on ``server`` and return their names."""
    from fastmcp.exceptions import ToolError

    from dna.application.runtime import (
        create_project_impl,
        get_project_impl,
        list_orgs_impl,
        list_projects_impl,
        list_repos_impl,
        list_workspaces_impl,
    )

    from dna_cli._mcp_auth import claims_from_context

    # Bound to the name the source guard `tests/test_tools_bind_their_scope.py`
    # looks for: it fails a tool that DECLARES a `scope` and then calls the seam
    # without `scope=`. Renaming the seam on the way in would make this module
    # invisible to that guard — a fence that never reaches the code it guards is
    # worse than no fence.
    _guard = guard

    def _refuse(exc: BaseException) -> "ToolError":
        """A refusal an AGENT can act on: the type name plus the reason.

        The type name is load-bearing over a conversational face. An agent that
        reads ``WorkspaceForbidden: …`` can change what it does; one that gets
        an unexplained failure retries the same call forever."""
        # The operator keeps the traceback; the agent gets the sentence. Without
        # this the server side of an unexpected failure is as blind as the
        # client side was.
        logger.warning("portfolio tool refused", exc_info=exc)
        return ToolError(f"{type(exc).__name__}: {exc}")

    #: EVERY exception, on purpose — this used to be an ENUMERATION and the
    #: enumeration was wrong on its first contact with production.
    #:
    #: It read ``(ValueError, LookupError, PermissionError)`` with a comment
    #: asserting that ``WorkspaceForbidden`` was a ``PermissionError``. It is
    #: not: it subclasses bare ``Exception``. So the single most likely refusal
    #: this door can produce — "you hold no membership there" — escaped
    #: unmapped and reached the agent as ``Error calling tool 'create_project'``
    #: with no reason at all. That is the exact defect four production bugs in
    #: this repo already were (``i-088`` … ``i-092``): the system knew the
    #: truth and reported something else.
    #:
    #: A list of exception types is a claim about a hierarchy someone else
    #: owns, and it goes stale silently — the failure mode is not a crash, it
    #: is a good message becoming a blank one. Naming ``type(exc).__name__``
    #: derives the answer instead of remembering it, and cannot go stale: a
    #: refusal type added upstream tomorrow arrives named, for free.
    #:
    #: The cost is that a genuine BUG (``AttributeError``, ``TypeError``) is
    #: also reported by name rather than crashing. That is the better trade
    #: over a conversational face — ``AttributeError: 'NoneType' …`` reads as a
    #: bug to anyone who sees it, and it is strictly more than the unexplained
    #: failure it replaces. The traceback is not lost; it goes to the log above.
    REFUSALS: tuple[type[BaseException], ...] = (Exception,)

    @server.tool(run_in_thread=False)
    async def list_workspaces() -> dict[str, Any]:
        """The workspaces YOU belong to — start here when you need a
        ``workspace_id``.

        A workspace is listed iff your verified identity holds an ACTIVE
        membership in it; pending invites are not listed, because they
        authorize nothing yet. A grant whose ``Workspace`` document is missing
        is still listed with a ``null`` name — the id is a fact and the display
        name is not, and inventing one would be fabricating data.

        ``workspace_id`` from here is what ``create_project`` takes."""
        await _guard("read", None)
        try:
            return await list_workspaces_impl(await live(), claims_from_context())
        except REFUSALS as exc:
            raise _refuse(exc) from None

    @server.tool(run_in_thread=False)
    async def list_projects(
        scope: str | None = None, tenant: str | None = None,
    ) -> dict[str, Any]:
        """The workspace's projects — each one a multi-repo container.

        **Every project carries a ``board_scope``, and that is the key to its
        board**: pass it as ``board_summary(scope=<board_scope>)`` to see that
        project's stories, features and issues, or to ``list_stories`` /
        ``sdlc_digest`` for the same board read other ways. A board always
        belongs to a project; this is how you get from one to the other.

        Also reported per project: ``slug``, ``workspace_id``, ``org_ref``,
        ``repo_refs`` (resolve them with ``get_project``), ``visibility``."""
        tenant = await _guard("read", tenant, scope=scope)
        try:
            return await list_projects_impl(await live(), scope, tenant)
        except REFUSALS as exc:
            raise _refuse(exc) from None

    @server.tool(run_in_thread=False)
    async def get_project(
        slug: str, scope: str | None = None, tenant: str | None = None,
    ) -> dict[str, Any]:
        """One project in detail, with its ``repo_refs`` RESOLVED to real repos.

        ``slug`` matches the project's ``spec.slug``, falling back to the
        document name. A ref pointing at a repo that is not there is skipped
        rather than invented — a missing repo reads as absent, never as a
        fabricated row.

        Its ``board_scope`` is that project's board (see ``list_projects``)."""
        tenant = await _guard("read", tenant, scope=scope)
        try:
            return await get_project_impl(await live(), slug, scope, tenant)
        except REFUSALS as exc:
            # ProjectNotFound included: it arrives NAMED, which is what lets an
            # agent tell "no such project" from "I could not reach the store".
            raise _refuse(exc) from None

    @server.tool(run_in_thread=False)
    async def create_project(
        workspace_id: str, name: str, slug: str | None = None,
    ) -> dict[str, Any]:
        """Create a project inside a workspace — and with it, its board.

        ``workspace_id`` comes from ``list_workspaces``; you must hold an ACTIVE
        membership there. ``slug`` defaults to a slugified ``name`` and is made
        unique within the workspace.

        You do NOT choose where it is stored. The write scope and the project's
        ``board_scope`` are DERIVED from (workspace, slug) — the project's
        identity is that pair, and the scope is a rendering of it. A
        caller-chosen scope would be a way to write into someone else's
        workspace, so this door does not offer one.

        The new project's ``board_scope`` is immediately usable with
        ``board_summary`` — a project and its board are created together."""
        await _guard("write", None)
        try:
            return await create_project_impl(
                await live(), workspace_id, name,
                claims_from_context(), slug=slug,
            )
        except REFUSALS as exc:
            raise _refuse(exc) from None

    @server.tool(run_in_thread=False)
    async def list_repos(
        scope: str | None = None, tenant: str | None = None,
    ) -> dict[str, Any]:
        """The workspace's repositories (name / url / provider / default branch).

        Repos are shared N—N across projects, so this is the whole roster, not
        one project's slice — for that, read ``repo_refs`` from
        ``get_project``."""
        tenant = await _guard("read", tenant, scope=scope)
        try:
            return await list_repos_impl(await live(), scope, tenant)
        except REFUSALS as exc:
            raise _refuse(exc) from None

    @server.tool(run_in_thread=False)
    async def list_orgs(
        scope: str | None = None, tenant: str | None = None,
    ) -> dict[str, Any]:
        """The workspace's organizations — the containers projects belong to.

        The portfolio model is Organization → Project → N repos, so an org is
        the top of that tree and a project's ``org_ref`` points back here."""
        tenant = await _guard("read", tenant, scope=scope)
        try:
            return await list_orgs_impl(await live(), scope, tenant)
        except REFUSALS as exc:
            raise _refuse(exc) from None

    return [
        "list_workspaces", "list_projects", "get_project",
        "create_project", "list_repos", "list_orgs",
    ]
