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
_ENV_SCOPES_SUPPORTED = "DNA_MCP_SCOPES_SUPPORTED"  # comma-separated OAuth scopes to advertise in PRM
_ENV_TENANT_CLAIM = "DNA_MCP_TENANT_CLAIM"          # claim key holding the tenant
_ENV_TENANT_SCOPE_PREFIX = "DNA_MCP_TENANT_SCOPE_PREFIX"  # e.g. "tenant:" in scopes
DEFAULT_TENANT_CLAIM = "tenant"
DEFAULT_TENANT_SCOPE_PREFIX = "tenant:"

# The plan/tier axis (DNA Cloud quota). A token's *plan* claim maps to a Tier id
# (free/pro/…), which the quota guard resolves to caps via ``kernel.tier``. This
# is the SECOND axis over the SAME verified token — orthogonal to tenant: tenant
# says *which data*, plan says *how much*. Mirrors the tenant knobs exactly.
_ENV_PLAN_CLAIM = "DNA_MCP_PLAN_CLAIM"              # claim key holding the plan/tier
_ENV_PLAN_SCOPE_PREFIX = "DNA_MCP_PLAN_SCOPE_PREFIX"  # e.g. "plan:" in scopes
DEFAULT_PLAN_CLAIM = "plan"
DEFAULT_PLAN_SCOPE_PREFIX = "plan:"

# Per-provider plan-claim stamping markers — the plan twins of
# ``_DNA_CLAIM_MARKER`` / ``_DNA_SCOPE_MARKER``. The single-env-provider path (and
# today's multi-provider composite, which stamps only the tenant markers) leaves
# these ABSENT, so ``enforce_tier_from_context`` falls back to the env/default
# plan claim — the forward-compatible seam for a per-provider plan claim later.
_DNA_PLAN_CLAIM_MARKER = "_dna_plan_claim"
_DNA_PLAN_SCOPE_MARKER = "_dna_plan_scope_prefix"

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


def scopes_supported_from_env() -> list[str] | None:
    """The OAuth scopes to ADVERTISE in Protected-Resource-Metadata (RFC 9728),
    from ``DNA_MCP_SCOPES_SUPPORTED`` (comma-separated). Returns ``None`` when unset.

    This drives PRM's ``scopes_supported`` — the list an MCP client (e.g. VS Code)
    reads to learn WHICH scope to request from the authorization server. Without it,
    a client that discovers the resource has no scope to ask for and can stall at
    the IdP (the Entra ``--auth jwt`` symptom).

    **Azure scope-format nuance** (PrefectHQ/fastmcp#3002): advertise the FULL scope
    URI here (e.g. ``api://dna-mcp-dnacloud/user_impersonation``) — the token's
    ``scp`` claim carries only the SHORT form (``user_impersonation``). So this value
    belongs ONLY in the PRM advertisement, NEVER in the JWTVerifier's
    ``required_scopes`` (a full-vs-short mismatch would reject valid tokens). Advertise
    only; do not hard-require.
    """
    raw = os.environ.get(_ENV_SCOPES_SUPPORTED)
    if not raw:
        return None
    scopes = [s.strip() for s in raw.split(",") if s.strip()]
    return scopes or None


def plan_claim_key() -> str:
    """The claim key the plan/tier is read from (``DNA_MCP_PLAN_CLAIM``, default
    ``plan``)."""
    return os.environ.get(_ENV_PLAN_CLAIM) or DEFAULT_PLAN_CLAIM


def plan_scope_prefix() -> str:
    """The scope prefix a plan may be encoded under (``DNA_MCP_PLAN_SCOPE_PREFIX``,
    default ``plan:`` → a ``plan:pro`` scope means tier ``pro``)."""
    return os.environ.get(_ENV_PLAN_SCOPE_PREFIX) or DEFAULT_PLAN_SCOPE_PREFIX


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


# ── the personal-identity axis (personal memory) — pure core ───────────────
#
# The THIRD orthogonal axis over the SAME verified token, mirroring the tenant /
# plan twins: tenant says *which workspace's data*, plan says *how much*, and the
# oid says *whose PERSONAL memory* (ADR-personal-memory). It is the seam the ADR
# flagged as "currently DISCARDED" — the bridge read only the tenant claim (tid),
# never the durable ``oid``; personal memory is the first feature to plumb it into
# a data path. Unlike tenant, the oid is NEVER a caller argument — it is always
# derived server-side (verified token claim, or the offline ``DNA_PERSONAL_ID``),
# which is INV-PERSONAL layer 1.

_ENV_PERSONAL_ID = "DNA_PERSONAL_ID"  # the offline/stdio single-user identity
_ENV_OID_CLAIM = "DNA_MCP_OID_CLAIM"  # claim key holding the durable identity oid
DEFAULT_OID_CLAIM = "oid"             # Entra durable object id (Model B key)


def oid_claim_key() -> str:
    """The claim key the durable identity ``oid`` is read from
    (``DNA_MCP_OID_CLAIM``, default ``oid`` — the Entra object id)."""
    return os.environ.get(_ENV_OID_CLAIM) or DEFAULT_OID_CLAIM


def oid_from_token(
    claims: dict[str, Any] | None, *, claim_key: str | None = None
) -> str | None:
    """Extract the durable identity ``oid`` from a verified token's claims — pure,
    no context. Returns ``None`` when the token carries no oid (an authenticated
    request with no oid then fails closed for personal memory)."""
    if not claims:
        return None
    raw = claims.get(claim_key or oid_claim_key())
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def personal_id_from_env() -> str | None:
    """The offline/stdio personal identity from ``DNA_PERSONAL_ID`` — the local
    single-user oid when there is no verified token. ``None`` when unset."""
    raw = os.environ.get(_ENV_PERSONAL_ID)
    return raw.strip() if raw and raw.strip() else None


def resolve_personal_oid(
    *, token_present: bool, token_oid: str | None, env_oid: str | None
) -> str:
    """Reconcile the server-derived personal identity ``oid`` — the policy,
    fail-closed (ADR-personal-memory §5 / §7 layer 1).

    * token present WITH an ``oid`` claim → that oid (the durable identity).
    * token present WITHOUT an ``oid`` claim → **denied** (an authenticated
      request that carries no verified identity gets NO personal memory — never a
      null/blank partition; mirrors the tenant bridge's fail-closed discipline).
    * no token (stdio / local) → ``env_oid`` (``DNA_PERSONAL_ID``) when set, else
      **denied** (offline personal memory needs an explicit local identity).

    Always returns a concrete non-empty oid or raises
    :class:`~dna.memory.personal.PersonalIdentityRequired`.
    """
    from dna.memory.personal import PersonalIdentityRequired

    if token_present:
        if not token_oid:
            raise PersonalIdentityRequired(
                "authenticated request carries no verified identity "
                f"(claim {oid_claim_key()!r}) — personal memory is denied "
                "(fail-closed); a personal partition must key on a real identity."
            )
        return token_oid
    if env_oid:
        return env_oid
    raise PersonalIdentityRequired(
        "personal memory needs an identity but none is available — set "
        f"{_ENV_PERSONAL_ID} for the offline/local single-user identity, or "
        "authenticate with a token that carries an oid claim."
    )


# ── the plan/tier axis (DNA Cloud quota) — pure core, mirror the tenant twins ─


def tier_from_token(
    claims: dict[str, Any] | None,
    scopes: list[str] | None = None,
    *,
    claim_key: str | None = None,
    scope_prefix: str | None = None,
) -> str | None:
    """Extract the DNA Cloud tier a token maps to — pure, no context.

    The plan twin of :func:`tenant_from_token`. Two encodings are honored (a claim
    wins over a scope):

    1. a **claim** ``{claim_key: "<tier>"}`` (default key ``plan``), and
    2. a **scope** ``"<scope_prefix><tier>"`` (default ``plan:pro`` → tier ``pro``).

    Returns ``None`` when the token carries neither — :func:`resolve_tier` then
    treats that as the Free floor (a missing plan is NOT a denial, unlike a missing
    tenant which fails closed).
    """
    key = claim_key or plan_claim_key()
    prefix = scope_prefix or plan_scope_prefix()

    # 1. explicit claim.
    if claims:
        raw = claims.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(raw, (list, tuple)):
            for item in raw:
                if isinstance(item, str) and item.strip():
                    return item.strip()

    # 2. plan-encoding scope (plan:<x>).
    for sc in scopes or []:
        if isinstance(sc, str) and sc.startswith(prefix):
            candidate = sc[len(prefix):].strip()
            if candidate:
                return candidate

    return None


def resolve_tier(
    *,
    token_present: bool,
    token_tier: str | None,
    default: str = "free",
) -> str:
    """Reconcile the token's tier into an effective tier id — the policy.

    Deliberately DIFFERENT from :func:`resolve_tenant`: a missing tier is **never a
    denial** and **never unlimited** — it is the **Free floor**:

    * ``token_present=False`` (no auth / stdio) → ``default`` (the caller never
      meters an unauthenticated call, but the policy still returns a concrete tier).
    * token present, no ``token_tier`` → ``default`` (Free floor — authenticated but
      un-planned callers get the free caps, never denied, never unlimited).
    * token present with a tier → that tier.

    Always returns a concrete tier id; never raises.
    """
    if not token_present:
        return default
    if not token_tier:
        return default
    return token_tier


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


# ── Model B: workspace resolution (identity → membership → workspace_id) ────
#
# The ADR "Model B" rework of the tenant-from-tid bridge above: the DNA tenancy
# dimension resolves from the caller's VERIFIED IDENTITY + WorkspaceMembership,
# NOT from the Azure `tid`. The PURE policy (Identity/Membership/resolve_workspace)
# lives in the CORE SDK (`dna.tenancy.resolution`) so it is transport-agnostic and
# has a byte-behavioral TS twin (guarded by tests/parity-fixtures/workspace-
# resolution/). Here is only the FastMCP+kernel glue: read the live token, load
# the grants, apply the pure resolver.


def identity_from_context() -> Any:
    """The verified :class:`dna.tenancy.resolution.Identity` of the CURRENT MCP
    request, or ``None`` when there is no token (stdio / unauthenticated).

    Reads the request's access token via FastMCP's ``get_access_token`` and
    distills ONLY verified claims (oid / email / preferred_username / upn / tid).
    The per-provider tenant-claim markers stamped by the multi-provider composite
    are irrelevant here — the identity is read from the standard Entra identity
    claims, not the (now-demoted) tenant claim."""
    from dna.tenancy.resolution import identity_from_token

    try:
        from fastmcp.server.dependencies import get_access_token
    except ModuleNotFoundError:  # pragma: no cover — no fastmcp ⇒ no auth
        return None

    token = get_access_token()
    if token is None:
        return None
    claims = getattr(token, "claims", None) or {}
    return identity_from_token(claims)


def workspace_from_mcp_path(path: str | None) -> str | None:
    """Extract the workspace SELECTOR from a per-workspace MCP URL path — pure.

    ADR "Model B" §2.2: a client (VS Code) picks its workspace by URL —
    ``…/w/<workspace-id>/mcp``. This reads ``<workspace-id>`` from the path so the
    workspace is a *named, verified* claim (the path names it; membership
    authorizes it — never trusted blind). A bare ``/mcp`` (or any path without the
    ``/w/<id>/`` segment) returns ``None`` → the resolver falls back to the sole /
    default membership.

    Matches ``/w/<id>/mcp`` anywhere in the path (with or without a trailing
    slash, and regardless of the mount prefix), e.g. ``/w/ws-a/mcp``,
    ``/w/ws-a/mcp/``. The id is any non-empty, non-``/`` segment."""
    if not path:
        return None
    segments = [s for s in path.split("/") if s]
    # find the LAST `w` immediately followed by an id then `mcp` (mount-prefix safe).
    # i ranges so that i+2 (the `mcp` segment) stays in-bounds.
    for i in range(len(segments) - 3, -1, -1):
        if segments[i] == "w" and segments[i + 2] == "mcp":
            candidate = segments[i + 1].strip()
            if candidate:
                return candidate
    return None


def workspace_selector_from_context() -> str | None:
    """The workspace id named in the CURRENT MCP request's URL path (``/w/<id>/mcp``),
    or ``None`` (stdio, no HTTP request, or a bare ``/mcp``).

    Reads the live Starlette request via FastMCP's ``get_http_request`` and applies
    the pure :func:`workspace_from_mcp_path`. Fail-soft: any absence (no fastmcp, no
    HTTP request context — e.g. stdio) yields ``None`` so the resolver falls back to
    the identity's sole/default membership."""
    try:
        from fastmcp.server.dependencies import get_http_request
    except ModuleNotFoundError:  # pragma: no cover — no fastmcp ⇒ no HTTP
        return None
    try:
        request = get_http_request()
    except Exception:  # noqa: BLE001 — no active HTTP request (stdio / non-HTTP tool call)
        return None
    if request is None:
        return None
    path = getattr(getattr(request, "url", None), "path", None)
    return workspace_from_mcp_path(path)


def _combine_workspace_selectors(
    path_selector: str | None, requested: str | None
) -> str | None:
    """Reconcile the URL-path workspace selector with an explicit tool ``requested``
    arg. Both are only ever SELECTORS (re-verified against membership downstream);
    this just picks the effective one and rejects a contradictory pair.

    * neither → ``None`` (sole/default membership);
    * exactly one → that one;
    * both, equal → that value;
    * both, different → a contradictory request → deny (:class:`CrossTenantError`
      surfaced as a tool error) rather than silently preferring one."""
    if path_selector is not None and requested is not None and path_selector != requested:
        raise CrossTenantError(
            f"conflicting workspace selectors: URL path names {path_selector!r} but "
            f"the request arg names {requested!r} — refuse to guess (denied)"
        )
    return requested if requested is not None else path_selector


async def enforce_workspace_from_context(live: Any, requested: str | None) -> str | None:
    """Resolve the **effective workspace** for the current MCP request (Model B).

    The rework of :func:`enforce_tenant_from_context`: instead of reading the
    token's ``tid`` as the tenant, resolve the workspace from the caller's
    verified identity + its active :class:`WorkspaceMembership` grants. With no
    token (stdio / unauthenticated) this is an identity over ``requested`` — the
    base path is untouched.

    Fail-OPEN-to-legacy seam (mirrors the quota guard's "no tiers configured →
    no-op"): when the source has **no WorkspaceMembership grants at all** it never
    opted into workspaces (OSS / pre-Model-B), so this falls back to the legacy
    ``tid`` tenancy (:func:`enforce_tenant_from_context`) — the existing
    single-tenant-token + self-host deployments keep working unchanged. Model B is
    ENGAGED only once workspaces exist (DNA Cloud, where the F1 seed created
    workspace #1 + the founder's grant); THEN the ``tid`` stops being the tenancy
    key and a request with no active membership is denied (fail-closed).

    Raises :class:`dna.tenancy.resolution.CrossWorkspaceError` on a no-membership /
    cross-workspace authenticated request (surfaced as a tool error by the caller).
    """
    from dna.tenancy.resolution import Membership, resolve_workspace

    if not token_present_in_context():
        return requested  # stdio / local → identity passthrough (base path).

    # The per-workspace URL (`…/w/<id>/mcp`) is the PRIMARY selector (ADR §2.2):
    # combine it with any explicit tool arg (both are re-verified against
    # membership below; a contradictory pair is denied).
    effective_requested = _combine_workspace_selectors(
        workspace_selector_from_context(), requested
    )

    identity = identity_from_context()
    grants_raw = await live.kernel.workspace_memberships()
    if not grants_raw:
        # No workspaces configured → legacy tid tenancy (OSS / pre-Model-B).
        return enforce_tenant_from_context(effective_requested)

    memberships = [Membership.from_spec(g.get("spec") or {}) for g in grants_raw]
    return resolve_workspace(
        token_present=True,
        identity=identity,
        requested=effective_requested,
        memberships=memberships,
    )


def entra_obo_assertion_from_context() -> tuple[str | None, str | None]:
    """The current request's raw Entra assertion (token A) + its home tenant
    (``tid``), for the Microsoft On-Behalf-Of exchange — or ``(None, None)``.

    OBO (``dna_cli.graph``) needs the RAW inbound token string as the ``assertion``
    (the exact verified token whose ``aud`` is the DNA MCP app) and the token's
    ``tid`` (the home tenant the exchange must target). This reads both off the live
    FastMCP access token. Returns ``(None, None)`` when there is no token (stdio /
    unauthenticated) OR the token is NOT an Entra identity (no ``tid`` claim —
    Clerk/WorkOS/OIDC), which is the honest capability-gap signal the graph tools
    branch on (ADR-mcp-obo §4.4). The token is never logged here."""
    try:
        from fastmcp.server.dependencies import get_access_token
    except ModuleNotFoundError:  # pragma: no cover — no fastmcp ⇒ no auth
        return None, None

    token = get_access_token()
    if token is None:
        return None, None
    claims = getattr(token, "claims", None) or {}
    tid = claims.get("tid")  # the standard Entra home-tenant claim.
    raw = getattr(token, "token", None)
    if not tid or not raw:
        return None, None
    return str(raw), str(tid)


def enforce_oid_from_context() -> str:
    """Resolve the **server-derived personal identity oid** for the current MCP
    request — the personal-memory twin of :func:`enforce_tenant_from_context`.

    Reads the request's access token (if any) via FastMCP's ``get_access_token``,
    extracts the durable ``oid`` claim, and applies :func:`resolve_personal_oid`:
    an authenticated request with no oid is DENIED (fail-closed); with no token
    (stdio / local) it falls back to ``DNA_PERSONAL_ID``. The oid is NEVER taken
    from a caller argument (INV-PERSONAL layer 1) — this is the ONLY way the
    personal partition ``personal:<oid>`` is keyed. Raises
    :class:`~dna.memory.personal.PersonalIdentityRequired` when no identity can be
    resolved."""
    env_oid = personal_id_from_env()
    try:
        from fastmcp.server.dependencies import get_access_token
    except ModuleNotFoundError:  # pragma: no cover — no fastmcp ⇒ no auth ⇒ offline
        return resolve_personal_oid(
            token_present=False, token_oid=None, env_oid=env_oid
        )

    token = get_access_token()
    if token is None:
        return resolve_personal_oid(
            token_present=False, token_oid=None, env_oid=env_oid
        )

    claims = getattr(token, "claims", None) or {}
    token_oid = oid_from_token(claims)
    return resolve_personal_oid(
        token_present=True, token_oid=token_oid, env_oid=env_oid
    )


def token_present_in_context() -> bool:
    """True when the CURRENT MCP request carries a verified access token.

    The single bit the quota guard needs to tell *authenticated / hosted SaaS*
    (meter + rate-limit + feature-gate) from *stdio / local / ``auth=None``* (an
    identity — no metering, unlimited). With no ``fastmcp`` installed there is no
    auth at all → ``False``. Mirrors the ``get_access_token() is None`` check the
    tenant bridge already makes."""
    try:
        from fastmcp.server.dependencies import get_access_token
    except ModuleNotFoundError:  # pragma: no cover — no fastmcp ⇒ no auth
        return False
    return get_access_token() is not None


def enforce_tier_from_context(default: str = "free") -> str:
    """Resolve the **effective tier** for the current MCP request — the plan twin
    of :func:`enforce_tenant_from_context`.

    Reads the request's access token (if any) via FastMCP's ``get_access_token``,
    derives the token's tier using the plan claim of the provider that issued it
    (a per-provider plan claim is honored if the verifier stamps one; otherwise the
    env/default ``plan`` claim), and applies :func:`resolve_tier`. With no token
    (stdio / unauthenticated) this returns ``default`` — and the CALLER must not
    meter that path (see ``token_present_in_context``). Never raises: a missing tier
    is the Free floor, not a denial."""
    try:
        from fastmcp.server.dependencies import get_access_token
    except ModuleNotFoundError:  # pragma: no cover — no fastmcp ⇒ no auth
        return default

    token = get_access_token()
    if token is None:
        return default  # unauthenticated (stdio) → the default tier (not metered).

    claims = getattr(token, "claims", None) or {}
    # Per-provider plan-claim key stamped by a (future) plan-aware verifier; absent
    # today → env/default plan claim.
    claim_key = claims.get(_DNA_PLAN_CLAIM_MARKER)
    scope_prefix = claims.get(_DNA_PLAN_SCOPE_MARKER)
    token_tier = tier_from_token(
        claims, getattr(token, "scopes", None),
        claim_key=claim_key, scope_prefix=scope_prefix,
    )
    return resolve_tier(
        token_present=True, token_tier=token_tier, default=default
    )


def token_has_explicit_plan_claim() -> bool:
    """True when the CURRENT MCP request's token carries an explicit plan/tier
    claim (or plan-encoding scope).

    The single bit the billing→enforcement bridge needs: whether to trust the
    token's plan verbatim (a claim WINS) or fall back to the ``WorkspacePlan``
    store (which dna-cloud's Stripe webhook writes) before the Free floor. With no
    token / no fastmcp there is no claim → ``False`` (the guard then consults the
    store keyed by workspace). Reads the SAME claim key / scope prefix as
    :func:`enforce_tier_from_context`, so the two never disagree on what "the
    token's plan" means."""
    try:
        from fastmcp.server.dependencies import get_access_token
    except ModuleNotFoundError:  # pragma: no cover — no fastmcp ⇒ no auth
        return False

    token = get_access_token()
    if token is None:
        return False

    claims = getattr(token, "claims", None) or {}
    claim_key = claims.get(_DNA_PLAN_CLAIM_MARKER)
    scope_prefix = claims.get(_DNA_PLAN_SCOPE_MARKER)
    return tier_from_token(
        claims, getattr(token, "scopes", None),
        claim_key=claim_key, scope_prefix=scope_prefix,
    ) is not None


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
            scopes_supported=scopes_supported_from_env(),
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

    # An explicit arg wins; otherwise advertise the env-configured scopes in PRM
    # (same full-scope-only-in-PRM nuance as the single-provider path above).
    if scopes_supported is None:
        scopes_supported = scopes_supported_from_env()

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
