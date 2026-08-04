"""``dna_cli._mcp_kinds`` — the CONVERSATIONAL face of Kind authoring.

A tenant declares its own Kind by talking to an agent. The agent calls
``author_kind``; what lands is a real, auditable ``KindDefinition`` document
that is **inert** — the registry withholds registration until a human approves,
and registration is what confers schema validation and storage routing. So the
Kind an agent authors has no effect until a person says so, and that is the
absence of a mechanism rather than a promise.

**Approval exists here now, and the MODEL cannot reach it.** The rule was never
"no such tool exists" — it was *the agent must not be able to approve its own
proposal*. That property used to be bought by absence; it is now bought by
declaration: ``approve_kind`` is registered ``visibility: ["app"]`` (MCP Apps,
SEP-1865), which a conforming host MUST keep out of the tool list it hands the
model. Only the button on :func:`~dna_cli._mcp_cards.kind_review_app` presses it.

Three things changed to make that trade honest, and none of them is optional:

* **A workspace has more than one person.** The approver's OWN token signs the
  call, so ``proposed_by`` names the author and ``approved_by`` names her — two
  distinct verified actors, which is what the audit wanted all along. The
  identity was never the weak part.
* **The weak part is forged CONSENT** — a model calling the tool because it is
  being helpful, recording an approval no human decided. ``visibility`` is what
  answers that, and see the next point for who enforces it.
* **Revocation exists** (i-085). A grant that cannot be taken back must not be
  one click away; this one can be, in a single act, with nothing to migrate.

**Whose fence this is.** The MCP Apps spec states plainly that a server cannot
distinguish a UI-initiated ``tools/call`` from a model-initiated one — same
transport, same token, nothing on the wire that says which pressed. So
``visibility`` is a declaration we make and the HOST enforces, and no test in
this repo can prove a third-party host honours it. The danger is not a malicious
host (it already holds the human's token) but an INCOMPLETE one. What is ours to
do is done: the declaration is exact; a client that tells us it cannot render
MCP Apps is not offered the tool at all
(``_mcp_server._ui_capability_middleware``); the act is reversible; and the tool
delegates to ``approve_kind_impl``, the same function the REST approve route
calls, so there is one implementation of the act and one audit shape.

Why a dedicated module + dedicated tools instead of the generic
``write_document``: the generic write refuses every BOOTSTRAP Kind
(``KindDefinition`` among them) by construction, and that refusal stays. A tool
that can write any document must not be the tool that rewrites the frame every
other document is validated against. This is a separate entry point with its own
authorization — and it writes exactly one Kind, always without an approval
marker, always into the caller's own assigned namespace.

THIN, like the rest of the face: every behaviour lives in the shared core
(``dna.application.kind_authoring``), which the REST face and the portal call
through the same functions. Registered from ``_mcp_server.build_server`` the way
``register_graph_tools`` / ``register_document_tools`` are — the ``guard`` seam
is injected, so this module never reaches into the server's closure.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from dna.application.kind_authoring import (
    NamespaceRegistryUnreadable,
    # The act that CONFERS EFFECT, reached from an agent-facing module — which
    # was forbidden until this branch, and the fence that forbade it has been
    # re-aimed rather than deleted (``tests/test_mcp_kind_authoring.py``). What
    # the fence pins now is the property the old one was buying: no tool the
    # MODEL can see reaches this function. Delegated to, never reimplemented:
    # one act, one audit shape, one guarded read-modify-write.
    approve_kind_impl,
    revoke_kind_impl,
    author_kind_impl,
    get_authored_kind_impl,
    list_authored_kinds_impl,
)
from dna.kernel.errors import KernelRefusal

#: The store-side conditions that mean "the claim registry could not be read",
#: as one tuple — the pair the REST doors map to **503**
#: (``_rest_api.py``'s three ``except (NamespaceRegistryUnreadable,
#: FileNotFoundError)`` arms), spelled once here so the two faces cannot drift.
#:
#: BOTH, because ``FileNotFoundError`` alone was only the filesystem store's
#: spelling of the failure: a missing ``_lib`` directory. The core refuses
#: broadly (:class:`NamespaceRegistryUnreadable`, mirroring the write gate), so
#: a transient networked-registry error is the same fact — and being a
#: ``RuntimeError`` it sits outside :data:`AUTHORING_REFUSALS` *by design*,
#: which is precisely how it used to escape BOTH handlers and reach the agent as
#: FastMCP's masked "Error calling tool".
NO_REGISTRY: tuple[type[BaseException], ...] = (
    NamespaceRegistryUnreadable, FileNotFoundError,
)

#: Everything an authoring call may legitimately be REFUSED with, as one tuple —
#: the same shape ``_mcp_documents.WRITE_REFUSALS`` has, and for the same reason.
#: ``KernelRefusal`` is the kernel's marker base for a deliberate verdict (the
#: namespace-ownership gate above all, plus the LayerPolicy veto, tenancy rules
#: and a read-only source); the builtins carry the application-layer refusals
#: raised beside it — ``ValueError`` for a missing tenant or a Kind name that is
#: not a CamelCase identifier, which is a security boundary and not a tidiness
#: check.
#:
#: Deliberately NOT ``Exception``: a genuine bug must keep looking like a bug.
AUTHORING_REFUSALS: tuple[type[BaseException], ...] = (
    KernelRefusal, ValueError, LookupError, PermissionError,
)

#: The signature ``_mcp_server`` injects: ``guard(family, tenant, scope=…,
#: family_op=…)`` → the resolved workspace (or None). Raises ``ToolError`` on
#: denial.
GuardFn = Callable[..., Awaitable[Any]]


def register_kind_tools(
    server: Any,
    *,
    live: Callable[[], Awaitable[Any]],
    guard: GuardFn,
) -> list[str]:
    """Register ``author_kind`` + ``list_my_kinds`` + ``review_kind`` +
    ``approve_kind`` on ``server``.

    Returns their names. Nothing reads them today — ``build_server`` discards
    the return, exactly as it does for ``register_document_tools`` — so the list
    is there for a caller that wants to report what it mounted, not because
    anything prints it.
    """
    from fastmcp.apps import AppConfig
    from fastmcp.exceptions import ToolError

    from dna_cli._mcp_auth import actor_from_context
    from dna_cli._mcp_cards import (
        APPROVE_TOOL,
        UI_PREFAB_URI,
        kind_review_app,
        kinds_app,
        with_card,
    )

    # The SHARED card renderer (`dna_cli._mcp_cards`) — the same resource the
    # board reads point, never a per-tool one. Built here rather than passed in
    # because this module owns its own registration, exactly as it owns its own
    # refusal mapping.
    prefab_card_app = AppConfig(resource_uri=UI_PREFAB_URI)

    # Kind Studio F3: o card INTERATIVO do Kind autorado. `author_kind` declara
    # o template `ui://dna/kind-draft` — o host empurra o resultado (que ecoa o
    # `schema`), o card renderiza linhas editáveis e REAUTORA via
    # `callServerTool`. O doc continua inerte; a aprovação segue humana.
    from dna.emit.mcp_ui import UI_KIND_DRAFT_URI

    kind_draft_card_app = AppConfig(resource_uri=UI_KIND_DRAFT_URI)

    # THE DECLARATION THAT KEEPS THE MODEL OUT (MCP Apps / SEP-1865).
    #
    # ``visibility=["app"]`` — the list omits ``"model"``, and the spec says a
    # host MUST NOT include such a tool in the tool list it gives the model.
    # Omitting the field entirely means BOTH, so this is not a default anybody
    # gets by accident; it is the whole safety property of this door and it is
    # one keyword long.
    #
    # No ``resource_uri``: this tool renders nothing. It is pressed by the
    # button on another tool's card, so it needs the visibility half of the
    # declaration and not the renderer half. (An AppConfig with only a
    # visibility puts exactly ``_meta.ui.visibility`` on the wire — measured
    # against the installed FastMCP, which does not model ``visibility`` as a
    # tool field but does emit it under ``_meta.ui``.)
    #
    # AND IT IS NOT OUR FENCE. The server cannot tell a UI-initiated
    # ``tools/call`` from a model-initiated one; both arrive on the same
    # transport with the same token. This declares an intent that a conforming
    # host honours. Read the module docstring before treating it as a guarantee.
    approve_only_from_the_card = AppConfig(visibility=["app"])

    # Bound to the name the source guard ``tests/test_tools_bind_their_scope.py``
    # looks for. That guard fails on a tool that DECLARES a ``scope`` and then
    # calls the seam without ``scope=`` — the omission that once let a member of
    # one workspace read another workspace's Skill. It matches on the call
    # ``_guard(...)``, so a module that renamed the seam on the way in would be
    # invisible to it: a fence that never reaches the code it guards is worse
    # than no fence. Keep this alias if you keep the guard.
    _guard = guard

    def _refuse(exc: BaseException) -> "ToolError":
        """A refusal an AGENT can act on: the type name plus the reason.

        The type name is load-bearing over a conversational face. An agent that
        reads ``ValueError: kind must be a CamelCase identifier …`` can fix its
        own call; one that gets an unexplained failure retries the same call
        forever, which is how a refusal turns into a loop."""
        return ToolError(f"{type(exc).__name__}: {exc}")

    def _no_registry(exc: BaseException) -> "ToolError":
        """The store has no namespace-registry scope at all.

        Not a caller error and not a policy refusal — a store that was never
        provisioned for authoring, or one whose registry could not be read.
        Neither member of :data:`NO_REGISTRY` is in :data:`AUTHORING_REFUSALS`,
        deliberately (``FileNotFoundError`` is an ``OSError``;
        ``NamespaceRegistryUnreadable`` is a ``RuntimeError``), so without this
        mapping both reach the agent as an unexplained failure. The REST face
        answers 503 for exactly this, and this is the same sentence over a
        transport that has no status codes.

        Raised ``from exc``, unlike :func:`_refuse`. Suppressing the chain is
        right for a policy REFUSAL — the verdict is the whole story and the
        traceback would only leak the shape of the machine that reached it. This
        is not a verdict, it is an operator's missing directory, and ``from
        None`` discards the one detail that says WHICH. The agent reads the same
        sentence either way; the operator keeps the server-side cause."""
        return ToolError(
            "the namespace registry scope is not provisioned in this store, so "
            "no Kind can be authored yet: authoring reads the KindNamespace "
            "registry before it mints a namespace. Ask an operator to provision "
            f"it ({type(exc).__name__}: {exc})"
        )

    @server.tool(run_in_thread=False, app=kind_draft_card_app)
    async def author_kind(
        kind: str, schema: dict[str, Any], traits: list[str] | None = None,
        presentation: dict[str, Any] | list[str] | None = None,
        tenant: str | None = None,
    ) -> dict[str, Any]:
        """Author a Kind for your workspace — a typed document shape of your own.

        ``kind`` is a **CamelCase identifier** (a capital letter then up to 63
        letters or digits: ``Contrato``, ``ApoliceDeSeguro``). It becomes part of
        the document's path, so anything else is refused, by name.
        ``schema`` is a JSON Schema object describing the Kind's ``spec``.
        ``traits`` (optional) are the behavioural traits the Kind opts into.

        ``presentation`` (optional) says how documents of this Kind should
        READ, so that every surface — a card in this chat, a screen in the
        portal — shows the same fields under the same names without anyone
        writing rendering code for your Kind. Declare it and your Kind is a
        first-class citizen; omit it and surfaces fall back to their generic
        rendering.

        Its shortest form is the field order: ``["name", "titulo", "situacao"]``.
        The full form adds a human label and what each field MEANS::

            {"fields": [{"field": "name", "label": "Contrato",
                         "role": "identifier"},
                        {"field": "situacao", "label": "Situação",
                         "role": "status"}],
             "hidden": ["assinado_em"]}

        ``role`` is a closed vocabulary — ``identifier``, ``title``,
        ``subtitle``, ``status``, ``owner``, ``parent``, ``rank``, ``tag``,
        ``timestamp``, ``metric``, ``body`` — and each word says what the VALUE
        MEANS, never how it should look. There is deliberately no way to
        declare a colour, a column, a width or a widget: how a status LOOKS is
        the surface's business, and a Kind that tried to say would be wrong on
        the next surface that rendered it. ``name`` refers to the document's
        own name; every other entry is a field of your ``spec``.

        **What you get back is INERT.** ``approved`` is always ``false``, and an
        unapproved Kind is not registered — so it validates nothing and routes
        nothing. A human has to approve it in the portal before it has any
        effect. That approval is NOT available here and never will be: an agent
        that could approve its own proposal would make the review pointless.
        Author the Kind, then tell the person you are working with that it is
        waiting for their approval — and do not go looking for a tool to do it.

        The document records who proposed it, taken from your VERIFIED identity
        on this connection. There is no argument for it; a proposer a caller can
        name is not a proposer.

        Calling it again for the same ``kind`` EDITS the declaration, and the
        edit clears the approval marker on the document: ``list_my_kinds`` will
        report it as ``approved: false`` again, and a human has to approve the
        new shape.

        **An edit does not take a Kind that is already in effect back out of
        effect.** Approval is checked when a Kind is LOADED, so one that was
        already approved and loaded keeps validating documents against the shape
        it was loaded with until the server restarts — which may be a while, and
        differs between servers. So after editing an approved Kind, expect
        ``approved: false`` and your new schema here while writes are still
        being checked against the OLD one. Do not tell the person you are
        working with that editing withdrew the Kind; tell them the edit is
        waiting for approval, and that the previous shape is still the one in
        force.

        The Kind lands under your workspace's own apiVersion namespace, minted on
        first use and stable afterwards, so two workspaces can both author
        ``Contrato`` without colliding. Use ``list_my_kinds`` to see what you have
        authored and which of it has been approved."""
        # No ``scope``, deliberately — and therefore nothing for the scope-binding
        # guard to bind. The Kind is authored at the BASE of the scope the
        # workspace owns, which the core derives from the resolved workspace
        # (``live.default_scope(tenant)``); a caller-supplied scope would be a
        # parameter the door then ignored, which reads as a capability it does
        # not have. The REST twin (``POST /v1/kinds``) takes none either.
        from dna.application.sdlc import now_iso

        tenant = await _guard("definitions", tenant, family_op="write")
        try:
            return await author_kind_impl(
                await live(), kind=kind, schema=schema, tenant=tenant or "",
                now=now_iso(), actor=actor_from_context(), traits=traits,
                presentation=presentation,
            )
        except NO_REGISTRY as exc:
            raise _no_registry(exc) from exc
        except AUTHORING_REFUSALS as exc:
            raise _refuse(exc) from None

    @server.tool(run_in_thread=False, app=prefab_card_app)
    async def list_my_kinds(
        scope: str | None = None, tenant: str | None = None,
    ) -> dict[str, Any]:
        """List the Kinds your workspace has authored, with their approval state
        — name, target Kind + apiVersion, namespace, ``approved``, and BOTH
        actors (``proposed_by``/``proposed_at``, ``approved_by``/``approved_at``).

        Reads DOCUMENTS, not the registry: an unapproved Kind is precisely the
        one the registry does not have, so this is the only surface that shows a
        proposal still waiting for a human. ``approved: false`` means the Kind
        exists and has no effect yet.

        The declaration points the shared ``ui://dna/prefab`` card (read-only,
        and read-only is the whole point — approval is not an act an agent may
        take): a host that renders MCP Apps shows the roster with the count
        still inert in the headline. Every other host reads the same textual
        result, unchanged."""
        tenant = await _guard("definitions", tenant, scope=scope, family_op="read")
        try:
            data = await list_authored_kinds_impl(
                await live(), tenant=tenant, scope=scope,
            )
        except NO_REGISTRY as exc:
            raise _no_registry(exc) from exc
        except AUTHORING_REFUSALS as exc:
            raise _refuse(exc) from None
        return with_card(data, kinds_app(data))

    @server.tool(run_in_thread=False, app=prefab_card_app)
    async def review_kind(
        kind: str, scope: str | None = None, tenant: str | None = None,
    ) -> dict[str, Any]:
        """Show ONE authored Kind in full, so a human can decide about it — the
        summary ``list_my_kinds`` gives PLUS the **schema**, the traits and the
        **presentation** (how documents of this Kind will read: which fields a
        person sees, in what order, under what names). The approval confers all
        three, so all three are here.

        This is the tool to reach for when somebody asks what there is to
        approve, or what a proposed Kind actually declares. The roster answers
        "which" and this answers "what": registration is what confers schema
        validation and storage routing, so the decision to confer effect is a
        decision about the schema, and the roster deliberately does not carry
        it (a table with a JSON Schema in every row is unreadable).

        On a host that renders MCP Apps the result is a card showing the schema,
        both actors, what the current state means for documents, and — when the
        Kind is not currently in effect — an **Approve** button for the person
        reading it to press. You cannot press it: the tool behind that button is
        declared app-only and is not in your tool list. Do not go looking for
        it, and do not tell the person you are working with that you approved
        anything. Show them this card and let them decide.

        Every other host reads the same textual answer, unchanged."""
        tenant = await _guard("definitions", tenant, scope=scope, family_op="read")
        handle = await live()
        try:
            found = await get_authored_kind_impl(
                handle, kind=kind, tenant=tenant, scope=scope,
            )
        except NO_REGISTRY as exc:
            raise _no_registry(exc) from exc
        except AUTHORING_REFUSALS as exc:
            raise _refuse(exc) from None
        # NESTED under ``declaration``, and not because nesting reads nicer.
        # The projection carries a field called ``state`` (i-085's three-valued
        # approval state) and ``state`` is also one of Prefab's own wire keys,
        # so a FLAT payload collides — ``with_card`` refuses it loudly, which is
        # exactly what that guard is for. The envelope makes the collision
        # structurally impossible for this field and every future one, and it
        # costs no vocabulary: ``declaration`` holds ``_authored_kind_summary``
        # unchanged, the same projection the roster and the portal read.
        data = {
            "scope": scope or handle.default_scope(tenant),
            "declaration": found,
        }
        return with_card(data, kind_review_app(found))

    # ``name=APPROVE_TOOL`` rather than the function's own name: the card's
    # button targets that same constant, so the two cannot drift into a button
    # that points at nothing (which fails silently, at render time, on somebody
    # else's machine).
    @server.tool(name=APPROVE_TOOL, run_in_thread=False,
                 app=approve_only_from_the_card)
    async def approve_kind(
        kind: str, tenant: str | None = None,
    ) -> dict[str, Any]:
        """Approve an authored Kind — the act that puts it INTO EFFECT.

        **This tool is for the Approve button on a ``review_kind`` card, pressed
        by a person.** It is declared app-only for that reason and a conforming
        host does not offer it to a model. Approval is a human decision; a model
        that called this would be recording a decision nobody made.

        The approver is the VERIFIED identity of this connection, resolved
        server-side. There is no argument for it, and none will be added: an
        approver a caller can name is not an approver. The proposal's own
        ``proposed_by`` is preserved untouched, so the record names both acts
        and neither wears the other's name — which is the whole point when the
        two are different people.

        Approving a REVOKED Kind clears the revocation, and every document that
        went invalid is valid again with nothing to migrate.

        Refused, in words: 'not found' when the workspace authored no such Kind
        (a neighbour's Kind is not found either — it is not yours to approve),
        and a stale-write refusal when the declaration changed between the read
        that produced the card and this call. That last one is the correct
        outcome and not a glitch: an approval that cannot see the shape it is
        approving is not an approval. Re-read the Kind and approve again."""
        from dna.application.sdlc import now_iso

        tenant = await _guard("definitions", tenant, family_op="write")
        try:
            # DELEGATED, never reimplemented. This is the same function the REST
            # approve route calls — the guarded read-modify-write (i-083), the
            # ownership-scoped lookup, the revocation clear (i-085) and the
            # response that echoes both actors. A second implementation of this
            # act would be a second audit shape, and a second place to forget
            # the ``if_match``.
            return await approve_kind_impl(
                await live(), kind=kind, tenant=tenant or "",
                actor=actor_from_context(), now=now_iso(),
            )
        except NO_REGISTRY as exc:
            raise _no_registry(exc) from exc
        except AUTHORING_REFUSALS as exc:
            # Everything this act can legitimately refuse with is already in
            # here, and each arrives as a SENTENCE the agent can relay to the
            # person who pressed the button: ``AuthoredKindNotFound`` (a
            # LookupError — no such Kind of yours, which is also the answer for
            # a neighbour's, so "it exists but is not yours" never becomes a
            # probe) and ``StaleDocumentWrite`` (a ValueError, i-083 — the
            # declaration moved between the card's read and this call, so the
            # approval was refused rather than stamped onto a shape nobody saw).
            # A separate arm per exception would only re-spell the same mapping.
            raise _refuse(exc) from None

    @server.tool(run_in_thread=False)
    async def revoke_kind(
        kind: str, tenant: str | None = None,
    ) -> dict[str, Any]:
        """Withdraw an authored Kind of your workspace — the un-author.

        The counterpart ``author_kind`` never had (measured in the 04/08 test
        battery: a discarded experiment stayed as an orphan proposal with no
        MCP path to withdraw it). Two cases, ONE deliberate asymmetry:

        * proposal never approved (inert) → withdrawn. Nothing was in effect,
          so a model may discard what a model proposed — the same gravity as
          authoring it.
        * Kind APPROVED → **refused here**. Withdrawing EFFECT invalidates the
          documents that relied on it; that is a human decision, symmetrical
          with approval (which is also human-only). Ask the person to revoke
          in the portal / review card.

        Revoked is a recorded third state, not an erasure: the declaration row
        stays (audit), existing documents stay readable (marked invalid when
        the Kind was approved), and ``approve_kind`` reverses it in one act.
        Only YOUR workspace's Kinds answer — a neighbour's is 'not found'.
        """
        from dna.application.sdlc import now_iso

        tenant = await _guard("definitions", tenant, family_op="write")
        try:
            atual = await get_authored_kind_impl(
                await live(), kind=kind, tenant=tenant or "",
            )
            if atual.get("approved"):
                raise ToolError(
                    f"Kind {kind!r} is APPROVED and in effect — withdrawing "
                    f"effect invalidates the documents that rely on it, and "
                    f"that is a human decision (like approval). Ask the "
                    f"workspace owner to revoke it in the portal."
                )
            return await revoke_kind_impl(
                await live(), kind=kind, tenant=tenant or "",
                actor=actor_from_context(), now=now_iso(),
            )
        except NO_REGISTRY as exc:
            raise _no_registry(exc) from exc
        except AUTHORING_REFUSALS as exc:
            raise _refuse(exc) from None

    return [
        "author_kind", "list_my_kinds", "review_kind", APPROVE_TOOL,
        "revoke_kind",
    ]
