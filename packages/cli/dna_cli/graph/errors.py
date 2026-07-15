"""``dna_cli.graph.errors`` — the OBO / Microsoft-Graph capability errors.

Every failure of the On-Behalf-Of chain surfaces as one of these — a clean,
honest tool error (never a masked 500, never a raw Graph body, never a token).
The MCP edge maps them to a FastMCP ``ToolError`` exactly as the tenancy bridge
maps :class:`dna_cli._mcp_auth.CrossTenantError`.

Design invariants (ADR-mcp-obo §4):

* **No secrets in messages.** A message may name the *scope* or the *AADSTS code*
  so the caller can act, but NEVER the inbound assertion, the Graph token, or the
  client secret.
* **Honest capability gap, not a crash.** A non-Entra identity, a missing consent,
  or a Conditional-Access step-up are expected outcomes, each with its own type so
  the caller (and the model) can distinguish "not available for you" from "broke".
"""
from __future__ import annotations


class OboError(Exception):
    """Base for every On-Behalf-Of / Graph capability error."""


class OboUnavailableError(OboError):
    """Microsoft Graph is not available for this identity.

    Raised when there is no Entra assertion to exchange — a non-Entra sign-in
    (Clerk/WorkOS/OIDC) or an unauthenticated (stdio) call. A capability gap, not
    a failure: the tool is simply not usable by this caller."""


class OboScopeNotAllowedError(OboError):
    """A tool requested a delegated scope the deployment did not allow.

    The config ``graph:`` block is a static, fail-closed allow-list: a tool can
    only ever request a scope its group declared. Raised BEFORE any exchange so an
    escalation attempt never reaches Entra."""


class OboConsentRequiredError(OboError):
    """The middle-tier→Graph delegated permission has not been consented.

    Maps Entra ``AADSTS65001`` / ``invalid_grant``. The remedy is an admin- or
    user-consent for the named scope (see the Entra-setup guide) — surfaced
    clearly, never as a stack trace."""


class OboInteractionRequiredError(OboError):
    """A Conditional-Access policy (MFA / device) requires a step-up.

    Maps Entra ``interaction_required`` + its *claims challenge*. Per ADR §2.2(6)
    the challenge is SURFACED to the client (so the user can satisfy the policy),
    never swallowed. ``claims_challenge`` carries the raw claims payload the client
    must echo back to the authorization server."""

    def __init__(self, message: str, *, claims_challenge: str | None = None) -> None:
        super().__init__(message)
        self.claims_challenge = claims_challenge


class OboExchangeError(OboError):
    """A generic, mapped exchange/Graph failure (bad credential, Graph 5xx, an
    unexpected response). Carries a sanitized diagnostic (an AADSTS/HTTP code at
    most) — never the raw body, never a token."""
