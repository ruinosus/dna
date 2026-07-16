"""``dna_cli.act_on_behalf._calendar`` — the provider-neutral ``calendar_list`` (B).

Step (B) of the flow (ADR-act-on-behalf-port §4.1 / §5): a capability adapter
written **once** that consumes a :class:`UserCredential` from any
:class:`ActOnBehalfPort` and returns a **neutral** shaped result — the same
``{count, events:[{id, subject, start, end, location, organizer, web_link}]}`` shape
whether Microsoft Graph or Google Calendar served it. The adapter never sees whether
the credential came from an OBO exchange, a Google OAuth refresh, or DWD — it sees
only ``bearer`` + ``api_base``.

The one place providers legitimately differ in (B) is the *API shape* (Graph
``/me/calendarView`` vs Google ``events.list``) — NOT the acquire mechanism. That
small per-provider surface lives here, keyed by ``port.provider``, each mapping onto
the ONE neutral event shape. The Microsoft binding reuses the shipped
``graph._tools`` shaping verbatim, so the neutral tool's Microsoft output is
byte-identical to ``ms_calendar_list`` (which stays callable as the alias).

The outbound HTTP call is an injectable seam (``http_call``) so the whole adapter is
unit-testable with no live network / no token — the same discipline as ``graph._obo``
and ``graph._tools``.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from ..graph import _tools as T
from ._port import ActContext, ActOnBehalfPort, ActOnBehalfUnavailable, UserCredential

#: Injectable HTTP transport: ``(url, bearer, params) -> json dict``. The default
#: reuses ``graph._tools._default_graph_call`` (a real httpx GET that sends the
#: bearer and never logs it); tests inject a fake so no network/token is needed.
HttpCall = Callable[..., Awaitable[dict[str, Any]]]


def shape_google_calendar(raw: dict[str, Any]) -> dict[str, Any]:
    """Shape a Google Calendar ``events.list`` response into the SAME neutral event
    shape ``graph._tools.shape_calendar`` produces — proving the neutral output is
    provider-independent. Copies only named fields; token-free by construction."""
    events = []
    for ev in (raw or {}).get("items") or []:
        start = (ev.get("start") or {})
        end = (ev.get("end") or {})
        events.append({
            "id": ev.get("id"),
            "subject": ev.get("summary") or "(no subject)",
            "start": start.get("dateTime") or start.get("date"),
            "end": end.get("dateTime") or end.get("date"),
            "location": ev.get("location"),
            "organizer": ((ev.get("organizer") or {}).get("displayName")
                          or (ev.get("organizer") or {}).get("email")),
            "web_link": ev.get("htmlLink"),
        })
    return {"count": len(events), "events": events}


def _microsoft_calendar_request(
    cred: UserCredential, start: str | None, end: str | None, top: int
) -> tuple[str, dict[str, Any]]:
    """The Graph ``calendarView`` request from a UserCredential — identical to the
    shipped ``ms_calendar_list`` call (reuses ``graph._tools`` helpers)."""
    win_start, win_end = T._default_window(start, end)
    url = f"{cred.api_base}/me/calendarView"
    params = {
        "startDateTime": win_start, "endDateTime": win_end,
        "$top": max(1, min(int(top or 25), 100)),
        "$select": "id,subject,start,end,location,organizer,webLink",
        "$orderby": "start/dateTime",
    }
    return url, params


def _google_calendar_request(
    cred: UserCredential, start: str | None, end: str | None, top: int
) -> tuple[str, dict[str, Any]]:
    """The Google Calendar ``events.list`` request from a UserCredential (the
    provider's own API shape; the neutral output is identical)."""
    win_start, win_end = T._default_window(start, end)
    url = f"{cred.api_base}/calendar/v3/calendars/primary/events"
    params = {
        "timeMin": win_start, "timeMax": win_end,
        "maxResults": max(1, min(int(top or 25), 100)),
        "singleEvents": "true", "orderBy": "startTime",
    }
    return url, params


#: Per-provider calendar binding: how to build the request + shape the response for
#: each ``ActOnBehalfPort.provider``. Each maps onto the ONE neutral event shape.
_CALENDAR_BINDINGS: dict[str, tuple[Callable[..., tuple[str, dict[str, Any]]],
                                    Callable[[dict[str, Any]], dict[str, Any]]]] = {
    "microsoft": (_microsoft_calendar_request, T.shape_calendar),
    "google": (_google_calendar_request, shape_google_calendar),
}


async def calendar_list(
    port: ActOnBehalfPort,
    ctx: ActContext,
    scopes: list[str],
    *,
    start: str | None = None,
    end: str | None = None,
    top: int = 25,
    http_call: HttpCall = T._default_graph_call,
) -> dict[str, Any]:
    """List the signed-in user's calendar events, on their behalf, provider-neutral.

    Step (A): ``port.credential_for(ctx, "calendar", scopes)`` acquires a
    request-lifetime :class:`UserCredential` (OBO / OAuth / DWD — invisible here).
    Step (B): the provider's calendar API is called with that credential and the
    response shaped into the ONE neutral event shape. The bearer is used on the
    single outbound call and dropped — never returned in the result.

    Raises :class:`ActOnBehalfUnavailable` when the resolved provider has no calendar
    binding (an honest gap). Any provider-level error (consent / scope / exchange)
    propagates from ``credential_for`` unchanged for the caller to map."""
    binding = _CALENDAR_BINDINGS.get(port.provider)
    if binding is None:
        raise ActOnBehalfUnavailable(
            f"the {port.provider!r} provider has no calendar binding in this PoC."
        )
    build_request, shape = binding

    cred = await port.credential_for(ctx, "calendar", scopes)
    url, params = build_request(cred, start, end, top)
    raw = await http_call(url, cred.bearer, params)
    # cred.bearer goes out of scope here — never returned, never logged.
    return shape(raw)
