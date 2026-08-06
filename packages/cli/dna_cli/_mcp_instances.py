"""``dna_cli._mcp_instances`` — the GENERIC instance tools on the MCP face.

Four tools that replace what would otherwise be four hand-written tools per
Kind. The MCP face had 21 hand-written tools and no loop over the Kind registry:
of the 76 registered Kinds (49 record-plane, most declared purely by a
``*.kind.yaml`` descriptor) only the handful somebody wrote tools for was
reachable by an agent. These four are resolved from the registry AT CALL TIME,
so a Kind that exists is a Kind an agent can use:

    list_kinds      — the catalog: what can I act on in this scope?
    list_instances  — the instances of one Kind
    get_instance    — one instance, verbatim (and ``as_of``: as it was believed)
    graph_refs      — what points at this instance (the derived edge graph)
    write_instance  — create/update one instance

This module is a THIN adapter, exactly like the rest of the face. The behavior
lives in the core (``dna.application.instances``); what lives HERE is the
MCP-edge concern that core cannot own — the plan/tenancy seam:

* every tool passes the SAME ``_guard`` the hand-written tools pass (workspace
  resolution + membership, scope binding, tier → caps → quota), so the generic
  surface opens no path a hand-written tool does not already honor;
* the metered FAMILY is derived from the target Kind
  (``instances.family_for_kind``), never chosen by the caller — so an ``sdlc``
  write cannot be reached through a "instance" tool by a tier that grants
  ``sdlc_mode: read``;
* a WRITE additionally requires the tier to grant ``write`` for that family's
  access mode (``_mcp_quota.enforce_family_mode``), fail closed.

Registered from ``_mcp_server.build_server`` the same way the ``graph.*`` tools
are (``register_graph_tools``): a ``guard`` callable is injected, so this module
never reaches into the server's closure and can be tested against a fake guard.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from dna.application import instances as D
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


def register_instance_tools(
    server: Any,
    *,
    live: Callable[[], Awaitable[Any]],
    guard: GuardFn,
    plan_families: PlanFamiliesFn,
) -> list[str]:
    """Register the four generic instance tools on ``server``. Returns their
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
        # The pre-resolution is for METERING only — it is unscoped because the
        # caller's effective scope is not known until the guard has yielded a
        # tenant, and the family a Kind name implies does not depend on where
        # the Kind lives.
        #
        # It is also, deliberately, NOT refreshed (i-090): a refresh needs a
        # scope and there is none yet. The consequence is bounded and worth
        # naming — the FIRST call on a replica that has not yet seen a newly
        # approved Kind meters that one call under the default family instead of
        # the Kind's own. The authoritative resolution below IS refreshed, so
        # the read/write itself is correct; only the family this single call is
        # counted under can lag, and by the next call it cannot.
        port = await _resolved(kind, api_version)
        tenant = await guard(
            D.family_for_kind(port), scope=scope, family_op=family_op,
        )
        # i-081: with the tenant known, resolve AUTHORITATIVELY inside the scope
        # this call targets. A Kind another workspace declared does not resolve
        # here, and the ``api_version`` pinned from this port travels down to the
        # adapter — resolving it unscoped is how a caller could be pinned to
        # somebody else's Kind.
        #
        # i-090: and it resolves through ``resolve_kind_port_live``, which
        # refreshes this scope's Kind registry once its window has expired.
        # Without that, a generic instance tool answered "Kind not registered"
        # for a Kind the workspace had just approved on ANOTHER replica — the
        # registry is only ever repopulated inside a Manifest Instance build and
        # no instance route builds one. The same seam closes a REVOCATION in the
        # other direction, which is the half that must not lag.
        ld = await live()
        try:
            port = await D.resolve_kind_port_live(
                ld, kind, api_version,
                scope=scope or ld.default_scope(tenant),
            )
        except (D.UnknownKindError, D.AmbiguousKindError) as exc:
            raise ToolError(str(exc)) from None
        return port, tenant

    @server.tool(run_in_thread=False)
    async def list_kinds(scope: str | None = None) -> dict[str, Any]:
        """List the Kinds this source serves — the catalog behind
        ``list_instances`` / ``get_instance`` / ``write_instance``.

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
        # of any one family's instances — the same call the `dna://{scope}/
        # manifest` resource already guards under that family.
        tenant = await guard("definitions", scope=scope)
        return await D.list_kinds_impl(
            await live(), scope=scope, tenant=tenant,
            families=await plan_families(),
        )

    @server.tool(run_in_thread=False)
    async def list_instances(
        kind: str, scope: str | None = None, api_version: str | None = None,
        limit: int | None = None, offset: int = 0,
        fields: list[str] | None = None, filter: dict[str, Any] | None = None,
        order_by: list[str] | None = None,
    ) -> dict[str, Any]:
        """List the instances of one Kind in a scope, optionally PROJECTED and
        FILTERED — one call instead of one per instance.

        Without ``fields`` you get names only, and answering "show me the open
        issues" then costs 1 + N calls: a list, then a ``get_instance`` per
        instance, most of them discarded. Both arguments push down into the
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
        family exactly as ``get_instance`` is. A projection reaches nothing your
        plan does not already let you read one instance at a time; what it changes
        is how many round trips it takes."""
        port, tenant = await _guard_for(
            kind, api_version, scope=scope, family_op="read")
        try:
            return await D.list_instances_impl(
                await live(), kind=port.kind, api_version=port.api_version,
                scope=scope, tenant=tenant, limit=limit, offset=offset,
                fields=fields, filter=filter, order_by=order_by,
            )
        except (ValueError, LookupError) as exc:
            # A bad operator / unresolvable field path is the caller's mistake —
            # say which, instead of a masked 500.
            raise ToolError(f"{type(exc).__name__}: {exc}") from None

    @server.tool(run_in_thread=False)
    async def get_instance(
        kind: str, name: str, scope: str | None = None,
        api_version: str | None = None, as_of: str | None = None,
        valid_at: str | None = None,
    ) -> dict[str, Any]:
        """Read one instance verbatim (``apiVersion`` / ``kind`` / ``metadata``
        / ``spec``), as your layer sees it — the per-tenant overlay wins over the
        inherited base, live, with no redeploy. Works for EVERY registered Kind,
        including the bootstrap ones the generic write refuses.

        The result also carries an ``etag``: pass it to ``write_instance`` as
        ``if_match`` and your update is refused rather than silently overwriting a
        change somebody made in between.

        ``as_of`` (ISO-8601 instant) reads the BELIEF STATE — the instance as this
        store RECORDED it at or before that moment (transaction time), instead of
        as it stands now. "What did this Issue say yesterday at 14:00?" is a
        question the live read cannot answer and must not appear to. The answer
        carries ``as_of``, ``as_of_version`` and ``as_of_recorded_at`` beside the
        instance, so a historical read is never mistakable for a live one.

        ⚠️ **It refuses rather than approximates, and the refusals are distinct
        on purpose** — collapsing any two of them re-creates i-106, where this
        parameter was ACCEPTED and IGNORED on the REST route and a caller was
        handed today's instance under yesterday's timestamp with nothing in the
        response to say so:

        * ``AsOfUnsupported`` — this deployment's store keeps no version history
          at all (the filesystem source declares ``versions=True`` and retains
          nothing). Never today's state under a past stamp.
        * ``AsOfTruncated`` — the instance HAS history, but none reaching back
          that far; those versions were pruned. Never "it did not exist", which
          is a claim only a store that kept the record may make.
        * a plain "no such instance …at <instant>" — it did not exist yet. That
          one is an ANSWER, and is deliberately worded so you can tell it from
          the refusal above.
        * a bad instant is refused as ``ValueError`` BEFORE the store's
          capability is consulted: a typo is the caller's, not the deployment's.

        Same four outcomes, same wording, as ``GET /v1/kinds/{kind}/instances/
        {name}?as_of=`` (there: 501 / 410 / 404 / 422).

        ``valid_at`` (ISO-8601 instant) reads the OTHER time axis — **world
        time**: *was the fact this instance states TRUE at that moment?*, from
        ``dna_instances.valid_at``. Two parameters and not one, because they
        answer different questions and the difference is the point: a note
        written today about last year is **valid** last year and **believed**
        today, so ``valid_at=<last year>`` finds it and ``as_of=<last year>``
        does not. "Which memories did we hold as true last March" is a
        ``valid_at`` question; "what did this Issue SAY last March" is an
        ``as_of`` one.

        * outside the window → *"no X named … was valid at …"*, which is an
          ANSWER: the instance exists and was not true then.
        * a deployment whose store keeps no world-time column (SQLite, the
          filesystem) → ``ValidTimeUnsupported``, never the instance unfiltered.
        * ``as_of`` and ``valid_at`` **together** → ``ValueError``. The true
          bitemporal intersection needs the validity window on the version rows
          and ``dna_versions`` has none; answering one axis while the caller
          asked for both is the silent wrong answer this whole family of
          parameters exists to refuse."""
        port, tenant = await _guard_for(
            kind, api_version, scope=scope, family_op="read")
        # ``CAPABILITY_REFUSALS`` (= ``dna.kernel.errors.CapabilityRefusal``) is
        # caught FIRST and by name, and the order is load-bearing rather than
        # tidy: ``AsOfTruncated`` IS a ``LookupError``, so the arm below would
        # swallow it and relay "history was pruned" in the same shape as "no such
        # instance" — the single collapse an as-of read may never make.
        from dna_cli._mcp_refusals import CAPABILITY_REFUSALS  # noqa: PLC0415

        try:
            return await D.get_instance_impl(
                await live(), kind=port.kind, api_version=port.api_version,
                name=name, scope=scope, tenant=tenant, as_of=as_of,
                valid_at=valid_at,
            )
        except CAPABILITY_REFUSALS as exc:
            raise ToolError(f"{type(exc).__name__}: {exc}") from None
        except LookupError as exc:
            raise ToolError(str(exc)) from None
        except ValueError as exc:
            # A non-ISO-8601 ``as_of``. Named, because "your timestamp is not a
            # timestamp" and "this store cannot read the past" have different
            # remedies and only the message can carry which.
            raise ToolError(f"{type(exc).__name__}: {exc}") from None

    @server.tool(run_in_thread=False)
    async def graph_refs(
        kind: str, name: str, scope: str | None = None,
        api_version: str | None = None,
        direction: str = "in", depth: int = 1,
    ) -> dict[str, Any]:
        """"What points at this instance?" — walk the DERIVED reference graph.

        The Kind catalog has always been able to say ``Story.feature → Feature``
        exists as a RULE. This answers the other question: THESE Stories point at
        THIS Feature — read from the edges the write path itself produced while
        validating references. Nothing here derives, guesses or reads slugs.

        * ``direction`` — ``in`` (the default, and the product question: what
          points AT this), ``out`` (what this points at), ``both``.
        * ``depth`` — how many hops. Clamped by the deployment's ceiling
          (``DNA_GRAPH_MAX_DEPTH``); a walk without a ceiling is an incident
          waiting for the first cyclic board, since ``Spec.supersedes`` and
          ``Story.dependencies`` are self-referential by design.

        Three fields travel with the answer and none is decoration — each exists
        so a caller cannot read the wrong thing out of a short list:

        * ``resolved`` per edge — ``false`` is a DANGLING reference (declared,
          written, resolving to nothing). Listed, never filtered: hiding the
          broken half would render the graph healthier than the data is.
        * ``stop`` — ``complete`` / ``depth_reached`` / ``truncated``. A caller
          that cannot tell "this is everything" from "this is where I stopped"
          will render the second as the first.
        * ``graph_producer`` — ``warn`` / ``enforce`` / ``off``. With the producer
          off no edges are made at all; that is a defensible operational choice,
          and a screen rendering the resulting emptiness as "no relations" is not.

        ⚠️ **A store that keeps no edge graph is REFUSED (``GraphUnsupported``),
        never answered with an empty list.** ``[]`` reads as *nothing points at
        this instance*, and that is a claim only a store that actually records
        edges may make. Same refusal the REST face answers **501** with.

        Only the ENFORCED relations appear: the ones ``spec.relations`` declares
        with a concrete target addressed by instance name, which is all the write
        path resolves. Calling this "the relations" would claim a completeness the
        producer does not have.

        (Unrelated to the ``ms_*`` Microsoft Graph tools — same English word, two
        different graphs, and they never meet.)"""
        # SAME SHAPE AS THE OTHER TWO FACES, deliberately and to the parameter:
        # ``GET /v1/kinds/{kind}/instances/{name}/refs`` and ``dna graph refs``
        # both take (kind, name) as the ADDRESS plus ``direction`` + ``depth`` as
        # the question, and all three go through ``graph_refs_impl`` →
        # ``Kernel.graph_refs`` → ``dna.kernel.query.graph.traverse``. Three faces
        # with three shapes of one verb is the debt this tool exists NOT to
        # create; ``sdk-py/tests/test_graph_telemetry.py::TestGatilho1Expressividade``
        # holds the count and goes red if a fourth, COMPOSING parameter appears
        # here or anywhere else on the path.
        port, tenant = await _guard_for(
            kind, api_version, scope=scope, family_op="read")
        from dna_cli._mcp_refusals import CAPABILITY_REFUSALS  # noqa: PLC0415

        if depth < 1:
            # Mirrors the REST route's ``ge=1`` (a 422 there). The kernel would
            # CLAMP it to 1 instead — fine for a CLI flag, wrong for a caller
            # that will read the returned ``depth`` as the one it asked for.
            raise ToolError(f"depth must be at least 1 (got {depth})")
        try:
            return await D.graph_refs_impl(
                await live(), kind=port.kind, api_version=port.api_version,
                name=name, scope=scope, tenant=tenant,
                direction=direction, depth=depth,
            )
        except CAPABILITY_REFUSALS as exc:
            # ``GraphUnsupported`` above all — see the warning in the docstring.
            raise ToolError(f"{type(exc).__name__}: {exc}") from None
        except (LookupError, ValueError) as exc:
            # An unknown Kind, or a direction that is not one of the three.
            raise ToolError(f"{type(exc).__name__}: {exc}") from None

    @server.tool(run_in_thread=False)
    async def resolve_instance(
        id: str, scope: str | None = None,
    ) -> dict[str, Any]:
        """Find an instance by its short ``metadata.id`` — the id lane (i-114).

        Every instance carries a 12-character ``metadata.id`` that NEVER changes,
        even when the instance is renamed. Give this tool the first four or more
        characters and it expands them to the one instance they name, the way
        ``git`` expands a short commit hash.

        Use it when you hold an id — from ``get_instance``'s ``metadata``, or
        from a ``to_id`` on the reference graph — and want the instance it
        belongs to WITHOUT knowing its Kind, its name or its scope. To read an
        instance you can already name, use ``get_instance``: that is the name
        lane, and the two stay separate so a name query can never be silently
        answered by an id match.

        **A prefix that matches more than one instance is REFUSED**, never
        resolved to the first hit. Lengthen the prefix; the error lists the
        candidates. Fewer than four characters is refused too — that is a typo,
        not a question.
        """
        # ``CAPABILITY_REFUSALS`` rather than ``InstanceIdLookupUnsupported``
        # alone: this arm used to name the one capability refusal THIS tool can
        # raise today, which is correct until the tool grows a second reach. The
        # tuple is the face's single list of "the store cannot answer that at
        # all" (see ``dna_cli._mcp_refusals``), so a read added here later is
        # honest without anyone remembering to widen this line.
        from dna_cli._mcp_refusals import CAPABILITY_REFUSALS  # noqa: PLC0415

        # Metered as a plain read against the DEFINITIONS family: the caller
        # has not named a Kind, so there is no Kind whose family could govern
        # the call, and picking one from the resolved instance would let a
        # caller reach a family their tier does not grant by holding an id.
        tenant = await guard(
            D.family_for_kind(None), scope=scope, family_op="read",
        )
        try:
            return await D.resolve_instance_impl(
                await live(), id=id, scope=scope, tenant=tenant,
            )
        except CAPABILITY_REFUSALS as exc:
            raise ToolError(str(exc)) from None
        except (LookupError, ValueError) as exc:
            raise ToolError(str(exc)) from None

    @server.tool(run_in_thread=False)
    async def write_instance(
        kind: str, name: str, spec: dict[str, Any],
        scope: str | None = None, api_version: str | None = None,
        merge: bool = True, if_match: str | None = None,
    ) -> dict[str, Any]:
        """Create or UPDATE one instance of any Kind — ``spec`` is the instance
        body (the ``apiVersion``/``kind``/``metadata`` envelope is built from the
        registered Kind, so you cannot write into another Kind's namespace).

        **An update MERGES.** Send only the fields you are changing: everything
        else in the stored instance — its ``timeline`` above all, which is an
        append-only history you cannot reconstruct — is preserved. To REMOVE a
        field, send it as ``null``. ``merge=false`` REPLACES the whole spec and
        drops anything you did not send; use it only when you mean exactly that.

        Board Kinds are stamped with the dates their read surfaces need
        (``created_at`` on create, ``updated_at`` on every write), so an instance
        filed here is visible to ``sdlc_digest``.

        ``if_match`` (optional): the ``etag`` from ``get_instance``. With it, the
        write is REFUSED if the instance changed since you read it, instead of
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
            return await D.write_instance_impl(
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
    async def delete_instance(
        kind: str, name: str, api_version: str,
        scope: str | None = None, if_match: str | None = None,
    ) -> dict[str, Any]:
        """DELETE one instance of any Kind. Destructive and not undoable here.

        The MCP face had no delete at all: an agent could create and update every
        Kind and remove nothing, so undoing a mistaken write needed a human with
        database access. This is ``kernel.delete_instance`` — the same operation
        ``dna instance delete`` and the REST routes already use — through the same
        tenancy + quota guard as ``write_instance``, and metered as a write.

        ``api_version`` is REQUIRED here, unlike ``write_instance`` where the
        instance supplies it. A delete carries no instance, and a bare Kind NAME
        can resolve to two ports once two workspaces each declare a Kind of the
        same name in their own namespace — so you state which Kind you mean, and
        that pin travels all the way to the storage adapter.

        ``if_match`` (optional): the ``etag`` from ``get_instance``. Pass it and
        the delete is REFUSED if the instance changed since you read it. It
        matters more here than on a write: a write that races loses one edit, a
        delete that races destroys an instance its author never saw.

        Two Kinds of thing are NEVER deletable here, and ``list_kinds`` reports
        both per Kind (``deletable`` / ``delete_refusal``) so you can see it
        before you try:

        * BOOTSTRAP Kinds (Genome / LayerPolicy / KindDefinition) — deleting one
          is worse than writing a bad one, because a bad Genome is fixed by
          writing a better Genome while deleting a KindDefinition orphans every
          instance of that Kind with nothing left to name them;
        * APPEND-ONLY records (AuditLog / Evidence / WorkflowEvent) — the record
          is the evidence of what happened; supersede it, never delete it.

        An instance that is not there is an ERROR, not a quiet success: reporting
        success for a delete that did nothing is how a caller convinces itself
        something is gone."""
        port, tenant = await _guard_for(
            kind, api_version, scope=scope, family_op="write")
        try:
            return await D.delete_instance_impl(
                await live(), kind=port.kind, api_version=port.api_version,
                name=name, scope=scope, tenant=tenant, if_match=if_match,
            )
        except D.DeleteRefused as exc:
            raise ToolError(str(exc)) from None
        except WRITE_REFUSALS as exc:
            raise ToolError(f"{type(exc).__name__}: {exc}") from None

    return [
        "list_kinds", "list_instances", "get_instance", "resolve_instance",
        "graph_refs", "write_instance", "delete_instance",
    ]
