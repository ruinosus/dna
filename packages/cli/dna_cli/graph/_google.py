"""``dna_cli.graph._google`` — the per-request Google delegated-token exchange.

The consumer-lane (Lane B) analog of :mod:`dna_cli.graph._obo`. Given a user's
Google **refresh token** (obtained once via the incremental-consent grant with
our own Google OAuth client), the client credentials (env-var *names* in config),
and a requested Google API scope, it mints a short-lived **access token** for the
user's own Gmail / Drive / Calendar — then returns it for immediate use.

**The token lives only for the request.** This returns the token STRING to its
single caller (the Google read tool, which puts it on the outbound
``Authorization`` header and drops it). It is NEVER logged, persisted, cached, or
placed in a tool result — mirroring ``_obo.py``'s discipline.

The exchange is behind an injectable ``acquire`` seam so the whole policy — scope
allow-list and honest, sanitized error mapping — is unit-testable with a fake, no
live Google and no secret. The default seam POSTs the ``refresh_token`` grant to
Google's token endpoint (stdlib only).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Iterable

#: Google's OAuth 2.0 token endpoint (the refresh-token grant target).
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


class GoogleError(Exception):
    """Base for the Google delegated-token exchange failures."""


class GoogleUnavailableError(GoogleError):
    """No Google grant for this identity — a capability gap, not a crash (the
    identity is not a Google-lane user, or never granted data consent)."""


class GoogleScopeNotAllowedError(GoogleError):
    """A requested scope is outside the deployment's allow-list — refused BEFORE
    any exchange (a tool cannot escalate to an unconsented scope)."""


class GoogleConsentRequiredError(GoogleError):
    """The grant was revoked or never covered the scope — the user must re-consent."""


class GoogleExchangeError(GoogleError):
    """Any other failure — sanitized (an error code at most, never a token/body)."""


#: ``(*, client_id, client_secret, refresh_token, scopes) -> result dict`` — the
#: injectable seam (the real one POSTs to Google; tests pass a fake).
Acquirer = Callable[..., dict[str, Any]]


def _default_acquire(
    *, client_id: str, client_secret: str, refresh_token: str, scopes: list[str]
) -> dict[str, Any]:
    """POST the ``refresh_token`` grant to Google's token endpoint. Stdlib only;
    no token cache (PoC — request-lifetime only)."""
    data = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": " ".join(scopes),
        }
    ).encode()
    req = urllib.request.Request(
        GOOGLE_TOKEN_ENDPOINT, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:  # Google returns JSON errors with a 4xx
        try:
            return json.loads(exc.read())
        except Exception:  # noqa: BLE001 — sanitized, body never surfaced
            return {"error": "http_error"}


def exchange_google(
    *,
    refresh_token: str | None,
    client_id: str | None,
    client_secret: str | None,
    scopes: Iterable[str],
    allowed_scopes: Iterable[str] | None = None,
    acquire: Acquirer = _default_acquire,
) -> str:
    """Exchange the user's Google refresh token for a scoped access token.

    Fail-closed and honest on every edge:

    * no ``refresh_token`` (not a Google-lane grant) → :class:`GoogleUnavailableError`;
    * a scope outside ``allowed_scopes`` → :class:`GoogleScopeNotAllowedError`,
      raised BEFORE any exchange;
    * missing client credential → :class:`GoogleExchangeError`;
    * revoked / unconsented → :class:`GoogleConsentRequiredError`;
    * any other failure → :class:`GoogleExchangeError` (sanitized).
    """
    scope_list = [s for s in scopes if s]

    if not refresh_token:
        raise GoogleUnavailableError(
            "Google data is not available for this identity — a Google consent "
            "grant is required (this request has none)."
        )
    if allowed_scopes is not None:
        allowed = set(allowed_scopes)
        for sc in scope_list:
            if sc not in allowed:
                raise GoogleScopeNotAllowedError(
                    f"scope {sc!r} is not in the deployment's allow-list "
                    f"{sorted(allowed)} — refused (a tool cannot request an "
                    "unconsented scope)."
                )
    if not client_id or not client_secret:
        raise GoogleExchangeError(
            "Google delegation is enabled but the OAuth client credential is not "
            "configured — set the env vars named by the config `google:` block "
            "(client_id_env / credential_env)."
        )

    result = acquire(
        client_id=client_id, client_secret=client_secret,
        refresh_token=refresh_token, scopes=scope_list,
    )
    return _map_result(result, scope_list)


def _map_result(result: Any, scopes: list[str]) -> str:
    """Map a Google token response → the access token, or raise an honest,
    sanitized error. NEVER echoes a token or the raw error body."""
    if not isinstance(result, dict):
        raise GoogleExchangeError("the Google token exchange returned an unexpected response.")
    token = result.get("access_token")
    if token:
        return token  # returned to the trusted caller ONLY; never logged.

    error = str(result.get("error") or "").strip()
    # invalid_grant = the refresh token was revoked / expired / never covered the
    # scope → the user must re-consent.
    if error in ("invalid_grant", "consent_required"):
        raise GoogleConsentRequiredError(
            f"Google access for scope(s) {scopes} was revoked or never granted — "
            f"the user must re-consent (Google data access). [{error}]"
        )
    raise GoogleExchangeError(
        f"the Google token exchange failed ({error or 'unknown_error'}) — could "
        "not mint a delegated token for this request."
    )
