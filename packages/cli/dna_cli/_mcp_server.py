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
    SDLC (read)  sdlc_digest · list_stories · get_adr · board_summary · board_item
    SDLC (write) create_story · create_issue · set_status · comment · create_feature
    memory       recall · remember · consolidate · list_memories · forget
    instances    list_kinds · list_instances · get_instance · write_instance
                 · delete_instance
                 (GENERIC — a loop over the Kind registry, not a per-Kind tool)
    kinds        author_kind · list_my_kinds
                 (a tenant declares its OWN Kind — INERT until a human approves;
                  there is deliberately no approval tool, see _mcp_kinds)
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

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# NOTE: no top-level ``import fastmcp`` — it is optional. ``build_server`` imports
# it lazily so the base CLI/SDK install never requires it.

# The application layer lives in the CORE now (adr-faces-reorg, move #1): the
# transport-agnostic ``*_impl`` use-cases were extracted out of this face into
# ``dna.application``. This module is a THIN adapter over them — it boots a
# ``LiveDna`` (the composition root ``boot_live`` below), wires FastMCP, and
# enforces MCP-edge concerns (auth/quota). The use-cases are re-exported here so
# ``dna_cli._mcp_server.compose_prompt_impl`` (etc.) keep resolving for callers.
from dna.application import (  # noqa: F401 — re-exported for the faces + tests
    BoardItemNotFound,
    InvalidTransition,
    LiveDna,
    adopt_workspace_scope_on_access,
    board_item_impl,
    board_summary_impl,
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
from dna.application.live import KIND_REFRESH_TTL_ENV, parse_scope_grants
from dna.application.runtime import (  # sdlc_digest_impl / the scope-grant binder
    _collect,
    workspace_granted_scopes,
)
from dna.emit.mcp_ui import MCP_APP_MIME  # the MCP Apps profile mimeType we serve
from dna.memory.contradiction import WHEN_TO_CLAIM
from dna.tenancy.enforcement import enforcement_boot_message


# ── the `remember` tool description (a docstring cannot interpolate) ────────
#
# Python docstrings are literals, so the ONE `WHEN_TO_CLAIM` text (owned by
# `dna.memory.contradiction`, beside the rule it paraphrases) cannot be spliced
# into `remember`'s docstring — it is composed here and handed to FastMCP as
# `description=`, which wins over the docstring (`Tool.from_function`:
# `metadata.description if not None else parsed_fn.description`). The docstring
# stays for the Python reader and says where the wire text comes from.
#
# The paragraph this replaced was the defect, not an omission: it said "declare
# a claim whenever you record a state that can later change — an approval, a
# status, an owner, a decision". A preference IS a state that can change, so
# that sentence asks for exactly the claim that makes the pass cry wolf. The
# fix is a discriminant, not a longer list.
_REMEMBER_DESCRIPTION = f"""\
Persist a memory (an Engram) so future recalls surface it.

`personal=true` remembers PRIVATELY — into your own identity-keyed partition,
portable across workspaces + clients, never shared with the workspace. The
default (`false`) shares to the workspace, unchanged.

**`claims` is what lets this memory be checked for CONTRADICTION against
another one.** Prose cannot be compared: "the Kind still needs approval" and
"the Kind was approved" share almost no words, so nothing can tell they
disagree. A claim states the same thing structurally — `[{{"subject":
"KindDefinition/livro", "predicate": "approval", "object": "pending"}}]` — and
`consolidate(dry_run=true)` then reports any OTHER memory asserting a different
`object` for the same `(subject, predicate)` while both are still believed. It
only ever REPORTS: nothing is overwritten, expired or merged.

{WHEN_TO_CLAIM}

A malformed claim is REFUSED naming the offending index and field, and nothing
is written."""


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
    live = LiveDna(
        base_scope=holder.scope,
        kernel=holder.kernel,
        provider=provider,
        vendor_workspace=vendor_workspace,
        workspace_scope_prefix=workspace_scope_prefix,
        workspace_definitions_base=workspace_definitions_base,
    )
    # i-090 — SAY THE NUMBER AT BOOT. This window is not a performance knob: it
    # is the worst case between one replica approving (or revoking) a Kind and
    # THIS replica honouring it, which makes it the SLA an operator publishes.
    # The value actually in force has to be findable without reading source.
    if live.kind_refresh_ttl > 0:
        logger.info(
            "Kind-registry refresh window: %.0fs (%s) — a Kind approved or "
            "revoked on another replica takes effect here within that window; "
            "the replica that serves the act honours it immediately.",
            live.kind_refresh_ttl, KIND_REFRESH_TTL_ENV,
        )
    else:
        logger.warning(
            "Kind-registry refresh window DISABLED (%s=0) — a Kind approved or "
            "revoked on ANOTHER replica does not take effect on this one until "
            "something else rebuilds that scope. Intended only for a "
            "single-replica deployment.", KIND_REFRESH_TTL_ENV,
        )
    return live


# ── SDLC digest (lives here by design; see note) ───────────────────────────
#
# adr-faces-reorg move #1 extracted the transport-agnostic ``*_impl`` use-cases
# into ``dna.application`` (re-exported at the top of this module).
# ``sdlc_digest_impl`` DELIBERATELY stays here: unlike its siblings it depends
# on CLI-internal machinery — the digest aggregator ``dna_cli._digest.build_digest``
# / ``resolve_since`` and the kind derivation ``dna_cli.sdlc_cmd._digest_kinds`` — and
# moving it cleanly into the core would mean relocating that aggregator too. It
# still delegates the raw fetch to the core ``_collect`` (imported above). It is
# MCP-only (no REST twin), so living here keeps both faces green.


async def sdlc_digest_impl(
    live: LiveDna, since: str | None = None, scope: str | None = None,
    tenant: str | None = None,
) -> dict[str, Any]:
    """The retrospective board digest — what happened in a window. Reuses the
    SAME pure aggregator ``dna sdlc digest`` uses (``_digest.build_digest``).

    Reports its own COVERAGE. This loop used to be ``except Exception:
    continue  # kind absent in this source``: the comment named one cause, the
    code caught every cause, and the digest then reported ``rag_status: green``
    and "nada precisa da sua atenção" for a board it had failed to read. Two
    distinctions replace it:

    * a Kind the source does not REGISTER is discovered from the Kind registry,
      before any query — no exception needed, and not a failure (``absent``);
    * anything a read RAISES is a failure, recorded with its type and message
      (``unreadable``), which makes the digest visibly ``partial`` and never
      green — the policy lives in ``build_digest``, so every caller inherits it.

    Still fail-soft by design: one broken Kind must not deny the delegator the
    nine that worked. What changes is that the result says which nine."""
    from dna_cli._digest import build_digest, resolve_since
    from dna_cli.sdlc_cmd import _digest_kinds

    sc = scope or live.default_scope(tenant)
    now = datetime.now(timezone.utc)
    try:
        since_dt, label = resolve_since(since, now=now)
    except ValueError as exc:
        raise ValueError(str(exc)) from None

    registered = {p.kind for p in live.kernel.kind_ports()}
    docs: list[dict[str, Any]] = []
    absent: list[str] = []
    unreadable: list[dict[str, str]] = []
    for kind in _digest_kinds(live.kernel):
        if kind not in registered:
            absent.append(kind)
            continue
        try:
            docs.extend(await _collect(live, sc, kind, tenant))
        except Exception as exc:  # noqa: BLE001 — one Kind must not deny the rest
            logger.warning(
                "sdlc_digest: reading %s in scope %s failed: %s: %s",
                kind, sc, type(exc).__name__, exc,
            )
            unreadable.append(
                {"kind": kind, "error": f"{type(exc).__name__}: {exc}"})
    return build_digest(
        docs=docs, since=since_dt, until=now, since_label=label, scope=sc,
        absent=absent, unreadable=unreadable, kernel=live.kernel,
    )


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


# ── MCP Apps: the extension negotiation (SEP-1865) ─────────────────────────
#
# The extension is negotiated in TWO directions and this section owns both.
#
# OUTBOUND — what WE declare. A server announces MCP Apps support in the
# `extensions` capability map, and the entry carries the mimeTypes it can
# serve. The runtime declares the extension id with an EMPTY config, so we
# enrich it with the one profile mimeType this server actually serves.
#
# INBOUND — what the CLIENT declared. The spec says a server SHOULD check the
# client's capability before registering UI-enabled tools. WHERE that
# declaration lives changed with the 2026-07-28 core, which removed
# `initialize` and sessions: protocol version, client info and capabilities
# now travel in `_meta` on EVERY request, so the check is per-call, not
# per-boot. The runtime this build pins still speaks the older handshake,
# where the same map arrives once at `initialize`. We read BOTH, per call,
# newest first — and we answer `None` when neither channel says anything,
# because a check that cannot see the client must say so rather than assume.
#
# The check gates the DECLARATION only. `content` is REQUIRED by the spec and
# `structuredContent` is OPTIONAL, so withholding the card never touches the
# textual answer — a client that cannot render still reads the same bytes.

#: The MCP Apps extension id, as it appears in the capability map.
UI_EXTENSION_ID = "io.modelcontextprotocol/ui"


def ui_extension_capability() -> dict[str, Any]:
    """The server's OWN entry in the ``extensions`` capability map: MCP Apps
    support, qualified by the profile mimeType we actually serve.

    ``MCP_APP_MIME`` is imported from the SDK surface that RENDERS those
    resources, so the mimeType we DECLARE and the one we SERVE cannot drift."""
    return {"mimeTypes": [MCP_APP_MIME]}


def _as_mapping(value: Any) -> dict[str, Any] | None:
    """A plain dict view of a mapping OR of a pydantic model (extras included).

    Both channels hand us models whose schema predates the fields we are
    reading — `_meta` and `ClientCapabilities` are both `extra="allow"` — so a
    field the installed models do not know still arrives, in `model_extra`."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return dump(by_alias=True, exclude_none=True)
        except Exception:  # noqa: BLE001 — a model we cannot read is "no answer"
            return None
    return None


def _ui_in_extension_map(capabilities: dict[str, Any]) -> bool:
    """Does this capability map declare the MCP Apps extension?"""
    extensions = capabilities.get("extensions")
    return isinstance(extensions, dict) and UI_EXTENSION_ID in extensions


def client_ui_extension(
    *, request_meta: Any = None, session_capabilities: Any = None
) -> bool | None:
    """Did the client declare the MCP Apps extension? Tri-state, on purpose.

    ``True``  — it declared the extension: advertise the card.
    ``False`` — it sent its capability map and the extension is NOT in it: it
                cannot render, so do not advertise.
    ``None``  — neither channel carried a capability map. We do not know, and
                we say so; answering "yes" here would be a fake check that
                merely looks conformant, and answering "no" would silently
                blind a host that can in fact render.

    ``request_meta`` is the per-request ``_meta`` (the 2026-07-28 shape, where
    capabilities ride every request); ``session_capabilities`` is the map from
    the ``initialize`` handshake (the shape the pinned runtime still speaks).
    The per-request map WINS — it is the fresher statement of the same fact."""
    meta = _as_mapping(request_meta)
    if meta is not None:
        caps = _as_mapping(meta.get("capabilities"))
        if caps is not None:
            return _ui_in_extension_map(caps)
        if isinstance(meta.get("extensions"), dict):
            return _ui_in_extension_map(meta)

    caps = _as_mapping(session_capabilities)
    if caps is not None:
        return _ui_in_extension_map(caps)
    return None


def client_ui_extension_from_context(ctx: Any) -> bool | None:
    """:func:`client_ui_extension`, sourced from a live FastMCP context.

    Never raises: a shape we cannot read is "no answer" (``None``), which is
    the reading that leaves the client's experience unchanged."""
    if ctx is None:
        return None
    request_meta = None
    session_capabilities = None
    try:
        rc = ctx.request_context
    except Exception:  # noqa: BLE001 — outside a request there is nothing to read
        rc = None
    if rc is not None:
        request_meta = getattr(rc, "meta", None)
        params = getattr(getattr(rc, "session", None), "_client_params", None)
        session_capabilities = getattr(params, "capabilities", None)
    return client_ui_extension(
        request_meta=request_meta, session_capabilities=session_capabilities,
    )


def _tool_without_ui_meta(tool: Any) -> Any:
    """A COPY of ``tool`` with the ``ui`` block dropped from its meta.

    A copy, never a mutation: the tool objects belong to the server's registry
    and are shared by every connected client — stripping in place would
    withhold the card from a UI-capable client because a UI-blind one asked
    first."""
    meta = getattr(tool, "meta", None)
    if not isinstance(meta, dict) or "ui" not in meta:
        return tool
    trimmed = {k: v for k, v in meta.items() if k != "ui"}
    return tool.model_copy(update={"meta": trimmed or None})


def app_only(tool: Any) -> bool:
    """Is this tool declared for the APP and not for the model? (SEP-1865)

    ``_meta.ui.visibility`` lists the surfaces a tool is offered on. A list that
    omits ``"model"`` means a conforming host must not put the tool in the tool
    list it hands the model. An ABSENT ``visibility`` means BOTH — so the
    reading here is "declared, and omits model", never "does not say model".

    Stated once because two places need the same answer: the listing filter
    below, and the test that reads the tool list the way a model would see it. A
    second spelling of this predicate would be a second answer to the one
    question that keeps the approval tool away from the model."""
    ui = (getattr(tool, "meta", None) or {}).get("ui")
    if not isinstance(ui, dict):
        return False
    visibility = ui.get("visibility")
    if not isinstance(visibility, list):
        return False
    return "model" not in visibility


def _ui_capability_middleware() -> Any:
    """Middleware applying the inbound half of the negotiation at ``tools/list``.

    FastMCP registers tools at build time, so "check before registering a
    UI-enabled tool" lands, for this runtime, on the listing: a client that
    told us it cannot render is not offered the pointer. THE GAP, stated
    plainly: when the client tells us nothing (``None``) we leave the pointer
    in place — it is inert metadata a non-supporting host ignores, and
    stripping on a shrug would break every host whose declaration this runtime
    cannot yet surface.

    An APP-ONLY tool is WITHHELD ENTIRELY from a client that told us it cannot
    render, not merely stripped — and this is a correctness fix, not a tidiness
    one. The whole safety of ``approve_kind`` is the ``visibility`` marker that
    lives inside the ``ui`` block; handing a UI-blind client the tool with that
    block removed would deliver an approval tool wearing no marker at all,
    straight into the model's list. There is also nothing to lose: a client that
    cannot render MCP Apps has no button to press it with."""
    from fastmcp.server.middleware import Middleware

    class UiCapabilityMiddleware(Middleware):
        #: Values already reported, so a chatty client does not flood the log.
        #: Per-process and deliberately unbounded: the set has three members.
        _reported: set[bool | None] = set()

        async def on_list_tools(self, context: Any, call_next: Any) -> Any:
            tools = await call_next(context)
            declared = client_ui_extension_from_context(context.fastmcp_context)
            self._report(declared, tools)
            if declared is not False:
                return tools
            return [
                _tool_without_ui_meta(t) for t in tools if not app_only(t)
            ]

        def _report(self, declared: bool | None, tools: Any) -> None:
            """Log the tri-state ONCE per value. Without this the answer to
            "did the host declare MCP Apps?" is computed and discarded, and the
            question can only be argued from the outside — where all three
            readings look alike (no card rendered). Each value implies a
            different tool count, so the line names it: whoever reads the log
            can compare it against what the client actually offered."""
            if declared in self._reported:
                return
            self._reported.add(declared)
            total = len(tools) if isinstance(tools, list) else -1
            app = (
                sum(1 for t in tools if app_only(t))
                if isinstance(tools, list) else -1
            )
            if declared is True:
                logger.info(
                    "MCP Apps: client DECLARED %s — advertising cards; "
                    "sending %d tools (%d app-only, which a conforming host "
                    "hides from the model)", UI_EXTENSION_ID, total, app,
                )
            elif declared is False:
                logger.info(
                    "MCP Apps: client sent capabilities WITHOUT %s — it "
                    "cannot render; withholding %d app-only tool(s) and "
                    "stripping ui metadata, sending %d tools",
                    UI_EXTENSION_ID, app, total - app,
                )
            else:
                logger.info(
                    "MCP Apps: client declared NOTHING readable about %s — "
                    "leaving the pointer in place; sending %d tools (%d "
                    "app-only). A card that does not render here is the host "
                    "ignoring inert metadata, not a refusal we made",
                    UI_EXTENSION_ID, total, app,
                )

    return UiCapabilityMiddleware()


def _declare_ui_extension(server: Any) -> None:
    """Enrich the server's declared MCP Apps extension with our mimeTypes.

    The runtime already puts ``{UI_EXTENSION_ID: {}}`` in the capability map;
    the spec's shape names the mimeTypes, and a host that filters on them
    would never prefetch a card from a server that declared none. Wrapping the
    capability builder keeps every other capability the runtime computes."""
    low_level = getattr(server, "_mcp_server", None)
    build = getattr(low_level, "get_capabilities", None)
    if build is None:  # pragma: no cover — a runtime without the seam
        logger.warning(
            "MCP Apps: cannot declare the %s extension mimeTypes — this "
            "runtime exposes no capability seam", UI_EXTENSION_ID,
        )
        return

    def get_capabilities(*args: Any, **kwargs: Any) -> Any:
        caps = build(*args, **kwargs)
        extensions = dict((caps.model_extra or {}).get("extensions") or {})
        extensions[UI_EXTENSION_ID] = {
            **(extensions.get(UI_EXTENSION_ID) or {}), **ui_extension_capability(),
        }
        return caps.model_copy(update={"extensions": extensions})

    low_level.get_capabilities = get_capabilities


# ── FastMCP wiring ─────────────────────────────────────────────────────────


def build_server(
    scope: str | None = None, base_dir: str | None = None, auth: Any = None,
    graph_config: Any = None, quota_store: Any = None, auth_providers: Any = None,
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

    # LOUD, NOT SILENT (i-074): a door running with the workspace boundary opened
    # must say so at boot — an operator may never discover that from behaviour.
    # Silent in the default (enforcing) posture; also speaks up when the knob
    # carries a value this build does not recognise (it enforces, and says so).
    _enforcement_line = enforcement_boot_message()
    if _enforcement_line:
        logger.warning("%s", _enforcement_line)

    # The declarative-config SUGAR (mirrors build_rest_app's auth_providers=): a
    # host may hand raw provider mappings (or ProviderConfig objects) instead of a
    # pre-built provider, and we assemble the N-provider auth layer via the SAME
    # public factory (build_auth_from_config). The `auth=<provider>` PORT still
    # works for jwt/azure/custom providers — this only fills in when auth is unset.
    if auth is None and auth_providers is not None:
        from dna_cli._mcp_auth import build_auth_from_config, parse_auth_providers

        _provs = auth_providers
        if isinstance(_provs, dict):  # the whole {"providers": [...]} mapping
            _provs = parse_auth_providers(_provs)
        elif _provs and isinstance(_provs[0], dict):  # a list of provider mappings
            _provs = parse_auth_providers({"providers": list(_provs)})
        auth = build_auth_from_config(list(_provs))

    # MCP Apps (SEP-1865): the memory card. The static template
    # `ui://dna/memory-list` (dna.emit.mcp_ui.memory_list_card_html — public,
    # data-free, self-contained) is registered as a resource below and pointed
    # from the `list_memories`/`recall` DECLARATIONS via `app=AppConfig(...)`,
    # so an MCP Apps host prefetches the template and pushes each result's
    # `structured_content` into it. Hosts without the extension see the same
    # declaration meta and ignore it — the textual `content` keeps carrying
    # the data, byte-identical.
    from fastmcp.apps import AppConfig

    from dna.emit.mcp_ui import UI_MEMORY_LIST_URI, memory_list_card_html

    memory_card_app = AppConfig(resource_uri=UI_MEMORY_LIST_URI)

    # The same mechanism for the READ tools whose answer is a table or a
    # dashboard rather than a paragraph (`dna_cli._mcp_cards`). Those cards are
    # Prefab views, so they share ONE renderer resource — `resource_uri` is
    # overridden precisely to stop FastMCP synthesising
    # `ui://prefab/tool/<hash>/renderer.html` per tool, which in bundled mode
    # is a separate 6.6 MB instance each. `with_card` merges rather than
    # replaces: `content` stays byte-identical for every client that renders
    # nothing.
    from dna_cli._mcp_cards import (
        UI_PREFAB_URI,
        digest_app,
        prefab_renderer_html,
        stories_app,
        with_card,
    )

    prefab_card_app = AppConfig(resource_uri=UI_PREFAB_URI)

    # The auth↔tenancy bridge: resolve the effective tenant from the current
    # token (identity when there is no token / no auth). CrossTenantError → a
    # clean MCP ToolError so the client sees the denial, not a masked 500.
    from contextlib import asynccontextmanager as _asynccontextmanager

    from fastmcp.exceptions import ToolError

    from dna.application.sdlc import InstanceExists
    from dna.kernel.errors import KernelRefusal

    from dna_cli._mcp_refusals import CAPABILITY_REFUSALS

    # Everything a tool call may legitimately be REFUSED with — the ONE tuple
    # every write tool relays through ``_refusing`` below.
    #
    # It is short because ``KernelRefusal`` is the kernel's own marker base for a
    # deliberate verdict (schema veto, LayerPolicy veto, tenancy rule, read-only
    # source, retired Kind). That base exists because THIS list used to be
    # hand-enumerated per tool and was wrong: ``write_instance`` caught
    # ``(ValueError, LookupError, PermissionError)`` and therefore missed the
    # LayerPolicy veto and every tenancy rule (plain ``Exception``;
    # ``NotWritableError`` is a ``RuntimeError``), while the three board create
    # tools and all five memory tools had no mapping at all — so the single
    # likeliest refusal on a tenant write reached the client as an unexplained
    # failure with no cause and no remedy.
    #
    # Deliberately NOT ``Exception``: a genuine bug must keep looking like a bug.
    # A caller told "refused" stops investigating, so a crash reported as a policy
    # decision costs more than a crash reported as a crash.
    #
    # ``dna_cli._mcp_refusals.CAPABILITY_REFUSALS`` is spliced in because those
    # are the refusals ``KernelRefusal`` does NOT reach. They are not verdicts
    # about the REQUEST — they are the deployment saying "this store cannot
    # answer that at all" — so no kernel marker base covers them, and they
    # inherit from ``RuntimeError`` / ``NotImplementedError`` / ``LookupError``.
    # The ports catalogue states all four as CONTRACT and the REST face maps all
    # four; this face translated only the one ``_mcp_instances`` catches inline,
    # so ``recall(as_of=…)`` against a store with no version history reached the
    # client as FastMCP's ``Error calling tool 'recall'`` — the type name gone,
    # and under ``mask_error_details`` the reason gone too.
    _REFUSALS: tuple[type[BaseException], ...] = (
        KernelRefusal, InvalidTransition, InstanceExists,
        *CAPABILITY_REFUSALS,
        ValueError, LookupError, PermissionError,
    )

    @_asynccontextmanager
    async def _refusing():
        """Relay a refusal to the client by NAME and reason, never as a 500.

        The type name is part of the message on purpose: an agent that reads
        ``LayerPolicyViolationError: layer 'tenant' LOCKED for alias X`` can tell
        "the operator forbade this" from "your instance is malformed" and act
        differently. A bare reason string cannot carry that."""
        try:
            yield
        except ToolError:
            raise  # already an honest, client-facing denial (quota / tenancy).
        except _REFUSALS as exc:
            raise ToolError(f"{type(exc).__name__}: {exc}") from None

    from dna_cli._mcp_auth import (
        CrossTenantError,
        actor_from_context,
        enforce_oid_from_context,
        enforce_personal_family_from_context,
        enforce_tier_from_context,
        enforce_workspace_from_context,
        token_has_explicit_plan_claim,
        token_present_in_context,
        unenforced_metering_key_from_context,
    )
    from dna.tenancy.enforcement import UnmeterableIdentityError
    from dna.memory.personal import (
        PersonalIdentityRequired,
        PersonalOverrideRejected,
        personal_tenant,
    )
    from dna_cli._mcp_quota import (
        InstanceModeError,
        FeatureNotInPlanError,
        MemoryModeError,
        OverQuotaError,
        SdlcModeError,
        TierRegistryUnavailableError,
        enforce_plan,
        resolve_metered_tier,
        resolve_tier_caps,
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
        sdlc_op: str | None = None, family_op: str | None = None,
    ) -> str | None:
        """The single tenancy + quota seam every tool passes through.

        1. Enforce tenancy (``_workspace``): the effective workspace is resolved
           from the verified identity + membership; a no-membership / cross-workspace
           authenticated request is denied. Then enforce **scope-binding**: when the
           runtime is multi-workspace a request may only name its OWN scope — a
           caller-supplied ``scope`` pointing at another workspace's (or the
           vendor's) scope is a cross-workspace read and is denied. With
           multi-workspace off, no token, or no explicit ``scope`` this is a no-op.
           A ``WorkspaceScopeGrant`` row can open a second scope, and it opens it
           for what the row SAYS — ``read`` (i-082); the read/write axis is the
           ``*_op`` this call already carries, so a cross-scope WRITE is refused
           on the same grant that permits the cross-scope read.
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
           Tier spec (zero hardcode). ``family_op`` is that same refinement made
           GENERIC over the family (``<family>_mode``) — what the
           registry-driven instance tools pass, since one of those tools spans
           every family and its family comes from the TARGET KIND, not from
           which tool was called.

        Tier resolution order — **token plan claim → AccountPlan store → Free**:
        an explicit ``plan`` claim on the token WINS (the store is not consulted);
        otherwise the billing→enforcement bridge resolves **workspace → account →
        plan**: the resolved workspace's ``account_id``
        (``kernel.account_for_workspace``) then that ACCOUNT's assigned Tier from
        the ``AccountPlan`` Kind (``kernel.account_plan`` — which dna-cloud's
        Stripe webhook writes). The subscription belongs to the account, so one
        plan covers every workspace the account owns and a second workspace is
        never a second charge. If the workspace has no ``account_id``, or that
        account has no AccountPlan, it falls to the **Free floor** — fail-closed,
        never another account's tier and never a paid default.

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
        #
        # A resolved workspace ALSO reaches any scope a ``WorkspaceScopeGrant``
        # row grants it (decision B). The grant is DATA — read here, per request,
        # from ``_lib`` — and the binder only ever checks MEMBERSHIP against it:
        # nothing infers a grant from the workspace id, the scope's name or a
        # prefix, so a leak is a row somebody wrote and can revoke. Only looked
        # up when a cross-scope read is actually being attempted, so the common
        # path (no ``scope``, or your own) costs nothing.
        #
        # And a grant grants what it SAYS it grants (i-082). The Kind pins
        # ``access`` to ``read``; the binder now asks, so the schema an operator
        # reads and the answer the code gives are the same sentence. The
        # read/write axis is not a new one to declare: it is the SAME ``*_op``
        # every mutating tool already passes for the tier's write-mode gate, so
        # a tool cannot be a write here and a read there — and a write tool that
        # forgot its op is already broken for metering, loudly, upstream of this.
        access = "write" if "write" in (memory_op, sdlc_op, family_op) else "read"
        granted: dict[str, str] | None = None
        dono_do_board = False
        if tenant and scope and scope != live.default_scope(tenant):
            # POSSE antes de grant (bateria de 04/08): o board_scope de um
            # Project do PRÓPRIO workspace é derivado de (workspace, slug) —
            # decisão A1: "the scope is a rendering of that" — então escrever
            # nele é a mesma decisão que criou o projeto, não uma travessia.
            # O WorkspaceScopeGrant segue read-only por desenho: grant governa
            # o CROSS-workspace; a posse deriva do doc Project, fail-closed.
            # ⚠️ A posse NÃO retorna cedo: neutraliza só a negação de binding
            # e segue para o metering — dono também é medido.
            from dna.application import workspace_owns_board_scope

            dono_do_board = await workspace_owns_board_scope(live, tenant, scope)
            if not dono_do_board:
                granted = await workspace_granted_scopes(live, tenant)
        if not dono_do_board and not live.scope_is_bound(
            scope, tenant, authenticated=True,
            granted_scopes=parse_scope_grants(os.environ.get("DNA_TOKEN_SCOPES")),
            workspace_grants=granted, access=access,
        ):
            if tenant and granted and scope in granted:
                # The scope IS granted — at a level that does not cover THIS
                # call. Name the level, or the operator re-reads a row that
                # plainly says the scope and concludes the grant is broken.
                raise ToolError(
                    f"scope {scope!r} is granted to workspace {tenant!r} for "
                    f"{granted[scope]!r} access only; this call is a "
                    f"{access!r} and is denied. A WorkspaceScopeGrant does not "
                    f"carry cross-workspace WRITE — that is a different decision "
                    f"from a cross-workspace read and is not a value the grant "
                    f"schema can currently express."
                )
            if tenant:
                raise ToolError(
                    f"request is bound to workspace {tenant!r} (scope "
                    f"{live.default_scope(tenant)!r}); cross-workspace access "
                    f"to scope {scope!r} is denied — it is not granted to this "
                    f"workspace. A workspace reaches another scope only through "
                    f"an active WorkspaceScopeGrant row"
                    + (f" (granted: {sorted(granted)})" if granted else
                       " (this workspace has none)")
                )
            raise ToolError(
                f"scope {scope!r} is not granted to this credential; a request that "
                f"resolves no workspace may only read the scopes explicitly granted "
                f"to its token (default: {live.base_scope!r})"
            )
        kernel = live.kernel
        # Bridge: a token WITHOUT an explicit plan claim consults the AccountPlan
        # store (Stripe-written) before the Free floor — TWO HOPS, workspace →
        # account → plan, because the subscription belongs to the BILLING
        # ACCOUNT, not to a workspace. An explicit claim wins. The whole
        # pipeline (tier → account resolution → caps → mode gates → quota,
        # incl. the i-051 fail-closed switch) is the SHARED core
        # `enforce_plan` (`resolve_metered_tier` carries the two hops); this
        # face only maps its exceptions to ToolError.
        tier = enforce_tier_from_context()
        # The METERING key. Normally it is the resolved workspace. An
        # authenticated call that resolves NO workspace only happens once the
        # workspace boundary has been explicitly opened (i-074), and it must
        # still be counted — "só registra os chamados" is the requirement — so it
        # meters against the caller's own verified IDENTITY. Never `None`, which
        # `quota_key` would collapse into a single '-' bucket shared by every
        # membership-less identity. A token with no durable subject cannot be
        # attributed and is denied rather than pooled.
        try:
            quota_tenant = (
                None if tenant is not None else unenforced_metering_key_from_context()
            )
        except UnmeterableIdentityError as exc:
            raise ToolError(str(exc)) from None
        try:
            await enforce_plan(
                kernel, tenant=tenant, family=family, store=quota,
                claimed_tier=tier if token_has_explicit_plan_claim() else None,
                memory_op=memory_op, sdlc_op=sdlc_op, family_op=family_op,
                quota_tenant=quota_tenant,
            )
        except (OverQuotaError, FeatureNotInPlanError, MemoryModeError,
                SdlcModeError, InstanceModeError,
                TierRegistryUnavailableError) as exc:
            raise ToolError(str(exc)) from None
        return tenant

    async def _plan_families() -> list[str] | None:
        """The feature families the CURRENT caller's tier unlocks — the filter
        ``list_kinds`` reports an honest catalog through.

        ``None`` means "no plan is gating this call": the unmetered stdio /
        self-host path (no token), or a source that seeded no ``Tier`` docs at
        all. It reuses the SAME resolution the guard meters with
        (``resolve_metered_tier`` → ``resolve_tier_caps``), so the catalog and
        the enforcement can never disagree about what is unlocked."""
        if not token_present_in_context():
            return None
        live = await _live()
        tier = await resolve_metered_tier(
            live.kernel, tenant=await _workspace(),
            claimed_tier=(
                enforce_tier_from_context()
                if token_has_explicit_plan_claim() else None
            ),
        )
        caps = await resolve_tier_caps(live.kernel, tier)
        families = caps.get("feature_families")
        if isinstance(families, list) and families:
            return [str(f) for f in families]
        return None

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
        # the AccountPlan store hangs off a workspace's account so it is deliberately
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
            "(sdlc_digest/list_stories/get_adr, and the whole board in one "
            "call via board_summary/board_item) AND WRITABLE "
            "(create_story/create_issue/set_status/comment/create_feature), so an "
            "agent can create + manage the board over MCP — and declarative MEMORY "
            "(recall/remember/consolidate/list_memories/forget). "
            "Beyond those named surfaces it exposes EVERY registered Kind "
            "generically (list_kinds/list_instances/get_instance/write_instance), "
            "resolved from the Kind registry at call time — so a Kind that exists "
            "is a Kind you can use, without a hand-written tool for it. "
            "A workspace can also declare a Kind OF ITS OWN "
            "(author_kind/list_my_kinds): what that writes is INERT — it is "
            "registered, and therefore has effect, only once a HUMAN approves it "
            "in the portal. There is no approval tool and there will not be one, "
            "so do not look for one: author the Kind and tell the person you are "
            "working with that it is waiting for their approval. "
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
        ``tenant`` for the per-workspace/tenant view (the overlay wins, no redeploy).

        Every row carries ``origin``: ``instance`` (someone authored it) or
        ``runtime-default`` (no instance yet — the voice the SDK ships is what
        runs). A scope with no authored templates is NOT an empty catalog.

        Without ``scope`` this resolves in the server's BASE scope (the shared
        catalog), NOT your workspace scope — templates are catalog, and the
        tenant view is an OVERLAY on it. Intentional; not a resolution bug."""
        return await list_templates_impl(await _live(), scope, await _guard("definitions", tenant, scope=scope))

    @server.tool(run_in_thread=False)
    async def get_template(
        name: str, scope: str | None = None, tenant: str | None = None
    ) -> dict[str, Any]:
        """Fetch one PromptTemplate's full body + variables. With ``tenant`` the
        per-workspace/tenant OVERLAY wins live — governance without redeploy.
        Without ``scope``, resolves in the BASE catalog scope (see list_templates).

        The reply always names its ``origin``. **No authored instance is not an
        error**: for a name the runtime ships a default for, you get the body
        that actually runs plus ``origin: "runtime-default"`` and a note saying
        how to override it. Only a name that is neither authored nor a known
        runtime default fails — and that error lists the ones that exist."""
        return await get_template_impl(await _live(), name, scope, await _guard("definitions", tenant, scope=scope))

    @server.tool(run_in_thread=False)
    async def list_skills(
        scope: str | None = None, tenant: str | None = None
    ) -> dict[str, Any]:
        """List the Skills in a scope (name + description). The Spec Kit
        slash-command definitions ingested as Skills surface here.

        Without ``scope`` this resolves in the server's BASE scope (the shared
        catalog), NOT your workspace scope — same catalog-with-overlay shape as
        ``list_templates``. Intentional; not a resolution bug."""
        return await list_skills_impl(await _live(), scope, await _guard("definitions", tenant, scope=scope))

    @server.tool(run_in_thread=False)
    async def get_skill(
        name: str, scope: str | None = None, tenant: str | None = None
    ) -> dict[str, Any]:
        """Fetch one Skill's full instruction body + metadata. With ``tenant``
        the per-workspace/tenant OVERLAY wins live — no redeploy.
        Without ``scope``, resolves in the BASE catalog scope (see list_skills).

        Same ``origin`` contract as ``get_template``."""
        return await get_skill_impl(await _live(), name, scope, await _guard("definitions", tenant, scope=scope))

    # -- SDLC ----------------------------------------------------------------

    @server.tool(run_in_thread=False, app=prefab_card_app)
    async def sdlc_digest(
        since: str | None = None, scope: str | None = None
    ) -> dict[str, Any]:
        """Retrospective board digest — what happened in a window (default 24h).
        ``since`` accepts a span (``90m``/``24h``/``3d``/``2w``) or ISO time.

        The declaration points the shared ``ui://dna/prefab`` card (read-only):
        a host that renders MCP Apps shows the RAG verdict, the counts and what
        needs a person as a dashboard; every other host reads the full digest
        from the textual result, unchanged."""
        data = await sdlc_digest_impl(
            await _live(), since, scope, await _guard("sdlc", scope=scope))
        return with_card(data, digest_app(data))

    @server.tool(run_in_thread=False, app=prefab_card_app)
    async def list_stories(
        status: str | None = None, scope: str | None = None
    ) -> dict[str, Any]:
        """List SDLC Stories, optionally filtered by status.

        The declaration points the shared ``ui://dna/prefab`` card (read-only):
        a host that renders MCP Apps shows the roster as a sortable, searchable
        table; every other host reads the same textual result, unchanged."""
        data = await list_stories_impl(
            await _live(), status, scope, await _guard("sdlc", scope=scope))
        return with_card(data, stories_app(data))

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
    # also calls — one write path through `kernel.write_instance`.
    #
    # ATTRIBUTION (identity, not channel): every board write threads
    # `actor=actor_from_context()` — the verified identity of THIS request, read
    # server-side off the token. Before, all five tools left the core's
    # `actor="mcp"` default in place, so every timeline row on every board ever
    # written over MCP said "mcp": the founder, an autonomous agent and a paying
    # customer were the same author, and the one question a timeline exists to
    # answer ("who did this?") had no answer. `source` still says "mcp" — that is
    # the channel, and it keeps its own field.
    #
    # Each tool relays refusals through `_refusing()`: three of the five had no
    # `try` at all, so a LayerPolicy veto or a tenancy rule reached the client as
    # an unexplained failure.

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
        tier whose ``sdlc_mode`` is ``write``.

        CREATE means create: an existing ``name`` is REFUSED, naming the instance
        that is already there. To change one, use ``set_status`` (status),
        ``comment`` (narration) or ``write_instance`` (any field, merged)."""
        tenant = await _guard("sdlc", scope=scope, sdlc_op="write")
        async with _refusing():
            return await create_story_impl(
                await _live(), name, feature=feature, description=description,
                title=title, priority=priority, labels=labels,
                acceptance_criteria=ac, definition_of_done=dod, scope=scope,
                tenant=tenant, actor=actor_from_context(),
            )

    @server.tool(run_in_thread=False)
    async def create_issue(
        slug: str, description: str, type: str = "bug", severity: str = "medium",
        title: str | None = None, feature: str | None = None,
        scope: str | None = None,
    ) -> dict[str, Any]:
        """File an Issue (bug / enhancement / question / task) with an
        auto-incremented ``i-NNN-<slug>`` name — the number steps past any name
        already taken, so filing never lands on top of an existing Issue.
        ``title`` is the short card label (falls back to the description when
        omitted). Returns ``{kind, name, type, severity}``. A write op — needs
        ``sdlc_mode='write'``."""
        tenant = await _guard("sdlc", scope=scope, sdlc_op="write")
        async with _refusing():
            return await create_issue_impl(
                await _live(), slug, description=description, issue_type=type,
                severity=severity, title=title, related_feature=feature,
                scope=scope, tenant=tenant, actor=actor_from_context(),
            )

    @server.tool(run_in_thread=False)
    async def set_status(
        kind: str, name: str, status: str, reason: str | None = None,
        scope: str | None = None, commit_ref: str | None = None,
        allow_no_tests: bool = False, no_code: bool = False,
        gate_reason: str | None = None,
    ) -> dict[str, Any]:
        """Transition a board item's status.

        ``kind`` is any board work item — Story / Issue / Feature / Epic / Spike
        / Bug / Task / Initiative — and ``status`` must be a valid status for
        THAT Kind, read from the Kind's own schema (Story:
        todo/in-progress/review/done/blocked; Issue: open/triaged/resolved;
        Feature: discovery/in-development/done; ...). An invalid target is
        refused and the refusal lists the valid set. ``list_kinds`` shows which
        Kinds carry the work-item trait. Pass ``reason`` to record a block reason
        / resolution. A write op — ``sdlc_mode='write'``.

        **Closing a gated item requires evidence.** A Kind that declares
        ``sdlc.test-gated`` (Story today) refuses a close without a passing
        product-lane TestRun verifying it — the SAME refusal ``dna sdlc story
        done`` makes, because a methodology gate that only the CLI enforces is
        not a gate. Two escapes, and both REQUIRE ``gate_reason``, which is
        written to the item's timeline as an ``exception`` event: an exception
        nobody recorded is indistinguishable from skipping the gate.

        * ``allow_no_tests`` — a registered exception.
        * ``no_code`` — the item has no code for a product smoke to exercise.

        ``commit_ref`` records the shipping commit on the transition event.
        The result carries ``warnings`` for the non-blocking guards (closing with
        no shipping commit, skipping review, no narration since the last
        transition, no linked outputs) — over MCP there is no stderr for them to
        go to."""
        tenant = await _guard("sdlc", scope=scope, sdlc_op="write")
        async with _refusing():
            return await set_status_impl(
                await _live(), kind, name, status, reason=reason, scope=scope,
                tenant=tenant, actor=actor_from_context(),
                commit_ref=commit_ref, allow_no_tests=allow_no_tests,
                no_code=no_code, gate_reason=gate_reason,
            )

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
        async with _refusing():
            return await comment_impl(
                await _live(), kind, name, body, event_type=type, scope=scope,
                tenant=tenant, actor=actor_from_context(),
            )

    @server.tool(run_in_thread=False)
    async def create_feature(
        name: str, title: str, description: str, epic: str | None = None,
        priority: str | None = None, labels: list[str] | None = None,
        scope: str | None = None,
    ) -> dict[str, Any]:
        """Create a Feature (a roadmap noun; optionally under an ``epic``). Returns
        ``{kind, name, status}``. A write op — ``sdlc_mode='write'``.

        An existing ``name`` is REFUSED (see ``create_story``)."""
        tenant = await _guard("sdlc", scope=scope, sdlc_op="write")
        async with _refusing():
            return await create_feature_impl(
                await _live(), name, title=title, description=description,
                epic=epic, priority=priority, labels=labels, scope=scope,
                tenant=tenant, actor=actor_from_context(),
            )

    # -- SDLC reads: the whole board in ONE call ------------------------------
    #
    # `board_summary_impl` / `board_item_impl` have lived in the shared core and
    # been served over REST for a long time; they were simply never wired here.
    # Without them, "show me the board" over MCP is `list_instances` + one
    # `get_instance` per row — 1 + N metered calls for a question the core already
    # answers in one. Same `_guard` seam, `sdlc` family, read op.

    @server.tool(run_in_thread=False)
    async def board_summary(
        scope: str | None = None, recent: int = 6
    ) -> dict[str, Any]:
        """The whole board in ONE call: Story + Feature counts by status, totals,
        every item (newest first) and the ``recent`` newest — the shape the DNA
        Cloud console renders. Prefer this over listing and then reading each
        instance."""
        tenant = await _guard("sdlc", scope=scope, sdlc_op="read")
        live = await _live()
        async with _refusing():
            return await board_summary_impl(
                live, scope or live.default_scope(tenant), tenant, recent)

    @server.tool(run_in_thread=False)
    async def board_item(
        name: str, kind: str | None = None, scope: str | None = None,
    ) -> dict[str, Any]:
        """One work item's FULL detail by ``name`` — title, status, description,
        acceptance_criteria, definition_of_done, the timeline, feature/epic refs
        and produces. ``kind`` is a hint (Story / Feature / Epic / Issue / Spike);
        omitted, the work-item Kinds are probed in order."""
        tenant = await _guard("sdlc", scope=scope, sdlc_op="read")
        live = await _live()
        async with _refusing():
            return await board_item_impl(
                live, scope or live.default_scope(tenant), name, tenant, kind)

    # -- memory --------------------------------------------------------------

    @server.tool(run_in_thread=False, app=memory_card_app)
    async def recall(
        query: str, scope: str | None = None, k: int = 5, personal: bool = False,
        as_of: str | None = None,
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

        **``scope`` is IGNORED when ``personal=true``.** Personal memory has ONE
        home — the server's base scope — because that is where every personal
        WRITE lands; honouring a workspace scope here would search a place
        nothing writes to and return an empty result that looks like an answer.
        The response's ``scope`` field always reports the scope actually read,
        so the drop is visible rather than documented-and-forgotten.

        The result reports its own mode: ``degraded: true`` + ``semantic:
        false`` means the search was a LITERAL token match, not semantic
        similarity — an empty result in that mode only proves no stored memory
        shares a word with the query. When relaying such an empty result, say
        the search was literal-only; never assert that no memories exist.
        ``index_refreshed: false`` (with ``index_error``) means the search index
        could not be refreshed, so anything written recently is INVISIBLE to
        this result — it is not read-your-writes, and ``degraded`` is set.

        **``as_of`` (ISO-8601, e.g. ``2026-08-01T12:00:00Z``) asks a DIFFERENT
        question:** what this deployment BELIEVED at that instant, not what it
        believes now. Each hit comes back as it was RECORDED then, so a memory
        later corrected or superseded answers with its old content, and one
        written after that instant does not appear at all. Use it for "what did
        we think last month?", never for "what was true last month" — those are
        different axes. The result echoes ``as_of``; any memory the store can no
        longer answer for (history pruned past that point) is listed by name in
        ``as_of_truncated``, and when relaying you must say the answer is
        incomplete for those rather than implying they did not exist."""
        if personal:
            oid, family = await _personal_guard("read")
            async with _refusing():
                return await recall_impl(
                    await _live(), query, None, k, memory_scope="personal",
                    oid=oid, family=family, as_of=as_of,
                )
        tenant = await _guard("memory", scope=scope, memory_op="read")
        async with _refusing():
            return await recall_impl(
                await _live(), query, scope, k, tenant, as_of=as_of,
            )

    @server.tool(run_in_thread=False, description=_REMEMBER_DESCRIPTION)
    async def remember(
        summary: str,
        scope: str | None = None,
        area: str = "general",
        affect: str = "triumph",
        tags: list[str] | None = None,
        owner: str = "mcp",
        personal: bool = False,
        claims: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Persist a memory (an Engram) so future recalls surface it.

        ⚠️ The text a CLIENT reads is :data:`_REMEMBER_DESCRIPTION`, not this
        docstring — it interpolates ``dna.memory.contradiction.WHEN_TO_CLAIM``,
        the ONE statement of when a claim is worth declaring, which a docstring
        literal cannot splice. Change the instruction there, never here, or the
        two drift and only the wire one is read."""
        if personal:
            oid, family = await _personal_guard("write")
            async with _refusing():
                return await remember_impl(
                    await _live(), summary, None, area=area, affect=affect,
                    tags=tags, owner=owner, claims=claims,
                    memory_scope="personal", oid=oid, family=family,
                )
        tenant = await _guard("memory", scope=scope, memory_op="write")
        async with _refusing():
            return await remember_impl(
                await _live(), summary, scope, area=area, affect=affect,
                tags=tags, owner=owner, claims=claims, tenant=tenant,
            )

    # `personal=` on the three tools below (i-… follow-up): `recall` and
    # `remember` have carried the flag since personal memory shipped, so a
    # personal Engram could be written and read — and then never listed, never
    # forgotten and never consolidated, because these three had no way to name
    # the partition. `forget` was the worst of it: it answered `forgotten: false`
    # for a memory it simply could not see, which is the same word it uses for
    # "already forgotten" — so the caller could not tell "you have no such
    # memory" from "there is nothing left to do".

    @server.tool(run_in_thread=False)
    async def consolidate(
        scope: str | None = None, apply: bool = False, dry_run: bool = False,
        personal: bool = False,
    ) -> dict[str, Any]:
        """Deterministic memory consolidation pass (retention re-score).

        ``dry_run=true`` previews the pass with ZERO effect (wins over
        ``apply``): the report adds per-memory ``actions`` (retain / expire /
        already_expired, each with its deterministic reason) plus
        ``merge_candidates`` (groups of overlapping memories with a proposed
        supersede fusion) — show it to the human FIRST, then call again with
        ``apply=true`` once approved.

        ``dry_run`` also returns **``contradictions``**: memories this workspace
        believes AT THE SAME TIME that assert different values for the same
        ``(subject, predicate)`` — the memory that was true when it was written
        and is false now. Each entry names the conflicting memories, the claims
        that clash, and a ``proposal`` whose ``strategy`` is
        ``await_confirmation``: this pass never resolves one, not even with
        ``apply=true``. RELAY THEM — answering from one side of a contradiction
        without saying the other side exists is the failure this report was
        built to stop. ``undecided`` lists memories about the same subject that
        the rule could NOT judge; report those as unresolved, never as
        agreement.

        ``personal=true`` consolidates ONLY your own private partition — never
        the workspace's shared memory."""
        if personal:
            oid, family = await _personal_guard("write")
            async with _refusing():
                return await consolidate_impl(
                    await _live(), None, apply=apply, dry_run=dry_run,
                    memory_scope="personal", oid=oid, family=family,
                )
        tenant = await _guard("memory", scope=scope, memory_op="write")
        async with _refusing():
            return await consolidate_impl(
                await _live(), scope, apply=apply, dry_run=dry_run,
                tenant=tenant)

    @server.tool(run_in_thread=False, app=memory_card_app)
    async def list_memories(
        scope: str | None = None, personal: bool = False,
    ) -> dict[str, Any]:
        """List your stored memories (tenant-scoped). Read-only.

        ``personal=true`` lists YOUR OWN private memories (identity-keyed,
        portable across workspaces + clients) unioned with the shared base
        defaults — each item's ``personal`` flag says which partition it came
        from. The default (``false``) lists the workspace's shared memory.

        The declaration points the ``ui://dna/memory-list`` MCP Apps card
        (SEP-1865): a host that renders MCP Apps shows the memory list as a
        read-only card in a sandboxed iframe, fed by this result's
        ``structured_content`` — DNA's "your context follows you across every
        client" thesis made visible. Hosts without MCP Apps read the plain
        data from ``content``, unchanged (graceful degradation)."""
        if personal:
            oid, family = await _personal_guard("read")
            async with _refusing():
                data = await list_memories_impl(
                    await _live(), None, memory_scope="personal", oid=oid,
                    family=family,
                )
            return _with_memory_card(data)
        tenant = await _guard("memory", scope=scope, memory_op="read")
        async with _refusing():
            data = await list_memories_impl(await _live(), scope, tenant=tenant)
        return _with_memory_card(data)

    @server.tool(run_in_thread=False)
    async def forget(
        name: str, scope: str | None = None, personal: bool = False,
    ) -> dict[str, Any]:
        """Forget one memory by name — a bi-temporal demotion (revivable), not a
        hard delete, and only in your own layer. A write op.

        ``personal=true`` forgets from YOUR OWN private partition; the default
        (``false``) forgets from the workspace's shared memory.

        The result's ``outcome`` distinguishes the three endings: ``forgotten``
        (it was live, now it is not), ``already_forgotten`` (idempotent — nothing
        to do) and ``not_found`` (no such memory in this layer — check the name,
        or ``personal``). ``forgotten: bool`` is kept for existing callers."""
        if personal:
            oid, family = await _personal_guard("write")
            async with _refusing():
                return await forget_impl(
                    await _live(), name, None, memory_scope="personal", oid=oid,
                    family=family,
                )
        tenant = await _guard("memory", scope=scope, memory_op="write")
        async with _refusing():
            return await forget_impl(await _live(), name, scope, tenant=tenant)

    # -- instances (GENERIC, registry-driven — every Kind, not a hand-written list)
    #
    # The tools above name ONE Kind each. These four name none: they loop over
    # the Kind registry at call time, so the 76 registered Kinds (49 of them
    # record-plane, most declared purely by a `*.kind.yaml` descriptor) stop
    # being invisible to an agent just because nobody hand-wrote tools for them.
    # Same `_guard` seam as everything else — with the metered family DERIVED
    # from the target Kind, so a generic tool can never be the cheap door into a
    # family the caller's tier gates (see `dna_cli._mcp_instances`).
    from dna_cli._mcp_instances import register_instance_tools

    register_instance_tools(
        server, live=_live, guard=_guard, plan_families=_plan_families,
    )

    # -- Kind authoring (the tenant declares its OWN Kind, conversationally) --
    #
    # The third face of the same door: the portal and the REST API already write
    # a tenant's `KindDefinition`, and a Kind born in one face and absent from
    # the others is worth nothing. Same shared core (`dna.application.
    # kind_authoring`), same `_guard` seam, metered as `definitions`.
    #
    # TWO tools, and the missing third is the point: there is no `approve_kind`.
    # Approval is what CONFERS effect (the registry withholds registration until
    # `spec.approved_by` names someone), so an agent able to call it could
    # approve its own proposal and the gate would be decorative. Approving stays
    # a human act on the portal, made with a reviewer's own credential.
    from dna_cli._mcp_kinds import register_kind_tools

    register_kind_tools(server, live=_live, guard=_guard)

    # -- the portfolio door: workspaces / projects / repos / orgs ------------
    #
    # These Kinds were always reachable through the generic instance door, and
    # the application seams already served the REST face. What was missing was
    # a NAME — and a catalog of 78 Kinds with no named tool is discoverable
    # only by luck. `list_projects` also carries the one sentence that joins
    # the halves: a project's `board_scope` IS its board's scope, which is how
    # a caller gets from the roster to `board_summary`.
    from dna_cli._mcp_portfolio import register_portfolio_tools

    register_portfolio_tools(server, live=_live, guard=_guard)

    # -- resources (prove resources beyond tools) ----------------------------

    @server.resource("dna://{scope}/manifest")
    async def manifest_resource(scope: str) -> dict[str, Any]:
        """The scope's manifest as a resource: its Kinds → instance names."""
        mi = await (await _live()).mi(scope, await _guard("definitions", scope=scope))
        by_kind: dict[str, list[str]] = {}
        for d in mi.instances:
            by_kind.setdefault(d.kind, []).append(d.name)
        return {"scope": mi.scope, "instances": {k: sorted(v) for k, v in by_kind.items()}}

    @server.resource("dna://{scope}/agents")
    async def agents_resource(scope: str) -> dict[str, Any]:
        """The scope's agent roster as a resource."""
        return await list_agents_impl(await _live(), scope, await _guard("definitions", scope=scope))

    @server.resource(UI_PREFAB_URI, mime_type=MCP_APP_MIME)
    def prefab_card_renderer() -> str:
        """The ONE MCP Apps renderer every Prefab card on this face points at
        (SEP-1865) — Prefab's bundled single-file renderer with the host-theme
        bridge appended to its ``<head>``.

        Shared on purpose: the default mints one renderer resource per tool,
        and in bundled mode that is a separate 6.6 MB instance each. Static,
        public and data-free (cacheable by URI): the host pushes each tool
        result's ``structured_content`` into it over the authenticated
        session."""
        return prefab_renderer_html()

    @server.resource(UI_MEMORY_LIST_URI, mime_type=MCP_APP_MIME)
    def memory_list_card() -> str:
        """The MCP Apps template for the memory card (SEP-1865) — the resource
        the ``list_memories``/``recall`` declarations point at. Static, public
        and data-free (cacheable by URI): the host pushes each tool result's
        ``structured_content`` into it over the authenticated session."""
        return memory_list_card_html()

    from dna.emit.mcp_ui import UI_KIND_DRAFT_URI, kind_draft_card_html

    @server.resource(UI_KIND_DRAFT_URI, mime_type=MCP_APP_MIME)
    def kind_draft_card() -> str:
        """O template MCP Apps do Kind autorado (Kind Studio F3) — o recurso
        que a declaração de ``author_kind`` aponta. Estático, público e sem
        dado; INTERATIVO: edita as linhas do schema e reautora via
        ``callServerTool`` (aprovação continua humana, no portal)."""
        return kind_draft_card_html()

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

    # MCP Apps negotiation (SEP-1865), both directions — see the section above:
    # we DECLARE the extension with the mimeType we serve, and we CHECK the
    # client's own declaration per call before advertising a UI-enabled tool.
    _declare_ui_extension(server)
    server.add_middleware(_ui_capability_middleware())

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
