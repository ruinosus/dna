"""The DNA REST API client (sync, ``httpx``-based).

Named methods for the FULL ``/v1/*`` surface — every operation in
``docs/openapi.json``, reads AND writes. :meth:`DnaClient.request` remains the
low-level escape hatch, but it is no longer the only way to reach a write.
Every method returns the API's JSON object (``dict[str, Any]``) and raises
:class:`DnaApiError` on a non-2xx status.

Coverage is enforced: ``tests/test_openapi_drift.py`` fails if the spec grows an
operation — of ANY HTTP method — with no named method here.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

__all__ = ["DnaClient", "DnaApiError"]

JsonObject = dict[str, Any]


class DnaApiError(Exception):
    """Raised when the DNA REST API responds with a non-2xx status. Carries the
    HTTP ``status`` and the API's ``{"detail": ...}`` payload (or the raw body)."""

    def __init__(self, status: int, detail: Any) -> None:
        self.status = status
        self.detail = detail
        message = (
            detail["detail"]
            if isinstance(detail, dict) and "detail" in detail
            else f"DNA REST API error (HTTP {status})"
        )
        super().__init__(str(message))


#: Routes that accept NO ``scope``/``tenant`` query param, so the client-level
#: defaults must NOT be merged into them, keyed by ``(METHOD, path)``. FastAPI
#: would silently ignore the stray params, but sending them misrepresents the
#: route: the workspace boundary is resolved from the caller's VERIFIED identity
#: (or the body), never from a tenant hint on the query string.
_NO_SCOPE_TENANT: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/health"),
        # The workspace boundary routes — identity-scoped, not tenant-scoped.
        ("GET", "/v1/workspaces"),
        ("POST", "/v1/workspaces"),
        ("POST", "/v1/workspaces/accept"),
        ("PUT", "/v1/account-plan"),
        # POST /v1/projects names its workspace in the BODY (decision A1); the
        # GET on the same path IS scope/tenant-aware, hence the method-keyed set.
        ("POST", "/v1/projects"),
        # The MIF import always targets the CALLER'S OWN personal partition,
        # resolved server-side from the token (INV-PERSONAL) — it is
        # identity-scoped, not tenant-scoped. Merging a default `tenant` here
        # would send a param the server ignores, implying a choice the caller
        # does not have. `scope` is passed explicitly by `import_memories`.
        ("POST", "/v1/memories/import"),
        # Its READ face — identity-scoped for the same reason; `scope` is
        # passed explicitly by `list_personal_memories`.
        ("GET", "/v1/memories/personal"),
    }
)


class DnaClient:
    """A typed client for the DNA REST API — the full read AND write surface.

    ``base_url`` is a running API, e.g. ``http://127.0.0.1:8080``. ``token`` (for
    ``--auth token``/``--auth config``) is sent as ``Authorization: Bearer``.
    ``tenant``/``scope`` are optional defaults merged into every call's query
    (a per-call value wins). Usable as a context manager (closes the transport).

    >>> with DnaClient("http://127.0.0.1:8080", scope="dna-development") as dna:
    ...     agents = dna.list_agents()
    ...     hits = dna.search_memories("tenancy invariant", k=3)
    """

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        tenant: str | None = None,
        scope: str | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._default_tenant = tenant
        self._default_scope = scope
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    # -- lifecycle -----------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> DnaClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- low-level (the full surface, incl. writes) --------------------------

    def request(
        self, method: str, path: str, *, params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> JsonObject:
        """Issue a raw request (the full API surface — reads AND writes). Drops
        ``None`` query params, merges the client-level default ``scope``/``tenant``
        when the path accepts them, and raises :class:`DnaApiError` on non-2xx."""
        query = self._merge_query(method, path, params)
        resp = self._http.request(method, path, params=query, json=json)
        if resp.is_success:
            return resp.json()
        try:
            detail: Any = resp.json()
        except Exception:  # noqa: BLE001 — a non-JSON error body is still an error.
            detail = resp.text
        raise DnaApiError(resp.status_code, detail)

    def _get(self, path: str, **params: Any) -> JsonObject:
        return self.request("GET", path, params=params)

    def _write(
        self, method: str, path: str, body: JsonObject, **params: Any
    ) -> JsonObject:
        """Issue a write, dropping ``None`` body keys so the server's own default
        (not the client's idea of one) applies to an omitted optional field."""
        payload = {k: v for k, v in body.items() if v is not None}
        return self.request(method, path, params=params, json=payload)

    def _merge_query(
        self, method: str, path: str, params: dict[str, Any] | None
    ) -> dict[str, Any]:
        params = dict(params or {})
        # A `/v1/workspaces/{id}/...` sub-route is identity-scoped like its parent.
        takes_scope_tenant = (
            (method.upper(), path) not in _NO_SCOPE_TENANT
            and not path.startswith("/v1/workspaces/")
        )
        if takes_scope_tenant:
            if self._default_scope is not None and params.get("scope") is None:
                params["scope"] = self._default_scope
            # `/v1/tenants/{tid}/...` takes `scope` but NOT `tenant` — the tenant
            # IS the `tid` path segment, so a default tenant must not shadow it.
            if (
                self._default_tenant is not None
                and params.get("tenant") is None
                and not path.startswith("/v1/tenants/")
            ):
                params["tenant"] = self._default_tenant
        return {k: v for k, v in params.items() if v is not None}

    # -- health --------------------------------------------------------------

    def health(self) -> JsonObject:
        """Liveness probe (unauthenticated). Returns ``{"ok": True}``."""
        return self._get("/health")

    # -- definitions ---------------------------------------------------------

    def list_agents(
        self, *, scope: str | None = None, tenant: str | None = None
    ) -> JsonObject:
        """List a scope's prompt-target agents, tenant-aware."""
        return self._get("/v1/agents", scope=scope, tenant=tenant)

    def agent_prompt(
        self, name: str, *, scope: str | None = None, tenant: str | None = None,
        explain: bool = False,
    ) -> JsonObject:
        """Compose one agent's system prompt LIVE (Soul + Guardrails + instruction).

        ``explain=True`` (opt-in) adds per-section provenance to the response:
        ``sections`` (source artifact, content hash, version, layer origin and
        tenant-overlay marker per composed section) and ``attribution``
        (``"declared"`` — kernel-owned template, section map correct by
        construction; ``"heuristic"`` — the agent has a custom promptTemplate,
        the map is fail-soft string matching and may omit/over-report
        sections). The composed ``prompt`` is byte-identical either way. When
        ``False`` (default) the request is exactly the historical plain
        compose — no ``explain`` query param is sent at all."""
        return self._get(
            f"/v1/agents/{name}/prompt", scope=scope, tenant=tenant,
            explain=True if explain else None,
        )

    def list_tools(
        self, *, scope: str | None = None, tenant: str | None = None
    ) -> JsonObject:
        """List a scope's Tool Kind surfaces (name + description), tenant-aware."""
        return self._get("/v1/tools", scope=scope, tenant=tenant)

    def genome_view(
        self, *, scope: str | None = None, tenant: str | None = None
    ) -> JsonObject:
        """The derived Genome view of a scope: identity + ships (the scope's own
        contents) + the tenant LayerPolicy, composed live."""
        return self._get("/v1/genome", scope=scope, tenant=tenant)

    def read_definition(
        self, kind: str, name: str, *,
        scope: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """Read one definition as the tenant sees it: the effective (composed)
        spec, the inherited base spec, whether the tenant has an override, and
        the Kind's edit schema (``ui_schema`` + overlayable fields) — what a
        customization editor renders. 404 for an unknown (kind, name)."""
        return self._get(f"/v1/definitions/{kind}/{name}", scope=scope, tenant=tenant)

    # -- definitions (writes) -------------------------------------------------

    def apply_definition(
        self, kind: str, name: str, spec: dict[str, Any], *,
        scope: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """Persist a tenant override of a definition (the editor's Save) — a
        tenant-layer write. A LOCKED Kind/field is vetoed by the kernel's
        LayerPolicy check and surfaces as a 403 :class:`DnaApiError`."""
        return self._write(
            "PUT", f"/v1/definitions/{kind}/{name}", {"spec": spec},
            scope=scope, tenant=tenant,
        )

    def revert_definition(
        self, kind: str, name: str, *,
        scope: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """Revert a tenant override — deletes the tenant-layer doc so reads
        fall back to the inherited base (the editor's "Reset to default")."""
        return self.request(
            "DELETE", f"/v1/definitions/{kind}/{name}",
            params={"scope": scope, "tenant": tenant},
        )

    # -- Kind authoring (a workspace declares its OWN Kind) ------------------

    def author_kind(
        self, kind: str, schema: dict[str, Any], *,
        traits: list[str] | None = None,
        presentation: dict[str, Any] | list[str] | None = None,
        relations: dict[str, Any] | None = None,
        plane: str | None = None,
        tenant: str | None = None,
    ) -> JsonObject:
        """Author a Kind for the calling workspace — a ``KindDefinition``
        instance written WITHOUT an approval marker, under the workspace's own
        assigned apiVersion namespace.

        What comes back is INERT: ``approved`` is always ``false``, and an
        unapproved Kind never enters the registry, so it neither validates
        instances nor routes their storage. Approval is a separate act with its
        own verified actor (:meth:`approve_kind`) — this call cannot perform it,
        and an ``approved_by`` supplied here would be ignored (there is no
        parameter for it on purpose). The instance records ``proposed_by``: the
        server-verified identity of THIS call, stamped here because a proposer
        cannot be back-filled onto an instance that never recorded one.

        ``kind`` must be a CamelCase identifier — a CAPITAL letter followed by
        up to 63 letters or digits, nothing else. It is the one value that
        reaches a path, and the initial capital is required so ``Contrato`` and
        ``contrato`` cannot collide on a case-insensitive filesystem.

        ``presentation`` (optional) declares how instances of this Kind READ —
        the ordered fields, their human labels and their semantic roles, plus
        what to hide. It is the SAME declaration a Kind shipped inside the SDK
        makes, which is the point: without it, only builtin Kinds could tell a
        surface how to render them and every tenant Kind would be
        second-class. Shortest form is the field order (``["name", "titulo"]``);
        the full form is ``{"fields": [{"field": …, "label": …, "role": …}],
        "hidden": [...]}``, where ``role`` is a closed vocabulary of MEANING
        (``identifier``/``title``/``status``/``owner``/…) and there is
        deliberately no way to declare a colour, a column or a width — how a
        field LOOKS is each surface's own business.

        ``relations`` (optional) declares what the Kind POINTS AT:
        ``{field: {"to": "Cliente", "cardinality": "one"}}``, where the KEY is
        the ``spec`` field holding the value. ``to`` takes a Kind name, a list
        of them, or ``"*"``; ``cardinality`` (``one``/``many``) is required and
        states the MODEL's multiplicity rather than the JSON's shape;
        ``inverse_of`` and ``by`` are optional. Omitting it leaves the Kind an
        island — which is a legitimate statement about a domain and, until this
        parameter existed, was the only statement a tenant Kind could make.
        Declaring a relation does NOT create an edge: relations are resolved
        only for REGISTERED Kinds, and registration is what human approval
        turns on.

        ``plane`` (optional) is ``composition`` or ``record``, and is stored
        only when declared — an instance that says nothing keeps the question of
        the right default open, which is deliberate.

        400 for a missing tenant, a ``kind`` that is not such an identifier, a
        malformed ``presentation`` or a ``relations`` block that is malformed or
        contradicts the ``schema`` (the response names the offending key); 403
        when the workspace does not own the target namespace; 503 when the
        store's namespace-registry scope has not been provisioned."""
        return self._write(
            "POST", "/v1/kinds",
            {
                "kind": kind, "schema": schema, "traits": traits,
                "presentation": presentation, "relations": relations,
                "plane": plane,
            },
            tenant=tenant,
        )

    def approve_kind(
        self, kind: str, *, tenant: str | None = None,
    ) -> JsonObject:
        """Approve an authored Kind — the act that puts it INTO EFFECT.

        Registration is what confers schema validation and storage routing, and
        the registry withholds it until ``approved_by`` names someone, so this
        is not a flag with a promise attached: it is the only thing that lets
        the next load take the Kind at all.

        The approver is the caller's server-VERIFIED identity; there is
        deliberately no parameter for it, and an ``approved_by`` in the payload
        would reach nothing. The instance's ``proposed_by`` is preserved, so the
        response names both acts. The two MAY be the same identity — a solo
        author approving their own proposal is two credentials, and the audit
        reports the coincidence rather than refusing it.

        404 when no such Kind was authored in this scope (approval acts on an
        existing instance and creates none); 400 for a missing tenant, a
        malformed ``kind``, or a Kind declared under two namespaces at once;
        403 when the namespace gate refuses the write; 409 when the Kind was
        edited between the read and this call (re-read, then approve again).

        It is also the UNDO of :meth:`revoke_kind`: approving again clears the
        revocation, and every existing instance is valid once more with nothing
        to migrate."""
        return self._write("POST", f"/v1/kinds/{kind}/approve", {}, tenant=tenant)

    def revoke_kind(
        self, kind: str, *, tenant: str | None = None,
    ) -> JsonObject:
        """Revoke an authored Kind — the act that WITHDRAWS its effect.

        Deliberately NOT the inverse of :meth:`approve_kind`. Un-approving would
        return the Kind to *never approved*, and a Kind that never registered is
        the PERMISSIVE state — its instances are accepted with no validation at
        all — so clearing the approval would switch the gate off rather than
        close it. Revoked is a THIRD state::

            state            existing instances   new instances
            ---------------  -------------------  --------------------------
            never approved   —                    accepted WITHOUT validation
            approved         valid, routed        validated against the schema
            revoked          INVALID              REFUSED

        Nothing is deleted. Existing instances stay readable and come back
        MARKED (``status.valid`` is ``false``), and in a listing they appear
        marked rather than vanishing — so this can never be used to hide data
        without deleting it. New instances of the Kind are refused outright,
        conforming ones included: what was withdrawn is the Kind, not a schema.

        Reversible in one call — :meth:`approve_kind` clears the revocation.
        ``approved_by`` survives here, because revoking is a third act and not
        an erasure of the second.

        The revoker is the caller's server-VERIFIED identity; there is
        deliberately no parameter for it.

        404 when no such Kind was authored in this scope, and equally when it
        belongs to another workspace; 400 for a missing tenant or a malformed
        ``kind``; 409 when the instance moved since it was read; 403 when the
        namespace gate refuses the write."""
        return self._write("POST", f"/v1/kinds/{kind}/revoke", {}, tenant=tenant)

    def list_authored_kinds(
        self, *, scope: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """List the scope's authored Kinds with their approval state — the
        audit view. Reads INSTANCES, not the registry: an unapproved Kind is
        precisely the one the registry does not have.

        Each row carries BOTH actors (``proposed_by``/``proposed_at`` and
        ``approved_by``/``approved_at``): a reviewer deciding whether to confer
        effect needs to see who asked for it without leaving the list."""
        return self._get("/v1/kinds", scope=scope, tenant=tenant)

    def get_authored_kind(
        self, kind: str, *, scope: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """Read ONE authored Kind in full — the listing's row PLUS the
        ``schema``, the ``traits`` and the ``presentation``.

        The roster (:meth:`list_authored_kinds`) deliberately omits the schema,
        which left a reviewer unable to see what they would be conferring effect
        ON. Registration is what gives a Kind schema validation and storage
        routing, so "should this take effect?" is a question about the schema;
        this is the call that answers it.

        ``presentation`` is the other half of that answer, and the one a UI
        needs: ``schema`` says what an instance may CONTAIN, ``presentation``
        says what a person will SEE of it — which fields, in what order, under
        what names — on every surface the workspace has. It is ``null`` for a
        Kind that declares none.

        Filtered to the CALLER: a Kind authored by another workspace in a shared
        scope is a **404**, the same answer a Kind nobody ever authored gets —
        "it exists but is not yours" would be a probe for what the neighbours
        are authoring, and this call would answer that probe with their data
        model.

        400 for a ``kind`` that is not a CamelCase identifier, or a Kind
        declared under two of the caller's own namespaces at once; 404 when no
        such Kind is the caller's; 403 for a namespace two claims give to
        different owners; 503 when the namespace registry cannot be read."""
        return self._get(f"/v1/kinds/{kind}", scope=scope, tenant=tenant)

    def get_registered_kind(
        self, kind: str, *, scope: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """The descriptor of a REGISTERED Kind — its JSON ``schema`` plus the
        ``ui_schema`` widget hints.

        The registry sibling of :meth:`get_authored_kind`: a registered Kind is
        the PRODUCT's data model (the same for every caller, holding nobody's
        content), so this door does not filter. It exists so a form can DERIVE
        validation (min/max, enums, required) from the schema instead of
        hand-copying constraints that then drift from the kernel's.

        ``tenant`` (i-094) resolves the scope the way the instance routes do
        (``default_scope`` server-side) — a caller that only knows the
        workspace id reaches that workspace's own registered Kinds without
        hardcoding the scope-prefix convention. Explicit ``scope`` wins.

        404 for a Kind the runtime does not register."""
        return self._get(f"/v1/kinds/registry/{kind}", scope=scope, tenant=tenant)

    def kind_graph(
        self, *, scope: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """The SCHEMA graph of the registered Kinds — which Kind may point at
        which, through which field, in ONE call.

        The SET sibling of :meth:`get_registered_kind`, and the reason it
        exists: answering "which Kinds reference which here?" through the
        per-Kind door costs one request per Kind and gets slower as a
        workspace grows. This is the same projection that generates
        ``docs/reference/data-model.md``, served as JSON.

        Returns ``kinds`` (nodes: kind/alias/group/plane), ``edges``
        (``from_kind``/``field``/``to_kind``/``cardinality``/``tier``/
        ``polymorphic``/``by``/``enforced``/``inverse_of``), the gap list
        ``unresolved``, and a ``coverage`` block.

        **``tier == "declared"`` is NOT the same as ``enforced``.** The kernel
        resolves a relation at write time only when it has a concrete target
        Kind addressed by instance name (``by == "name"``). A relation
        addressed by a spec field of the target (``by: "workspace_id"``) or
        carrying its Kind in the value (``to_kind == "*"``) is fully declared
        and deliberately not followed. Filter on ``enforced`` — never on the
        tier — when the question is "what does the runtime check?".

        **Rank ``unresolved`` by ``origin``, never by ``reason``.**
        ``declared``, ``composition`` and ``inverse`` rows are declarations the
        model cannot honour — an authoring error, and ``inverse`` specifically
        means two Kinds each claim to be half of one relation while disagreeing
        about it. ``undeclared`` rows are fields whose NAME looks like a
        reference and which nothing declares; they are usually not references
        at all (an OAuth ``client_id``, a Stripe customer id).
        ``coverage.declared_origins`` names the ones worth alarm, so the
        ranking is derived from the answer instead of re-typed in a screen —
        and ``reason`` stays English prose nobody has to translate.

        **Read the coverage block.** ``coverage.enforced`` says how much of the
        graph the runtime actually checks, and ``limits`` names what the graph
        structurally cannot see. The first limit is the one that matters most:
        these edges are SCHEMA — which Kinds MAY reference which. Which
        INSTANCES reference which is a different graph, and this call does not
        answer it.

        No 404: a scope with nothing registered is an empty graph whose
        ``coverage.kinds`` is 0, which is an answer."""
        return self._get("/v1/graph/kinds", scope=scope, tenant=tenant)
    def list_registered_kinds(
        self, *, scope: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """The Kind CATALOG of a scope — every Kind the registry serves here.

        The collection sibling of :meth:`get_registered_kind`, and the answer
        to "what can I act on?" without hardcoding a list. A hardcoded list is
        how a Kind registered tomorrow stays invisible; the enumeration belongs
        to the registry, not to each caller.

        Not :meth:`list_authored_kinds`, which lists the caller's own
        KindDefinition INSTANCES *including the unapproved ones* — the audit
        roster behind an approval decision. This lists what is REGISTERED and
        therefore in force, built-ins included.

        Each row carries ``kind``/``api_version``/``alias``, the quota
        ``family``, the ``plane`` (``composition`` vs ``record``),
        ``tenant_scope``, ``storage_pattern``, ``traits``, and the
        ``writable``/``deletable`` pair with the refusal explaining a false —
        so a refused operation is visible before it is attempted."""
        return self._get("/v1/kinds/registry", scope=scope, tenant=tenant)

    # -- the generic, kubernetes-shaped instance read/write -------------------

    def list_kind_instances(
        self, kind: str, *,
        api_version: str | None = None, tenant: str | None = None,
        limit: int = 50, offset: int = 0,
        fields: Sequence[str] | None = None,
        order_by: Sequence[str] | None = None,
    ) -> JsonObject:
        """List the instances of ``kind`` — the READ face of the generic door.

        The write (:meth:`write_kind_instance`) accepted any Kind, but reading
        back only worked for the Kinds someone had hand-written a route for
        (``/v1/memories``, ``/v1/projects``, …). Whoever wrote through the
        generic door could not read through it, and found that out AFTER
        writing.

        ``fields`` (dotted paths; an unprefixed one resolves under ``spec.``)
        pushes the PROJECTION down to the kernel. Without it, answering "which
        ones are open" costs 1 + N calls — list the names, then read each. On
        Postgres the projection becomes a SELECT and the row travels trimmed.

        An unknown Kind is 404 NAMING it, the same answer the write gives. An
        empty list from a Kind that exists is 200 with ``instances: []`` —
        "exists and holds nothing" is an answer, and conflating it with "does
        not exist" would make a screen say *error* where it should say *none
        yet*.

        Like the write, this route takes no ``scope`` parameter — identity and
        scope are never caller input here (see the server route's docstring).
        """
        return self._get(
            f"/v1/kinds/{kind}/instances",
            tenant=tenant, api_version=api_version, limit=limit, offset=offset,
            # CSV on the wire: the server splits on comma. `None` stays `None`
            # so an omitted projection means "the whole instance", not "no
            # fields" — an empty CSV would read as the latter.
            fields=",".join(fields) if fields else None,
            order_by=",".join(order_by) if order_by else None,
        )

    def get_kind_instance(
        self, kind: str, name: str, *,
        api_version: str | None = None, tenant: str | None = None,
        as_of: str | None = None,
    ) -> JsonObject:
        """Read ONE instance of ``kind``, VERBATIM — what the list cannot give.

        The projected list travels through the readers' view when the Kind is
        bundle-producible (Agent, Skill…), and the view NORMALIZES: real spec
        fields written through the generic door can simply not travel through
        it (measured 2026-08-05: an Agent's ``description`` and
        ``tools_requiring_confirmation``). This is the verbatim read, as the
        caller's layer sees the instance, with the optimistic-concurrency
        ``etag`` for a follow-up :meth:`write_kind_instance` ``if_match``.

        404 names what is missing — the unknown Kind or the instance.

        ``as_of`` (ISO-8601) reads the instance as the store RECORDED it at that
        instant — transaction time, not world time. The response then carries
        ``as_of`` / ``as_of_version`` / ``as_of_recorded_at``, which is how a
        caller tells a historical body from a live one. It REFUSES rather than
        approximates: **404** the instance did not exist yet, **410** its
        history was pruned past the instant (not the same statement), **501**
        the server's store keeps no history at all, **422** the instant is not
        ISO-8601. Before i-106 the server accepted this parameter and dropped
        it in silence, handing back the present under a past timestamp."""
        return self._get(
            f"/v1/kinds/{kind}/instances/{name}",
            tenant=tenant, api_version=api_version, as_of=as_of,
        )

    def resolve_instance(
        self, instance_id: str, *,
        scope: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """Expand a short ``metadata.id`` PREFIX to the instance it names.

        The id lane (i-114). Every instance carries a 12-character
        ``metadata.id`` that does not move when the instance is renamed; give
        the first four or more characters and this returns the whole instance,
        with the FULL id echoed back — the way ``git rev-parse`` expands a short
        commit hash.

        Deliberately separate from :meth:`get_kind_instance`, which is the NAME
        lane. A short name and a short id are both strings, so one door that
        accepted either would eventually answer a name query with an id match,
        and nothing in the response would say so.

        It REFUSES rather than guesses: **409** the prefix matches more than one
        instance (the detail names the candidates — lengthen it), **404** it
        matches none, **422** it is shorter than four characters or uses
        characters outside ``[a-z2-7]``, **501** the server's store cannot
        search by id.

        ``scope`` is normally unnecessary — ids are unique across the store, and
        not needing to know where the instance lives is most of what an id
        buys."""
        return self._get(
            f"/v1/instances/{instance_id}", tenant=tenant, scope=scope,
        )

    def graph_refs(
        self, kind: str, name: str, *,
        direction: str = "in", depth: int = 1,
        as_of: str | None = None,
        api_version: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """"What points at this instance?" — the derived reference graph.

        ``direction="in"`` (the default, and the product question) returns the
        instances pointing AT this one; ``"out"`` what it points at; ``"both"``
        the union. ``depth`` walks further and is clamped server-side — two of
        the declared references are self-referential by design, so an unbounded
        walk is not on offer.

        Each edge carries ``resolved``: ``false`` is a DANGLING reference —
        declared, written, and resolving to nothing. Those rows are the list of
        what is broken and are never filtered out.

        ``stop`` says why the walk ended (``complete`` / ``depth_reached`` /
        ``truncated``) and ``graph_producer`` reports whether the producer is
        even on. A server whose store keeps no edge graph answers **501**, not
        an empty list — "nothing points at this" is a claim only a store that
        records edges may make.

        ``as_of`` (ISO-8601) returns **the graph AS IT WAS at that transaction
        instant** — the fourth coordinate of the same question, and the same
        axis :meth:`get_kind_instance` carries for one instance. The response
        echoes ``as_of`` and lists ``as_of_truncated``: nodes the walk reached
        and could not read that far back, because their history was pruned. Not
        an error — the part of the past this store cannot know, named instead of
        dropped.

        Under ``as_of`` the server answers **501** when it retains no version
        history and **410** when this instance's history was pruned past the
        instant. Neither degrades into today's graph, and a **404** ("it did not
        exist yet then") is an ANSWER rather than either of those."""
        return self._get(
            f"/v1/kinds/{kind}/instances/{name}/refs",
            tenant=tenant, api_version=api_version,
            direction=direction, depth=depth, as_of=as_of,
        )

    def write_kind_instance(
        self, kind: str, metadata: dict[str, Any], spec: dict[str, Any], *,
        source_sha256: str | None = None,
        api_version: str | None = None, tenant: str | None = None,
        merge: bool = True, if_match: str | None = None,
    ) -> JsonObject:
        """Write one instance of ``kind`` — the generic door, kubernetes-shaped:
        the endpoint names the Kind (applying a CRD creates the endpoint that
        serves it; ``kind`` is inferred from where the client submits, never
        re-stated ambiguously), the body is exactly ``{metadata, spec}`` plus
        an optional provenance citation.

        ``metadata["name"]`` is REQUIRED — a blank/absent one is 400. The
        server validates ``spec`` against the Kind's REGISTERED JSON Schema
        before writing (like the Kubernetes API server since 1.25), and names
        the offending field on refusal (400 — unknown property, or a missing
        required one). A BOOTSTRAP Kind (Genome / LayerPolicy /
        KindDefinition) is refused (403) — the generic write's own gate,
        untouched here. An authored-but-unapproved Kind and a Kind nobody
        ever authored answer the SAME 404 naming it: there is no third,
        more-specific answer visible from this door. A stale ``if_match`` is
        409.

        ``source_sha256`` (optional) cites the ``SourceArtifact`` (by content
        address) this instance was extracted from; the server closes the
        ``derived_refs`` provenance edge, preserving every OTHER instance
        already recorded there and updating THIS one's own entry in place on
        a re-write rather than duplicating it. A citation naming no
        registered artifact under ``tenant`` is 400.

        There is deliberately no ``scope`` parameter and no ``claims``
        parameter here — identity and scope are never caller input on this
        route (see the server route's docstring)."""
        return self._write(
            "POST", f"/v1/kinds/{kind}/instances",
            {"metadata": metadata, "spec": spec, "source_sha256": source_sha256},
            tenant=tenant, api_version=api_version, merge=merge,
            if_match=if_match,
        )

    # -- definitions (bundle entries — fork a bundle-file, plane B) ----------

    def list_bundle_entries(
        self, kind: str, name: str, *,
        scope: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """List a bundle instance's entry files (base ∪ tenant overlay), each
        flagged ``overridden`` — whether THIS tenant forked that specific file."""
        return self._get(
            f"/v1/definitions/{kind}/{name}/entries", scope=scope, tenant=tenant
        )

    def read_bundle_entry(
        self, kind: str, name: str, entry: str, *,
        scope: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """Read one bundle entry's effective content (tenant overlay wins over
        base), plus whether THIS tenant forked it and whether it's binary."""
        return self._get(
            f"/v1/definitions/{kind}/{name}/entries/{entry}",
            scope=scope, tenant=tenant,
        )

    def write_bundle_entry(
        self, kind: str, name: str, entry: str, content: str, *,
        scope: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """Fork one bundle entry into the tenant layer. A LOCKED Kind is
        vetoed by the kernel's LayerPolicy check and surfaces as a 403
        :class:`DnaApiError`."""
        return self._write(
            "PUT", f"/v1/definitions/{kind}/{name}/entries/{entry}",
            {"content": content}, scope=scope, tenant=tenant,
        )

    def revert_bundle_entry(
        self, kind: str, name: str, entry: str, *,
        scope: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """Revert a tenant's fork of one bundle entry — reads fall back to the
        inherited base file."""
        return self.request(
            "DELETE", f"/v1/definitions/{kind}/{name}/entries/{entry}",
            params={"scope": scope, "tenant": tenant},
        )

    # -- reconcile (2-way diff of a tenant's forks vs base-NOW, plane B2) ----

    def reconcile_forks(
        self, kind: str, name: str, *,
        scope: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """For each of the tenant's forked bundle-entry files, diff the
        fork's content against the base's CURRENT content — READ-only. A
        file the tenant forked that the base has since changed underneath
        it comes back ``"diverged"`` even if the fork itself is untouched;
        a tenant-added file (no base at all) is always ``"diverged"`` with
        ``base: None``. Resolve with the EXISTING bundle-entry primitives:
        keep = no-op, take-base = :meth:`revert_bundle_entry`, edit =
        :meth:`write_bundle_entry`."""
        return self._get(
            f"/v1/definitions/{kind}/{name}/reconcile", scope=scope, tenant=tenant
        )

    # -- memory (reads) ------------------------------------------------------

    def list_memories(
        self, *, scope: str | None = None, tenant: str | None = None
    ) -> JsonObject:
        """List the tenant's memory — base + the tenant's OWN overlay."""
        return self._get("/v1/memories", scope=scope, tenant=tenant)

    def list_personal_memories(self, *, scope: str | None = None) -> JsonObject:
        """List the CALLER'S OWN personal memories — the read face of
        :meth:`import_memories`.

        Same identity contract as the import: the ``personal:<oid>`` partition
        is resolved server-side from the token (INV-PERSONAL), so there is
        deliberately **no tenant/identity parameter** and the client-level
        default ``tenant`` is not merged. A shared bearer (``--auth token``) is
        not an identity — 403 always; a token with no identity claim is 403
        too. Each item carries a per-item ``personal`` flag: the caller's own
        memories say ``True``, the shared base memories riding along say
        ``False``."""
        return self.request(
            "GET", "/v1/memories/personal", params={"scope": scope},
        )

    def search_memories(
        self, q: str, *, k: int = 5, scope: str | None = None,
        tenant: str | None = None,
    ) -> JsonObject:
        """Recall the tenant's memory for ``q`` (hybrid/bi-temporal or lexical)."""
        return self._get("/v1/memories/search", q=q, k=k, scope=scope, tenant=tenant)

    # -- memory (writes) -----------------------------------------------------

    def remember_memory(
        self, summary: str, *, area: str = "general", tags: list[str] | None = None,
        affect: str = "triumph", owner: str = "portal", scope: str | None = None,
        tenant: str | None = None,
    ) -> JsonObject:
        """Persist ONE memory (an ``Engram``) into the tenant's OWN overlay.

        Writes only to the caller's overlay — never the base scope, never another
        tenant. 400 on a blank ``summary``. The deterministic name it returns is
        the id :meth:`delete_memory` targets to undo the write."""
        return self._write(
            "POST", "/v1/memories",
            {"summary": summary, "area": area, "tags": tags,
             "affect": affect, "owner": owner},
            scope=scope, tenant=tenant,
        )

    def import_memories(
        self, bundle: Any, *, as_mode: str = "both", dedupe: str = "id",
        scope: str | None = None,
    ) -> JsonObject:
        """Import a MIF bundle into the CALLER'S OWN personal memory.

        ``bundle`` is the MIF payload in any shape the export side emits: a
        JSON-LD ``{"@graph": [...]}``, a bare list of Memory Units, or one
        Memory Unit. ``as_mode`` (``both``/``passthrough``/``native``) picks
        verbatim storage, the recallable ``Engram`` projection, or both;
        ``dedupe`` (``id``/``content-hash``/``off``) makes a re-import
        idempotent.

        There is deliberately **no tenant/identity parameter**: the write always
        lands in the caller's own ``personal:<oid>`` partition, with the identity
        derived server-side from the token (INV-PERSONAL). A malformed bundle is
        a 400 with nothing written; an oversized one a 413; a token carrying no
        identity a 403. The returned counts always reconcile with ``received``,
        so a partial import is never silent."""
        return self._write(
            "POST", "/v1/memories/import",
            {"bundle": bundle, "as": as_mode, "dedupe": dedupe},
            scope=scope,
        )

    def delete_memory(
        self, name: str, *, scope: str | None = None, tenant: str | None = None
    ) -> JsonObject:
        """Delete ONE memory from the tenant's OWN overlay.

        Refuses anything outside that overlay: a base-scope memory, or another
        tenant's, is a 404 — the delete cannot reach across the isolation."""
        return self.request(
            "DELETE", f"/v1/memories/{name}", params={"scope": scope, "tenant": tenant},
        )

    def forget_memory(
        self,
        name: str,
        *,
        superseded_by: str | None = None,
        scope: str | None = None,
        tenant: str | None = None,
    ) -> JsonObject:
        """RETIRE a memory — the lane ``delete_memory`` refuses and names.

        A memory is never hard-deleted (``record.invalidate-only``): this stamps
        ``valid_to`` so it drops out of default recall, and the row stays —
        auditable and point-in-time reconstructable. Idempotent: an already
        retired memory keeps its ORIGINAL ``valid_to``, so a retry finishes an
        interrupted edit instead of rewriting when it stopped being true.

        ``superseded_by`` records WHICH memory replaces this one, and is what
        turns an edit into one intent instead of two unrelated writes. The
        portal edits by writing the new memory first and retiring the old one
        with this pointer — write-first on purpose, so the bad outcome is TWO
        memories, never zero.
        """
        return self.request(
            "POST",
            f"/v1/memories/{name}/forget",
            params={"scope": scope, "tenant": tenant},
            json={"superseded_by": superseded_by} if superseded_by else None,
        )

    # -- intel (reads) -------------------------------------------------------

    def list_sources(
        self, *, scope: str | None = None, tenant: str | None = None
    ) -> JsonObject:
        """List the tenant's watched IntelSource docs (the Direction stage)."""
        return self._get("/v1/sources", scope=scope, tenant=tenant)

    def list_insights(
        self, *, scope: str | None = None, tenant: str | None = None,
        state: str | None = None, source: str | None = None,
        source_ref: str | None = None,
    ) -> JsonObject:
        """List the tenant's IntelInsight docs (ranked), filterable by state/source."""
        return self._get(
            "/v1/insights", scope=scope, tenant=tenant, state=state,
            source=source, source_ref=source_ref,
        )

    def insight_metrics(
        self, *, scope: str | None = None, tenant: str | None = None,
        source_ref: str | None = None,
    ) -> JsonObject:
        """The feedback KPIs (precision + noise rate) over the insight stream."""
        return self._get(
            "/v1/insights/metrics", scope=scope, tenant=tenant, source_ref=source_ref
        )

    # -- intel (write) -------------------------------------------------------

    def set_insight_state(
        self, name: str, state: str, *, scope: str | None = None,
        tenant: str | None = None,
    ) -> JsonObject:
        """Set an insight's feedback state — the reader's disposition.

        ``state`` is one of ``new|actioned|dismissed|snoozed``; anything else is a
        400. An insight unknown to this (scope, tenant) is a 404."""
        return self._write(
            "PATCH", f"/v1/insights/{name}/state", {"state": state},
            scope=scope, tenant=tenant,
        )

    # -- portfolio (reads) ---------------------------------------------------

    def list_orgs(
        self, *, scope: str | None = None, tenant: str | None = None
    ) -> JsonObject:
        """List the tenant's Organization docs."""
        return self._get("/v1/orgs", scope=scope, tenant=tenant)

    def list_projects(
        self, *, scope: str | None = None, tenant: str | None = None
    ) -> JsonObject:
        """List the tenant's Project docs."""
        return self._get("/v1/projects", scope=scope, tenant=tenant)

    def get_project(
        self, slug: str, *, scope: str | None = None, tenant: str | None = None
    ) -> JsonObject:
        """One project's detail + its RESOLVED repos. 404 → :class:`DnaApiError`."""
        return self._get(f"/v1/projects/{slug}", scope=scope, tenant=tenant)

    def list_project_members(
        self, slug: str, *, scope: str | None = None, tenant: str | None = None,
        viewer: str | None = None,
    ) -> JsonObject:
        """List a project's members with their RESOLVED role, tenant-scoped."""
        return self._get(
            f"/v1/projects/{slug}/members", scope=scope, tenant=tenant, viewer=viewer
        )

    def list_repos(
        self, *, scope: str | None = None, tenant: str | None = None
    ) -> JsonObject:
        """List the tenant's Repo docs (code repositories the portfolio references)."""
        return self._get("/v1/repos", scope=scope, tenant=tenant)

    # -- portfolio (writes) --------------------------------------------------

    def register_artifact(
        self, workspace_id: str, sha256: str, uri: str, *,
        filename: str | None = None, mime: str | None = None,
        size_bytes: int | None = None,
        claims: dict[str, Any] | None = None,
    ) -> JsonObject:
        """Record the ORIGINAL a projection will be derived from.

        SECURITY: the caller must hold an ACTIVE ``WorkspaceMembership`` in
        ``workspace_id`` — without one it is **403**. The write scope is DERIVED
        from the workspace and the route refuses to accept one.

        ``uri`` names WHERE the bytes live and is stored verbatim. It must not
        be a signed URL: an instance carrying one would BE the access to its own
        original, and would hand that access to anyone the instance reaches.

        IDEMPOTENT by content address — the same ``sha256`` updates the same
        artifact, and any ``derived_refs`` already extracted from it survive the
        call. A retried upload leaves no second row and erases no projection.

        ``claims`` is the caller's identity for a trusted server-side call under
        ``--auth none``/``--auth token``. Under ``--auth config`` the VERIFIED
        token claims always win and this argument is ignored."""
        return self._write(
            "POST", "/v1/artifacts",
            {"workspace_id": workspace_id, "sha256": sha256, "uri": uri,
             "filename": filename, "mime": mime, "size_bytes": size_bytes,
             "claims": claims},
        )

    def create_project(
        self, workspace_id: str, name: str, *, slug: str | None = None,
        claims: dict[str, Any] | None = None,
    ) -> JsonObject:
        """Create a Project inside ``workspace_id``.

        SECURITY: the caller must hold an ACTIVE ``WorkspaceMembership`` in that
        workspace — a caller without one is **403**, and a pending invite does not
        count. The write scope and the project's ``board_scope`` are DERIVED from
        the workspace + slug; the route refuses to accept either from the caller.
        400 on a blank ``workspace_id``/``name``.

        ``claims`` is the caller's identity for a trusted server-side call under
        ``--auth none``/``--auth token``. Under ``--auth config`` the VERIFIED
        token claims always win and this argument is ignored."""
        return self._write(
            "POST", "/v1/projects",
            {"workspace_id": workspace_id, "name": name, "slug": slug,
             "claims": claims},
        )

    def set_project_member(
        self, slug: str, user: str, role: str, *, actor: str | None = None,
        scope: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """Invite / set a user's PROJECT-scope role (upserts one Membership doc).

        SECURITY: ``actor`` must be Owner/Admin of the project or its org, and only
        an Owner may grant ``owner`` — **403** otherwise. 404 for an unknown
        project; 422 for an unknown role."""
        return self._write(
            "POST", f"/v1/projects/{slug}/members",
            {"user": user, "role": role, "actor": actor},
            scope=scope, tenant=tenant,
        )

    def remove_project_member(
        self, slug: str, user: str, *, actor: str | None = None,
        scope: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """Remove a user's PROJECT-scope grant.

        SECURITY: ``actor`` must be Owner/Admin, and removing an Owner requires
        Owner — **403** otherwise. Deletes ONLY the project-scope grant; an
        inherited org-scope grant is untouched (the user may still resolve to a
        role afterwards). 404 when the user holds no project grant here."""
        return self.request(
            "DELETE", f"/v1/projects/{slug}/members/{user}",
            params={"actor": actor, "scope": scope, "tenant": tenant},
        )

    def provision_tenant_owner(
        self, tid: str, user: str, *, scope: str | None = None
    ) -> JsonObject:
        """First-owner bootstrap: make ``user`` Owner of tenant ``tid`` when it has
        no Owner yet (org- + project-scope grants).

        SECURITY: FIRST-owner only and idempotent — once ANY Owner exists this is a
        no-op, so a later user cannot auto-escalate into an established tenant.
        This is a trusted server-side call (the portal's shared bearer), not a
        user-facing one. 400 on a missing tenant/user."""
        return self._write(
            "POST", f"/v1/tenants/{tid}/provision-owner", {"user": user}, scope=scope,
        )

    # -- board (reads) -------------------------------------------------------

    def get_board(
        self, scope: str, *, tenant: str | None = None, recent: int = 6
    ) -> JsonObject:
        """A compact SDLC summary for a project's ``board_scope``."""
        return self._get("/v1/board", scope=scope, tenant=tenant, recent=recent)

    def get_board_item(
        self, scope: str, name: str, *, tenant: str | None = None,
        kind: str | None = None,
    ) -> JsonObject:
        """One board work-item's FULL doc (the console's item-detail drawer)."""
        return self._get(
            "/v1/board/item", scope=scope, name=name, tenant=tenant, kind=kind
        )

    # -- workspaces (read) ---------------------------------------------------

    def list_workspaces(
        self, *, actor_oid: str | None = None, actor_email: str | None = None,
    ) -> JsonObject:
        """The workspaces the caller holds an ACTIVE membership in.

        Enumerates by membership, never by tenant provenance: a pending invite
        does not appear, and an unknown identity gets an empty list rather than
        somebody else's. This is the data source a workspace switcher builds on."""
        return self._get(
            "/v1/workspaces", actor_oid=actor_oid, actor_email=actor_email,
        )

    def list_workspace_members(
        self, workspace_id: str, *, actor_oid: str | None = None,
        actor_email: str | None = None,
    ) -> JsonObject:
        """List a workspace's members (grants). RBAC: the actor must be Owner/Admin."""
        return self._get(
            f"/v1/workspaces/{workspace_id}/members",
            actor_oid=actor_oid, actor_email=actor_email,
        )

    # -- workspaces (writes) -------------------------------------------------
    # Every route below is identity-scoped: the boundary is resolved from the
    # caller's VERIFIED claims, never from a `tenant` query hint. Under
    # `--auth config` the token's claims WIN over any `claims`/`actor` argument
    # here; those arguments exist for a TRUSTED server-side caller running the API
    # under `--auth none`/`--auth token` (the portal, holding the shared bearer).

    def create_workspace(
        self, name: str, *, slug: str | None = None,
        claims: dict[str, Any] | None = None,
    ) -> JsonObject:
        """Create a workspace and its first OWNER, in one call.

        SECURITY: the ``workspace_id`` is MINTED SERVER-SIDE and cannot be supplied
        — there is deliberately no field for it, so a caller cannot name a
        workspace into existence and race its real owner for it. The caller's
        verified identity becomes the active owner. ``slug`` defaults to a
        slugified ``name`` and is made unique. 400 on a blank name or a missing
        oid/email claim."""
        return self._write(
            "POST", "/v1/workspaces",
            {"name": name, "slug": slug, "claims": claims},
        )

    def create_invite(
        self, workspace_id: str, email: str, *, role: str = "member",
        actor: dict[str, Any] | None = None,
    ) -> JsonObject:
        """Invite an identity (by email) into a workspace — a ``pending``
        ``WorkspaceMembership`` that only :meth:`accept_invites` can activate.

        SECURITY: the actor must be Owner/Admin of the workspace, and only an
        Owner may invite an Owner — **403** otherwise. 422 on an unknown role."""
        return self._write(
            "POST", f"/v1/workspaces/{workspace_id}/invites",
            {"email": email, "role": role, "actor": actor},
        )

    def accept_invites(self, *, claims: dict[str, Any] | None = None) -> JsonObject:
        """Accept EVERY pending invite matching the caller's verified sign-in
        claims — binds the durable ``oid`` and flips ``pending`` → ``active``.

        SECURITY: matches on a VERIFIED email claim only, and refuses to hijack a
        grant already bound to a different ``oid``. Takes no workspace argument by
        design: a caller cannot accept an invite that was not addressed to them."""
        return self._write("POST", "/v1/workspaces/accept", {"claims": claims})

    def provision_workspace_owner(
        self, workspace_id: str, *, claims: dict[str, Any] | None = None
    ) -> JsonObject:
        """Reconcile the verified identity's membership in ``workspace_id`` — the
        portal's every-sign-in idempotent no-op.

        SECURITY: since decision **D5** this CREATES NOTHING. It REQUIRES an
        existing ACTIVE ``WorkspaceMembership`` and merely returns it (back-filling
        a missing Workspace identity doc for an owner). A caller holding no active
        membership here — a stranger included — is **403**. To create a workspace
        use :meth:`create_workspace`, which mints its own id. 400 on a missing
        oid/email claim."""
        return self._write(
            "POST", f"/v1/workspaces/{workspace_id}/provision-owner",
            {"claims": claims},
        )

    def revoke_workspace_member(
        self, workspace_id: str, *, target_email: str | None = None,
        target_oid: str | None = None, actor: dict[str, Any] | None = None,
    ) -> JsonObject:
        """Revoke (remove) a member's ``WorkspaceMembership``.

        SECURITY: the actor must be Owner/Admin — **403** otherwise. The LAST
        remaining owner can NEVER be revoked (**409**, fail-closed), so a workspace
        cannot be orphaned. A target holding no grant here is 404. Name the target
        by ``target_email`` or ``target_oid`` (oid wins when both are given)."""
        return self._write(
            "POST", f"/v1/workspaces/{workspace_id}/members/revoke",
            {"target_email": target_email, "target_oid": target_oid, "actor": actor},
        )

    # -- billing (write) -----------------------------------------------------

    def set_account_plan(
        self, account_id: str, tier_id: str, *, source: str = "stripe",
        stripe_customer_id: str | None = None,
        stripe_subscription_id: str | None = None, status: str | None = None,
    ) -> JsonObject:
        """Upsert the ``AccountPlan`` assigning ``account_id`` → ``tier_id`` — the
        billing→enforcement bridge.

        The subscription belongs to the BILLING ACCOUNT: this ONE call covers
        every workspace whose ``account_id`` matches, so a customer's second
        workspace needs no billing write and is never a second charge.

        SECURITY: this route ASSIGNS a plan and performs no membership check of its
        own; it is a trusted server-side call (the portal's Stripe webhook handler,
        holding the shared bearer) and must never be exposed to an end user.
        Idempotent under Stripe retries. 400 on a missing account_id/tier_id."""
        return self._write(
            "PUT", "/v1/account-plan",
            {"account_id": account_id, "tier_id": tier_id, "source": source,
             "stripe_customer_id": stripe_customer_id,
             "stripe_subscription_id": stripe_subscription_id, "status": status},
        )
