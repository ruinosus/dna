"""``dna_cli._mcp_documents`` — the GENERIC document tools on the MCP face.

Four tools that replace what would otherwise be four hand-written tools per
Kind. The MCP face had 21 hand-written tools and no loop over the Kind registry:
of the 76 registered Kinds (49 record-plane, most declared purely by a
``*.kind.yaml`` descriptor) only the handful somebody wrote tools for was
reachable by an agent. These four are resolved from the registry AT CALL TIME,
so a Kind that exists is a Kind an agent can use:

    list_kinds      — the catalog: what can I act on in this scope?
    list_documents  — the documents of one Kind
    get_document    — one document, verbatim
    write_document  — create/update one document

This module is a THIN adapter, exactly like the rest of the face. The behavior
lives in the core (``dna.application.documents``); what lives HERE is the
MCP-edge concern that core cannot own — the plan/tenancy seam:

* every tool passes the SAME ``_guard`` the hand-written tools pass (workspace
  resolution + membership, scope binding, tier → caps → quota), so the generic
  surface opens no path a hand-written tool does not already honor;
* the metered FAMILY is derived from the target Kind
  (``documents.family_for_kind``), never chosen by the caller — so an ``sdlc``
  write cannot be reached through a "document" tool by a tier that grants
  ``sdlc_mode: read``;
* a WRITE additionally requires the tier to grant ``write`` for that family's
  access mode (``_mcp_quota.enforce_family_mode``), fail closed.

Registered from ``_mcp_server.build_server`` the same way the ``graph.*`` tools
are (``register_graph_tools``): a ``guard`` callable is injected, so this module
never reaches into the server's closure and can be tested against a fake guard.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from dna.application import documents as D
from dna.kernel.errors import KernelRefusal

#: Everything a write may legitimately be REFUSED with, as one tuple.
#:
#: ``KernelRefusal`` is the kernel's own marker base for a deliberate verdict
#: (schema veto, LayerPolicy veto, tenancy rule, read-only source, retired Kind)
#: — it exists precisely because this tuple used to be a hand-enumeration that
#: MISSED the LayerPolicy veto and every tenancy rule (they are plain
#: ``Exception``; ``NotWritableError`` is a ``RuntimeError``), so the likeliest
#: refusal on a tenant write escaped as an unexplained failure. The three
#: builtins stay for the application-layer refusals raised beside it
#: (``BootstrapKindWriteRefused``, ``ConcurrentWriteError``, an unknown Kind).
WRITE_REFUSALS: tuple[type[BaseException], ...] = (
    KernelRefusal, ValueError, LookupError, PermissionError,
)

#: The signature ``_mcp_server`` injects: ``guard(family, scope=…, family_op=…)``
#: → the resolved workspace (or None). Raises the face's ``ToolError`` on denial.
GuardFn = Callable[..., Awaitable[Any]]

#: ``plan_families()`` → the feature families the caller's tier unlocks, or
#: ``None`` when the call is unmetered (stdio / self-host) or the source
#: configured no tiers. ``list_kinds`` uses it to report an HONEST catalog.
PlanFamiliesFn = Callable[[], Awaitable[Any]]


def register_document_tools(
    server: Any,
    *,
    live: Callable[[], Awaitable[Any]],
    guard: GuardFn,
    plan_families: PlanFamiliesFn,
) -> list[str]:
    """Register the four generic document tools on ``server``. Returns their
    names (the boot log prints them, like the graph tools)."""
    from fastmcp.exceptions import ToolError

    async def _resolved(kind: str, api_version: str | None) -> Any:
        """The target Kind's port, or ``None`` when the name is unknown.

        Resolution happens BEFORE the guard because the guard needs the family
        the port implies. An unknown/ambiguous name yields ``None`` here and is
        refused AFTER the guard has run, so probing Kind names still costs the
        caller a metered call instead of being a free oracle over the registry."""
        try:
            return D.resolve_kind_port((await live()).kernel, kind, api_version)
        except (D.UnknownKindError, D.AmbiguousKindError):
            return None

    async def _guard_for(
        kind: str, api_version: str | None, *, scope: str | None,
        family_op: str,
    ) -> tuple[Any, Any]:
        """Resolve the port, meter the call against ITS family, return both.

        The single seam every generic tool goes through. When the Kind name did
        not resolve, the call is still metered as ``definitions`` and then the
        real resolution error is re-raised as a clean ToolError."""
        port = await _resolved(kind, api_version)
        tenant = await guard(
            D.family_for_kind(port), scope=scope, family_op=family_op,
        )
        if port is None:  # metered, now say why it cannot proceed.
            try:
                port = D.resolve_kind_port(
                    (await live()).kernel, kind, api_version)
            except (D.UnknownKindError, D.AmbiguousKindError) as exc:
                raise ToolError(str(exc)) from None
        return port, tenant

    @server.tool(run_in_thread=False)
    async def list_kinds(scope: str | None = None) -> dict[str, Any]:
        """List the Kinds this source serves — the catalog behind
        ``list_documents`` / ``get_document`` / ``write_document``.

        Each entry carries the Kind's ``alias``, ``api_version``, ``plane``
        (``composition`` = it composes into prompts, ``record`` = it does not),
        ``tenant_scope``, ``storage_pattern``, the quota ``family`` a call on it
        is metered under, and ``writable`` + ``write_refusal`` — so a Kind the
        generic write refuses (a BOOTSTRAP Kind: Genome / LayerPolicy /
        KindDefinition) is visible before you try.

        Over an authenticated server the catalog reports only the Kinds your
        plan's feature families unlock (``filtered_by_plan: true``) — an honest
        short list beats a long one whose entries answer 403."""
        # Metered as `definitions`: the catalog is a read OF THE REGISTRY, not
        # of any one family's documents — the same call the `dna://{scope}/
        # manifest` resource already guards under that family.
        tenant = await guard("definitions", scope=scope)
        return await D.list_kinds_impl(
            await live(), scope=scope, tenant=tenant,
            families=await plan_families(),
        )

    @server.tool(run_in_thread=False)
    async def list_documents(
        kind: str, scope: str | None = None, api_version: str | None = None,
        limit: int = 50, offset: int = 0,
        fields: list[str] | None = None, filter: dict[str, Any] | None = None,
        order_by: list[str] | None = None,
    ) -> dict[str, Any]:
        """List the documents of one Kind in a scope, optionally PROJECTED and
        FILTERED — one call instead of one per document.

        Without ``fields`` you get names only, and answering "show me the open
        issues" then costs 1 + N calls: a list, then a ``get_document`` per
        document, most of them discarded. Both arguments push down into the
        kernel's own query:

        * ``fields`` — dotted spec paths to include per row
          (``["spec.title", "spec.status"]``; unprefixed paths resolve under
          ``spec.``, and ``name`` is always present). Omit for names only.
        * ``filter`` — field → value, ANDed. ``{"status": "open"}``, or an
          operator: ``{"status": {"in": ["todo", "in-progress"]}}``,
          ``{"updated_at": {"gt": "2026-07-01"}}``, ``{"title": {"like": "%mcp%"}}``.
          Operators: eq / neq / in / like / gt / gte / lt / lte.
        * ``order_by`` — dotted paths, ``-`` prefix for descending
          (``["-spec.updated_at"]``).

        Pass ``api_version`` when a Kind NAME is registered under more than one
        (the tool says so rather than guessing). Paged: ``limit`` (max 500) +
        ``offset``, with an honest ``has_more``.

        Metering is unchanged — one call, one unit, gated by the TARGET Kind's
        family exactly as ``get_document`` is. A projection reaches nothing your
        plan does not already let you read one document at a time; what it changes
        is how many round trips it takes."""
        port, tenant = await _guard_for(
            kind, api_version, scope=scope, family_op="read")
        try:
            return await D.list_documents_impl(
                await live(), kind=port.kind, api_version=port.api_version,
                scope=scope, tenant=tenant, limit=limit, offset=offset,
                fields=fields, filter=filter, order_by=order_by,
            )
        except (ValueError, LookupError) as exc:
            # A bad operator / unresolvable field path is the caller's mistake —
            # say which, instead of a masked 500.
            raise ToolError(f"{type(exc).__name__}: {exc}") from None

    @server.tool(run_in_thread=False)
    async def get_document(
        kind: str, name: str, scope: str | None = None,
        api_version: str | None = None,
    ) -> dict[str, Any]:
        """Read one document verbatim (``apiVersion`` / ``kind`` / ``metadata``
        / ``spec``), as your layer sees it — the per-tenant overlay wins over the
        inherited base, live, with no redeploy. Works for EVERY registered Kind,
        including the bootstrap ones the generic write refuses.

        The result also carries an ``etag``: pass it to ``write_document`` as
        ``if_match`` and your update is refused rather than silently overwriting a
        change somebody made in between."""
        port, tenant = await _guard_for(
            kind, api_version, scope=scope, family_op="read")
        try:
            return await D.get_document_impl(
                await live(), kind=port.kind, api_version=port.api_version,
                name=name, scope=scope, tenant=tenant,
            )
        except LookupError as exc:
            raise ToolError(str(exc)) from None

    @server.tool(run_in_thread=False)
    async def write_document(
        kind: str, name: str, spec: dict[str, Any],
        scope: str | None = None, api_version: str | None = None,
        merge: bool = True, if_match: str | None = None,
    ) -> dict[str, Any]:
        """Create or UPDATE one document of any Kind — ``spec`` is the document
        body (the ``apiVersion``/``kind``/``metadata`` envelope is built from the
        registered Kind, so you cannot write into another Kind's namespace).

        **An update MERGES.** Send only the fields you are changing: everything
        else in the stored document — its ``timeline`` above all, which is an
        append-only history you cannot reconstruct — is preserved. To REMOVE a
        field, send it as ``null``. ``merge=false`` REPLACES the whole spec and
        drops anything you did not send; use it only when you mean exactly that.

        Board Kinds are stamped with the dates their read surfaces need
        (``created_at`` on create, ``updated_at`` on every write), so a document
        filed here is visible to ``sdlc_digest``.

        ``if_match`` (optional): the ``etag`` from ``get_document``. With it, the
        write is REFUSED if the document changed since you read it, instead of
        overwriting the other change. The result returns the new ``etag``, so a
        chain of updates needs no re-read.

        The write goes through the kernel's own pipeline: the Kind's JSON Schema
        validates it, the operator's LayerPolicy (and the Kind's overlayable-field
        allowlist) may veto it, references are checked and the ``pre_save`` hooks
        can refuse it — identical to every hand-written write tool. Every one of
        those refusals reaches you by name, with its reason.

        Two refusals are this tool's own, and both fail CLOSED: a BOOTSTRAP Kind
        (Genome / LayerPolicy / KindDefinition — see ``list_kinds``) is never
        writable here, and over an authenticated server the write needs your plan
        to grant ``write`` for the target Kind's family (``sdlc_mode`` for the
        board, ``memory_mode`` for memory, ``definitions_mode`` otherwise)."""
        port, tenant = await _guard_for(
            kind, api_version, scope=scope, family_op="write")
        try:
            return await D.write_document_impl(
                await live(), kind=port.kind, api_version=port.api_version,
                name=name, spec=spec, scope=scope, tenant=tenant,
                merge=merge, if_match=if_match,
            )
        except D.BootstrapKindWriteRefused as exc:
            raise ToolError(str(exc)) from None
        except WRITE_REFUSALS as exc:
            # Schema violation / LayerPolicy veto / tenancy rule / read-only
            # source / stale if_match — surfaced verbatim, never masked as a 500.
            raise ToolError(f"{type(exc).__name__}: {exc}") from None

    @server.tool(run_in_thread=False)
    async def delete_document(
        kind: str, name: str, api_version: str,
        scope: str | None = None, if_match: str | None = None,
    ) -> dict[str, Any]:
        """DELETE one document of any Kind. Destructive and not undoable here.

        The MCP face had no delete at all: an agent could create and update every
        Kind and remove nothing, so undoing a mistaken write needed a human with
        database access. This is ``kernel.delete_document`` — the same operation
        ``dna doc delete`` and the REST routes already use — through the same
        tenancy + quota guard as ``write_document``, and metered as a write.

        ``api_version`` is REQUIRED here, unlike ``write_document`` where the
        document supplies it. A delete carries no document, and a bare Kind NAME
        can resolve to two ports once two workspaces each declare a Kind of the
        same name in their own namespace — so you state which Kind you mean, and
        that pin travels all the way to the storage adapter.

        ``if_match`` (optional): the ``etag`` from ``get_document``. Pass it and
        the delete is REFUSED if the document changed since you read it. It
        matters more here than on a write: a write that races loses one edit, a
        delete that races destroys a document its author never saw.

        Two Kinds of thing are NEVER deletable here, and ``list_kinds`` reports
        both per Kind (``deletable`` / ``delete_refusal``) so you can see it
        before you try:

        * BOOTSTRAP Kinds (Genome / LayerPolicy / KindDefinition) — deleting one
          is worse than writing a bad one, because a bad Genome is fixed by
          writing a better Genome while deleting a KindDefinition orphans every
          document of that Kind with nothing left to name them;
        * APPEND-ONLY records (AuditLog / Evidence / WorkflowEvent) — the record
          is the evidence of what happened; supersede it, never delete it.

        A document that is not there is an ERROR, not a quiet success: reporting
        success for a delete that did nothing is how a caller convinces itself
        something is gone."""
        port, tenant = await _guard_for(
            kind, api_version, scope=scope, family_op="write")
        try:
            return await D.delete_document_impl(
                await live(), kind=port.kind, api_version=port.api_version,
                name=name, scope=scope, tenant=tenant, if_match=if_match,
            )
        except D.DeleteRefused as exc:
            raise ToolError(str(exc)) from None
        except WRITE_REFUSALS as exc:
            raise ToolError(f"{type(exc).__name__}: {exc}") from None

    return [
        "list_kinds", "list_documents", "get_document", "write_document",
        "delete_document",
    ]
