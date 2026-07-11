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
from dataclasses import dataclass
from typing import Any

# Env knobs (all optional; sensible defaults).
_ENV_TENANT_CLAIM = "DNA_MCP_TENANT_CLAIM"          # claim key holding the tenant
_ENV_TENANT_SCOPE_PREFIX = "DNA_MCP_TENANT_SCOPE_PREFIX"  # e.g. "tenant:" in scopes
DEFAULT_TENANT_CLAIM = "tenant"
DEFAULT_TENANT_SCOPE_PREFIX = "tenant:"

# Synthetic claim markers the multi-provider composite verifier stamps onto a
# verified token so the tenancy bridge reads the RIGHT per-provider claim key —
# without global/request state, and without re-deriving which provider matched
# from the token's ``iss`` (which breaks for Entra ``common``, where the token's
# ``iss`` carries the real Azure tenant GUID, not the literal configured issuer).
_DNA_CLAIM_MARKER = "_dna_tenant_claim"
_DNA_SCOPE_MARKER = "_dna_scope_prefix"

# Per-IdP-type conventions. A provider is a BLOCK OF CONFIG, not code — every
# serious IdP exposes JWKS + OIDC discovery, so the only per-type knowledge we
# bake in is (a) the default claim the DNA tenant is read from, and (b) how to
# derive the JWKS endpoint from the issuer when the block omits ``jwks_uri``.
#
#   entra  — Azure Entra ID; the Azure tenant is the ``tid`` claim → DNA tenant.
#   clerk  — tenant is the organization ``org_id``.
#   workos — organization-based (``org_id``).
#   auth0  — organization-based (``org_id``); no DCR → ``OAuthProxy`` seam.
#   oidc   — any OIDC-generic IdP; ``tenant_claim`` MUST be given (no default).
_PROVIDER_TENANT_CLAIM_DEFAULT = {
    "entra": "tid",
    "clerk": "org_id",
    "workos": "org_id",
    "auth0": "org_id",
}
_KNOWN_PROVIDER_TYPES = frozenset(
    {"entra", "clerk", "workos", "auth0", "oidc", "generic"}
)


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


# ── the pluggable N-provider IdP layer — a provider is CONFIG, not code ─────


@dataclass(frozen=True)
class ProviderConfig:
    """One IdP, described declaratively (a block under ``auth.providers[]``).

    The whole point of the layer: adding an IdP is a config block, not a code
    path. Every serious IdP exposes JWKS + OIDC discovery, so the fields below —
    ``issuer`` / ``audience`` / ``jwks_uri`` (or a static ``public_key``) plus the
    ``tenant_claim`` the DNA tenant is read from — cover Entra / Clerk / WorkOS /
    Auth0 / generic-OIDC without any per-provider code.

    ``jwks_uri`` is resolved eagerly by :func:`parse_auth_providers` (derived from
    the issuer per the type's convention when the block omits it), so by the time
    a ``ProviderConfig`` exists it carries a concrete key source (``jwks_uri`` or
    ``public_key``). ``name`` is a human label (defaults to ``type``).
    """

    type: str
    tenant_claim: str
    issuer: str | None = None
    audience: str | None = None
    jwks_uri: str | None = None
    public_key: str | None = None
    algorithm: str | None = None
    scope_prefix: str = DEFAULT_TENANT_SCOPE_PREFIX
    name: str = ""

    @property
    def label(self) -> str:
        return self.name or self.type


def _entra_multitenant(issuer: str | None) -> bool:
    """Entra multi-tenant endpoints (``/common``, ``/organizations``,
    ``/consumers``) mint tokens whose ``iss`` carries the *caller's* Azure tenant
    GUID — never the literal ``common``. Strict ``iss`` validation would reject
    every real token, so for these the verifier validates by **audience +
    signature** (the security boundary is your app-id audience) and the DNA tenant
    comes from the ``tid`` claim. A concrete per-tenant issuer stays strict."""
    if not issuer:
        return False
    lowered = issuer.lower()
    return any(f"/{seg}/" in lowered or lowered.endswith(f"/{seg}")
               for seg in ("common", "organizations", "consumers"))


def _derive_jwks_uri(ptype: str, issuer: str) -> str:
    """Derive the JWKS endpoint from the issuer per the IdP type's convention.

    * ``entra`` → ``…/discovery/v2.0/keys`` (the fixed Azure AD keys endpoint).
    * everything else → ``<issuer>/.well-known/jwks.json`` (the de-facto OIDC
      location; override with an explicit ``jwks_uri`` if your IdP differs).
    """
    base = issuer.rstrip("/")
    if ptype == "entra":
        if base.endswith("/v2.0"):
            base = base[: -len("/v2.0")]
        return f"{base}/discovery/v2.0/keys"
    return f"{base}/.well-known/jwks.json"


def verifier_issuer(pc: ProviderConfig) -> str | None:
    """The issuer value to ENFORCE in the token verifier — ``None`` (audience-only)
    for an Entra multi-tenant endpoint, else the concrete configured issuer."""
    if pc.type == "entra" and _entra_multitenant(pc.issuer):
        return None
    return pc.issuer


def parse_auth_providers(auth_cfg: dict[str, Any] | None) -> list[ProviderConfig]:
    """Parse + validate the ``auth:`` section of ``dna.config.yaml`` into a list of
    :class:`ProviderConfig` — the pure core of the pluggable IdP layer (no FastMCP).

    Fails loud (``ValueError``) on: no ``auth`` section, missing/empty
    ``providers``, a provider without a ``type``, a provider whose tenant claim
    cannot be resolved (a generic ``oidc`` provider MUST name its ``tenant_claim``),
    or one with no derivable key source (needs ``jwks_uri`` / ``public_key``, or an
    ``issuer`` to derive the JWKS from).
    """
    if not auth_cfg or not isinstance(auth_cfg, dict):
        raise ValueError(
            "no `auth:` section — the multi-provider IdP layer needs "
            "`auth.providers: [...]` in dna.config.yaml (each entry is one IdP)."
        )
    raw_providers = auth_cfg.get("providers")
    if not isinstance(raw_providers, list) or not raw_providers:
        raise ValueError(
            "`auth.providers:` must be a non-empty list — each entry is one IdP "
            "block ({type, issuer, audience, tenant_claim, ...})."
        )

    out: list[ProviderConfig] = []
    for i, raw in enumerate(raw_providers):
        where = f"auth.providers[{i}]"
        if not isinstance(raw, dict):
            raise ValueError(f"{where}: must be a mapping, got {type(raw).__name__}.")

        ptype = str(raw.get("type") or "").strip()
        if not ptype:
            raise ValueError(f"{where}: `type` is required (e.g. entra/oidc/clerk/workos).")
        if ptype not in _KNOWN_PROVIDER_TYPES:
            raise ValueError(
                f"{where}: unknown provider type {ptype!r} — supported: "
                f"{sorted(_KNOWN_PROVIDER_TYPES)} (use `oidc` for any OIDC-generic IdP)."
            )

        issuer = _opt_str(raw.get("issuer"))
        audience = _opt_str(raw.get("audience"))
        jwks_uri = _opt_str(raw.get("jwks_uri"))
        public_key = _opt_str(raw.get("public_key"))
        algorithm = _opt_str(raw.get("algorithm"))
        scope_prefix = _opt_str(raw.get("scope_prefix")) or DEFAULT_TENANT_SCOPE_PREFIX
        name = _opt_str(raw.get("name")) or ptype

        # tenant_claim: block value → per-type default → error (oidc/generic).
        tenant_claim = _opt_str(raw.get("tenant_claim")) or \
            _PROVIDER_TENANT_CLAIM_DEFAULT.get(ptype)
        if not tenant_claim:
            raise ValueError(
                f"{where}: `tenant_claim` is required for a {ptype!r} provider "
                f"(there is no default) — name the claim that carries the DNA tenant."
            )

        # key source: explicit jwks_uri/public_key, else derive from issuer.
        if not jwks_uri and not public_key:
            if not issuer:
                raise ValueError(
                    f"{where}: no key source — set `jwks_uri` (or `public_key`), or "
                    f"an `issuer` to derive the JWKS from."
                )
            jwks_uri = _derive_jwks_uri(ptype, issuer)

        # Entra multi-tenant needs an audience as the security boundary (the
        # issuer is relaxed for `common`/`organizations`).
        if ptype == "entra" and _entra_multitenant(issuer) and not audience:
            raise ValueError(
                f"{where}: an Entra multi-tenant issuer ({issuer!r}) needs an "
                f"`audience` (your app-id) — it is the validation boundary when the "
                f"issuer is relaxed for `common`/`organizations`."
            )

        out.append(ProviderConfig(
            type=ptype, tenant_claim=tenant_claim, issuer=issuer, audience=audience,
            jwks_uri=jwks_uri, public_key=public_key, algorithm=algorithm,
            scope_prefix=scope_prefix, name=name,
        ))
    return out


def _opt_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def select_provider_for_issuer(
    providers: list[ProviderConfig], iss: str | None
) -> ProviderConfig | None:
    """Pure routing helper: the provider a token with issuer ``iss`` belongs to.

    Exact issuer match first; then an Entra multi-tenant provider claims any token
    whose ``iss`` shares its ``login.microsoftonline.com`` host (``common`` mints
    per-tenant issuers). Returns ``None`` if no provider owns the issuer — the
    runtime never relies on this (it uses the stamped claim), but it documents +
    tests the routing intent."""
    if not iss:
        return None
    for pc in providers:
        if pc.issuer and pc.issuer.rstrip("/") == iss.rstrip("/"):
            return pc
    for pc in providers:
        if pc.type == "entra" and _entra_multitenant(pc.issuer):
            host = "login.microsoftonline.com"
            if host in (pc.issuer or "") and host in iss:
                return pc
    return None


# ── context glue (reads the live FastMCP request) ──────────────────────────


def enforce_tenant_from_context(requested: str | None) -> str | None:
    """Resolve the **effective** tenant for the current MCP request.

    Reads the request's access token (if any) via FastMCP's ``get_access_token``,
    derives the token's tenant using the claim key of the provider that issued it
    (the multi-provider composite stamps it onto the token; the single-env-provider
    path falls back to the env/default claim), and applies :func:`resolve_tenant`.
    With no token (stdio / unauthenticated) this is an identity over ``requested``
    — so the base path is untouched. Raises :class:`CrossTenantError` on a
    cross-tenant or tenant-less authenticated request.
    """
    try:
        from fastmcp.server.dependencies import get_access_token
    except ModuleNotFoundError:  # pragma: no cover — no fastmcp ⇒ no auth ⇒ passthrough
        return requested

    token = get_access_token()
    if token is None:
        return requested  # unauthenticated (stdio) → MVP passthrough.

    claims = getattr(token, "claims", None) or {}
    # Per-provider claim key stamped by the multi-provider composite verifier;
    # absent on the single-env-provider (`--auth jwt`) path → env/default claim.
    claim_key = claims.get(_DNA_CLAIM_MARKER)
    scope_prefix = claims.get(_DNA_SCOPE_MARKER)
    token_tenant = tenant_from_token(
        claims, getattr(token, "scopes", None),
        claim_key=claim_key, scope_prefix=scope_prefix,
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


# ── multi-provider factory (build the N-provider layer from config) ────────


def _provider_verifier(pc: ProviderConfig) -> Any:
    """Build a FastMCP ``JWTVerifier`` for one provider (its own JWKS + issuer +
    audience). Entra multi-tenant relaxes the issuer to audience-only (see
    :func:`verifier_issuer`)."""
    from fastmcp.server.auth.providers.jwt import JWTVerifier

    return JWTVerifier(
        public_key=pc.public_key,
        jwks_uri=pc.jwks_uri,
        issuer=verifier_issuer(pc),
        audience=pc.audience,
        algorithm=pc.algorithm,
    )


def _multi_provider_verifier(providers: list[ProviderConfig]) -> Any:
    """A composite ``TokenVerifier`` over N providers — the multi-issuer router.

    Tries each provider's ``JWTVerifier`` in order; the ONLY one whose issuer +
    audience + signature match the token succeeds, so a token is routed to its
    provider by ``iss`` for free. On success it STAMPS the matching provider's
    ``tenant_claim`` / ``scope_prefix`` onto ``token.claims`` (keys
    ``_dna_tenant_claim`` / ``_dna_scope_prefix``), so the tenancy bridge reads the
    RIGHT per-provider claim with no global/request state — and it survives Entra
    ``common`` (where the token ``iss`` differs from the configured issuer)."""
    from fastmcp.server.auth import TokenVerifier

    pairs = [(pc, _provider_verifier(pc)) for pc in providers]

    class _MultiProviderVerifier(TokenVerifier):
        async def verify_token(self, token: str) -> Any:
            for pc, verifier in pairs:
                access = await verifier.verify_token(token)
                if access is not None:
                    claims = dict(getattr(access, "claims", None) or {})
                    claims[_DNA_CLAIM_MARKER] = pc.tenant_claim
                    claims[_DNA_SCOPE_MARKER] = pc.scope_prefix
                    access.claims = claims
                    return access
            return None

    return _MultiProviderVerifier()


def build_auth_from_config(
    providers: list[ProviderConfig],
    *,
    resource_url: str | None = None,
    authorization_servers: list[str] | None = None,
    scopes_supported: list[str] | None = None,
) -> Any:
    """Assemble the pluggable N-provider auth layer into a FastMCP auth provider.

    One ``JWTVerifier`` per provider, composed into a multi-issuer composite
    (:func:`_multi_provider_verifier`) that routes each token to its provider and
    stamps the per-provider tenant claim for the bridge. When a resource URL is
    known (arg or ``DNA_MCP_RESOURCE_URL``) the composite is wrapped as a Resource
    Server that advertises PRM (RFC 9728) listing **every** provider's issuer as an
    authorization server; otherwise the bare composite still guards the tools.

    Providers WITHOUT DCR (WorkOS/Auth0 interactive flows) plug in at the same
    ``resource_server`` seam via FastMCP's ``OAuthProxy`` — the bridge is
    provider-agnostic (it only reads the stamped claim off the verified token)."""
    if not providers:
        raise RuntimeError(
            "no auth providers — `auth.providers[]` in dna.config.yaml is empty."
        )

    composite = _multi_provider_verifier(providers)

    resource_url = resource_url or os.environ.get("DNA_MCP_RESOURCE_URL")
    if authorization_servers is None:
        env_as = os.environ.get("DNA_MCP_AUTH_SERVERS")
        if env_as:
            authorization_servers = [s.strip() for s in env_as.split(",") if s.strip()]
        else:
            authorization_servers = [p.issuer for p in providers if p.issuer]

    if resource_url and authorization_servers:
        return resource_server(
            composite,
            base_url=resource_url,
            authorization_servers=authorization_servers,
            scopes_supported=scopes_supported,
        )
    return composite


def providers_from_config(config_path: str | None = None) -> list[ProviderConfig]:
    """Load ``dna.config.yaml`` and parse its ``auth:`` section into providers.

    Raises ``RuntimeError`` when there is no config file at all (``--auth config``
    needs one); delegates shape validation to :func:`parse_auth_providers`."""
    from dna.config import load_config

    cfg = load_config(config_path)
    if cfg is None:
        raise RuntimeError(
            "--auth config needs a dna.config.yaml with an `auth:` section — none "
            "found in the current directory."
        )
    return parse_auth_providers(cfg.auth)
