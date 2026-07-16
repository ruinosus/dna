"""``dna_cli.act_on_behalf._dispatch`` — identity → provider resolution + glue.

The seam that makes "the verified inbound provider selects the port" concrete
(ADR-act-on-behalf-port §6): a token verified by the Entra provider acts through
``MicrosoftOboProvider``; one verified by Google acts through
``GoogleWorkspaceProvider``. Deterministic, no extra config, no new sign-in — it
reads the **provider-family stamp** the composite verifier already wrote onto the
token (``_mcp_auth._DNA_PROVIDER_FAMILY_MARKER``).

Two halves, split like every other bridge in ``_mcp_auth``:

* :func:`resolve_port` — PURE: a provider-family string + a registry → the port (or
  an honest :class:`ActOnBehalfUnavailable`). No FastMCP, fully unit-testable.
* :func:`act_context_from_context` — GLUE: reads the live FastMCP request's access
  token and builds the provider-neutral :class:`ActContext` (``fastmcp`` imported
  lazily, exactly like ``entra_obo_assertion_from_context``).
"""
from __future__ import annotations

from typing import Mapping

from ._port import ActContext, ActOnBehalfPort, ActOnBehalfUnavailable


def resolve_port(
    registry: Mapping[str, ActOnBehalfPort], provider_hint: str | None
) -> ActOnBehalfPort:
    """Select the :class:`ActOnBehalfPort` for a verified inbound provider family.

    ``registry`` maps a provider family (``"microsoft"`` / ``"google"``) to the port
    a deployment enabled. A ``provider_hint`` with no registered port — a family DNA
    cannot act on behalf of here (not configured / off / a non-actable IdP whose
    stamp is ``None``) — is an honest :class:`ActOnBehalfUnavailable`, never a
    crash. This is the whole identity→provider decision, in one pure function."""
    if not provider_hint:
        raise ActOnBehalfUnavailable(
            "this identity has no act-on-behalf provider — DNA cannot act on its "
            "productivity data (the inbound IdP maps to no Microsoft/Google family)."
        )
    port = registry.get(provider_hint)
    if port is None:
        raise ActOnBehalfUnavailable(
            f"no act-on-behalf provider is enabled for the {provider_hint!r} identity "
            f"in this deployment (enabled: {sorted(registry)!r})."
        )
    return port


def act_context_from_context() -> ActContext | None:
    """Build the provider-neutral :class:`ActContext` for the CURRENT MCP request.

    Reads the request's verified access token via FastMCP's ``get_access_token`` and
    distills the provider-neutral shape the port needs: the ``provider_hint`` from
    the composite verifier's family stamp, the tenant from the stamped tenant claim,
    the ``subject`` from the durable ``oid`` (falling back to ``sub`` / email), the
    raw inbound bearer (Microsoft OBO's assertion; ``None`` when unavailable), and
    the verified claims. Returns ``None`` when there is no token (stdio /
    unauthenticated) — the caller then reports an honest capability gap. The token is
    never logged here."""
    from dna_cli import _mcp_auth as A

    try:
        from fastmcp.server.dependencies import get_access_token
    except ModuleNotFoundError:  # pragma: no cover — no fastmcp ⇒ no auth
        return None

    token = get_access_token()
    if token is None:
        return None

    claims = dict(getattr(token, "claims", None) or {})
    scopes = getattr(token, "scopes", None)

    provider_hint = claims.get(A._DNA_PROVIDER_FAMILY_MARKER)
    # The tenant uses the SAME per-provider claim key the tenancy bridge reads (the
    # stamp), so the two never disagree on "the token's tenant".
    tenant = A.tenant_from_token(
        claims, scopes,
        claim_key=claims.get(A._DNA_CLAIM_MARKER),
        scope_prefix=claims.get(A._DNA_SCOPE_MARKER),
    )
    subject = (
        A.oid_from_token(claims)
        or _first_str(claims, "sub", "preferred_username", "upn", "email")
    )
    raw = getattr(token, "token", None)

    return ActContext(
        provider_hint=str(provider_hint) if provider_hint else "",
        tenant=str(tenant) if tenant else "",
        subject=str(subject) if subject else "",
        raw_token=str(raw) if raw else None,
        claims=claims,
    )


def _first_str(claims: Mapping[str, object], *keys: str) -> str | None:
    for k in keys:
        v = claims.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None
