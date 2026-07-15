"""``dna_cli.graph._tools`` — the built-in ``ms_calendar_list`` OBO tool.

Story ``s-mcp-obo-calendar-tool`` (ADR-mcp-obo §6). A THIN adapter, exactly like
the other MCP tools: the tenancy/quota ``_guard`` seam → resolve the inbound Entra
assertion → OBO exchange for the group's scope (:func:`dna_cli.graph._obo`) → one
Microsoft Graph call → a shaped, token-free result.

Two properties matter:

* **The surface is DATA.** ``description`` + ``input_schema`` come from the governed
  Tool doc ``tools/ms_calendar_list.yaml`` (:func:`tool_surface`) — not hardcoded —
  so the model's view is overlayable like any Tool.
* **Token B never leaves.** The Graph token is acquired per request, used on the
  single outbound Graph ``Authorization`` header, and dropped. The tool returns
  domain events only; :func:`shape_calendar` copies named fields (never the token,
  never the raw Graph body).
"""
from __future__ import annotations

import functools
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from dna.tools import ToolSurface

from . import _config as C
from . import _obo as O
from .errors import OboError, OboUnavailableError

_TOOLS_DIR = Path(__file__).resolve().parent / "tools"
_GRAPH_BASE = "https://graph.microsoft.com/v1.0"

#: Injectable Graph transport: ``(url, token, params) -> json dict``. Default does
#: a real httpx GET; tests inject a fake so no network/token is needed.
GraphCall = Callable[..., Awaitable[dict[str, Any]]]


@functools.lru_cache(maxsize=None)
def _load_doc(name: str) -> dict[str, Any]:
    import yaml

    path = _TOOLS_DIR / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"graph Tool doc not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def tool_surface(name: str) -> ToolSurface:
    """The governed agent-facing surface (description + parameters) of a graph
    Tool doc — the SAME projection ``dna.load_tools`` serves, read from the
    packaged Tool YAML so the built-in tool's description is data, not code."""
    doc = _load_doc(name)
    meta = doc.get("metadata") or {}
    spec = doc.get("spec") or {}
    return ToolSurface(
        description=str(meta.get("description") or "").strip(),
        parameters=dict(spec.get("input_schema") or {}),
    )


# ── Graph response shaping (pure) ──────────────────────────────────────────


def shape_calendar(raw: dict[str, Any]) -> dict[str, Any]:
    """Shape a Graph ``calendarView`` / ``events`` response into a compact,
    token-free result. Copies only named fields — tolerant of missing ones."""
    events = []
    for ev in (raw or {}).get("value") or []:
        events.append({
            "id": ev.get("id"),
            "subject": ev.get("subject") or "(no subject)",
            "start": ((ev.get("start") or {}).get("dateTime")),
            "end": ((ev.get("end") or {}).get("dateTime")),
            "location": ((ev.get("location") or {}).get("displayName")),
            "organizer": (((ev.get("organizer") or {}).get("emailAddress") or {}).get("name")),
            "web_link": ev.get("webLink"),
        })
    return {"count": len(events), "events": events}


def _default_window(start: str | None, end: str | None) -> tuple[str, str]:
    """Default the calendarView window to [today 00:00 UTC, +7d) when omitted."""
    if not start:
        now = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        start = now.isoformat().replace("+00:00", "Z")
    if not end:
        try:
            base = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            base = datetime.now(timezone.utc)
        end = (base + timedelta(days=7)).isoformat().replace("+00:00", "Z")
    return start, end


async def _default_graph_call(
    url: str, token: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """A real Microsoft Graph GET (httpx). Sends token B on the Authorization
    header; returns the JSON body. Never logs the token."""
    try:
        import httpx
    except ModuleNotFoundError as exc:  # pragma: no cover — exercised via CLI
        from .errors import OboExchangeError

        raise OboExchangeError(
            "the Microsoft Graph call needs the optional 'httpx' dependency — "
            "install it with: pip install 'dna-cli[graph]'"
        ) from exc

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            url, params=params or {},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        if resp.status_code >= 400:
            # Map to an honest, sanitized tool error — never echo the raw body.
            from .errors import OboExchangeError

            raise OboExchangeError(
                f"Microsoft Graph returned HTTP {resp.status_code} for the calendar "
                "request."
            )
        return resp.json()


async def calendar_list_impl(
    *,
    assertion: str | None,
    tid: str | None,
    client_id: str | None,
    client_secret: str | None,
    scopes: list[str],
    start: str | None = None,
    end: str | None = None,
    top: int = 25,
    acquire: O.Acquirer = O._default_acquire,
    graph_call: GraphCall = _default_graph_call,
) -> dict[str, Any]:
    """The calendar-list use-case: OBO exchange → Graph ``calendarView`` → shape.

    Fully injectable (``acquire`` + ``graph_call``) so it is unit-testable with no
    live Entra / Graph. Raises the honest :mod:`dna_cli.graph.errors` on any edge."""
    token_b = O.exchange_on_behalf_of(
        assertion=assertion, tid=tid, client_id=client_id,
        client_secret=client_secret, scopes=scopes, allowed_scopes=scopes,
        acquire=acquire,
    )
    win_start, win_end = _default_window(start, end)
    raw = await graph_call(
        f"{_GRAPH_BASE}/me/calendarView", token_b,
        {
            "startDateTime": win_start, "endDateTime": win_end,
            "$top": max(1, min(int(top or 25), 100)),
            "$select": "id,subject,start,end,location,organizer,webLink",
            "$orderby": "start/dateTime",
        },
    )
    # token_b goes out of scope here — never returned, never logged.
    return shape_calendar(raw)


# ── registration into the FastMCP server ───────────────────────────────────


def register_graph_tools(
    server: Any,
    cfg: C.GraphConfig,
    *,
    guard: Callable[..., Awaitable[Any]],
    obo_context: Callable[[], tuple[str | None, str | None]],
) -> list[str]:
    """Register the active ``graph.*`` tools on ``server`` (ADR §5 — built-in
    execution, config enablement).

    Only groups the config marks ACTIVE (block enabled AND group enabled) get
    their tools. With OBO off (``cfg is None`` handled by the caller) nothing is
    registered — the OSS/stdio path is untouched. ``guard`` is the tenancy/quota
    seam every tool passes through; ``obo_context`` yields the current request's
    (raw Entra assertion, tid) or ``(None, None)`` for a non-Entra identity.

    Returns the list of registered tool names (for the boot log / tests)."""
    from fastmcp.exceptions import ToolError

    registered: list[str] = []
    if cfg is None or not cfg.is_active("calendar"):
        return registered

    surface = tool_surface("ms_calendar_list")
    scopes = cfg.scopes_for("calendar")

    @server.tool(name="ms_calendar_list", description=surface.description,
                 run_in_thread=False)
    async def ms_calendar_list(
        start: str | None = None, end: str | None = None, top: int = 25,
    ) -> dict[str, Any]:
        # Tenancy + quota (auth gating) — same seam as every other tool.
        await guard("definitions")
        assertion, tid = obo_context()
        if not assertion or not tid:
            raise ToolError(
                "Microsoft Graph is not available for this identity — the "
                "ms_calendar_list tool needs a Microsoft Entra sign-in (On-Behalf-Of "
                "has no assertion to exchange for this token)."
            )
        client_id = os.environ.get(cfg.client_id_env or "")
        client_secret = os.environ.get(cfg.credential_env or "")
        try:
            return await calendar_list_impl(
                assertion=assertion, tid=tid, client_id=client_id,
                client_secret=client_secret, scopes=scopes,
                start=start, end=end, top=top,
            )
        except OboUnavailableError as exc:
            raise ToolError(str(exc)) from None
        except OboError as exc:
            # consent / interaction / scope / exchange — all honest tool errors.
            raise ToolError(str(exc)) from None

    registered.append("ms_calendar_list")
    return registered
