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
        traits: list[str] | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """Author a Kind for the calling workspace — a ``KindDefinition``
        document written WITHOUT an approval marker, under the workspace's own
        assigned apiVersion namespace.

        What comes back is INERT: ``approved`` is always ``false``, and an
        unapproved Kind never enters the registry, so it neither validates
        documents nor routes their storage. Approval is a separate act with its
        own verified actor (:meth:`approve_kind`) — this call cannot perform it,
        and an ``approved_by`` supplied here would be ignored (there is no
        parameter for it on purpose). The document records ``proposed_by``: the
        server-verified identity of THIS call, stamped here because a proposer
        cannot be back-filled onto a document that never recorded one.

        ``kind`` must be a CamelCase identifier — a CAPITAL letter followed by
        up to 63 letters or digits, nothing else. It is the one value that
        reaches a path, and the initial capital is required so ``Contrato`` and
        ``contrato`` cannot collide on a case-insensitive filesystem.

        400 for a missing tenant, or a ``kind`` that is not such an identifier;
        403 when the workspace does not own the target namespace; 503 when the
        store's namespace-registry scope has not been provisioned."""
        return self._write(
            "POST", "/v1/kinds",
            {"kind": kind, "schema": schema, "traits": traits},
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
        would reach nothing. The document's ``proposed_by`` is preserved, so the
        response names both acts. The two MAY be the same identity — a solo
        author approving their own proposal is two credentials, and the audit
        reports the coincidence rather than refusing it.

        404 when no such Kind was authored in this scope (approval acts on an
        existing document and creates none); 400 for a missing tenant, a
        malformed ``kind``, or a Kind declared under two namespaces at once;
        403 when the namespace gate refuses the write; 409 when the Kind was
        edited between the read and this call (re-read, then approve again).

        It is also the UNDO of :meth:`revoke_kind`: approving again clears the
        revocation, and every existing document is valid once more with nothing
        to migrate."""
        return self._write("POST", f"/v1/kinds/{kind}/approve", {}, tenant=tenant)

    def revoke_kind(
        self, kind: str, *, tenant: str | None = None,
    ) -> JsonObject:
        """Revoke an authored Kind — the act that WITHDRAWS its effect.

        Deliberately NOT the inverse of :meth:`approve_kind`. Un-approving would
        return the Kind to *never approved*, and a Kind that never registered is
        the PERMISSIVE state — its documents are accepted with no validation at
        all — so clearing the approval would switch the gate off rather than
        close it. Revoked is a THIRD state::

            state            existing documents   new documents
            ---------------  -------------------  --------------------------
            never approved   —                    accepted WITHOUT validation
            approved         valid, routed        validated against the schema
            revoked          INVALID              REFUSED

        Nothing is deleted. Existing documents stay readable and come back
        MARKED (``status.valid`` is ``false``), and in a listing they appear
        marked rather than vanishing — so this can never be used to hide data
        without deleting it. New documents of the Kind are refused outright,
        conforming ones included: what was withdrawn is the Kind, not a schema.

        Reversible in one call — :meth:`approve_kind` clears the revocation.
        ``approved_by`` survives here, because revoking is a third act and not
        an erasure of the second.

        The revoker is the caller's server-VERIFIED identity; there is
        deliberately no parameter for it.

        404 when no such Kind was authored in this scope, and equally when it
        belongs to another workspace; 400 for a missing tenant or a malformed
        ``kind``; 409 when the document moved since it was read; 403 when the
        namespace gate refuses the write."""
        return self._write("POST", f"/v1/kinds/{kind}/revoke", {}, tenant=tenant)

    def list_authored_kinds(
        self, *, scope: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """List the scope's authored Kinds with their approval state — the
        audit view. Reads DOCUMENTS, not the registry: an unapproved Kind is
        precisely the one the registry does not have.

        Each row carries BOTH actors (``proposed_by``/``proposed_at`` and
        ``approved_by``/``approved_at``): a reviewer deciding whether to confer
        effect needs to see who asked for it without leaving the list."""
        return self._get("/v1/kinds", scope=scope, tenant=tenant)

    def get_authored_kind(
        self, kind: str, *, scope: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """Read ONE authored Kind in full — the listing's row PLUS the
        ``schema`` and the ``traits``.

        The roster (:meth:`list_authored_kinds`) deliberately omits the schema,
        which left a reviewer unable to see what they would be conferring effect
        ON. Registration is what gives a Kind schema validation and storage
        routing, so "should this take effect?" is a question about the schema;
        this is the call that answers it.

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

    # -- definitions (bundle entries — fork a bundle-file, plane B) ----------

    def list_bundle_entries(
        self, kind: str, name: str, *,
        scope: str | None = None, tenant: str | None = None,
    ) -> JsonObject:
        """List a bundle document's entry files (base ∪ tenant overlay), each
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
