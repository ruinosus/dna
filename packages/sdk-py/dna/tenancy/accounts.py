"""``dna.tenancy.accounts`` — who the BILLING ACCOUNT is, as pure policy.

**The product decision this implements:** a subscription belongs to a billing
ACCOUNT, and one plan covers every workspace that account owns. Creating a
second workspace is not a second charge. So a workspace must record WHICH
account owns it (``Workspace.account_id``), and enforcement resolves
``workspace → account_id → AccountPlan``.

This module answers the one question that decision leaves open: **given a
verified sign-in, which account is this?** It is CORE — no HTTP, no FastMCP, no
kernel — so the answer is unit-testable and identical on every face.

No new entity was invented. The auth layer already carries a per-IdP "which
org/tenant is this token from" claim, configured per provider block as
``tenant_claim`` and defaulted per provider type
(``dna_cli._mcp_auth._PROVIDER_TENANT_CLAIM_DEFAULT``)::

    entra  → tid       clerk  → org_id     workos → org_id
    auth0  → org_id    google → hd         oidc   → (must be configured)

That is the same string the portal's plan table has always been keyed by and
the same one the Stripe customer carries in ``metadata.tenant``. Reusing it is
what makes this a re-keying rather than a new concept.

**Fail-closed is the whole contract.** Every ambiguous input returns ``None``,
and ``None`` means "no account" — which the quota guard turns into the Free
floor. It never guesses, never falls back to the identity, and never falls back
to the workspace id. The cost of a wrong ``None`` is a customer under-served for
as long as it takes them to complain; the cost of a wrong non-``None`` is one
account paying for another's usage, or one account's tier leaking to strangers.
Those are not symmetric, so the tie always breaks toward ``None``.
"""
from __future__ import annotations

from typing import Any, Iterable

#: The claim-key marker the composite MCP verifier stamps onto verified claims,
#: naming WHICH claim that provider block reads its account/tenant from. Kept
#: byte-identical to ``dna_cli._mcp_auth._DNA_CLAIM_MARKER`` — the CLI owns the
#: stamping, this module owns the reading, and they must agree. (The constant is
#: duplicated rather than imported because sdk-py must not depend on dna-cli.)
DNA_TENANT_CLAIM_MARKER = "_dna_tenant_claim"

#: The generic account claim a plain token may carry directly.
DEFAULT_ACCOUNT_CLAIM = "tenant"

#: Well-known per-IdP account claims, probed IN ORDER when nothing else names
#: one. Mirrors ``_PROVIDER_TENANT_CLAIM_DEFAULT``. This is a fallback for a
#: token that reached us without a provider stamp; a configured deployment
#: always takes the stamped path above.
FALLBACK_ACCOUNT_CLAIMS: tuple[str, ...] = ("tid", "org_id", "hd")

#: Microsoft's well-known **shared consumer tenant**. Every personal Microsoft
#: account (outlook.com, hotmail.com, live.com — an MSA, not an org member)
#: presents THIS as its ``tid``. It identifies the consumer lane itself, not any
#: one customer, so accepting it as an ``account_id`` would put every personal
#: Microsoft user on the planet into a SINGLE billing account: the first one to
#: subscribe would upgrade all of them, and their usage would meter against that
#: one payer. It is refused — such a sign-in has NO account and gets the Free
#: floor. (See the open product question in the story: the consumer lane needs
#: an account concept of its own before it can be sold to.)
MSA_SHARED_TENANT_ID = "9188040d-6c67-4c5b-b112-36a304b66dad"

#: Claim values that never denote an account. Compared case-insensitively.
_NON_ACCOUNT_VALUES = frozenset({
    MSA_SHARED_TENANT_ID,
    "common", "organizations", "consumers",  # Entra authority placeholders.
    "none", "null", "undefined", "-",
})


def _clean(value: Any) -> str | None:
    """A non-blank string, trimmed — else ``None``. Lists yield their first
    usable string (a claim may arrive as a single-element list)."""
    if isinstance(value, str):
        v = value.strip()
        return v or None
    if isinstance(value, (list, tuple)):
        for item in value:
            got = _clean(item)
            if got:
                return got
    return None


def is_account_id(value: Any) -> bool:
    """True when ``value`` is usable as a billing ``account_id``.

    Rejects blanks and the placeholder/shared values in
    :data:`_NON_ACCOUNT_VALUES` — most importantly
    :data:`MSA_SHARED_TENANT_ID`, which is one tenant shared by every personal
    Microsoft account and would otherwise merge them all into one payer."""
    cleaned = _clean(value)
    if cleaned is None:
        return False
    return cleaned.lower() not in _NON_ACCOUNT_VALUES


def account_id_from_claims(
    claims: dict[str, Any] | None,
    *,
    claim_key: str | None = None,
    fallback_claims: Iterable[str] | None = None,
) -> str | None:
    """The BILLING ACCOUNT id a set of VERIFIED token claims denotes.

    Resolution order — the first that yields a usable value wins:

    1. an explicit ``claim_key`` (the caller knows its provider's config);
    2. the claim named by the stamped :data:`DNA_TENANT_CLAIM_MARKER` — the
       per-provider ``tenant_claim`` the verifier recorded on the token;
    3. the generic :data:`DEFAULT_ACCOUNT_CLAIM` (``tenant``);
    4. the well-known per-IdP claims in :data:`FALLBACK_ACCOUNT_CLAIMS`
       (``tid`` → ``org_id`` → ``hd``).

    Returns ``None`` when no step yields a value that passes
    :func:`is_account_id`. ``None`` is a legitimate, expected answer — it means
    "this sign-in belongs to no billing account", and every caller must treat it
    as the **Free floor**, never as a default plan and never as another
    account's plan.

    NOTE the values it returns are OPAQUE. Nothing downstream parses an
    ``account_id``; it is only ever compared."""
    claims = claims or {}

    keys: list[str] = []
    if claim_key:
        keys.append(claim_key)
    stamped = _clean(claims.get(DNA_TENANT_CLAIM_MARKER))
    if stamped:
        keys.append(stamped)
    keys.append(DEFAULT_ACCOUNT_CLAIM)
    keys.extend(
        FALLBACK_ACCOUNT_CLAIMS if fallback_claims is None else fallback_claims
    )

    seen: set[str] = set()
    for key in keys:
        if not key or key in seen:
            continue
        seen.add(key)
        candidate = _clean(claims.get(key))
        if candidate and is_account_id(candidate):
            return candidate
    return None


__all__ = [
    "DEFAULT_ACCOUNT_CLAIM",
    "DNA_TENANT_CLAIM_MARKER",
    "FALLBACK_ACCOUNT_CLAIMS",
    "MSA_SHARED_TENANT_ID",
    "account_id_from_claims",
    "is_account_id",
]
