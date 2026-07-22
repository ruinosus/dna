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
    SDLC (read)  sdlc_digest · list_stories · get_adr
    SDLC (write) create_story · create_issue · set_status · comment · create_feature
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
from datetime import datetime, timezone
from typing import Any

# NOTE: no top-level ``import fastmcp`` — it is optional. ``build_server`` imports
# it lazily so the base CLI/SDK install never requires it.

# The application layer lives in the CORE now (adr-faces-reorg, move #1): the
# transport-agnostic ``*_impl`` use-cases were extracted out of this face into
# ``dna.application``. This module is a THIN adapter over them — it boots a
# ``LiveDna`` (the composition root ``boot_live`` below), wires FastMCP, and
# enforces MCP-edge concerns (auth/quota). The use-cases are re-exported here so
# ``dna_cli._mcp_server.compose_prompt_impl`` (etc.) keep resolving for callers.
from dna.application import (  # noqa: F401 — re-exported for the faces + tests
    InvalidTransition,
    LiveDna,
    adopt_workspace_scope_on_access,
    comment_impl,
    compose_prompt_impl,
    consolidate_impl,
    create_feature_impl,
    create_issue_impl,
    create_story_impl,
    forget_impl,
    get_adr_impl,
    get_skill_impl,
    get_template_impl,
    get_tool_impl,
    list_agents_impl,
    list_memories_impl,
    list_skills_impl,
    list_stories_impl,
    list_templates_impl,
    list_tools_impl,
    recall_impl,
    remember_impl,
    set_status_impl,
)
from dna.application.live import parse_scope_grants
from dna.application.runtime import _collect  # sdlc_digest_impl (below) uses it


# ── live DNA handle (composition root) ─────────────────────────────────────


async def boot_live(scope: str | None = None, base_dir: str | None = None) -> LiveDna:
    """Boot the kernel against the configured source and register the search
    provider (pgvector on a Postgres source, sqlite-vec when the
    ``search-sqlite`` extra is present; honest lexical fallback otherwise).
    Reuses the CLI's own boot path so the server sees EXACTLY the DNA the
    ``dna`` CLI sees."""
    if base_dir:
        # Programmatic override (tests / embedding). The CLI serve path relies
        # purely on DNA_SOURCE_URL / DNA_BASE_DIR from the environment.
        os.environ["DNA_BASE_DIR"] = base_dir
    from dna_cli._ctx import _build_holder_async
    from dna_cli.recall_cmd import _register_provider

    holder = await _build_holder_async(scope)
    provider = _register_provider(holder)  # holder exposes .kernel — enough
    # Model B workspace base-scope isolation (ADR "Model B"): when
    # DNA_VENDOR_WORKSPACE is set the runtime is multi-workspace — a scope-less
    # read resolves to a PER-WORKSPACE default (LiveDna.default_scope), the vendor
    # workspace #1 (id == the founder's tid) reserved to the base scope. Unset
    # (OSS / single-tenant) leaves every default at base_scope (unchanged).
    vendor_workspace = (os.environ.get("DNA_VENDOR_WORKSPACE") or "").strip() or None
    workspace_scope_prefix = (
        os.environ.get("DNA_WORKSPACE_SCOPE_PREFIX") or "tenant-"
    )
    # i-058 — the definitions base a NEW workspace's scope declares as its
    # Genome ``parent_scope`` (and an existing one adopts on sign-in), so the
    # per-workspace overlay has a curated base to inherit. Unset (OSS /
    # self-host): nothing is written, behavior unchanged.
    workspace_definitions_base = (
        os.environ.get("DNA_WORKSPACE_DEFINITIONS_BASE") or ""
    ).strip() or None
    return LiveDna(
        base_scope=holder.scope,
        kernel=holder.kernel,
        provider=provider,
        vendor_workspace=vendor_workspace,
        workspace_scope_prefix=workspace_scope_prefix,
        workspace_definitions_base=workspace_definitions_base,
    )


# ── SDLC digest (lives here by design; see note) ───────────────────────────
#
# adr-faces-reorg move #1 extracted the transport-agnostic ``*_impl`` use-cases
# into ``dna.application`` (re-exported at the top of this module).
# ``sdlc_digest_impl`` DELIBERATELY stays here: unlike its siblings it depends
# on CLI-internal machinery — the digest aggregator ``dna_cli._digest.build_digest``
# / ``resolve_since`` and the kind list ``dna_cli.sdlc_cmd._DIGEST_KINDS`` — and
# moving it cleanly into the core would mean relocating that aggregator too. It
# still delegates the raw fetch to the core ``_collect`` (imported above). It is
# MCP-only (no REST twin), so living here keeps both faces green.


async def sdlc_digest_impl(
    live: LiveDna, since: str | None = None, scope: str | None = None,
    tenant: str | None = None,
) -> dict[str, Any]:
    """The retrospective board digest — what happened in a window. Reuses the
    SAME pure aggregator ``dna sdlc digest`` uses (``_digest.build_digest``)."""
    from dna_cli._digest import build_digest, resolve_since
    from dna_cli.sdlc_cmd import _DIGEST_KINDS

    sc = scope or live.default_scope(tenant)
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


# ── The memory result shape: data first, for every kind of host ────────────
#
# The DATA is always the primary `content` (the lesson of M0): every MCP
# client reads the memories from the textual result, byte-stable.
# `structured_content` mirrors the same data for hosts that consume the
# structured channel.


def _with_memory_card(data: dict[str, Any]) -> Any:
    """Shape the ``list_memories`` result for every kind of host, data first.

    The DATA is the primary ``content`` (a JSON text block) so EVERY MCP client
    reads the memories directly — a normal MCP client reads ``content``, not
    ``structured_content`` (verified live: ``langchain-mcp-adapters`` returns
    just the content blocks). ``structured_content`` mirrors the data. The
    result carries no UI metadata."""
    import json

    from fastmcp.tools.tool import ToolResult
    from mcp.types import TextContent

    return ToolResult(
        content=[TextContent(type="text", text=json.dumps(data))],
        structured_content=data,
    )


# ── FastMCP wiring ─────────────────────────────────────────────────────────


def build_server(
    scope: str | None = None, base_dir: str | None = None, auth: Any = None,
    graph_config: Any = None, quota_store: Any = None,
) -> Any:
    """Build the DNA MCP server (a ``FastMCP`` instance) with every tool +
    resource wired. ``scope`` fixes the default scope (else the source's sole /
    first scope); ``base_dir`` overrides the source directory (tests / embedding).

    ``graph_config`` is an optional parsed :class:`dna_cli.graph._config.GraphConfig`
    (the ``graph:`` block of ``dna.config.yaml``). When present AND a tool-group is
    active, the Microsoft On-Behalf-Of ``graph.*`` tools (e.g. ``ms_calendar_list``)
    are registered — gated on the config enablement + an Entra inbound identity
    (ADR-mcp-obo). ``None`` (the default) → OBO off, not one graph tool registered;
    the OSS / stdio path is untouched.

    ``auth`` is an optional FastMCP ``AuthProvider`` / ``TokenVerifier`` (e.g. a
    ``JWTVerifier`` — see :func:`dna_cli._mcp_auth.jwt_provider_from_env`). When
    set, every tool resolves its **effective tenant from the verified token** via
    the auth↔tenancy bridge (``_mcp_auth.enforce_tenant_from_context``): the token's
    tenant claim/scope is injected into all data access and a cross-tenant (or
    tenant-less) request is denied. With ``auth=None`` (stdio / local) the bridge
    is an identity — the base path is untouched.

    ``quota_store`` is an optional :class:`dna_cli._mcp_quota.QuotaStore` — the
    metering counter this server's quota guard spends against. ``None`` (the
    default) selects one from the environment via ``_mcp_quota.store_from_env``:
    a Postgres DSN present → the DURABLE store (survives restart, shared by
    every replica, readable by the billing job); absent → the in-process store,
    which is the correct default for local / self-hosted single-process use.
    Passing one explicitly is how a host wires its own (and how tests get an
    isolated counter instead of resetting a module singleton).

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

    # MCP Apps (SEP-1865): the memory card. The static template
    # `ui://dna/memory-list` (dna.emit.mcp_ui.memory_list_card_html — public,
    # data-free, self-contained) is registered as a resource below and pointed
    # from the `list_memories`/`recall` DECLARATIONS via `app=AppConfig(...)`,
    # so an MCP Apps host prefetches the template and pushes each result's
    # `structured_content` into it. Hosts without the extension see the same
    # declaration meta and ignore it — the textual `content` keeps carrying
    # the data, byte-identical.
    from fastmcp.apps import AppConfig

    from dna.emit.mcp_ui import MCP_APP_MIME, UI_MEMORY_LIST_URI, memory_list_card_html

    memory_card_app = AppConfig(resource_uri=UI_MEMORY_LIST_URI)

    # The auth↔tenancy bridge: resolve the effective tenant from the current
    # token (identity when there is no token / no auth). CrossTenantError → a
    # clean MCP ToolError so the client sees the denial, not a masked 500.
    from fastmcp.exceptions import ToolError

    from dna_cli._mcp_auth import (
        CrossTenantError,
        enforce_oid_from_context,
        enforce_personal_family_from_context,
        enforce_tier_from_context,
        enforce_workspace_from_context,
        token_has_explicit_plan_claim,
        token_present_in_context,
    )
    from dna.memory.personal import (
        PersonalIdentityRequired,
        PersonalOverrideRejected,
        personal_tenant,
    )
    from dna_cli._mcp_quota import (
        FeatureNotInPlanError,
        MemoryModeError,
        OverQuotaError,
        SdlcModeError,
        TierRegistryUnavailableError,
        enforce_plan,
        store_from_env,
    )
    from dna.tenancy.resolution import CrossWorkspaceError

    # The metering counter for THIS server. Resolved once, here, and closed
    # over by both guards — so the quota port is genuinely swappable instead of
    # every call site silently defaulting to the module singleton.
    quota = quota_store if quota_store is not None else store_from_env()

    # NOTE (i-042): the tier-resolution → caps → mode-gates → enforce_quota
    # pipeline that used to live here as `_caps_from` + `_tier_row` + inline
    # code in the guards is now `dna_cli._mcp_quota.enforce_plan` — the ONE
    # metered-call policy shared with the REST face. This face keeps only the
    # transport mapping (quota exceptions → ToolError).

    async def _workspace(requested: str | None = None) -> str | None:
        """Resolve the effective **workspace** (Model B) for the current request.

        The rework of the old ``_tenant``: the tenancy dimension comes from the
        caller's VERIFIED IDENTITY + active WorkspaceMembership (never the Azure
        ``tid``). A no-membership / cross-workspace authenticated request is denied
        (fail-closed) as a clean MCP ToolError. Stdio / OSS (no token, or a source
        with no workspaces configured) passes through unchanged. The returned value
        is the ``workspace_id`` — the opaque value the kernel ``tenant`` dimension
        carries."""
        try:
            return await enforce_workspace_from_context(await _live(), requested)
        except (CrossWorkspaceError, CrossTenantError) as exc:
            raise ToolError(str(exc)) from None

    async def _guard(
        family: str, requested: str | None = None, *,
        scope: str | None = None, memory_op: str | None = None,
        sdlc_op: str | None = None,
    ) -> str | None:
        """The single tenancy + quota seam every tool passes through.

        1. Enforce tenancy (``_workspace``): the effective workspace is resolved
           from the verified identity + membership; a no-membership / cross-workspace
           authenticated request is denied. Then enforce **scope-binding**: when the
           runtime is multi-workspace a request may only name its OWN scope — a
           caller-supplied ``scope`` pointing at another workspace's (or the
           vendor's) scope is a cross-workspace read and is denied. With
           multi-workspace off, no token, or no explicit ``scope`` this is a no-op.
        2. If there is NO token (stdio / local / ``auth=None``) → identity: return
           the workspace and meter NOTHING (the OSS/self-host path is untouched — the
           quota invariant mirrors the tenant bridge exactly).
        3. Otherwise (authenticated / hosted SaaS) resolve the token's tier, read
           its caps from the ``Tier`` Kind via ``kernel.tier`` (zero hardcoded
           caps), and meter this call's ``family`` against them. For the memory
           tools ``memory_op`` (``read`` for recall / ``write`` for remember +
           consolidate) additionally enforces the tier's ``memory_mode`` — the
           read-vs-write refinement of the coarse ``memory`` feature-family gate
           (Free=read/recall-only, Pro=write/remember+consolidate), read from the
           Tier spec (zero hardcode).

        Tier resolution order — **token plan claim → WorkspacePlan store → Free**:
        an explicit ``plan`` claim on the token WINS (the store is not consulted);
        otherwise the billing→enforcement bridge looks up the workspace's assigned
        Tier from the ``WorkspacePlan`` Kind (``kernel.workspace_plan`` — which
        dna-cloud's Stripe webhook writes) and uses its ``tier_id``; only if there
        is no WorkspacePlan either does it fall to the Free floor.

        Empty-caps fallback: if the resolved tier names no ``Tier`` doc, fall back
        to the ``free`` doc (the Free floor); if THAT is also absent (no tiers
        configured at all = an OSS / unconfigured source) enforce nothing — never
        block a source that never opted into DNA Cloud pricing.
        """
        tenant = await _workspace(requested)  # the resolved workspace_id.
        # Adopt-on-access (i-058 hardening): the request just RESOLVED a
        # workspace — the one moment no portal navigation path can skip. If the
        # workspace scope has no declared parent and a definitions base is
        # configured, declare it NOW, before the tool impl runs, so THIS very
        # compose/list already inherits the base's definitions. Cached +
        # single-flighted inside (one set lookup steady-state), NO-OP without
        # the env (OSS untouched), fail-soft (never fails the request).
        await adopt_workspace_scope_on_access(await _live(), tenant)
        if not token_present_in_context():
            return tenant  # stdio / local → identity, no metering.

        live = await _live()
        # Scope-binding (isolation): a resolved workspace may only reach its own
        # scope — a caller-supplied ``scope`` naming another workspace's is denied.
        # Control reaches here only past the `token_present_in_context()` return
        # above, so this caller IS authenticated — which is what makes the
        # workspace-less branch fail-closed (i-034). A token that resolves NO
        # workspace (the legacy tid passthrough on a source with no workspaces
        # configured, or a provider whose token carries no tid) used to be allowed
        # ANY scope precisely because it had no workspace to be bound to; it is now
        # limited to the scopes explicitly granted to it (`DNA_TOKEN_SCOPES`,
        # defaulting to the server's own base scope).
        if not live.scope_is_bound(
            scope, tenant, authenticated=True,
            granted_scopes=parse_scope_grants(os.environ.get("DNA_TOKEN_SCOPES")),
        ):
            if tenant:
                raise ToolError(
                    f"request is bound to workspace {tenant!r} (scope "
                    f"{live.default_scope(tenant)!r}); cross-workspace access to "
                    f"scope {scope!r} is denied"
                )
            raise ToolError(
                f"scope {scope!r} is not granted to this credential; a request that "
                f"resolves no workspace may only read the scopes explicitly granted "
                f"to its token (default: {live.base_scope!r})"
            )
        kernel = live.kernel
        # Bridge: a token WITHOUT an explicit plan claim consults the
        # WorkspacePlan store (Stripe-written) before the Free floor. An explicit
        # claim wins. `tenant` is the resolved workspace_id (ADR "Model B") — so
        # billing is keyed on the workspace, not the Azure tid. The whole
        # pipeline (tier → caps → mode gates → quota, incl. the i-051
        # fail-closed switch) is the SHARED core `enforce_plan`; this face only
        # maps its exceptions to ToolError.
        tier = enforce_tier_from_context()
        try:
            await enforce_plan(
                kernel, tenant=tenant, family=family, store=quota,
                claimed_tier=tier if token_has_explicit_plan_claim() else None,
                memory_op=memory_op, sdlc_op=sdlc_op,
            )
        except (OverQuotaError, FeatureNotInPlanError, MemoryModeError,
                SdlcModeError, TierRegistryUnavailableError) as exc:
            raise ToolError(str(exc)) from None
        return tenant

    async def _personal_guard(memory_op: str) -> tuple[str, str]:
        """The tenancy + quota seam for a PERSONAL memory call — the identity twin
        of :func:`_guard` (ADR-personal-memory).

        Personal memory is keyed on the durable identity, not a workspace, so this
        deliberately does NOT go through workspace resolution/membership (personal
        works in a bare MCP client with no workspace — the portability thesis).
        Instead it:

        1. resolves the ``oid`` SERVER-SIDE via ``enforce_oid_from_context`` — an
           authenticated request with no verified oid, or an offline caller with no
           ``DNA_PERSONAL_ID``, is DENIED (INV-PERSONAL layer 1, fail-closed);
        2. with NO token (stdio / local) → returns the oid, meters nothing (the
           OSS/self-host path, exactly like ``_guard``);
        3. otherwise meters this call against the token's tier — the SAME
           ``memory_mode`` (read vs write) + quota caps as workspace memory, but
           keyed on the personal partition ``personal:<oid>`` so personal usage
           meters per identity, independent of any workspace.

        Returns ``(oid, family)`` — the server-resolved identity + its personal-
        memory KEY family ("entra"/"google"/"workos"); the caller passes
        ``memory_scope="personal"`` + this ``oid`` + ``family`` to the impl, which
        keys the partition ``personal:<oid>`` (Entra) / ``personal:google:<sub>``
        (direct Google sign-in) / ``personal:workos:<sub>`` (WorkOS/consumer —
        ``sub`` there is the WorkOS user id, never a Google subject, and lives in
        its OWN namespace precisely so it can never collide with the google family;
        see ``dna_cli._mcp_auth.identity_claim_for_family``)."""
        try:
            oid = enforce_oid_from_context()
            family = enforce_personal_family_from_context()
        except (PersonalIdentityRequired, PersonalOverrideRejected) as exc:
            raise ToolError(str(exc)) from None
        if not token_present_in_context():
            return oid, family  # stdio / local → identity, no metering.
        kernel = (await _live()).kernel
        # Personal metering keys on the identity partition, never a workspace,
        # and the tier comes from the token's plan claim (Free floor default) —
        # the WorkspacePlan store is keyed by workspace so it is deliberately
        # not consulted (claimed_tier is always set). Same shared core as
        # _guard, incl. the i-051 fail-closed opt-in.
        try:
            await enforce_plan(
                kernel, tenant=None, family="memory", store=quota,
                claimed_tier=enforce_tier_from_context(),
                memory_op=memory_op,
                quota_tenant=personal_tenant(oid, family=family),
            )
        except (OverQuotaError, FeatureNotInPlanError, MemoryModeError,
                TierRegistryUnavailableError) as exc:
            raise ToolError(str(exc)) from None
        return oid, family

    server = FastMCP(
        "dna",
        auth=auth,
        instructions=(
            "The DNA runtime face — the LIVE, vendor-neutral intelligence layer. "
            "One server exposes everything DNA stores: agent DEFINITIONS composed "
            "live and tenant-aware (compose_prompt/list_agents/list_tools/get_tool), "
            "the self-describing SDLC board — READABLE "
            "(sdlc_digest/list_stories/get_adr) AND WRITABLE "
            "(create_story/create_issue/set_status/comment/create_feature), so an "
            "agent can create + manage the board over MCP — and declarative MEMORY "
            "(recall/remember/consolidate/list_memories/forget). "
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
        agent: str, scope: str | None = None, tenant: str | None = None,
        explain: bool = False,
    ) -> dict[str, Any]:
        """Compose an agent's system prompt LIVE (Soul + Guardrails +
        instruction). Pass ``tenant`` to get the per-tenant overlay — the
        composition a static emit artifact cannot express. When the server is
        authenticated, the effective tenant is bound to the token (a cross-tenant
        ``tenant`` is denied). Pass ``explain=true`` (opt-in) to ALSO get
        per-section provenance: ``sections`` (source artifact, content hash,
        version, layer origin, tenant-overlay marker per composed section) and
        ``attribution`` (``declared`` = kernel-owned template, section map
        correct by construction; ``heuristic`` = custom promptTemplate, section
        detection is fail-soft string matching and may omit/over-report
        sections). The composed ``prompt`` is byte-identical with or without
        the flag; without it the response shape is unchanged."""
        return await compose_prompt_impl(
            await _live(), agent, scope,
            await _guard("definitions", tenant, scope=scope),
            explain=explain,
        )

    @server.tool(run_in_thread=False)
    async def list_agents(scope: str | None = None) -> dict[str, Any]:
        """List the agents (prompt targets) declared in a scope."""
        return await list_agents_impl(await _live(), scope, await _guard("definitions", scope=scope))

    @server.tool(run_in_thread=False)
    async def list_tools(scope: str | None = None) -> dict[str, Any]:
        """List the Tool Kind surfaces (name + description) in a scope."""
        return await list_tools_impl(await _live(), scope, await _guard("definitions", scope=scope))

    @server.tool(run_in_thread=False)
    async def get_tool(name: str, scope: str | None = None) -> dict[str, Any]:
        """Get one Tool's full agent-facing surface (description + input schema)."""
        return await get_tool_impl(await _live(), name, scope, await _guard("definitions", scope=scope))

    # -- toolkit (Spec Kit Layer 3: templates + skills served live) ----------

    @server.tool(run_in_thread=False)
    async def list_templates(
        scope: str | None = None, tenant: str | None = None
    ) -> dict[str, Any]:
        """List the PromptTemplates in a scope (name + description + variable
        count). The Spec Kit templates ingested by ``dna specify
        install-templates`` surface here — servable to any MCP client. Pass
        ``tenant`` for the per-workspace/tenant view (the overlay wins, no redeploy)."""
        return await list_templates_impl(await _live(), scope, await _guard("definitions", tenant))

    @server.tool(run_in_thread=False)
    async def get_template(
        name: str, scope: str | None = None, tenant: str | None = None
    ) -> dict[str, Any]:
        """Fetch one PromptTemplate's full body + variables. With ``tenant`` the
        per-workspace/tenant OVERLAY wins live — governance without redeploy."""
        return await get_template_impl(await _live(), name, scope, await _guard("definitions", tenant))

    @server.tool(run_in_thread=False)
    async def list_skills(
        scope: str | None = None, tenant: str | None = None
    ) -> dict[str, Any]:
        """List the Skills in a scope (name + description). The Spec Kit
        slash-command definitions ingested as Skills surface here."""
        return await list_skills_impl(await _live(), scope, await _guard("definitions", tenant))

    @server.tool(run_in_thread=False)
    async def get_skill(
        name: str, scope: str | None = None, tenant: str | None = None
    ) -> dict[str, Any]:
        """Fetch one Skill's full instruction body + metadata. With ``tenant``
        the per-workspace/tenant OVERLAY wins live — no redeploy."""
        return await get_skill_impl(await _live(), name, scope, await _guard("definitions", tenant))

    # -- SDLC ----------------------------------------------------------------

    @server.tool(run_in_thread=False)
    async def sdlc_digest(
        since: str | None = None, scope: str | None = None
    ) -> dict[str, Any]:
        """Retrospective board digest — what happened in a window (default 24h).
        ``since`` accepts a span (``90m``/``24h``/``3d``/``2w``) or ISO time."""
        return await sdlc_digest_impl(await _live(), since, scope, await _guard("sdlc", scope=scope))

    @server.tool(run_in_thread=False)
    async def list_stories(
        status: str | None = None, scope: str | None = None
    ) -> dict[str, Any]:
        """List SDLC Stories, optionally filtered by status."""
        return await list_stories_impl(await _live(), status, scope, await _guard("sdlc", scope=scope))

    @server.tool(run_in_thread=False)
    async def get_adr(name: str, scope: str | None = None) -> dict[str, Any]:
        """Fetch one ADR (Architecture Decision Record) verbatim."""
        return await get_adr_impl(await _live(), name, scope, await _guard("sdlc", scope=scope))

    # -- SDLC writes (the board is CREATABLE + MANAGEABLE over MCP) -----------
    #
    # The write half of the board: close the dogfood loop so any MCP client
    # (Copilot / an agent / a bare client) can create + manage the board over its
    # own interface, not just read it. Each write tool passes the SAME `_guard`
    # tenancy + quota seam as every other tool, PLUS `sdlc_op="write"` — the finer
    # read-vs-write gate within the `sdlc` family (Free=read/list-only,
    # Pro=write), mirroring memory's `remember`. A denied write is an honest
    # ToolError; the stdio/OSS (no-token) path is unmetered + unrestricted. The
    # write logic is the shared `dna.application.sdlc` core the `dna sdlc` CLI
    # also calls — one write path through `kernel.write_document`.

    @server.tool(run_in_thread=False)
    async def create_story(
        name: str, feature: str, description: str,
        title: str | None = None, priority: str | None = None,
        labels: list[str] | None = None,
        ac: list[str] | None = None, dod: list[str] | None = None,
        scope: str | None = None,
    ) -> dict[str, Any]:
        """Create a Story on the board. ``feature`` is the parent Feature; ``ac`` /
        ``dod`` are the acceptance-criteria / definition-of-done bullets (the exit
        criteria). Returns ``{kind, name, status, feature}``. A write op — needs a
        tier whose ``sdlc_mode`` is ``write``."""
        return await create_story_impl(
            await _live(), name, feature=feature, description=description,
            title=title, priority=priority, labels=labels,
            acceptance_criteria=ac, definition_of_done=dod, scope=scope,
            tenant=await _guard("sdlc", scope=scope, sdlc_op="write"),
        )

    @server.tool(run_in_thread=False)
    async def create_issue(
        slug: str, description: str, type: str = "bug", severity: str = "medium",
        feature: str | None = None, scope: str | None = None,
    ) -> dict[str, Any]:
        """File an Issue (bug / enhancement / question / task) with an
        auto-incremented ``i-NNN-<slug>`` name. Returns ``{kind, name, type,
        severity}``. A write op — needs ``sdlc_mode='write'``."""
        return await create_issue_impl(
            await _live(), slug, description=description, issue_type=type,
            severity=severity, related_feature=feature, scope=scope,
            tenant=await _guard("sdlc", scope=scope, sdlc_op="write"),
        )

    @server.tool(run_in_thread=False)
    async def set_status(
        kind: str, name: str, status: str, reason: str | None = None,
        scope: str | None = None,
    ) -> dict[str, Any]:
        """Transition a board item's status. ``kind`` is Story / Issue / Feature /
        Epic; ``status`` must be a valid status for that Kind (e.g. Story:
        todo/in-progress/review/done/blocked; Issue: open/triaged/resolved;
        Feature: discovery/in-development/done). An invalid target is refused. Pass
        ``reason`` to record a block reason / resolution. A write op —
        ``sdlc_mode='write'``."""
        tenant = await _guard("sdlc", scope=scope, sdlc_op="write")
        try:
            return await set_status_impl(
                await _live(), kind, name, status, reason=reason, scope=scope,
                tenant=tenant,
            )
        except (InvalidTransition, LookupError) as exc:
            raise ToolError(str(exc)) from None

    @server.tool(run_in_thread=False)
    async def comment(
        kind: str, name: str, body: str, type: str | None = None,
        scope: str | None = None,
    ) -> dict[str, Any]:
        """Add a timeline comment (or ``type='decision'``) to a board item WITHOUT
        changing its status — the FOCUS-feed narration ("agora vou fazer X",
        "decidi Y porque Z"). A decision-shaped body auto-promotes. A write op —
        ``sdlc_mode='write'``."""
        tenant = await _guard("sdlc", scope=scope, sdlc_op="write")
        try:
            return await comment_impl(
                await _live(), kind, name, body, event_type=type, scope=scope,
                tenant=tenant,
            )
        except (InvalidTransition, LookupError) as exc:
            raise ToolError(str(exc)) from None

    @server.tool(run_in_thread=False)
    async def create_feature(
        name: str, title: str, description: str, epic: str | None = None,
        priority: str | None = None, labels: list[str] | None = None,
        scope: str | None = None,
    ) -> dict[str, Any]:
        """Create a Feature (a roadmap noun; optionally under an ``epic``). Returns
        ``{kind, name, status}``. A write op — ``sdlc_mode='write'``."""
        return await create_feature_impl(
            await _live(), name, title=title, description=description, epic=epic,
            priority=priority, labels=labels, scope=scope,
            tenant=await _guard("sdlc", scope=scope, sdlc_op="write"),
        )

    # -- memory --------------------------------------------------------------

    @server.tool(run_in_thread=False, app=memory_card_app)
    async def recall(
        query: str, scope: str | None = None, k: int = 5, personal: bool = False,
    ) -> dict[str, Any]:
        """Recall DNA memory for a query (hybrid/bi-temporal when available).

        The declaration points the ``ui://dna/memory-list`` MCP Apps card
        (read-only): a host that renders MCP Apps shows the recalled hits as a
        card fed by this result's ``structured_content``; every other host
        reads the textual result, unchanged.

        ``personal=true`` recalls YOUR OWN private memory (keyed on your verified
        identity, portable across workspaces + clients) unioned with the shared
        base defaults — never any workspace's memory. The default (``false``)
        recalls the workspace's shared memory, unchanged.

        The result reports its own mode: ``degraded: true`` + ``semantic:
        false`` means the search was a LITERAL token match, not semantic
        similarity — an empty result in that mode only proves no stored memory
        shares a word with the query. When relaying such an empty result, say
        the search was literal-only; never assert that no memories exist."""
        if personal:
            oid, family = await _personal_guard("read")
            return await recall_impl(
                await _live(), query, None, k, memory_scope="personal", oid=oid,
                family=family,
            )
        return await recall_impl(
            await _live(), query, scope, k, await _guard("memory", scope=scope, memory_op="read")
        )

    @server.tool(run_in_thread=False)
    async def remember(
        summary: str,
        scope: str | None = None,
        area: str = "general",
        affect: str = "triumph",
        tags: list[str] | None = None,
        owner: str = "mcp",
        personal: bool = False,
    ) -> dict[str, Any]:
        """Persist a memory (an Engram) so future recalls surface it.

        ``personal=true`` remembers PRIVATELY — into your own identity-keyed
        partition, portable across workspaces + clients, never shared with the
        workspace. The default (``false``) shares to the workspace, unchanged."""
        if personal:
            oid, family = await _personal_guard("write")
            return await remember_impl(
                await _live(), summary, None, area=area, affect=affect, tags=tags,
                owner=owner, memory_scope="personal", oid=oid, family=family,
            )
        return await remember_impl(
            await _live(), summary, scope, area=area, affect=affect, tags=tags,
            owner=owner, tenant=await _guard("memory", scope=scope, memory_op="write"),
        )

    @server.tool(run_in_thread=False)
    async def consolidate(scope: str | None = None, apply: bool = False) -> dict[str, Any]:
        """Deterministic memory consolidation pass (retention re-score)."""
        return await consolidate_impl(
            await _live(), scope, apply=apply,
            tenant=await _guard("memory", scope=scope, memory_op="write"),
        )

    @server.tool(run_in_thread=False, app=memory_card_app)
    async def list_memories(scope: str | None = None) -> dict[str, Any]:
        """List your stored memories (tenant-scoped). Read-only.

        The declaration points the ``ui://dna/memory-list`` MCP Apps card
        (SEP-1865): a host that renders MCP Apps shows the memory list as a
        read-only card in a sandboxed iframe, fed by this result's
        ``structured_content`` — DNA's "your context follows you across every
        client" thesis made visible. Hosts without MCP Apps read the plain
        data from ``content``, unchanged (graceful degradation)."""
        data = await list_memories_impl(
            await _live(), scope, tenant=await _guard("memory", scope=scope, memory_op="read")
        )
        return _with_memory_card(data)

    @server.tool(run_in_thread=False)
    async def forget(name: str, scope: str | None = None) -> dict[str, Any]:
        """Delete one memory by name (tenant-scoped, your own overlay only). A write op."""
        return await forget_impl(
            await _live(), name, scope, tenant=await _guard("memory", scope=scope, memory_op="write")
        )

    # -- resources (prove resources beyond tools) ----------------------------

    @server.resource("dna://{scope}/manifest")
    async def manifest_resource(scope: str) -> dict[str, Any]:
        """The scope's manifest as a resource: its Kinds → document names."""
        mi = await (await _live()).mi(scope, await _guard("definitions", scope=scope))
        by_kind: dict[str, list[str]] = {}
        for d in mi.documents:
            by_kind.setdefault(d.kind, []).append(d.name)
        return {"scope": mi.scope, "documents": {k: sorted(v) for k, v in by_kind.items()}}

    @server.resource("dna://{scope}/agents")
    async def agents_resource(scope: str) -> dict[str, Any]:
        """The scope's agent roster as a resource."""
        return await list_agents_impl(await _live(), scope, await _guard("definitions", scope=scope))

    @server.resource(UI_MEMORY_LIST_URI, mime_type=MCP_APP_MIME)
    def memory_list_card() -> str:
        """The MCP Apps template for the memory card (SEP-1865) — the resource
        the ``list_memories``/``recall`` declarations point at. Static, public
        and data-free (cacheable by URI): the host pushes each tool result's
        ``structured_content`` into it over the authenticated session."""
        return memory_list_card_html()

    # -- graph.* (Microsoft On-Behalf-Of — opt-in, off by default) -----------
    #
    # Registered ONLY when the `graph:` config marks a tool-group active. The
    # tools reuse the SAME `_guard` tenancy/quota seam; each additionally requires
    # an Entra inbound identity (the raw assertion + tid) to run — a non-Entra
    # identity gets an honest capability-gap ToolError (ADR-mcp-obo §4.4).
    if graph_config is not None:
        from dna_cli._mcp_auth import entra_obo_assertion_from_context
        from dna_cli.graph._tools import register_graph_tools

        async def _graph_guard(family: str, **kw: Any) -> Any:
            return await _guard(family, **kw)

        names = register_graph_tools(
            server, graph_config,
            guard=_graph_guard, obo_context=entra_obo_assertion_from_context,
        )
        for n in names:
            print(f"[dna-mcp] graph tool wired: {n}")  # noqa: T201 — boot log

        # Provider-NEUTRAL capabilities (f-act-on-behalf-port): `calendar_list`
        # dispatches to the right ActOnBehalfPort by the caller's verified provider
        # family. Added ALONGSIDE the ms_* tools above (ms_calendar_list stays the
        # Microsoft binding/alias). Same gate/guard; Google off until configured.
        from dna_cli.act_on_behalf._server import register_neutral_capabilities

        for n in register_neutral_capabilities(
            server, graph_config, guard=_graph_guard,
        ):
            print(f"[dna-mcp] capability tool wired: {n}")  # noqa: T201 — boot log

    return server


def build_http_app(
    server: Any, *, path: str = "/mcp", transport: str = "http",
    lane_b_server: Any = None,
) -> Any:
    """Wrap the FastMCP ``server`` as a Starlette ASGI app that ALSO accepts the
    per-workspace URL ``/w/<workspace-id>/mcp`` (ADR "Model B" §2.2 — S2.3),
    alongside the bare ``/mcp``.

    FastMCP mounts the MCP endpoint at ``path``; we additionally mount the SAME app
    instance under ``/w/{workspace_id}`` so a client can paste
    ``https://…/w/<id>/mcp`` into VS Code to pick its workspace by URL. The workspace
    id is NOT read here — the auth bridge reads it from the live request path
    (``_mcp_auth.workspace_selector_from_context``) and re-verifies it against
    membership, so the path is a *named, verified* selector, never trusted blind.

    Mounting the one app instance at both prefixes shares its lifespan (the MCP
    session manager), which the outer app forwards. The bare ``/mcp`` route keeps
    the default single-workspace / stdio-parity behavior (falls back to the
    identity's sole/default membership).

    ``lane_b_server`` (optional, the identity front-door Option X): a SECOND FastMCP
    server — the consumer lane (WorkOS AuthKit auth) — mounted at ``/consumer`` with
    its OWN discovery + auth surface, beside Lane A (Entra). Its lifespan is composed
    with Lane A's so both session managers run. Absent → single-lane, unchanged."""
    from starlette.applications import Starlette
    from starlette.routing import Mount

    mcp_app = server.http_app(path=path, transport=transport)
    routes = [
        # Per-workspace URL first (more specific).
        Mount("/w/{workspace_id}", app=mcp_app),
    ]
    lifespan = mcp_app.lifespan
    root_app: Any = mcp_app
    if lane_b_server is not None:
        from contextlib import asynccontextmanager

        lane_b_app = lane_b_server.http_app(path=path, transport=transport)
        routes.append(Mount("/consumer", app=lane_b_app))  # Lane B (WorkOS)

        @asynccontextmanager
        async def _both_lanes(app: Any):
            # Run BOTH FastMCP session managers (each app owns one).
            async with mcp_app.lifespan(app), lane_b_app.lifespan(app):
                yield

        lifespan = _both_lanes

        # RFC 9728: Lane B's Protected-Resource-Metadata lives at the HOST ROOT
        # (`/.well-known/oauth-protected-resource/consumer/mcp`) — that is what the
        # `/consumer/mcp` 401 advertises. But the `/consumer` mount would only serve
        # it UNDER `/consumer/`, so an MCP client following the 401 to the root 404s
        # and falls back to Lane A. Dispatch the root Lane-B well-known to lane_b_app
        # (with the full, UNstripped path — it owns that exact route); everything else
        # is Lane A. This is the seam that makes two OAuth resource servers coexist
        # on one host (f-identity-frontdoor).
        _mcp_app = mcp_app
        _lane_b_app = lane_b_app

        async def _root(scope: Any, receive: Any, send: Any) -> None:
            if scope.get("type") == "http" and scope.get("path", "").startswith(
                "/.well-known/oauth-protected-resource/consumer"
            ):
                await _lane_b_app(scope, receive, send)
            else:
                await _mcp_app(scope, receive, send)

        root_app = _root
    routes.append(Mount("/", app=root_app))  # bare mount, least specific → last
    return Starlette(routes=routes, lifespan=lifespan)
