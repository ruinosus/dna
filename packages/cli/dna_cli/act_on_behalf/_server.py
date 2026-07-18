"""``dna_cli.act_on_behalf._server`` — register the neutral capability tools.

The MCP-runtime face of the port (ADR-act-on-behalf-port §5): register the
provider-**neutral** ``calendar_list`` tool that resolves the caller's provider from
their verified identity (the family stamp) and dispatches to the right
:class:`ActOnBehalfPort`. This is ADDED **alongside** the shipped ``ms_calendar_list``
/ ``ms_files_search`` / ``ms_file_read`` tools — those stay registered and unchanged
(``ms_calendar_list`` is the Microsoft *binding/alias* of the neutral tool, per §10).

Fail-closed and opt-in exactly like the graph tools: nothing registers unless the
config marks the ``calendar`` group active. The provider registry is built per
request (env creds read at call time, matching the shipped tools). For the PoC the
registry holds Microsoft; Google is off by default (its config surface is the
deferred ``s-aob-config-surface``) — a Google identity then gets an honest
``ActOnBehalfUnavailable`` until it is wired.
"""
from __future__ import annotations

import os
from typing import Any, Awaitable, Callable

from ..graph import _config as C
from ..graph._obo import _default_acquire
from ..graph.errors import OboError
from ._calendar import calendar_list
from ._dispatch import act_context_from_context, resolve_port
from ._google import GoogleWorkspaceProvider
from ._microsoft import MicrosoftOboProvider
from ._port import ActOnBehalfPort, ActOnBehalfUnavailable


def build_provider_registry(cfg: C.GraphConfig) -> dict[str, ActOnBehalfPort]:
    """Assemble the enabled ``ActOnBehalfPort`` registry from config — keyed by
    provider family (``"microsoft"`` / ``"google"``).

    PoC: Microsoft is built from the ``graph:`` block (the reference impl re-used as
    the port), reading the confidential-client id + secret from the env-var NAMES the
    config declares (never stored). **Google (Lane B data)** is registered when the
    ``calendar`` group is active AND the Google OAuth client creds are present
    (``DNA_MCP_GOOGLE_CLIENT_ID`` / ``DNA_MCP_GOOGLE_CLIENT_SECRET``); its per-user
    consent flow + refresh-token store is the remaining deferred piece (the port's
    ``refresh_lookup`` default returns ``None`` → an honest capability gap until it
    lands), so a Google identity gets "no consented credential yet", never a crash.
    Fail-closed, OSS/stdio untouched."""
    registry: dict[str, ActOnBehalfPort] = {}
    if cfg is not None and cfg.is_active("calendar"):
        registry["microsoft"] = MicrosoftOboProvider(
            client_id=os.environ.get(cfg.client_id_env or "") or None,
            client_secret=os.environ.get(cfg.credential_env or "") or None,
            allowed_scopes=cfg.scopes_for("calendar"),
            supported_capabilities={"calendar"},
            acquire=_default_acquire,
        )
        g_id = os.environ.get("DNA_MCP_GOOGLE_CLIENT_ID") or None
        g_secret = os.environ.get("DNA_MCP_GOOGLE_CLIENT_SECRET") or None
        if g_id and g_secret:
            g_scopes = [
                s.strip()
                for s in os.environ.get(
                    "DNA_MCP_GOOGLE_CALENDAR_SCOPES",
                    "https://www.googleapis.com/auth/calendar.readonly",
                ).split(",")
                if s.strip()
            ]
            registry["google"] = GoogleWorkspaceProvider(
                client_id=g_id, client_secret=g_secret,
                allowed_scopes=g_scopes, supported_capabilities={"calendar"},
            )
    return registry


def register_neutral_capabilities(
    server: Any,
    cfg: C.GraphConfig,
    *,
    guard: Callable[..., Awaitable[Any]],
    context_builder: Callable[[], Any] = act_context_from_context,
) -> list[str]:
    """Register the provider-neutral capability tools (currently ``calendar_list``).

    Registered ONLY when the ``calendar`` group is active (same gate as the graph
    tools). The tool resolves the port from the caller's verified provider family and
    dispatches; a non-actable / unconfigured identity is an honest capability
    ``ToolError`` (never a crash). Returns the registered tool names."""
    from fastmcp.exceptions import ToolError

    registered: list[str] = []
    if cfg is None or not cfg.is_active("calendar"):
        return registered

    scopes = cfg.scopes_for("calendar")

    @server.tool(
        name="calendar_list",
        description=(
            "List the signed-in user's calendar events in a time window, on their "
            "behalf — provider-neutral. Resolves your provider from your verified "
            "identity (Microsoft 365 today; Google Workspace when enabled) and reads "
            "your own calendar with a read-only, per-request delegated credential. "
            "The Microsoft binding is also callable as `ms_calendar_list`."
        ),
        run_in_thread=False,
    )
    async def calendar_list_tool(
        start: str | None = None, end: str | None = None, top: int = 25,
    ) -> dict[str, Any]:
        await guard("definitions")
        ctx = context_builder()
        if ctx is None:
            raise ToolError(
                "calendar_list needs a signed-in identity — no verified token on "
                "this request (On-Behalf-Of has nothing to act as)."
            )
        try:
            registry = build_provider_registry(cfg)
            port = resolve_port(registry, ctx.provider_hint)
            return await calendar_list(
                port, ctx, scopes, start=start, end=end, top=top,
            )
        except (ActOnBehalfUnavailable, OboError) as exc:
            # honest capability gap / consent / interaction / scope / exchange.
            raise ToolError(str(exc)) from None

    registered.append("calendar_list")
    return registered
