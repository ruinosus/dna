"""``dna_cli._rest_api`` — the DNA **REST read-API face** (server).

The THIRD face of DNA serving runtimes, and the correct HTTP boundary for a WEB
app (the DNA Cloud portal). It is a sibling of the MCP server, NOT a replacement:

    MCP  — a stateful, long-lived session protocol for AI clients (Claude
           Code/Desktop, Cursor, Copilot). A client opens ONE session and keeps
           it. Opening an MCP session per web page render is the wrong pattern —
           fragile, off-label.
    REST — a normal request/response HTTP API. The portal is a Next.js web app;
           each page render is a stateless GET. This face is exactly that: a thin
           HTTP surface a browser/BFF calls with a ``tenant`` query param today,
           an OAuth bearer later.

**One core, three faces.** This module does ZERO business logic of its own — it
imports and calls the SAME ``*_impl`` cores the MCP server already uses
(``dna_cli._mcp_server``: ``list_agents_impl`` / ``compose_prompt_impl`` /
``list_tools_impl`` / ``recall_impl``, booted by the SAME ``boot_live`` /
``LiveDna``). The memory LIST + DELETE endpoints (which have no MCP twin) query
the memory Kind (``LessonLearned``) directly through the kernel, tenant-aware —
mirroring exactly how ``recall`` and the kernel query/delete paths already work.

**Tenant isolation is load-bearing.** Every endpoint scopes to the ``tenant``
query param via the kernel's tenant-aware read/write paths — the SAME base +
own-overlay resolution recall uses, and the SAME overlay-only delete the local
docs facade uses. A tenant never reads or deletes another tenant's memory, and a
tenant can never delete the shared base (the filesystem source routes a
tenant-bound delete to that tenant's overlay layout, raising ``not_found`` for a
base doc).

``fastapi`` is imported **lazily** (optional ``dna-cli[api]`` extra) inside
:func:`build_app`, so the base install never carries it — ``import dna_cli`` (and
even importing this module) stays FastAPI-free.
"""
from __future__ import annotations

import asyncio
import os
import secrets
from typing import Any

# NOTE: no top-level ``import fastapi`` — it is optional. ``build_app`` imports it
# lazily so the base CLI/SDK install never requires it (guarded by a test).


# ── memory read/delete cores (no MCP twin — query the kernel directly) ──────
#
# The definitions + search endpoints reuse the MCP server's impls verbatim (see
# build_app). These two are the memory LIST + DELETE the portal needs and the
# MCP surface does not have; they go straight to the memory Kind through the
# kernel, tenant-aware, mirroring how recall/the local docs facade already read
# and delete.

_MEMORY_KIND = "LessonLearned"


async def list_memories_impl(
    live: Any, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """List the tenant's memory (``LessonLearned``) — base + the tenant's OWN
    overlay, per the #83 isolation. Tenant-aware ``kernel.query`` returns exactly
    that set (never another tenant's overlay). Projects each to the portal card
    surface (name/summary/area/tags/created_at)."""
    sc = scope or live.base_scope
    memories: list[dict[str, Any]] = []
    async for raw in live.kernel.query(sc, _MEMORY_KIND, tenant=tenant):
        if not isinstance(raw, dict):
            continue
        meta = raw.get("metadata") or {}
        spec = raw.get("spec") or {}
        name = (meta.get("name") if hasattr(meta, "get") else None) or raw.get("name")
        # Bi-temporal courtesy: a forgotten (valid_to in the past) memory is a
        # tombstone — hide it from the roster the same way recall drops it.
        if spec.get("valid_to"):
            continue
        memories.append(
            {
                "name": name,
                "summary": spec.get("summary"),
                "area": spec.get("area"),
                "tags": list(spec.get("tags") or []),
                "created_at": spec.get("created_at"),
            }
        )
    memories.sort(key=lambda m: m["name"] or "")
    return {"scope": sc, "tenant": tenant, "memories": memories}


class MemoryNotFound(Exception):
    """The requested memory is not in the tenant's OWN overlay (so this tenant
    cannot delete it) — mapped to HTTP 404 by the route."""


async def delete_memory_impl(
    live: Any, name: str, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """Delete ONE memory from the tenant's OWN overlay — never base, never
    another tenant. This is the single write on the read-API, so it is guarded:

    * ``tenant`` set → the kernel's tenant-bound delete routes to that tenant's
      overlay layout. A doc that lives only in base (or in another tenant's
      overlay) is not present there, so the source raises ``not_found`` and this
      surfaces a 404 — the base/other-tenant memory is untouched.
    * ``tenant`` unset (local dev / ``--auth none``) → the caller's own (base)
      store, symmetric with how an unauthenticated request reads it.
    """
    sc = scope or live.base_scope
    kernel = live.kernel.with_tenant(tenant) if tenant else live.kernel
    try:
        await kernel.delete_document(
            sc, _MEMORY_KIND, name, invalidate_mode="doc"
        )
    except ValueError as exc:  # filesystem source raises ValueError("not_found")
        if "not_found" in str(exc).lower():
            raise MemoryNotFound(
                f"memory {name!r} not found in tenant {tenant!r}'s own memory "
                f"(scope {sc!r}) — nothing to delete"
            ) from None
        raise
    return {"deleted": name, "scope": sc, "tenant": tenant}


# ── FastAPI wiring ─────────────────────────────────────────────────────────


def _resolve_cors_origins(cors_origins: list[str] | None) -> list[str]:
    """Resolve the allowed browser origins for the portal: explicit arg wins,
    else ``DNA_API_CORS_ORIGINS`` (comma-separated), else a dev default."""
    if cors_origins:
        return list(cors_origins)
    env = os.environ.get("DNA_API_CORS_ORIGINS")
    if env:
        return [o.strip() for o in env.split(",") if o.strip()]
    # Dev default: the portal's local Next.js origin.
    return ["http://localhost:3000"]


def build_app(
    *,
    scope: str | None = None,
    base_dir: str | None = None,
    auth: str = "none",
    token: str | None = None,
    cors_origins: list[str] | None = None,
) -> Any:
    """Build the DNA REST read-API (a ``FastAPI`` app) over the live kernel.

    ``scope`` fixes the default scope (else the source's sole/first scope);
    ``base_dir`` overrides the source directory (tests / embedding — same seam as
    the MCP server's ``build_server``). The live kernel handle is booted LAZILY on
    the first request, on the running event loop, via the SAME ``boot_live`` the
    MCP server uses — so the source pool binds to the serving loop.

    ``auth``:
      * ``"none"`` — local dev, no bearer required.
      * ``"token"`` — every route (except ``/health``) requires
        ``Authorization: Bearer <token>``; the expected token is ``token`` (arg)
        or ``DNA_API_TOKEN`` (env). A shared token for the MVP.

    Raises a clean ``RuntimeError`` if the optional ``fastapi`` dependency is absent.
    """
    try:
        from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query
        from fastapi.middleware.cors import CORSMiddleware
    except ModuleNotFoundError as exc:  # pragma: no cover — exercised via CLI
        raise RuntimeError(
            "the REST read-API needs the optional 'fastapi' dependency — install "
            "it with:  pip install 'dna-cli[api]'"
        ) from exc

    from dna_cli._mcp_server import (
        boot_live,
        compose_prompt_impl,
        list_agents_impl,
        list_tools_impl,
        recall_impl,
    )
    # The intel face delegates to the CORE engine (adr-faces-reorg: logic in the
    # core, faces thin). These handlers only translate transport + call in.
    from dna.extensions.intel import engine as intel_engine

    app = FastAPI(
        title="DNA REST read-API",
        version="1",
        description=(
            "The correct HTTP boundary for a WEB app (the DNA Cloud portal) — a "
            "thin request/response REST face over the SAME DNA kernel + impls the "
            "MCP server uses. Read-focused, tenant-aware."
        ),
    )

    origins = _resolve_cors_origins(cors_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # -- auth (shared bearer token for the MVP) ------------------------------
    # TODO(hosted): OAuth 2.1 / per-tenant bearer — swap this shared-token gate
    # for a verified-token → tenant bridge (the SAME tenancy model as the MCP
    # server's dna_cli._mcp_auth: the token's tenant claim becomes the effective
    # tenant, and a cross-tenant request is denied), so `tenant` stops being a
    # query param a caller can forge and becomes bound to the verified token.
    def _auth_dep(authorization: str | None = Header(default=None)) -> None:
        if auth != "token":
            return
        expected = token or os.environ.get("DNA_API_TOKEN")
        if not expected:
            raise HTTPException(
                status_code=500,
                detail="token auth is enabled but no token is configured "
                "(set DNA_API_TOKEN or pass --token)",
            )
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")
        provided = authorization[len("Bearer "):].strip()
        if not secrets.compare_digest(provided, expected):
            raise HTTPException(status_code=401, detail="invalid bearer token")

    # -- lazy live kernel (booted once, on the serving loop) -----------------
    _state: dict[str, Any] = {"live": None}
    _boot_lock = asyncio.Lock()

    async def _live() -> Any:
        if _state["live"] is None:
            async with _boot_lock:
                if _state["live"] is None:
                    _state["live"] = await boot_live(scope, base_dir)
        return _state["live"]

    guarded = [Depends(_auth_dep)]

    # -- health (unguarded) --------------------------------------------------

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True}

    # -- definitions (reuse the MCP impls verbatim — zero duplication) -------

    @app.get("/v1/agents", dependencies=guarded)
    async def agents(
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """List a scope's prompt-target agents, tenant-aware."""
        return await list_agents_impl(await _live(), scope, tenant)

    @app.get("/v1/agents/{name}/prompt", dependencies=guarded)
    async def agent_prompt(
        name: str,
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Compose one agent's system prompt LIVE (Soul + Guardrails +
        instruction), tenant-aware — the per-tenant overlay a static emit
        artifact cannot express."""
        try:
            return await compose_prompt_impl(await _live(), name, scope, tenant)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    @app.get("/v1/tools", dependencies=guarded)
    async def tools(
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """List a scope's Tool Kind surfaces (name + description), tenant-aware."""
        return await list_tools_impl(await _live(), scope, tenant)

    # -- memory (list + search + the one guarded write: delete) --------------

    @app.get("/v1/memories", dependencies=guarded)
    async def memories(
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """List the tenant's memory — base + the tenant's OWN overlay (per the #83
        isolation), never another tenant's."""
        return await list_memories_impl(await _live(), scope, tenant)

    @app.get("/v1/memories/search", dependencies=guarded)
    async def memories_search(
        q: str = Query(...),
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
        k: int = Query(default=5, ge=1, le=50),
    ) -> dict[str, Any]:
        """Recall the tenant's memory for ``q`` (hybrid/bi-temporal when the
        search extra is present, honest lexical otherwise), tenant-scoped."""
        return await recall_impl(await _live(), q, scope, k, tenant)

    @app.delete("/v1/memories/{name}", dependencies=guarded)
    async def delete_memory(
        name: str,
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Delete ONE memory from the tenant's OWN overlay — the portal's
        ownership/delete. Never base, never another tenant (a 404 otherwise)."""
        try:
            return await delete_memory_impl(await _live(), name, scope, tenant)
        except MemoryNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    # -- intel (sources + insights + the feedback state transition) ----------
    # Thin delegates to dna.extensions.intel.engine — the portal's intelligence
    # surface. ZERO business logic here (adr-faces-reorg).

    @app.get("/v1/sources", dependencies=guarded)
    async def sources(
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """List the tenant's watched IntelSource docs (the Direction stage)."""
        live = await _live()
        sc = scope or live.base_scope
        items = await intel_engine.list_sources(live.kernel, scope=sc, tenant=tenant)
        return {"scope": sc, "tenant": tenant, "sources": items}

    @app.get("/v1/insights", dependencies=guarded)
    async def insights(
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
        state: str | None = Query(default=None),
        source_ref: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """List the tenant's IntelInsight docs (ranked), optionally filtered by
        ``state`` and/or originating ``source_ref``."""
        live = await _live()
        sc = scope or live.base_scope
        items = await intel_engine.list_insights(
            live.kernel, scope=sc, tenant=tenant, state=state, source_ref=source_ref,
        )
        return {"scope": sc, "tenant": tenant, "insights": items}

    @app.patch("/v1/insights/{name}/state", dependencies=guarded)
    async def set_insight_state(
        name: str,
        state: str = Body(..., embed=True),
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Set an insight's feedback state (new|actioned|dismissed|snoozed) —
        the reader's disposition. Delegates the read-modify-write to the core."""
        live = await _live()
        sc = scope or live.base_scope
        try:
            return await intel_engine.set_insight_state(
                live.kernel, name, state, scope=sc, tenant=tenant,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except intel_engine.InsightNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    return app
