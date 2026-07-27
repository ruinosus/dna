"""``dna_cli._mcp_kinds`` — the CONVERSATIONAL face of Kind authoring.

A tenant declares its own Kind by talking to an agent. The agent calls
``author_kind``; what lands is a real, auditable ``KindDefinition`` document
that is **inert** — the registry withholds registration until a human approves,
and registration is what confers schema validation and storage routing. So the
Kind an agent authors has no effect until a person says so, and that is the
absence of a mechanism rather than a promise.

**There is no approval tool here, and there must never be one.** Approval is the
act that confers effect, and an agent able to call it could approve its own
proposal — which would make the whole gate decorative. The human act lives in
the portal (``POST /v1/kinds/{kind}/approve`` on the REST face, reached by a
reviewer's own credential). ``tests/test_mcp_kind_authoring.py`` asserts the
absence over the WHOLE advertised tool surface, so the rule survives somebody
adding a tool anywhere on this server, not just in this module.

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
    author_kind_impl,
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
    """Register ``author_kind`` + ``list_my_kinds`` on ``server``.

    Returns their names. Nothing reads them today — ``build_server`` discards
    the return, exactly as it does for ``register_document_tools`` — so the list
    is there for a caller that wants to report what it mounted, not because
    anything prints it.
    """
    from fastmcp.exceptions import ToolError

    from dna_cli._mcp_auth import actor_from_context

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

    @server.tool(run_in_thread=False)
    async def author_kind(
        kind: str, schema: dict[str, Any], traits: list[str] | None = None,
        tenant: str | None = None,
    ) -> dict[str, Any]:
        """Author a Kind for your workspace — a typed document shape of your own.

        ``kind`` is a **CamelCase identifier** (a capital letter then up to 63
        letters or digits: ``Contrato``, ``ApoliceDeSeguro``). It becomes part of
        the document's path, so anything else is refused, by name.
        ``schema`` is a JSON Schema object describing the Kind's ``spec``.
        ``traits`` (optional) are the behavioural traits the Kind opts into.

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
            )
        except NO_REGISTRY as exc:
            raise _no_registry(exc) from exc
        except AUTHORING_REFUSALS as exc:
            raise _refuse(exc) from None

    @server.tool(run_in_thread=False)
    async def list_my_kinds(
        scope: str | None = None, tenant: str | None = None,
    ) -> dict[str, Any]:
        """List the Kinds your workspace has authored, with their approval state
        — name, target Kind + apiVersion, namespace, ``approved``, and BOTH
        actors (``proposed_by``/``proposed_at``, ``approved_by``/``approved_at``).

        Reads DOCUMENTS, not the registry: an unapproved Kind is precisely the
        one the registry does not have, so this is the only surface that shows a
        proposal still waiting for a human. ``approved: false`` means the Kind
        exists and has no effect yet."""
        tenant = await _guard("definitions", tenant, scope=scope, family_op="read")
        try:
            return await list_authored_kinds_impl(
                await live(), tenant=tenant, scope=scope,
            )
        except NO_REGISTRY as exc:
            raise _no_registry(exc) from exc
        except AUTHORING_REFUSALS as exc:
            raise _refuse(exc) from None

    return ["author_kind", "list_my_kinds"]
