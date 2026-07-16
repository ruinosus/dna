"""Story ``s-aob-microsoft-as-port`` — the Microsoft OBO behind the port.

``MicrosoftOboProvider`` is the REFERENCE implementation of :class:`ActOnBehalfPort`
(ADR-act-on-behalf-port §4.3 / §8-2): it wraps the shipped, unchanged
``graph._obo.exchange_on_behalf_of`` so its behavior is identical to ``ADR-mcp-obo``.
These tests prove the port satisfies the contract AND that the OBO security posture
(per-request / never-persisted / never-returned, fail-closed scope allow-list, honest
capability gap for a non-Entra identity) survives the wrapping verbatim.

The no-regression proof for the *shipped tools* lives in the untouched
``test_mcp_graph.py`` (still green); this file proves the port façade over the same
exchanger.
"""
from __future__ import annotations

import asyncio

import pytest

from dna_cli.act_on_behalf import ActContext, ActOnBehalfUnavailable, UserCredential
from dna_cli.act_on_behalf._microsoft import MicrosoftOboProvider
from dna_cli.graph import errors as E

_TID = "11111111-2222-3333-4444-555555555555"
_ASSERTION = "eyJ.inbound-user-token.sig"
_TOKEN_B = "eyJ.graph-audience-token-B.sig"


def _ok_acquirer(recorder: dict | None = None):
    def acquire(*, client_id, client_secret, authority, assertion, scopes):
        if recorder is not None:
            recorder.update(
                client_id=client_id, authority=authority, assertion=assertion,
                scopes=list(scopes),
            )
        return {"access_token": _TOKEN_B, "expires_in": 3600, "token_type": "Bearer"}

    return acquire


def _err_acquirer(result: dict):
    def acquire(**_):
        return result

    return acquire


def _ms(acquire, **over) -> MicrosoftOboProvider:
    base = dict(
        client_id="app", client_secret="secret",
        allowed_scopes=["Calendars.Read"], supported_capabilities={"calendar"},
        acquire=acquire,
    )
    base.update(over)
    return MicrosoftOboProvider(**base)


def _entra_ctx(**over) -> ActContext:
    base = dict(
        provider_hint="microsoft", tenant="ws-1", subject="oid-1",
        raw_token=_ASSERTION, claims={"tid": _TID},
    )
    base.update(over)
    return ActContext(**base)


# ── the port contract, satisfied ───────────────────────────────────────────


def test_provider_family_is_microsoft():
    assert _ms(_ok_acquirer()).provider == "microsoft"


def test_supports_reflects_the_configured_capabilities():
    prov = _ms(_ok_acquirer(), supported_capabilities={"calendar"})
    assert prov.supports("calendar") is True
    assert prov.supports("mail") is False


# ── credential_for = the OBO exchange, wrapped ─────────────────────────────


def test_credential_for_yields_a_graph_user_credential():
    prov = _ms(_ok_acquirer())
    cred = asyncio.run(prov.credential_for(_entra_ctx(), "calendar", ["Calendars.Read"]))
    assert isinstance(cred, UserCredential)
    assert cred.bearer == _TOKEN_B
    assert "graph.microsoft.com" in cred.api_base


def test_credential_for_exchanges_at_the_assertions_home_tenant():
    """Multi-tenant correctness preserved: the OBO authority is the ctx's own tid."""
    rec: dict = {}
    prov = _ms(_ok_acquirer(rec))
    asyncio.run(prov.credential_for(_entra_ctx(), "calendar", ["Calendars.Read"]))
    assert rec["authority"] == f"https://login.microsoftonline.com/{_TID}"
    assert rec["assertion"] == _ASSERTION  # the inbound token IS the assertion.
    assert rec["scopes"] == ["Calendars.Read"]


def test_non_entra_identity_is_act_on_behalf_unavailable_not_a_crash():
    """A non-Entra ctx (no raw_token / no tid) is an honest capability gap — the
    Microsoft impl cannot act (no assertion to exchange). Maps OboUnavailableError
    → ActOnBehalfUnavailable."""
    prov = _ms(_ok_acquirer())
    with pytest.raises(ActOnBehalfUnavailable):
        asyncio.run(prov.credential_for(
            _entra_ctx(raw_token=None), "calendar", ["Calendars.Read"]
        ))
    with pytest.raises(ActOnBehalfUnavailable):
        asyncio.run(prov.credential_for(
            _entra_ctx(claims={}), "calendar", ["Calendars.Read"]  # no tid
        ))


def test_scope_allow_list_is_fail_closed_through_the_port():
    """A capability cannot request a scope outside the provider's allow-list — the
    exchanger refuses BEFORE any exchange (defense in depth, preserved)."""
    called = {"n": 0}

    def acquire(**_):
        called["n"] += 1
        return {"access_token": _TOKEN_B}

    prov = _ms(acquire, allowed_scopes=["Calendars.Read"])
    with pytest.raises(E.OboScopeNotAllowedError):
        asyncio.run(prov.credential_for(_entra_ctx(), "calendar", ["Mail.Send"]))
    assert called["n"] == 0  # never reached the exchange.


def test_credential_never_leaks_the_assertion_or_secret():
    """The UserCredential carries the downstream token B for immediate use, but the
    inbound assertion and the client secret never appear on it."""
    prov = _ms(_ok_acquirer())
    cred = asyncio.run(prov.credential_for(_entra_ctx(), "calendar", ["Calendars.Read"]))
    blob = repr(cred)
    assert _ASSERTION not in blob
    assert "secret" not in blob


def test_consent_error_surfaces_honestly_through_the_port():
    result = {
        "error": "invalid_grant",
        "error_description": "AADSTS65001: not consented.",
        "error_codes": [65001],
    }
    prov = _ms(_err_acquirer(result))
    with pytest.raises(E.OboConsentRequiredError):
        asyncio.run(prov.credential_for(_entra_ctx(), "calendar", ["Calendars.Read"]))
