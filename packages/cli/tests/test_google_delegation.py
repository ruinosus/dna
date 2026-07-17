"""P3 Task 9 — Google delegated-token exchange (``graph/_google.py``).

The Lane B data analog of the OBO exchanger: fail-closed, scope-allow-listed,
sanitized errors, never logs a token. Tested against a FAKE ``acquire`` seam — no
live Google, no secret.
"""
from __future__ import annotations

import pytest

from dna_cli.graph._google import (
    GoogleConsentRequiredError,
    GoogleExchangeError,
    GoogleScopeNotAllowedError,
    GoogleUnavailableError,
    exchange_google,
)

_GMAIL = "https://www.googleapis.com/auth/gmail.readonly"
_DRIVE = "https://www.googleapis.com/auth/drive.readonly"


def _ok_acquire(**_):
    return {"access_token": "ya29.TOKEN_B", "expires_in": 3600}


def test_success_returns_access_token():
    tok = exchange_google(
        refresh_token="rt", client_id="cid", client_secret="sec",
        scopes=[_GMAIL], allowed_scopes=[_GMAIL, _DRIVE], acquire=_ok_acquire,
    )
    assert tok == "ya29.TOKEN_B"


def test_no_refresh_token_is_unavailable():
    with pytest.raises(GoogleUnavailableError):
        exchange_google(
            refresh_token=None, client_id="cid", client_secret="sec",
            scopes=[_GMAIL], acquire=_ok_acquire,
        )


def test_scope_outside_allowlist_refused_before_exchange():
    called = {"n": 0}

    def _spy(**_):
        called["n"] += 1
        return {"access_token": "x"}

    with pytest.raises(GoogleScopeNotAllowedError):
        exchange_google(
            refresh_token="rt", client_id="cid", client_secret="sec",
            scopes=[_DRIVE], allowed_scopes=[_GMAIL], acquire=_spy,
        )
    assert called["n"] == 0, "must refuse BEFORE calling the exchange"


def test_missing_credential_is_exchange_error():
    with pytest.raises(GoogleExchangeError):
        exchange_google(
            refresh_token="rt", client_id=None, client_secret=None,
            scopes=[_GMAIL], acquire=_ok_acquire,
        )


def test_invalid_grant_maps_to_consent_required():
    def _revoked(**_):
        return {"error": "invalid_grant", "error_description": "Token has been expired or revoked."}

    with pytest.raises(GoogleConsentRequiredError):
        exchange_google(
            refresh_token="rt", client_id="cid", client_secret="sec",
            scopes=[_GMAIL], acquire=_revoked,
        )


def test_other_error_is_sanitized_exchange_error():
    def _boom(**_):
        return {"error": "some_backend_detail", "error_description": "secret-ish body"}

    with pytest.raises(GoogleExchangeError) as ei:
        exchange_google(
            refresh_token="rt", client_id="cid", client_secret="sec",
            scopes=[_GMAIL], acquire=_boom,
        )
    # sanitized — the error name at most, never the raw body / a token
    assert "secret-ish body" not in str(ei.value)
