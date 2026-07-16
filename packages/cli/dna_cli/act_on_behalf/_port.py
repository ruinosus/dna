"""``dna_cli.act_on_behalf._port`` — the provider-agnostic act-on-behalf contract.

The outbound twin of the inbound N-provider IdP seam (``_mcp_auth``): where
``_mcp_auth`` made *verifying any identity* provider-agnostic, this port makes
*acting on any provider's user data* provider-agnostic (ADR-act-on-behalf-port
§4). The abstraction splits the flow into two steps and abstracts only the first:

    (A) acquire a user-scoped credential      ← PROVIDER-SPECIFIC (OBO / OAuth / DWD)
    (B) call "the calendar API" as that user  ← COMMON, per-capability adapter

:class:`ActOnBehalfPort` is step (A): "given a verified inbound identity + a
requested capability, hand me a live, user-scoped way to call the provider's
API." A capability adapter (step B, :mod:`._calendar`) consumes the returned
:class:`UserCredential` and never sees whether it came from a Microsoft OBO
exchange, a Google OAuth refresh, or a DWD-impersonated token.

Security posture — inherited verbatim from the Microsoft OBO reference impl
(``dna_cli.graph._obo``): a :class:`UserCredential` is **request-lifetime only**;
it is never persisted, never logged, and never returned to the MCP client. The
port raises :class:`ActOnBehalfUnavailable` when an identity cannot be acted upon
(an honest capability gap, not a crash).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class ActOnBehalfUnavailable(Exception):
    """This identity cannot be acted upon for the requested capability.

    The honest capability-gap signal (ADR §4.3) — e.g. a non-Entra identity asking
    the Microsoft impl (no inbound assertion to exchange), a provider that does not
    offer the capability, or a deployment where the provider is off. A structural,
    testable branch, NOT a masked failure. Carries no token/secret by construction.
    """


@dataclass(frozen=True)
class ActContext:
    """The verified inbound request, provider-neutral (ADR §4.2).

    Built from the token the N-provider IdP layer already verified — it reuses
    ``_mcp_auth``'s output and adds no new trust surface.

    ``raw_token`` is **Optional** and that is the whole point: the Microsoft OBO
    exchange needs the inbound bearer as its ``assertion``; Google auth-code/DWD do
    NOT (they use a previously-consented refresh token or a self-signed
    service-account JWT). The port abstracts the *outcome*, not Microsoft's
    *mechanism*, so each impl takes only what it needs.
    """

    provider_hint: str
    """Which provider family this identity maps to (``"microsoft"`` / ``"google"``)
    — the provider-family stamp the composite verifier writes onto the token."""

    tenant: str
    """The resolved DNA tenant/workspace (already computed by the tenancy bridge)."""

    subject: str
    """The principal to act as — the user's durable id / email."""

    raw_token: str | None = None
    """The inbound bearer. Microsoft OBO needs it as the ``assertion``; Google does
    not — hence Optional (defaults to ``None``)."""

    claims: dict[str, Any] = field(default_factory=dict)
    """The verified claims, for providers that need more (e.g. Entra ``tid``)."""


@dataclass(frozen=True)
class UserCredential:
    """The common output of step (A): a bearer + the base URL of the provider's API.

    A capability adapter (step B) uses ONLY this — it never sees OBO vs OAuth vs
    DWD. **Request-lifetime only**: never persisted, never logged, never returned to
    the client (inherits the Microsoft-OBO security posture verbatim).
    """

    bearer: str
    """The user-scoped access token to put on the outbound API request. Never
    surfaced back to the model / MCP client."""

    api_base: str
    """The provider API root the capability adapter calls
    (``graph.microsoft.com`` | ``www.googleapis.com``)."""

    expires_at: float
    """Unix epoch seconds when ``bearer`` expires (0 when the provider does not
    report it). Advisory — the credential is dropped at end of request regardless."""


@runtime_checkable
class ActOnBehalfPort(Protocol):
    """Provider-agnostic "act on behalf of the user" — step (A) of the flow.

    Each provider implements this its own way behind one contract:

    * ``MicrosoftOboProvider`` → OBO exchange (assertion = ``ctx.raw_token``) → Graph
      token (:mod:`._microsoft`).
    * ``GoogleWorkspaceProvider`` → the user's consented OAuth token / a DWD-
      impersonated token (``sub = ctx.subject``); needs no ``raw_token``
      (:mod:`._google`).
    """

    provider: str
    """The provider-family this impl serves (``"microsoft"`` | ``"google"``) — the
    key the identity→provider dispatch (:mod:`._dispatch`) matches on."""

    def supports(self, capability: str) -> bool:
        """Does this provider+deployment offer ``capability``
        (``calendar`` / ``files`` / ``mail``)?"""
        ...

    async def credential_for(
        self, ctx: ActContext, capability: str, scopes: list[str]
    ) -> UserCredential:
        """Return a user-scoped :class:`UserCredential` for ``capability`` at
        least-privilege ``scopes``. THE provider-specific step. Raises
        :class:`ActOnBehalfUnavailable` when this identity cannot be acted upon."""
        ...
