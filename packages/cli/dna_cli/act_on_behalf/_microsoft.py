"""``dna_cli.act_on_behalf._microsoft`` — the Microsoft OBO behind the port.

``MicrosoftOboProvider`` is the REFERENCE implementation of
:class:`~dna_cli.act_on_behalf._port.ActOnBehalfPort` (ADR-act-on-behalf-port
§4.3). It is a thin façade over the shipped, **unchanged**
``dna_cli.graph._obo.exchange_on_behalf_of``: ``credential_for`` maps to the OBO
exchange (``assertion = ctx.raw_token`` — the inbound Entra token — at the token's
home tenant ``ctx.claims['tid']``), so nothing about the Microsoft behavior in
``ADR-mcp-obo`` changes. The shipped ``ms_calendar_list`` / ``ms_files_search`` /
``ms_file_read`` tools keep calling ``graph._obo`` directly and are untouched; this
provider is the port view over the same exchanger for the neutral capability
adapter (:mod:`._calendar`) to consume.

Security posture — inherited verbatim: the returned :class:`UserCredential` carries
the request-lifetime Graph token B for immediate use and is never persisted,
logged, or returned to the client. A non-Entra identity (no ``raw_token`` / no
``tid``) is an honest :class:`ActOnBehalfUnavailable`, not a crash; the fail-closed
scope allow-list is enforced by the exchanger BEFORE any network call.
"""
from __future__ import annotations

import time
from collections.abc import Iterable

from ..graph import _obo as O
from ..graph.errors import OboUnavailableError
from ._port import ActContext, ActOnBehalfUnavailable, UserCredential

#: The Microsoft Graph v1.0 API root — the ``api_base`` a capability adapter calls.
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"


class MicrosoftOboProvider:
    """Act on the signed-in user's Microsoft 365 via On-Behalf-Of (ADR §4.3).

    ``provider = "microsoft"``. Constructed with the confidential-client credential
    (already read from the config's env-var NAMES by the caller), the fail-closed
    scope allow-list, and the set of capabilities the deployment enabled. The MSAL
    ``acquire`` seam is injectable so the whole provider is unit-testable with a fake
    — no live Entra, no secret (exactly as ``graph._obo`` is).
    """

    provider = "microsoft"

    def __init__(
        self,
        *,
        client_id: str | None,
        client_secret: str | None,
        allowed_scopes: Iterable[str],
        supported_capabilities: Iterable[str] = ("calendar",),
        acquire: O.Acquirer = O._default_acquire,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._allowed_scopes = tuple(allowed_scopes)
        self._capabilities = frozenset(supported_capabilities)
        self._acquire = acquire

    def supports(self, capability: str) -> bool:
        """True when this deployment enabled ``capability`` for Microsoft."""
        return capability in self._capabilities

    async def credential_for(
        self, ctx: ActContext, capability: str, scopes: list[str]
    ) -> UserCredential:
        """Acquire a Graph-audience user credential via the OBO exchange.

        THE provider-specific step (A): the inbound Entra token (``ctx.raw_token``) is
        the OBO ``assertion``, exchanged at its home tenant (``ctx.claims['tid']``)
        for a downstream Graph token minted for the same user. Fail-closed on scope
        (the exchanger refuses anything outside ``allowed_scopes``). A non-Entra
        identity → :class:`ActOnBehalfUnavailable` (honest gap)."""
        if not self.supports(capability):
            raise ActOnBehalfUnavailable(
                f"the Microsoft provider does not offer the {capability!r} capability "
                f"in this deployment."
            )
        tid = (ctx.claims or {}).get("tid")
        try:
            token_b = O.exchange_on_behalf_of(
                assertion=ctx.raw_token,
                tid=tid,
                client_id=self._client_id,
                client_secret=self._client_secret,
                scopes=scopes,
                allowed_scopes=self._allowed_scopes,
                acquire=self._acquire,
            )
        except OboUnavailableError as exc:
            # A non-Entra identity (no assertion/tid to exchange) is the port's honest
            # capability gap — re-raised as the port-level type (the message, which
            # carries no token, is preserved). Every OTHER OboError (consent /
            # interaction / scope / exchange) propagates unchanged: it is already the
            # honest, sanitized capability error the caller maps to a ToolError.
            raise ActOnBehalfUnavailable(str(exc)) from None
        # token_b is request-lifetime; it goes onto the outbound Graph call and is
        # dropped. expires_at is advisory (MSAL reports expires_in; we don't cache).
        return UserCredential(
            bearer=token_b, api_base=GRAPH_API_BASE, expires_at=time.time() + 3600.0,
        )
