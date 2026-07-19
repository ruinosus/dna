"""Story ``s-aob-neutral-calendar`` — provider-family stamp + neutral dispatch.

Three things proven (all pure / fake-injected, no live network):

1. **Provider-family stamp** — ``provider_family_for_type`` maps ``entra →
   microsoft`` / ``google → google`` (else ``None``), the outbound twin of the
   inbound tenant-claim stamp.
2. **``resolve_port``** — a verified provider family selects its ``ActOnBehalfPort``
   from the registry; an unregistered / absent family is an honest
   ``ActOnBehalfUnavailable``.
3. **The neutral ``calendar_list`` adapter** — consumes a ``UserCredential`` from
   *whatever* port and returns the ONE neutral event shape; a Microsoft-family port
   and a Google-family port each route to their own API binding.
"""
from __future__ import annotations

import asyncio

import pytest

from dna_cli import _mcp_auth as A
from dna_cli.act_on_behalf import ActContext, ActOnBehalfUnavailable, UserCredential
from dna_cli.act_on_behalf import _calendar as CAL
from dna_cli.act_on_behalf._dispatch import resolve_port


# ── 1. the provider-family stamp ───────────────────────────────────────────


def test_provider_family_for_type_maps_actable_providers():
    assert A.provider_family_for_type("entra") == "microsoft"
    assert A.provider_family_for_type("google") == "google"


def test_workos_shares_the_google_family_for_personal_memory_key_reuse():
    """``s-consumer-lane-memory-key``: ``workos`` (Lane B / AuthKit, the consumer
    sign-in IdP) is mapped into the SAME ``"google"`` family as the Google Workspace
    IdP — NOT because a WorkOS identity is a Google one, but because personal
    memory's ``personal:google:<sub>`` namespaced-key shape is reused for the
    consumer lane (see ``identity_claim_for_family``).

    Side effect worth documenting: this table is ALSO the act-on-behalf dispatch
    registry key (``resolve_port``), so a WorkOS-authenticated caller now resolves
    to the same family as a Google identity there too. That is harmless in
    practice — ``GoogleWorkspaceProvider.credential_for`` never reads the inbound
    token; it looks up a separately-consented Google refresh token by subject, and
    nothing ever populates one for a WorkOS subject, so the request still fails
    closed (``ActOnBehalfUnavailable: no consented credential ... yet``) instead of
    the previous "no Microsoft/Google family" message. No live Google API is ever
    reachable via a WorkOS token."""
    assert A.provider_family_for_type("workos") == "google"


def test_provider_family_is_none_for_non_actable_identities():
    for t in ("clerk", "auth0", "oidc", "generic", None, ""):
        assert A.provider_family_for_type(t) is None


def test_google_is_a_known_provider_type_with_a_tenant_claim_default():
    """Google can be configured as an IdP (its ``hd`` hosted-domain is the tenant)
    without a code change — a config block, like every other provider."""
    provs = A.parse_auth_providers({"providers": [
        {"type": "google", "issuer": "https://accounts.google.com",
         "audience": "dna-mcp"},
    ]})
    assert provs[0].type == "google"
    assert provs[0].tenant_claim == "hd"


# ── 2. resolve_port (identity → provider) ──────────────────────────────────


class _FamilyPort:
    def __init__(self, provider: str):
        self.provider = provider

    def supports(self, capability: str) -> bool:
        return capability == "calendar"

    async def credential_for(self, ctx, capability, scopes):
        return UserCredential(
            bearer=f"{self.provider}-token",
            api_base=("https://graph.microsoft.com/v1.0" if self.provider == "microsoft"
                      else "https://www.googleapis.com"),
            expires_at=1.0,
        )


def test_resolve_port_selects_by_verified_provider_family():
    registry = {"microsoft": _FamilyPort("microsoft"), "google": _FamilyPort("google")}
    assert resolve_port(registry, "microsoft").provider == "microsoft"
    assert resolve_port(registry, "google").provider == "google"


def test_resolve_port_unregistered_family_is_honest_gap():
    registry = {"microsoft": _FamilyPort("microsoft")}
    with pytest.raises(ActOnBehalfUnavailable):
        resolve_port(registry, "google")       # enabled nowhere → honest gap.
    with pytest.raises(ActOnBehalfUnavailable):
        resolve_port(registry, None)           # no family at all → honest gap.
    with pytest.raises(ActOnBehalfUnavailable):
        resolve_port(registry, "")


# ── 3. the neutral calendar_list adapter, per provider ─────────────────────


def _ctx(provider: str) -> ActContext:
    return ActContext(
        provider_hint=provider, tenant="ws-1", subject="u",
        raw_token=("eyJ.tok.sig" if provider == "microsoft" else None),
        claims={"tid": "tid-1"} if provider == "microsoft" else {"hd": "x.test"},
    )


def test_neutral_calendar_dispatches_microsoft_to_graph():
    seen: dict = {}

    async def fake_http(url, bearer, params=None):
        seen["url"] = url
        seen["bearer"] = bearer
        return {"value": [
            {"id": "1", "subject": "Sync",
             "start": {"dateTime": "2026-07-16T10:00:00"},
             "end": {"dateTime": "2026-07-16T10:30:00"},
             "location": {"displayName": "Room A"},
             "organizer": {"emailAddress": {"name": "Robin"}},
             "webLink": "https://outlook.example.test/x"},
        ]}

    out = asyncio.run(CAL.calendar_list(
        _FamilyPort("microsoft"), _ctx("microsoft"), ["Calendars.Read"],
        http_call=fake_http,
    ))
    assert seen["url"].endswith("/me/calendarView")     # Graph API shape.
    assert seen["bearer"] == "microsoft-token"
    assert out["count"] == 1
    ev = out["events"][0]
    assert ev["subject"] == "Sync" and ev["location"] == "Room A"
    assert ev["organizer"] == "Robin"
    assert "microsoft-token" not in str(out)            # bearer never surfaced.


def test_neutral_calendar_dispatches_google_to_googleapis():
    """The SAME neutral adapter, a Google-family port → Google's events.list API →
    the SAME neutral event shape. This is the agnosticism claim, demonstrated."""
    seen: dict = {}

    async def fake_http(url, bearer, params=None):
        seen["url"] = url
        seen["bearer"] = bearer
        return {"items": [
            {"id": "g1", "summary": "Planning",
             "start": {"dateTime": "2026-07-16T11:00:00Z"},
             "end": {"dateTime": "2026-07-16T12:00:00Z"},
             "location": "HQ",
             "organizer": {"displayName": "Sam", "email": "sam@x.test"},
             "htmlLink": "https://calendar.google.test/x"},
        ]}

    out = asyncio.run(CAL.calendar_list(
        _FamilyPort("google"), _ctx("google"),
        ["https://www.googleapis.com/auth/calendar.readonly"],
        http_call=fake_http,
    ))
    assert "/calendar/v3/calendars/primary/events" in seen["url"]  # Google API shape.
    assert seen["bearer"] == "google-token"
    assert out["count"] == 1
    ev = out["events"][0]                                 # identical neutral shape.
    assert ev["subject"] == "Planning" and ev["location"] == "HQ"
    assert ev["organizer"] == "Sam"
    assert set(ev) == {"id", "subject", "start", "end", "location", "organizer", "web_link"}


def test_two_providers_produce_the_same_neutral_shape():
    """The keys of a Microsoft event and a Google event are identical — 'author once,
    operate anywhere' at the data layer."""
    ms = CAL.T.shape_calendar({"value": [{"id": "1", "subject": "A"}]})["events"][0]
    g = CAL.shape_google_calendar({"items": [{"id": "1", "summary": "A"}]})["events"][0]
    assert set(ms) == set(g)
