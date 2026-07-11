"""``dna_cli._mcp_auth`` — the DNA MCP **auth ↔ tenancy bridge**.

FastMCP already ships the OAuth 2.1 / JWT machinery (Resource Server, PKCE, DCR,
``OAuthProxy`` for WorkOS/Auth0, ``JWTVerifier`` + scope enforcement). What FastMCP
does NOT know is **DNA tenancy** — that a token belongs to a tenant and must only
compose/read what is that tenant's. This module is that missing piece: it maps a
verified token's **claims/scopes → a DNA tenant**, and enforces the mapping so a
tenant-A token can never reach tenant-B data (the ``compose_prompt`` / ``recall`` /
``list_stories`` surfaces become **tenant-scoped by the token**, not by a caller
argument).

The bridge is deliberately split:

* **Pure core** (``tenant_from_token`` / ``resolve_tenant``) — no FastMCP import,
  fully unit-testable, holds the entire policy.
* **Context glue** (``enforce_tenant_from_context``) — reads the *current* request's
  access token via FastMCP's ``get_access_token`` and applies the pure core.
* **Provider factory** (``jwt_provider_from_env``) — builds a FastMCP
  ``JWTVerifier`` from env (the MVP provider; a WorkOS/Auth0 ``OAuthProxy`` slots
  in the same seam later).

``fastmcp`` is imported **lazily** inside the two functions that need it, so the
pure core (and importing this module) never pulls the optional dependency.

The policy in one paragraph — **the token is authoritative**:

* No token at all (stdio / local, unauthenticated) → the caller's ``tenant``
  argument passes through unchanged (the MVP behavior; auth is an opt-in extra
  that must never break the base/stdio path).
* A token WITH a tenant claim/scope → that tenant is injected into every data
  access. A caller that also passes a *different* ``tenant`` is **denied**
  (cross-tenant). Omitting it (or passing the same) resolves to the token's tenant.
* A token WITHOUT a tenant claim/scope → **denied** (an authenticated request with
  no tenant binding gets nothing — fail closed, never fall back to "all tenants").
"""
from __future__ import annotations

import os
from typing import Any

# Env knobs (all optional; sensible defaults).
_ENV_TENANT_CLAIM = "DNA_MCP_TENANT_CLAIM"          # claim key holding the tenant
_ENV_TENANT_SCOPE_PREFIX = "DNA_MCP_TENANT_SCOPE_PREFIX"  # e.g. "tenant:" in scopes
DEFAULT_TENANT_CLAIM = "tenant"
DEFAULT_TENANT_SCOPE_PREFIX = "tenant:"


class CrossTenantError(PermissionError):
    """A token tried to reach a tenant it is not scoped to (or carried no tenant).

    Raised by the bridge and surfaced to the MCP client as a tool error — the
    denial half of the auth↔tenancy contract.
    """


def tenant_claim_key() -> str:
    """The claim key the tenant is read from (``DNA_MCP_TENANT_CLAIM``, default
    ``tenant``)."""
    return os.environ.get(_ENV_TENANT_CLAIM) or DEFAULT_TENANT_CLAIM


def tenant_scope_prefix() -> str:
    """The scope prefix a tenant may be encoded under (``DNA_MCP_TENANT_SCOPE_PREFIX``,
    default ``tenant:`` → a ``tenant:acme`` scope means tenant ``acme``)."""
    return os.environ.get(_ENV_TENANT_SCOPE_PREFIX) or DEFAULT_TENANT_SCOPE_PREFIX


# ── pure core (no FastMCP) ─────────────────────────────────────────────────


def tenant_from_token(
    claims: dict[str, Any] | None,
    scopes: list[str] | None = None,
    *,
    claim_key: str | None = None,
    scope_prefix: str | None = None,
) -> str | None:
    """Extract the DNA tenant a token maps to — pure, no context.

    Two encodings are honored (a claim wins over a scope):

    1. a **claim** ``{claim_key: "<tenant>"}`` (default key ``tenant``), and
    2. a **scope** ``"<scope_prefix><tenant>"`` (default ``tenant:acme``).

    Returns ``None`` when the token carries neither — the caller decides whether
    that is allowed (``resolve_tenant`` fails it closed for authenticated calls).
    """
    key = claim_key or tenant_claim_key()
    prefix = scope_prefix or tenant_scope_prefix()

    # 1. explicit claim.
    if claims:
        raw = claims.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        # a claim may itself be a list of scope-like strings.
        if isinstance(raw, (list, tuple)):
            for item in raw:
                if isinstance(item, str) and item.strip():
                    return item.strip()

    # 2. tenant-encoding scope (tenant:<x>).
    for sc in scopes or []:
        if isinstance(sc, str) and sc.startswith(prefix):
            candidate = sc[len(prefix):].strip()
            if candidate:
                return candidate

    return None


def resolve_tenant(
    *,
    token_present: bool,
    token_tenant: str | None,
    requested: str | None,
) -> str | None:
    """Reconcile a caller's requested tenant with the token's tenant — the policy.

    * ``token_present=False`` (no auth) → ``requested`` passes through (MVP/stdio).
    * token present, no ``token_tenant`` → **denied** (fail closed).
    * token present, requested differs from ``token_tenant`` → **denied** (cross-tenant).
    * token present, requested is ``None`` or equal → the ``token_tenant``.
    """
    if not token_present:
        return requested
    if not token_tenant:
        raise CrossTenantError(
            "authenticated token carries no tenant claim/scope — access denied "
            f"(expected claim {tenant_claim_key()!r} or scope "
            f"{tenant_scope_prefix()!r}<tenant>)"
        )
    if requested is not None and requested != token_tenant:
        raise CrossTenantError(
            f"token is scoped to tenant {token_tenant!r}; cross-tenant access to "
            f"{requested!r} is denied"
        )
    return token_tenant


# ── context glue (reads the live FastMCP request) ──────────────────────────


def enforce_tenant_from_context(requested: str | None) -> str | None:
    """Resolve the **effective** tenant for the current MCP request.

    Reads the request's access token (if any) via FastMCP's ``get_access_token``,
    derives the token's tenant, and applies :func:`resolve_tenant`. With no token
    (stdio / unauthenticated) this is an identity over ``requested`` — so the base
    path is untouched. Raises :class:`CrossTenantError` on a cross-tenant or
    tenant-less authenticated request.
    """
    try:
        from fastmcp.server.dependencies import get_access_token
    except ModuleNotFoundError:  # pragma: no cover — no fastmcp ⇒ no auth ⇒ passthrough
        return requested

    token = get_access_token()
    if token is None:
        return requested  # unauthenticated (stdio) → MVP passthrough.

    token_tenant = tenant_from_token(
        getattr(token, "claims", None), getattr(token, "scopes", None)
    )
    return resolve_tenant(
        token_present=True, token_tenant=token_tenant, requested=requested
    )


# ── provider factory (the MVP auth provider) ───────────────────────────────


def jwt_provider_from_env() -> Any:
    """Build a FastMCP ``JWTVerifier`` (Resource Server / bearer-JWT) from env.

    The MVP auth provider: verify signed bearer JWTs and let the bridge read the
    tenant claim off the verified token. Env:

    * ``DNA_MCP_JWT_PUBLIC_KEY`` — PEM public key (symmetric/asymmetric static key), OR
    * ``DNA_MCP_JWKS_URI``       — a JWKS endpoint (rotating keys / real IdP),
    * ``DNA_MCP_JWT_ISSUER``     — expected ``iss`` (optional),
    * ``DNA_MCP_JWT_AUDIENCE``   — expected ``aud`` (optional),
    * ``DNA_MCP_JWT_ALGORITHM``  — signing alg (optional, e.g. ``RS256``).

    For providers WITHOUT DCR (WorkOS, Auth0) FastMCP's ``OAuthProxy`` slots into
    this same factory later — the tenancy bridge above is provider-agnostic (it
    only reads claims/scopes off the verified token).
    """
    from fastmcp.server.auth.providers.jwt import JWTVerifier

    public_key = os.environ.get("DNA_MCP_JWT_PUBLIC_KEY")
    jwks_uri = os.environ.get("DNA_MCP_JWKS_URI")
    if not public_key and not jwks_uri:
        raise RuntimeError(
            "jwt auth needs a key source — set DNA_MCP_JWT_PUBLIC_KEY (PEM) or "
            "DNA_MCP_JWKS_URI (a JWKS endpoint)"
        )
    verifier = JWTVerifier(
        public_key=public_key,
        jwks_uri=jwks_uri,
        issuer=os.environ.get("DNA_MCP_JWT_ISSUER"),
        audience=os.environ.get("DNA_MCP_JWT_AUDIENCE"),
        algorithm=os.environ.get("DNA_MCP_JWT_ALGORITHM"),
    )

    # When the resource-server URL + its authorization server(s) are known, wrap
    # the verifier so FastMCP advertises Protected Resource Metadata (RFC 9728) at
    # /.well-known/oauth-protected-resource — the discovery an MCP client needs to
    # find where to authorize. Without them the bare verifier still guards tools.
    resource_url = os.environ.get("DNA_MCP_RESOURCE_URL")
    auth_servers = os.environ.get("DNA_MCP_AUTH_SERVERS")
    if resource_url and auth_servers:
        return resource_server(
            verifier,
            base_url=resource_url,
            authorization_servers=[s.strip() for s in auth_servers.split(",") if s.strip()],
        )
    return verifier


def resource_server(
    token_verifier: Any,
    *,
    base_url: str,
    authorization_servers: list[str],
    scopes_supported: list[str] | None = None,
) -> Any:
    """Wrap a ``TokenVerifier`` as a FastMCP ``RemoteAuthProvider`` — an OAuth 2.1
    Resource Server that advertises Protected Resource Metadata (RFC 9728).

    This is the provider-agnostic seam: the ``token_verifier`` may be a
    ``JWTVerifier`` (the MVP) or, later, a WorkOS/Auth0 ``OAuthProxy`` — the DNA
    tenancy bridge above reads the tenant off whatever verified token comes back,
    so nothing downstream changes.
    """
    from fastmcp.server.auth import RemoteAuthProvider

    return RemoteAuthProvider(
        token_verifier=token_verifier,
        authorization_servers=authorization_servers,
        base_url=base_url,
        scopes_supported=scopes_supported,
    )
