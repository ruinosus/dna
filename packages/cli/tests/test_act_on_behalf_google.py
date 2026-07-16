"""Story ``s-aob-google-skeleton`` — a 2nd provider fits the SAME port.

``GoogleWorkspaceProvider`` implements :class:`ActOnBehalfPort` for calendar with the
network boundary STUBBED (injectable ``refresh_lookup`` + ``exchange`` seams — no live
Google). Proven here:

* the port is satisfied and yields a ``www.googleapis.com`` ``UserCredential`` from a
  fake dev token;
* ``credential_for`` NEVER reads ``ctx.raw_token`` — the Microsoft↔Google asymmetry
  (Google needs no inbound assertion), demonstrated concretely;
* fail-closed: unsupported capability, scope escalation, no consented token, and a
  missing client credential are each honest ``ActOnBehalfUnavailable`` (no crash, no
  leak);
* the neutral ``calendar_list`` routes a Google identity to ``GoogleWorkspaceProvider``
  (stubbed) instead of Microsoft — the agnosticism claim, end-to-end without a real
  Google Cloud project.
"""
from __future__ import annotations

import asyncio

import pytest

from dna_cli.act_on_behalf import ActContext, ActOnBehalfUnavailable, UserCredential
from dna_cli.act_on_behalf import _calendar as CAL
from dna_cli.act_on_behalf._dispatch import resolve_port
from dna_cli.act_on_behalf._google import (
    GOOGLE_API_BASE,
    GoogleScopeNotAllowedError,
    GoogleWorkspaceProvider,
)

_CAL_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
_DEV_ACCESS = "ya29.dev-access-token-stub"


def _google(**over) -> GoogleWorkspaceProvider:
    base = dict(
        client_id="gclient", client_secret="gsecret",
        allowed_scopes=[_CAL_SCOPE], supported_capabilities={"calendar"},
        refresh_lookup=lambda subject: "1//refresh-stub",
        exchange=lambda **kw: {"access_token": _DEV_ACCESS, "expires_in": 3600},
    )
    base.update(over)
    return GoogleWorkspaceProvider(**base)


def _google_ctx(**over) -> ActContext:
    base = dict(
        provider_hint="google", tenant="ws-1", subject="user@example.test",
        raw_token=None, claims={"hd": "example.test"},
    )
    base.update(over)
    return ActContext(**base)


# ── the port contract, satisfied by a 2nd provider ─────────────────────────


def test_provider_family_is_google_and_supports_calendar_only():
    prov = _google()
    assert prov.provider == "google"
    assert prov.supports("calendar") is True
    assert prov.supports("files") is False  # skeleton is calendar-only.
    assert prov.supports("mail") is False


def test_credential_for_yields_a_googleapis_credential_from_a_stub_token():
    prov = _google()
    cred = asyncio.run(prov.credential_for(_google_ctx(), "calendar", [_CAL_SCOPE]))
    assert isinstance(cred, UserCredential)
    assert cred.bearer == _DEV_ACCESS
    assert cred.api_base == GOOGLE_API_BASE


def test_credential_for_never_reads_raw_token_the_asymmetry():
    """The concrete proof the port abstracts the OUTCOME: Google acquires a
    credential with ctx.raw_token=None (no inbound assertion), where Microsoft OBO
    REQUIRES it. The exchange seam must be called with the refresh token, never the
    (absent) inbound assertion."""
    seen: dict = {}

    def fake_exchange(**kw):
        seen.update(kw)
        return {"access_token": _DEV_ACCESS, "expires_in": 3600}

    prov = _google(exchange=fake_exchange)
    cred = asyncio.run(prov.credential_for(
        _google_ctx(raw_token=None), "calendar", [_CAL_SCOPE]
    ))
    assert cred.bearer == _DEV_ACCESS
    assert seen["refresh_token"] == "1//refresh-stub"   # refresh drives it,
    assert "assertion" not in seen                       # NOT an inbound-token exchange.


# ── fail-closed / honest gaps (security) ───────────────────────────────────


def test_unsupported_capability_is_honest_gap():
    with pytest.raises(ActOnBehalfUnavailable):
        asyncio.run(_google().credential_for(_google_ctx(), "mail", ["m.read"]))


def test_scope_allow_list_is_fail_closed_before_any_exchange():
    called = {"n": 0}

    def exchange(**kw):
        called["n"] += 1
        return {"access_token": _DEV_ACCESS}

    prov = _google(exchange=exchange)
    with pytest.raises(GoogleScopeNotAllowedError):
        asyncio.run(prov.credential_for(
            _google_ctx(), "calendar",
            ["https://www.googleapis.com/auth/calendar"],  # read-WRITE, not allowed.
        ))
    assert called["n"] == 0  # never reached the exchange — fail-closed.


def test_no_consented_token_is_an_honest_gap_not_a_crash():
    """The skeleton has no consent flow → no refresh token → honest capability gap."""
    prov = _google(refresh_lookup=lambda subject: None)
    with pytest.raises(ActOnBehalfUnavailable):
        asyncio.run(prov.credential_for(_google_ctx(), "calendar", [_CAL_SCOPE]))


def test_missing_client_credential_is_a_clean_gap():
    prov = _google(client_secret=None)
    with pytest.raises(ActOnBehalfUnavailable):
        asyncio.run(prov.credential_for(_google_ctx(), "calendar", [_CAL_SCOPE]))


def test_failed_exchange_never_leaks_a_token_or_body():
    """A failure surfaces the error NAME only — never the refresh token, the raw
    description, or any token-ish blob."""
    prov = _google(exchange=lambda **kw: {
        "error": "invalid_grant",
        "error_description": "leaked 1//refresh-stub ya29.some-token-value-here",
    })
    with pytest.raises(ActOnBehalfUnavailable) as exc:
        asyncio.run(prov.credential_for(_google_ctx(), "calendar", [_CAL_SCOPE]))
    msg = str(exc.value)
    assert "1//refresh-stub" not in msg
    assert "ya29.some-token-value-here" not in msg


# ── the agnosticism claim: neutral calendar_list → Google (stubbed) ────────


def test_neutral_calendar_list_routes_google_identity_to_google_provider():
    """The SAME neutral tool + a registry with both providers: a Google identity
    resolves to GoogleWorkspaceProvider and hits googleapis — no Microsoft, no real
    Google Cloud project."""
    seen: dict = {}

    async def fake_http(url, bearer, params=None):
        seen["url"] = url
        seen["bearer"] = bearer
        return {"items": [
            {"id": "g1", "summary": "Design review",
             "start": {"dateTime": "2026-07-16T14:00:00Z"},
             "end": {"dateTime": "2026-07-16T15:00:00Z"}},
        ]}

    registry = {"google": _google()}
    port = resolve_port(registry, "google")
    assert port.provider == "google"

    out = asyncio.run(CAL.calendar_list(
        port, _google_ctx(), [_CAL_SCOPE], http_call=fake_http,
    ))
    assert "/calendar/v3/calendars/primary/events" in seen["url"]  # Google API.
    assert seen["bearer"] == _DEV_ACCESS
    assert out["count"] == 1 and out["events"][0]["subject"] == "Design review"
    assert _DEV_ACCESS not in str(out)  # bearer never surfaced.


def test_google_off_by_default_is_fail_closed():
    """With Google not in the registry (its config surface is deferred), a Google
    identity is an honest gap — OSS/stdio and the Microsoft-only deployment are
    untouched."""
    registry = {"microsoft": object()}  # only Microsoft enabled.
    with pytest.raises(ActOnBehalfUnavailable):
        resolve_port(registry, "google")
