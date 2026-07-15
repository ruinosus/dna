"""``dna_cli.graph._obo`` — the per-request On-Behalf-Of token exchange.

The security-critical heart of ``f-mcp-obo`` (ADR-mcp-obo §7, story
``s-mcp-obo-exchanger``). Given the VERIFIED inbound Entra assertion (token A,
whose ``aud`` is the DNA MCP app), the confidential-client credential (a secret
read from an env-var *name* in config), and a requested downstream Graph scope,
it exchanges token A at the token's **home-tenant** endpoint for a Graph-audience
**token B** minted for the same user — then returns token B for immediate use.

**Token B lives only for the request.** This function returns the token string to
its single caller (the graph tool, which puts it straight on the outbound Graph
``Authorization`` header and drops it). It is NEVER logged, persisted, cached, or
placed in a tool result. Use :func:`audit_line` to record *that* an exchange
happened — it takes no token by construction.

The MSAL call is behind an injectable ``acquire`` seam so the whole policy — scope
allow-list, home-tenant targeting, and the honest error mapping — is unit-testable
with a fake, no live Entra and no secret. The default seam builds a real MSAL
``ConfidentialClientApplication`` for the assertion's ``tid`` and calls
``acquire_token_on_behalf_of`` (the flow Microsoft recommends over hand-rolling the
POST). No token cache is used (PoC — request-lifetime only; a bounded in-memory
MSAL cache is deferred prod-hardening per ADR §6).
"""
from __future__ import annotations

import re
from typing import Any, Callable, Iterable

from .errors import (
    OboConsentRequiredError,
    OboExchangeError,
    OboInteractionRequiredError,
    OboScopeNotAllowedError,
    OboUnavailableError,
)

# The Entra login host. The exchange ALWAYS targets ``<host>/<tid>`` where ``tid``
# is the inbound token's home tenant — so OBO hits the Graph of the tenant that
# issued the token (ADR §4.4, multi-tenant correctness).
LOGIN_HOST = "https://login.microsoftonline.com"

# Entra error codes that mean "the delegated permission is not consented".
_CONSENT_AADSTS = frozenset({65001})
_AADSTS_RE = re.compile(r"AADSTS\d+")

#: The MSAL acquire seam: ``(client_id, client_secret, authority, assertion,
#: scopes) -> result dict`` (MSAL's ``acquire_token_on_behalf_of`` shape:
#: ``{"access_token": ...}`` on success, ``{"error": ..., ...}`` on failure).
Acquirer = Callable[..., dict[str, Any]]


def authority_for_tenant(tid: str) -> str:
    """The token endpoint authority for a tenant — the assertion's OWN ``tid``.

    Never a fixed / configured tenant: OBO must hit the home tenant that issued
    the inbound token (a guest/partner token exchanges at its resource tenant)."""
    return f"{LOGIN_HOST}/{tid}"


def _default_acquire(
    *, client_id: str, client_secret: str, authority: str,
    assertion: str, scopes: list[str],
) -> dict[str, Any]:
    """The production seam: a real MSAL confidential-client OBO exchange.

    Imported lazily so importing this module never requires ``msal`` (it is part
    of the optional ``graph`` extra). No token cache is passed — PoC request-
    lifetime only."""
    try:
        import msal  # optional dep — dna-cli[graph]
    except ModuleNotFoundError as exc:  # pragma: no cover — exercised via CLI
        raise OboExchangeError(
            "On-Behalf-Of needs the optional 'msal' dependency — install it with: "
            "pip install 'dna-cli[graph]'"
        ) from exc

    app = msal.ConfidentialClientApplication(
        client_id, authority=authority, client_credential=client_secret,
    )
    return app.acquire_token_on_behalf_of(user_assertion=assertion, scopes=scopes)


def exchange_on_behalf_of(
    *,
    assertion: str | None,
    tid: str | None,
    client_id: str | None,
    client_secret: str | None,
    scopes: Iterable[str],
    allowed_scopes: Iterable[str] | None = None,
    acquire: Acquirer = _default_acquire,
) -> str:
    """Exchange the inbound assertion for a downstream Graph token (token B).

    Returns the Graph-audience access-token STRING (for immediate use on the
    outbound Graph request). Fail-closed and honest on every edge:

    * no ``assertion`` / ``tid`` (non-Entra or unauthenticated) →
      :class:`OboUnavailableError` (capability gap, not a crash);
    * a requested scope outside ``allowed_scopes`` (when given) →
      :class:`OboScopeNotAllowedError`, raised BEFORE any exchange;
    * missing confidential-client credential → :class:`OboExchangeError`;
    * consent not granted → :class:`OboConsentRequiredError`;
    * Conditional-Access step-up → :class:`OboInteractionRequiredError`
      (claims challenge preserved);
    * any other failure → :class:`OboExchangeError` (sanitized — an AADSTS code at
      most, never the raw body, never a token).
    """
    scope_list = [s for s in scopes if s]

    # 1. Entra precondition — no assertion ⇒ no OBO (honest capability gap).
    if not assertion or not tid:
        raise OboUnavailableError(
            "Microsoft Graph is not available for this identity — On-Behalf-Of "
            "needs an Entra-issued token (this request has none)."
        )

    # 2. Fail-closed scope allow-list (defense in depth; the config layer also
    #    enforces it, but the exchanger refuses escalation independently).
    if allowed_scopes is not None:
        allowed = set(allowed_scopes)
        for sc in scope_list:
            if sc not in allowed:
                raise OboScopeNotAllowedError(
                    f"scope {sc!r} is not in the deployment's allow-list "
                    f"{sorted(allowed)} — refused (a tool cannot request an "
                    f"unconsented scope)."
                )

    # 3. Credential presence — a clean error, never an MSAL call with a None secret.
    if not client_id or not client_secret:
        raise OboExchangeError(
            "On-Behalf-Of is enabled but the confidential-client credential is "
            "not configured — set the env vars named by the config `graph:` block "
            "(client_id_env / credential_env)."
        )

    # 4. The exchange — always at the assertion's HOME tenant.
    authority = authority_for_tenant(tid)
    result = acquire(
        client_id=client_id, client_secret=client_secret, authority=authority,
        assertion=assertion, scopes=scope_list,
    )
    return _map_result(result, scope_list)


def _map_result(result: Any, scopes: list[str]) -> str:
    """Map an MSAL result dict → token B, or raise an honest, sanitized error.

    NEVER echoes a token or the raw error body: on success it returns the token
    string (to the single trusted caller); on failure it raises with, at most, an
    AADSTS code."""
    if not isinstance(result, dict):
        raise OboExchangeError("the OBO exchange returned an unexpected response.")

    token = result.get("access_token")
    if token:
        return token  # token B — returned to the trusted caller ONLY; never logged.

    error = str(result.get("error") or "").strip()
    desc = str(result.get("error_description") or "")
    codes = result.get("error_codes") or []
    codes = {int(c) for c in codes if isinstance(c, int)}
    aadsts = _AADSTS_RE.search(desc)
    aadsts_code = aadsts.group(0) if aadsts else None

    # Conditional Access / MFA — surface the claims challenge, do not swallow it.
    if error == "interaction_required" or result.get("claims"):
        raise OboInteractionRequiredError(
            "Microsoft Graph requires an interactive step-up (Conditional Access) "
            f"for scope(s) {scopes} — the client must satisfy the claims challenge."
            + (f" [{aadsts_code}]" if aadsts_code else ""),
            claims_challenge=result.get("claims"),
        )

    # Consent missing (AADSTS65001 / invalid_grant / consent_required).
    if (
        error in ("invalid_grant", "consent_required")
        or _CONSENT_AADSTS & codes
        or (aadsts_code == "AADSTS65001")
    ):
        raise OboConsentRequiredError(
            f"Microsoft Graph access for scope(s) {scopes} has not been consented "
            "— an administrator or the user must grant it (see the OBO setup guide)."
            + (f" [{aadsts_code}]" if aadsts_code else "")
        )

    # Anything else — sanitized: the error name + an AADSTS code, never the body.
    tag = aadsts_code or (error or "unknown_error")
    raise OboExchangeError(
        f"the On-Behalf-Of exchange failed ({tag}) — Microsoft Graph could not "
        "mint a delegated token for this request."
    )


def audit_line(
    *, tenant: str | None, tool: str, scopes: Iterable[str], ok: bool,
    detail: str | None = None,
) -> str:
    """A structured, secret-free audit line for an OBO exchange (ADR §4.1).

    Records THAT an exchange happened — tenant/workspace, tool, scopes, outcome —
    and, by construction, takes NO token/assertion/secret argument, so it can never
    leak one. ``detail`` is an already-sanitized error tag (e.g. an AADSTS code)."""
    status = "ok" if ok else "fail"
    parts = [
        "obo",
        f"tool={tool}",
        f"tenant={tenant or '-'}",
        f"scopes={','.join(scopes) or '-'}",
        f"result={status}",
    ]
    if detail:
        parts.append(f"detail={detail}")
    return " ".join(parts)
