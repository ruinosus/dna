"""``dna_cli._mcp_server`` — the DNA **MCP runtime face** (server).

The second face of DNA serving runtimes, and the INVERSE of ``dna emit``:

    emit  — build-time, STATIC artifact. Materializes one neutral DNA
            definition into a runtime's native file. By construction it DROPS
            composition *structure*, per-tenant *overlay*, and *no-deploy*
            change (the artifact is frozen at emit time).
    MCP   — runtime, LIVE query. A client asks "compose the ACME concierge
            **now**" and this server composes it live, tenant-aware, zero
            deploy — recovering exactly the axes emit loses.

**Server ÚNICO expõe TUDO.** One thin server surfaces everything DNA stores over
the neutral MCP protocol, so any MCP client (Claude Code/Desktop, Cursor, GitHub
Copilot, agent-framework, Bedrock AgentCore) reaches it:

    definitions  compose_prompt · list_agents · list_tools · get_tool
    SDLC         sdlc_digest · list_stories · get_adr
    memory       recall · remember · consolidate · list_memories · forget
    resources    dna://{scope}/manifest · dna://{scope}/agents

DNA already *consumes* MCP (the ``MCPFederation`` Kind pulls external tools into
a scope); this is the inverse — DNA *exposing itself*.

The tools are THIN adapters over already-tested pure cores — the kernel
composition (``build_prompt``), the emit tool projection (``ToolLibrary``), the
digest aggregator (``dna_cli._digest.build_digest``) and the memory verbs
(``dna.memory``). No new business logic lives here.

Built on **FastMCP** (the standalone ``fastmcp`` framework, 2.x+ — the leading
MCP framework that the official MCP Python SDK's FastMCP 1.0 was derived from).
FastMCP is deliberate: it ships **native transports** (stdio for local clients +
Streamable **HTTP** for remote/web clients) AND **built-in auth** (OAuth 2.1 with
Dynamic Client Registration, an OAuth proxy for providers without DCR like
WorkOS/Auth0, and JWT token verification with scope enforcement). So the MVP is
stdio-only, and Phase 2 (remote + authenticated) becomes *enable + bridge* — flip
the transport and bind FastMCP's token scopes to DNA tenancy — not *build*.

``fastmcp`` is imported **lazily** (optional ``dna-cli[mcp]`` extra), so the base
install never carries it — ``import dna_cli`` stays MCP-free.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

# NOTE: no top-level ``import fastmcp`` — it is optional. ``build_server`` imports
# it lazily so the base CLI/SDK install never requires it.


# ── live DNA handle ───────────────────────────────────────────────────────


@dataclass
class LiveDna:
    """A live handle over the configured DNA source — the kernel plus the
    default scope, bound to the MCP server's event loop. Built ONCE per server
    (lazily, on the first tool call) and shared by every tool/resource."""

    base_scope: str
    kernel: Any
    provider: Any  # sqlite-vec search provider, or None (lexical fallback)

    async def mi(self, scope: str | None = None, tenant: str | None = None) -> Any:
        """Build a (optionally tenant-resolved) ManifestInstance for ``scope``.

        Eager (``lazy=False``) so ``mi.documents`` is fully materialized for
        agent/tool enumeration. ``tenant`` promotes into the layer context, so
        ``build_prompt`` composes the per-tenant overlay — the axis emit drops.
        """
        layers = {"tenant": tenant} if tenant else None
        return await self.kernel.instance_async(
            scope or self.base_scope, layers, lazy=False
        )


async def boot_live(scope: str | None = None, base_dir: str | None = None) -> LiveDna:
    """Boot the kernel against the configured source and register the search
    provider (semantic recall when the ``search-sqlite`` extra is present;
    honest lexical fallback otherwise). Reuses the CLI's own boot path so the
    server sees EXACTLY the DNA the ``dna`` CLI sees."""
    if base_dir:
        # Programmatic override (tests / embedding). The CLI serve path relies
        # purely on DNA_SOURCE_URL / DNA_BASE_DIR from the environment.
        os.environ["DNA_BASE_DIR"] = base_dir
    from dna_cli._ctx import _build_holder_async
    from dna_cli.recall_cmd import _register_provider

    holder = await _build_holder_async(scope)
    provider = _register_provider(holder)  # holder exposes .kernel — enough
    return LiveDna(base_scope=holder.scope, kernel=holder.kernel, provider=provider)


# ── pure impls (kernel-driven; testable without FastMCP) ───────────────────


async def compose_prompt_impl(
    live: LiveDna, agent: str, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """Compose ``agent``'s system prompt LIVE (Soul + Guardrails + instruction),
    tenant-aware. This is the killer surface: with ``tenant`` set it returns the
    per-tenant overlay — the composition emit cannot express in a flat file."""
    mi = await live.mi(scope, tenant)
    doc = mi.find_agent(agent)
    if doc is None:
        raise ValueError(f"agent {agent!r} not found in scope {mi.scope!r}")
    prompt = await mi.build_prompt_async(agent)
    spec = getattr(doc, "spec", None) or {}
    return {
        "scope": mi.scope,
        "agent": agent,
        "tenant": tenant,
        "model": spec.get("model") if hasattr(spec, "get") else None,
        "prompt": prompt,
    }


def _prompt_target_kinds(mi: Any) -> set[str]:
    kinds: set[str] = set()
    for kp in getattr(mi, "_kinds", {}).values():
        if getattr(kp, "is_prompt_target", False) and getattr(kp, "kind", None):
            kinds.add(kp.kind)
    return kinds


async def list_agents_impl(
    live: LiveDna, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """List the prompt-target agents (Agent/UtilityAgent/…) in ``scope``,
    tenant-aware when ``tenant`` is set (the auth bridge injects it)."""
    mi = await live.mi(scope, tenant)
    targets = _prompt_target_kinds(mi)
    agents: list[dict[str, Any]] = []
    for d in mi.documents:
        if d.kind not in targets:
            continue
        meta = getattr(d, "metadata", None) or {}
        agents.append(
            {
                "name": d.name,
                "kind": d.kind,
                "description": (meta.get("description") if hasattr(meta, "get") else "") or "",
            }
        )
    agents.sort(key=lambda a: a["name"])
    return {"scope": mi.scope, "agents": agents}


def _tool_surface(row: dict[str, Any]) -> dict[str, Any]:
    """Project a raw Tool doc (kernel-query row) to its agent-facing surface —
    the SAME projection ``dna.tools.ToolSurface`` performs (description =
    ``metadata.description``, parameters = ``spec.input_schema``). Read off the
    async-query row so no sync kernel roundtrip fires inside the event loop
    (Tool is a record-plane Kind — it is NOT in ``mi.documents``)."""
    meta = row.get("metadata") or {}
    spec = row.get("spec") or {}
    return {
        "name": meta.get("name") or row.get("name"),
        "description": (meta.get("description") or ""),
        "parameters": dict(spec.get("input_schema") or {}),
    }


async def _tool_rows(
    live: LiveDna, scope: str, tenant: str | None = None
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    async for row in live.kernel.query(scope, "Tool", tenant=tenant):
        if isinstance(row, dict):
            rows.append(row)
    return rows


async def list_tools_impl(
    live: LiveDna, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """List the Tool Kind surfaces declared in ``scope`` (name + description)."""
    mi = await live.mi(scope, tenant)
    tools = [
        {"name": s["name"], "description": s["description"]}
        for s in (_tool_surface(r) for r in await _tool_rows(live, mi.scope, tenant))
    ]
    tools.sort(key=lambda t: t["name"] or "")
    return {"scope": mi.scope, "tools": tools}


async def get_tool_impl(
    live: LiveDna, name: str, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """The full agent-facing surface of one Tool: description + input schema."""
    mi = await live.mi(scope, tenant)
    rows = await _tool_rows(live, mi.scope, tenant)
    surface = next((s for s in map(_tool_surface, rows) if s["name"] == name), None)
    if surface is None:
        available = sorted(filter(None, (s["name"] for s in map(_tool_surface, rows))))
        raise ValueError(f"tool {name!r} not found in scope {mi.scope!r}; available: {available}")
    return {"scope": mi.scope, **surface}


# ── SDLC (the self-describing board) ───────────────────────────────────────


async def _collect(
    live: LiveDna, scope: str, kind: str, tenant: str | None = None
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    async for row in live.kernel.query(scope, kind, tenant=tenant):
        meta = row.get("metadata") if isinstance(row, dict) else None
        name = (meta or {}).get("name") if isinstance(meta, dict) else None
        spec = row.get("spec") if isinstance(row, dict) else None
        out.append(
            {
                "kind": kind,
                "name": name or (row.get("name") if isinstance(row, dict) else None),
                "spec": spec if isinstance(spec, dict) else dict(spec or {}),
            }
        )
    return out


async def sdlc_digest_impl(
    live: LiveDna, since: str | None = None, scope: str | None = None,
    tenant: str | None = None,
) -> dict[str, Any]:
    """The retrospective board digest — what happened in a window. Reuses the
    SAME pure aggregator ``dna sdlc digest`` uses (``_digest.build_digest``)."""
    from dna_cli._digest import build_digest, resolve_since
    from dna_cli.sdlc_cmd import _DIGEST_KINDS

    sc = scope or live.base_scope
    now = datetime.now(timezone.utc)
    try:
        since_dt, label = resolve_since(since, now=now)
    except ValueError as exc:
        raise ValueError(str(exc)) from None

    docs: list[dict[str, Any]] = []
    for kind in _DIGEST_KINDS:
        try:
            docs.extend(await _collect(live, sc, kind, tenant))
        except Exception:  # noqa: BLE001 — kind absent in this source
            continue
    return build_digest(docs=docs, since=since_dt, until=now, since_label=label, scope=sc)


async def list_stories_impl(
    live: LiveDna, status: str | None = None, scope: str | None = None,
    tenant: str | None = None,
) -> dict[str, Any]:
    """List Stories, optionally filtered by ``status`` (todo/in-progress/…)."""
    sc = scope or live.base_scope
    stories: list[dict[str, Any]] = []
    for d in await _collect(live, sc, "Story", tenant):
        spec = d["spec"]
        st = spec.get("status")
        if status and st != status:
            continue
        stories.append(
            {
                "name": d["name"],
                "title": spec.get("title"),
                "status": st,
                "feature": spec.get("feature"),
                "priority": spec.get("priority"),
            }
        )
    stories.sort(key=lambda s: (s.get("status") or "", s.get("name") or ""))
    return {"scope": sc, "count": len(stories), "stories": stories}


async def get_adr_impl(
    live: LiveDna, name: str, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """Fetch one ADR (Architecture Decision Record) by name — the decision the
    board recorded, verbatim (context / decision / consequences / body)."""
    sc = scope or live.base_scope
    raw = await live.kernel.get_document(sc, "ADR", name, tenant=tenant)
    if raw is None:
        raise ValueError(f"ADR {name!r} not found in scope {sc!r}")
    spec = raw.get("spec") or {}
    return {
        "scope": sc,
        "name": name,
        "title": spec.get("title"),
        "status": spec.get("status"),
        "context": spec.get("context"),
        "decision": spec.get("decision"),
        "consequences": spec.get("consequences"),
        "body": spec.get("body"),
    }


# ── memory (declarative recall) ────────────────────────────────────────────


async def recall_impl(
    live: LiveDna, query: str, scope: str | None = None, k: int = 5,
    tenant: str | None = None,
) -> dict[str, Any]:
    """Recall DNA memory for ``query`` — hybrid + bi-temporal + retention
    re-scored when the search extra is present, honest lexical otherwise.
    Tenant-scoped when ``tenant`` is set (the auth bridge injects it)."""
    from dna.memory import recall
    from dna.memory.verbs import MEMORY_KINDS

    sc = scope or live.base_scope
    if live.provider is not None:
        try:
            from dna.memory import backfill_index

            await backfill_index(live.kernel, sc, kinds=MEMORY_KINDS, tenant=tenant)
        except Exception:  # noqa: BLE001 — indexing failure degrades to lexical
            pass
    res = await recall(live.kernel, sc, query, k=k, actor="mcp", tenant=tenant)
    return res


async def remember_impl(
    live: LiveDna,
    summary: str,
    scope: str | None = None,
    kind: str = "LessonLearned",
    area: str = "general",
    affect: str = "triumph",
    tags: list[str] | None = None,
    owner: str = "mcp",
    tenant: str | None = None,
) -> dict[str, Any]:
    """Persist a memory Kind (deterministically enriched + indexed) — mirrors
    ``dna memory remember``. Written into the tenant overlay when ``tenant`` is
    set (the auth bridge injects it)."""
    from dna.memory import remember

    sc = scope or live.base_scope
    name = _slug(summary)
    spec: dict[str, Any] = {"summary": summary}
    if kind == "LessonLearned":
        spec.update(
            {
                "area": area,
                "surface_when": ["feature_touched"],
                "source_refs": [area],
                "affect": affect,
                "owner": owner,
            }
        )
        if tags:
            spec["tags"] = list(tags)
    out = await remember(live.kernel, sc, kind=kind, name=name, spec=spec, tenant=tenant)
    return {"kind": out["kind"], "name": out["name"], "indexed": out["indexed"]}


async def consolidate_impl(
    live: LiveDna, scope: str | None = None, apply: bool = False,
    tenant: str | None = None,
) -> dict[str, Any]:
    """Deterministic memory consolidation pass (Ebbinghaus retention). With
    ``apply=True`` stale memories are soft-forgotten (bi-temporal, never
    deleted). Mirrors ``dna memory consolidate``."""
    from dna.memory import consolidate

    sc = scope or live.base_scope
    return await consolidate(live.kernel, sc, apply=apply, tenant=tenant)


async def list_memories_impl(
    live: LiveDna, scope: str | None = None, kind: str = "LessonLearned",
    tenant: str | None = None,
) -> dict[str, Any]:
    """List the tenant's stored memories — the LIST surface the DNA Cloud memory
    dashboard renders. Tenant-aware via the same ``kernel.query`` idiom every
    list surface uses (``_collect``): with ``tenant`` set the caller sees the
    shared base PLUS its own overlay only, never another tenant's overlay (#83).
    Projects each memory to ``{name, summary, area, tags, affect, created_at}``
    and sorts newest-first when a timestamp is available. FORGOTTEN memories
    (bi-temporally demoted by ``forget`` — ``spec.valid_to`` set/in the past) are
    EXCLUDED, using the SAME ``currently_valid`` predicate ``recall`` applies
    (verbs.py) so the list and recall agree: a memory dropped by ``forget``
    disappears from BOTH surfaces, never a ghost."""
    from dna.memory.decay import currently_valid

    sc = scope or live.base_scope
    memories: list[dict[str, Any]] = []
    for d in await _collect(live, sc, kind, tenant):
        spec = d["spec"]
        if not currently_valid(spec.get("valid_to")):
            continue  # forgotten / superseded — never surfaced (mirrors recall).
        # LessonLearned stamps ``created_at`` (== ``valid_from`` seed); fall back
        # to the reconsolidation timeline's first ``at`` when a variant omits it.
        created = spec.get("created_at") or spec.get("valid_from")
        if not created:
            history = spec.get("cues_history") or []
            if isinstance(history, list) and history and isinstance(history[0], dict):
                created = history[0].get("at")
        memories.append(
            {
                "name": d["name"],
                "summary": spec.get("summary"),
                "area": spec.get("area"),
                "tags": list(spec.get("tags") or []),
                "affect": spec.get("affect"),
                "created_at": created,
            }
        )
    memories.sort(key=lambda m: (m.get("created_at") or ""), reverse=True)
    return {"scope": sc, "memories": memories}


async def forget_impl(
    live: LiveDna, name: str, scope: str | None = None,
    kind: str = "LessonLearned", tenant: str | None = None,
) -> dict[str, Any]:
    """Forget ONE memory by its doc ``name`` (slug) — the DELETE surface the DNA
    Cloud memory dashboard calls. NOT a hard delete: routes through the memory
    verb ``dna.memory.forget`` — a **bi-temporal DEMOTION** that stamps
    ``valid_to`` (a revivable tombstone, auditable, never destroyed; verbs.py
    "NEVER hard-delete"). ``tenant=tenant`` writes the demotion into the caller's
    OWN overlay only — never base, never another tenant (#83). Because the write
    invalidates the recall index AND ``recall``/``list_memories`` both exclude
    ``valid_to`` memories, a forgotten memory disappears from both surfaces (no
    ghost).

    Result mapping: a real demotion → ``forgotten: True``; an already-forgotten
    memory (idempotent re-forget) → ``forgotten: False``; a name that does not
    exist in the caller's layer (``forget`` raises ``KeyError``) → a clean
    ``forgotten: False`` no-op, never a 500."""
    from dna.memory import forget

    sc = scope or live.base_scope
    try:
        out = await forget(live.kernel, sc, name, kind=kind, tenant=tenant)
    except KeyError:
        return {"kind": kind, "name": name, "forgotten": False}
    return {"kind": kind, "name": name, "forgotten": not out["already_forgotten"]}


def _slug(text: str) -> str:
    import hashlib
    import re

    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]
    h = hashlib.sha1(text.encode()).hexdigest()[:10]
    return f"rem-{h}-{base}" if base else f"rem-{h}"


# ── FastMCP wiring ─────────────────────────────────────────────────────────


def build_server(
    scope: str | None = None, base_dir: str | None = None, auth: Any = None
) -> Any:
    """Build the DNA MCP server (a ``FastMCP`` instance) with every tool +
    resource wired. ``scope`` fixes the default scope (else the source's sole /
    first scope); ``base_dir`` overrides the source directory (tests / embedding).

    ``auth`` is an optional FastMCP ``AuthProvider`` / ``TokenVerifier`` (e.g. a
    ``JWTVerifier`` — see :func:`dna_cli._mcp_auth.jwt_provider_from_env`). When
    set, every tool resolves its **effective tenant from the verified token** via
    the auth↔tenancy bridge (``_mcp_auth.enforce_tenant_from_context``): the token's
    tenant claim/scope is injected into all data access and a cross-tenant (or
    tenant-less) request is denied. With ``auth=None`` (stdio / local) the bridge
    is an identity — the base path is untouched.

    The live kernel handle is built LAZILY on the first tool call, on whatever
    event loop is running the server (stdio ``mcp.run()`` or the test loop) — so
    the source pool binds to that loop.

    Raises a clean ``RuntimeError`` if the optional ``fastmcp`` dependency is absent.
    """
    try:
        from fastmcp import FastMCP
    except ModuleNotFoundError as exc:  # pragma: no cover — exercised via CLI
        raise RuntimeError(
            "the MCP server needs the optional 'fastmcp' dependency — install it "
            "with:  pip install 'dna-cli[mcp]'"
        ) from exc

    # The auth↔tenancy bridge: resolve the effective tenant from the current
    # token (identity when there is no token / no auth). CrossTenantError → a
    # clean MCP ToolError so the client sees the denial, not a masked 500.
    from fastmcp.exceptions import ToolError

    from dna_cli._mcp_auth import (
        CrossTenantError,
        enforce_tenant_from_context,
        enforce_tier_from_context,
        token_has_explicit_plan_claim,
        token_present_in_context,
    )
    from dna_cli._mcp_quota import (
        FeatureNotInPlanError,
        MemoryModeError,
        OverQuotaError,
        enforce_memory_mode,
        enforce_quota,
    )

    def _tenant(requested: str | None = None) -> str | None:
        try:
            return enforce_tenant_from_context(requested)
        except CrossTenantError as exc:
            raise ToolError(str(exc)) from None

    async def _guard(
        family: str, requested: str | None = None, *, memory_op: str | None = None
    ) -> str | None:
        """The single tenancy + quota seam every tool passes through.

        1. Enforce tenancy (existing ``_tenant``): a cross-tenant / tenant-less
           authenticated request is denied.
        2. If there is NO token (stdio / local / ``auth=None``) → identity: return
           the tenant and meter NOTHING (the OSS/self-host path is untouched — the
           quota invariant mirrors the tenant bridge exactly).
        3. Otherwise (authenticated / hosted SaaS) resolve the token's tier, read
           its caps from the ``Tier`` Kind via ``kernel.tier`` (zero hardcoded
           caps), and meter this call's ``family`` against them. For the memory
           tools ``memory_op`` (``read`` for recall / ``write`` for remember +
           consolidate) additionally enforces the tier's ``memory_mode`` — the
           read-vs-write refinement of the coarse ``memory`` feature-family gate
           (Free=read/recall-only, Pro=write/remember+consolidate), read from the
           Tier spec (zero hardcode).

        Tier resolution order — **token plan claim → TenantPlan store → Free**:
        an explicit ``plan`` claim on the token WINS (the store is not consulted);
        otherwise the billing→enforcement bridge looks up the tenant's assigned
        Tier from the ``TenantPlan`` Kind (``kernel.tenant_plan`` — which
        dna-cloud's Stripe webhook writes) and uses its ``tier_id``; only if there
        is no TenantPlan either does it fall to the Free floor.

        Empty-caps fallback: if the resolved tier names no ``Tier`` doc, fall back
        to the ``free`` doc (the Free floor); if THAT is also absent (no tiers
        configured at all = an OSS / unconfigured source) enforce nothing — never
        block a source that never opted into DNA Cloud pricing.
        """
        tenant = _tenant(requested)
        if not token_present_in_context():
            return tenant  # stdio / local → identity, no metering.

        kernel = (await _live()).kernel
        tier = enforce_tier_from_context()
        # Bridge: a token WITHOUT an explicit plan claim consults the TenantPlan
        # store (Stripe-written) before the Free floor. An explicit claim wins.
        if tenant and not token_has_explicit_plan_claim():
            plan = await kernel.tenant_plan(tenant)
            store_tier = ((plan or {}).get("spec") or {}).get("tier_id")
            if store_tier:
                tier = store_tier
        row = await kernel.tier(tier)
        if row is None:
            row = await kernel.tier("free")  # unknown tier → Free floor.
        caps = (row or {}).get("spec") or {}  # no tiers configured → empty → no-op.
        try:
            # memory_mode is a pre-counter gate (like the family gate): a denied
            # write costs no quota. Enforce it BEFORE metering.
            if memory_op is not None:
                enforce_memory_mode(caps=caps, tier=tier, op=memory_op)
            enforce_quota(caps=caps, tenant=tenant, tier=tier, family=family)
        except (OverQuotaError, FeatureNotInPlanError, MemoryModeError) as exc:
            raise ToolError(str(exc)) from None
        return tenant

    server = FastMCP(
        "dna",
        auth=auth,
        instructions=(
            "The DNA runtime face — the LIVE, vendor-neutral intelligence layer. "
            "One server exposes everything DNA stores: agent DEFINITIONS composed "
            "live and tenant-aware (compose_prompt/list_agents/list_tools/get_tool), "
            "the self-describing SDLC board (sdlc_digest/list_stories/get_adr), and "
            "declarative MEMORY (recall/remember/consolidate/list_memories/forget). "
            "Unlike a static emit "
            "artifact, compose_prompt composes on demand — so per-tenant overlays "
            "and no-deploy changes are preserved."
        ),
    )

    _state: dict[str, LiveDna | None] = {"live": None}

    async def _live() -> LiveDna:
        if _state["live"] is None:
            _state["live"] = await boot_live(scope, base_dir)
        return _state["live"]

    # -- definitions ---------------------------------------------------------

    @server.tool(run_in_thread=False)
    async def compose_prompt(
        agent: str, scope: str | None = None, tenant: str | None = None
    ) -> dict[str, Any]:
        """Compose an agent's system prompt LIVE (Soul + Guardrails +
        instruction). Pass ``tenant`` to get the per-tenant overlay — the
        composition a static emit artifact cannot express. When the server is
        authenticated, the effective tenant is bound to the token (a cross-tenant
        ``tenant`` is denied)."""
        return await compose_prompt_impl(
            await _live(), agent, scope, await _guard("definitions", tenant)
        )

    @server.tool(run_in_thread=False)
    async def list_agents(scope: str | None = None) -> dict[str, Any]:
        """List the agents (prompt targets) declared in a scope."""
        return await list_agents_impl(await _live(), scope, await _guard("definitions"))

    @server.tool(run_in_thread=False)
    async def list_tools(scope: str | None = None) -> dict[str, Any]:
        """List the Tool Kind surfaces (name + description) in a scope."""
        return await list_tools_impl(await _live(), scope, await _guard("definitions"))

    @server.tool(run_in_thread=False)
    async def get_tool(name: str, scope: str | None = None) -> dict[str, Any]:
        """Get one Tool's full agent-facing surface (description + input schema)."""
        return await get_tool_impl(await _live(), name, scope, await _guard("definitions"))

    # -- SDLC ----------------------------------------------------------------

    @server.tool(run_in_thread=False)
    async def sdlc_digest(
        since: str | None = None, scope: str | None = None
    ) -> dict[str, Any]:
        """Retrospective board digest — what happened in a window (default 24h).
        ``since`` accepts a span (``90m``/``24h``/``3d``/``2w``) or ISO time."""
        return await sdlc_digest_impl(await _live(), since, scope, await _guard("sdlc"))

    @server.tool(run_in_thread=False)
    async def list_stories(
        status: str | None = None, scope: str | None = None
    ) -> dict[str, Any]:
        """List SDLC Stories, optionally filtered by status."""
        return await list_stories_impl(await _live(), status, scope, await _guard("sdlc"))

    @server.tool(run_in_thread=False)
    async def get_adr(name: str, scope: str | None = None) -> dict[str, Any]:
        """Fetch one ADR (Architecture Decision Record) verbatim."""
        return await get_adr_impl(await _live(), name, scope, await _guard("sdlc"))

    # -- memory --------------------------------------------------------------

    @server.tool(run_in_thread=False)
    async def recall(query: str, scope: str | None = None, k: int = 5) -> dict[str, Any]:
        """Recall DNA memory for a query (hybrid/bi-temporal when available)."""
        return await recall_impl(
            await _live(), query, scope, k, await _guard("memory", memory_op="read")
        )

    @server.tool(run_in_thread=False)
    async def remember(
        summary: str,
        scope: str | None = None,
        area: str = "general",
        affect: str = "triumph",
        tags: list[str] | None = None,
        owner: str = "mcp",
    ) -> dict[str, Any]:
        """Persist a memory (a LessonLearned) so future recalls surface it."""
        return await remember_impl(
            await _live(), summary, scope, area=area, affect=affect, tags=tags,
            owner=owner, tenant=await _guard("memory", memory_op="write"),
        )

    @server.tool(run_in_thread=False)
    async def consolidate(scope: str | None = None, apply: bool = False) -> dict[str, Any]:
        """Deterministic memory consolidation pass (retention re-score)."""
        return await consolidate_impl(
            await _live(), scope, apply=apply,
            tenant=await _guard("memory", memory_op="write"),
        )

    @server.tool(run_in_thread=False)
    async def list_memories(scope: str | None = None) -> dict[str, Any]:
        """List your stored memories (tenant-scoped). Read-only."""
        return await list_memories_impl(
            await _live(), scope, tenant=await _guard("memory", memory_op="read")
        )

    @server.tool(run_in_thread=False)
    async def forget(name: str, scope: str | None = None) -> dict[str, Any]:
        """Delete one memory by name (tenant-scoped, your own overlay only). A write op."""
        return await forget_impl(
            await _live(), name, scope, tenant=await _guard("memory", memory_op="write")
        )

    # -- resources (prove resources beyond tools) ----------------------------

    @server.resource("dna://{scope}/manifest")
    async def manifest_resource(scope: str) -> dict[str, Any]:
        """The scope's manifest as a resource: its Kinds → document names."""
        mi = await (await _live()).mi(scope, await _guard("definitions"))
        by_kind: dict[str, list[str]] = {}
        for d in mi.documents:
            by_kind.setdefault(d.kind, []).append(d.name)
        return {"scope": mi.scope, "documents": {k: sorted(v) for k, v in by_kind.items()}}

    @server.resource("dna://{scope}/agents")
    async def agents_resource(scope: str) -> dict[str, Any]:
        """The scope's agent roster as a resource."""
        return await list_agents_impl(await _live(), scope, await _guard("definitions"))

    return server
