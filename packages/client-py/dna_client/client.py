"""The DNA REST read-API client (sync, ``httpx``-based).

Named methods for the ``/v1/*`` GET read surface; :meth:`DnaClient.request` for
the full surface (incl. writes). Every method returns the API's JSON object
(``dict[str, Any]``) and raises :class:`DnaApiError` on a non-2xx status.
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


class DnaClient:
    """A typed, read-first client for the DNA REST read-API.

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
        query = self._merge_query(path, params)
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

    def _merge_query(
        self, path: str, params: dict[str, Any] | None
    ) -> dict[str, Any]:
        params = dict(params or {})
        # /health and the /v1/workspaces/* boundary routes do not take scope/tenant.
        takes_scope_tenant = path != "/health" and not path.startswith(
            "/v1/workspaces"
        )
        if takes_scope_tenant:
            if self._default_scope is not None and params.get("scope") is None:
                params["scope"] = self._default_scope
            if self._default_tenant is not None and params.get("tenant") is None:
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
        self, name: str, *, scope: str | None = None, tenant: str | None = None
    ) -> JsonObject:
        """Compose one agent's system prompt LIVE (Soul + Guardrails + instruction)."""
        return self._get(f"/v1/agents/{name}/prompt", scope=scope, tenant=tenant)

    def list_tools(
        self, *, scope: str | None = None, tenant: str | None = None
    ) -> JsonObject:
        """List a scope's Tool Kind surfaces (name + description), tenant-aware."""
        return self._get("/v1/tools", scope=scope, tenant=tenant)

    # -- memory (reads) ------------------------------------------------------

    def list_memories(
        self, *, scope: str | None = None, tenant: str | None = None
    ) -> JsonObject:
        """List the tenant's memory — base + the tenant's OWN overlay."""
        return self._get("/v1/memories", scope=scope, tenant=tenant)

    def search_memories(
        self, q: str, *, k: int = 5, scope: str | None = None,
        tenant: str | None = None,
    ) -> JsonObject:
        """Recall the tenant's memory for ``q`` (hybrid/bi-temporal or lexical)."""
        return self._get("/v1/memories/search", q=q, k=k, scope=scope, tenant=tenant)

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

    def list_workspace_members(
        self, workspace_id: str, *, actor_oid: str | None = None,
        actor_email: str | None = None,
    ) -> JsonObject:
        """List a workspace's members (grants). RBAC: the actor must be Owner/Admin."""
        return self._get(
            f"/v1/workspaces/{workspace_id}/members",
            actor_oid=actor_oid, actor_email=actor_email,
        )
