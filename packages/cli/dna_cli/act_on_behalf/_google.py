"""``dna_cli.act_on_behalf._google`` — the Google Workspace provider SKELETON.

The SECOND implementation of :class:`~dna_cli.act_on_behalf._port.ActOnBehalfPort`
(ADR-act-on-behalf-port §8-4) — the PoC proof that a different provider fits the
SAME contract. Calendar ONLY, with the **network boundary stubbed**: no live Google
Cloud project, no OAuth consent screen, no ``gcloud``. Both moving parts are
injectable seams (exactly like ``graph._obo``'s ``acquire``), so the whole provider
is unit-testable with fakes:

* ``refresh_lookup(subject) -> str | None`` — the user's previously-consented OAuth
  refresh token (the real consent-flow + refresh-token store is the DEFERRED full
  Google impl). Default returns ``None`` → an honest capability gap (fail-closed:
  no consented token ⇒ cannot act).
* ``exchange(...) -> dict`` — the refresh-token → access-token POST at Google's token
  endpoint. Default is a real ``httpx`` POST (lazily imported); tests inject a fake
  that returns a dev token.

**The asymmetry, demonstrated.** ``credential_for`` does NOT read ``ctx.raw_token``
at all — Google auth-code/refresh needs no inbound assertion (unlike Microsoft OBO).
That is the concrete proof the port abstracts the *outcome*, not Microsoft's
*mechanism*.

DEFERRED (NOT in this skeleton, per ADR §8): the real OAuth consent flow, durable
refresh-token storage, Domain-Wide Delegation (super-admin + service-account key),
files/mail capabilities, all write scopes, token caching, and prod credential
hardening (Workload Identity Federation).
"""
from __future__ import annotations

import re
import time
from collections.abc import Iterable
from typing import Any, Callable

from ._port import ActContext, ActOnBehalfUnavailable, UserCredential

#: The Google APIs root — the ``api_base`` the neutral calendar adapter calls
#: (``…/calendar/v3/calendars/primary/events``).
GOOGLE_API_BASE = "https://www.googleapis.com"

#: Google's OAuth 2.0 token endpoint (both the auth-code refresh and DWD assertion).
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

# A bare token-ish string — used only to sanitize error messages (never to validate).
_TOKENISH = re.compile(r"[A-Za-z0-9\-_]{20,}")

#: The refresh-token lookup seam: ``subject -> refresh_token | None``. The DEFAULT
#: has no consented-token store yet (that is the deferred full impl), so it always
#: returns ``None`` → an honest capability gap.
#:
#: ⚠️ **KEYING WARNING for the real store (the deferred full impl, NOT this
#: skeleton)** — reviewed under ``s-consumer-lane-memory-key``: this seam takes
#: ``subject`` ALONE, no provider-family / issuer. That is safe TODAY only because
#: (a) dispatch (``dna_cli._mcp_auth._PROVIDER_FAMILY`` /
#: ``act_on_behalf._dispatch.resolve_port``) routes a token to a port BY FAMILY
#: FIRST, so only a ``"google"``-family subject ever reaches this seam, and (b) the
#: skeleton's own default always returns ``None`` regardless of what it's called
#: with. It stops being safe the moment a real, persistent refresh-token store is
#: built: a bare ``subject`` string is NOT guaranteed unique across issuers (a
#: numeric Google ``sub`` and, hypothetically, some other family's subject COULD
#: collide as raw strings — this is exactly the class of bug
#: ``s-consumer-lane-memory-key`` fixed for the personal-memory partition key,
#: where ``google`` and ``workos`` were briefly merged into one family before the
#: founder decision split them back apart).
#:
#: **The real store MUST key on ``(family, subject)`` — or an issuer-qualified id
#: (e.g. ``f"{ctx.provider_hint}:{ctx.subject}"``) — never bare ``subject`` alone.**
#: This is a documented invariant, not (yet) a structural change to this
#: ``Callable[[str], str | None]`` signature: today's dispatch-by-family already
#: makes a cross-family collision here unreachable for any REGISTERED port
#: (nothing routes a non-``"google"`` family to this provider), so widening the
#: seam's signature was judged out of scope for a personal-memory story. Whoever
#: builds the real store SHOULD widen this signature (or namespace the lookup key
#: internally) at that time — do not skip it because "dispatch already filters".
RefreshLookup = Callable[[str], str | None]

#: The token-exchange seam (Google token endpoint shape): ``(client_id,
#: client_secret, refresh_token, scopes) -> {"access_token": ..., "expires_in": ...}``
#: on success, ``{"error": ...}`` on failure.
GoogleExchanger = Callable[..., dict[str, Any]]


class GoogleScopeNotAllowedError(ActOnBehalfUnavailable):
    """A capability requested a Google scope outside the provider's allow-list.

    The Google twin of ``graph.errors.OboScopeNotAllowedError`` — the fail-closed
    scope allow-list is preserved for every provider (ADR §7 invariant). Raised
    BEFORE any token exchange so an escalation attempt never reaches Google."""


def _default_refresh_lookup(subject: str) -> str | None:
    """The skeleton's refresh-token store: EMPTY (no consent flow yet).

    Always ``None`` → ``credential_for`` reports an honest capability gap. The real
    per-user consent + refresh-token persistence is the deferred full Google impl
    — see the ``RefreshLookup`` KEYING WARNING above before building it: key on
    ``(family, subject)``, never bare ``subject``."""
    return None


def _default_google_exchange(
    *, client_id: str, client_secret: str, refresh_token: str, scopes: list[str],
) -> dict[str, Any]:
    """The production seam: a real Google OAuth refresh-token exchange (httpx POST).

    Imported lazily so importing this module never requires ``httpx`` (part of the
    optional ``graph`` extra). No token cache — PoC request-lifetime only."""
    try:
        import httpx  # optional dep — dna-cli[graph]
    except ModuleNotFoundError as exc:  # pragma: no cover — exercised via CLI
        raise ActOnBehalfUnavailable(
            "the Google token exchange needs the optional 'httpx' dependency — "
            "install it with: pip install 'dna-cli[graph]'"
        ) from exc

    resp = httpx.post(
        GOOGLE_TOKEN_ENDPOINT,
        data={
            "client_id": client_id, "client_secret": client_secret,
            "refresh_token": refresh_token, "grant_type": "refresh_token",
            "scope": " ".join(scopes),
        },
        timeout=20.0,
    )
    try:
        return resp.json()
    except Exception:  # noqa: BLE001 — a non-JSON body is a mapped failure below.
        return {"error": f"http_{resp.status_code}"}


class GoogleWorkspaceProvider:
    """Act on the signed-in user's Google Workspace via OAuth (skeleton, calendar).

    ``provider = "google"``. Mechanism default = per-user OAuth (auth-code + refresh)
    per ADR §10-2. The inbound assertion is deliberately unused — the whole point of
    the abstraction."""

    provider = "google"

    def __init__(
        self,
        *,
        client_id: str | None,
        client_secret: str | None,
        allowed_scopes: Iterable[str],
        supported_capabilities: Iterable[str] = ("calendar",),
        refresh_lookup: RefreshLookup = _default_refresh_lookup,
        exchange: GoogleExchanger = _default_google_exchange,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._allowed_scopes = tuple(allowed_scopes)
        self._capabilities = frozenset(supported_capabilities)
        self._refresh_lookup = refresh_lookup
        self._exchange = exchange

    def supports(self, capability: str) -> bool:
        """The skeleton offers ``calendar`` only (files/mail are the deferred impl)."""
        return capability in self._capabilities

    async def credential_for(
        self, ctx: ActContext, capability: str, scopes: list[str]
    ) -> UserCredential:
        """Acquire a Google user credential via the OAuth refresh-token exchange.

        Note ``ctx.raw_token`` is NEVER read — Google needs no inbound assertion
        (the asymmetry). Fail-closed: an unsupported capability, a scope outside the
        allow-list, no consented refresh token, or a missing client credential each
        yields an honest :class:`ActOnBehalfUnavailable` (never a crash, never a leak).

        ``self._refresh_lookup(ctx.subject)`` is keyed on ``subject`` ALONE — see the
        ``RefreshLookup`` KEYING WARNING above; this is only safe while dispatch
        routes strictly by provider family before any call ever reaches here."""
        if not self.supports(capability):
            raise ActOnBehalfUnavailable(
                f"the Google provider does not offer the {capability!r} capability "
                f"(this skeleton is calendar-only)."
            )

        # Fail-closed scope allow-list — refuse BEFORE any exchange (ADR §7).
        allowed = set(self._allowed_scopes)
        for sc in scopes:
            if sc not in allowed:
                raise GoogleScopeNotAllowedError(
                    f"Google scope {sc!r} is not in the deployment's allow-list "
                    f"{sorted(allowed)} — refused (a tool cannot request an "
                    f"unconsented scope)."
                )

        if not self._client_id or not self._client_secret:
            raise ActOnBehalfUnavailable(
                "Google act-on-behalf is enabled but the OAuth client credential is "
                "not configured (client_id / client_secret)."
            )

        # The consented refresh token for THIS user (subject) — Google has no inbound
        # assertion to exchange; it relies on prior consent (the deferred full impl).
        refresh_token = self._refresh_lookup(ctx.subject)
        if not refresh_token:
            raise ActOnBehalfUnavailable(
                "Google Workspace has no consented credential for this user yet — "
                "the OAuth consent flow is not wired in this PoC (skeleton)."
            )

        result = self._exchange(
            client_id=self._client_id, client_secret=self._client_secret,
            refresh_token=refresh_token, scopes=list(scopes),
        )
        return _map_google_result(result)


def _map_google_result(result: Any) -> UserCredential:
    """Map a Google token-endpoint result → a :class:`UserCredential`, or raise an
    honest, sanitized error. NEVER echoes a token or the raw body."""
    if not isinstance(result, dict):
        raise ActOnBehalfUnavailable(
            "the Google token exchange returned an unexpected response."
        )
    token = result.get("access_token")
    if token:
        expires_in = result.get("expires_in")
        try:
            ttl = float(expires_in) if expires_in is not None else 3600.0
        except (TypeError, ValueError):
            ttl = 3600.0
        return UserCredential(
            bearer=token, api_base=GOOGLE_API_BASE, expires_at=time.time() + ttl,
        )
    # Failure — surface the error NAME only, never the raw description/token.
    error = str(result.get("error") or "invalid_grant").strip()
    error = _TOKENISH.sub("<redacted>", error)
    raise ActOnBehalfUnavailable(
        f"the Google OAuth token exchange failed ({error}) — could not obtain a "
        "user credential for this request."
    )
