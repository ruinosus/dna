"""``dna.tenancy.accounts`` — who the BILLING ACCOUNT is, as pure policy.

**The product decision this implements:** a subscription belongs to a billing
ACCOUNT, and one plan covers every workspace that account owns. Creating a
second workspace is not a second charge. So a workspace must record WHICH
account owns it (``Workspace.account_id``), and enforcement resolves
``workspace → account_id → AccountPlan``.

This module answers the one question that decision leaves open: **given a
verified sign-in, which account is this?** It is CORE — no HTTP, no FastMCP, no
kernel — so the answer is unit-testable and identical on every face.

TWO KINDS OF ACCOUNT
--------------------

An account is an ORGANIZATION or a PERSON, and both can be sold to.

* **Organization** — the per-IdP "which org/tenant is this token from" claim the
  auth layer already carries, configured per provider block as ``tenant_claim``
  and defaulted per provider type
  (``dna_cli._mcp_auth._PROVIDER_TENANT_CLAIM_DEFAULT``)::

      entra  → tid       clerk  → org_id     workos → org_id
      auth0  → org_id    google → hd         oidc   → (must be configured)

* **Person** — the consumer lane. A WorkOS/AuthKit (or Clerk/Auth0/Google)
  sign-in that belongs to NO organization used to resolve to no account at all,
  which meant permanent Free with no way to buy — and the consumer lane is the
  product's wedge ("your Claude memory, alive everywhere"), an individual story.
  So when there is no organization, **the account is the durable subject of the
  identity** (the ``sub`` claim): the person IS the account.

  The person lane is deliberately NOT universal. It is enabled only for
  providers whose ``sub`` is documented durable AND unique *for the issuer*
  (:data:`PROVIDER_ACCOUNT_NAMESPACES`). **Entra is excluded on purpose**: its
  ``sub`` is *pairwise* — unique per (user, application), so the same human gets
  a different ``sub`` from a different app registration, and two DNA faces would
  bill one person twice. Its durable identifier is ``oid``, but turning a
  personal Microsoft account into a billable account is a product decision that
  has not been taken; until it is, the shared-MSA refusal below stands and such
  a sign-in has NO account.

THE ID CARRIES ITS OWN KIND
---------------------------

Every ``account_id`` this module returns is **namespaced by provider and by
account kind**::

    entra-org:<tid>            an Entra (Azure AD) organization
    workos-org:<org_id>        a WorkOS organization
    workos-user:<sub>          a WorkOS person  (the consumer lane)
    clerk-org:<org_id>         clerk-user:<sub>
    auth0-org:<org_id>         auth0-user:<sub>
    google-org:<hd>            google-user:<sub>
    tenant:<value>             an account from a provider we cannot name

Two properties come from this, and only these two:

1. **Uniqueness.** A ``tid`` and a ``sub`` that happen to be the same literal
   string are now different accounts. Before the namespace, they were the same
   account — a theoretical collision, but the kind that ends with one person
   paying for a stranger's usage.
2. **Legibility.** Reading ``workos-user:user_01H…`` in a support ticket, a
   Stripe customer or a log line tells you *what kind of account* it is. That
   matters the moment a person and a company are priced differently.

⚠️ **The prefix is NOT a parsing surface.** Nothing downstream may split, read
or branch on it. ``account_plan()`` matches the whole string; the Kind schemas
call it opaque. If you find yourself writing ``if account_id.startswith("entra-")``
to decide *permission* or *entitlement*, stop — the authorization input is the
verified claim, not a substring of an id we minted. The namespace exists so two
ids never accidentally mean the same account, not so anyone can ask an id what
it is allowed to do.

**Fail-closed is the whole contract.** Every ambiguous input returns ``None``,
and ``None`` means "no account" — which the quota guard turns into the Free
floor. It never guesses, never falls back to the identity, and never falls back
to the workspace id. The cost of a wrong ``None`` is a customer under-served for
as long as it takes them to complain; the cost of a wrong non-``None`` is one
account paying for another's usage, or one account's tier leaking to strangers.
Those are not symmetric, so the tie always breaks toward ``None``.
"""
from __future__ import annotations

from typing import Any, Iterable, NamedTuple

#: The claim-key marker the composite MCP verifier stamps onto verified claims,
#: naming WHICH claim that provider block reads its account/tenant from. Kept
#: byte-identical to ``dna_cli._mcp_auth._DNA_CLAIM_MARKER`` — the CLI owns the
#: stamping, this module owns the reading, and they must agree. (The constant is
#: duplicated rather than imported because sdk-py must not depend on dna-cli.)
DNA_TENANT_CLAIM_MARKER = "_dna_tenant_claim"

#: The provider-TYPE marker the composite verifier stamps (``entra``/``workos``/
#: ``clerk``/``auth0``/``google``/``oidc``). Byte-identical to
#: ``dna_cli._mcp_auth._DNA_PROVIDER_TYPE_MARKER``. This is what tells the
#: resolver WHICH namespace to mint under, and — for the consumer lane — whether
#: this provider has a durable subject at all.
DNA_PROVIDER_TYPE_MARKER = "_dna_provider_type"

#: The provider-FAMILY marker (``microsoft``/``google``/``workos``), stamped by
#: the composite verifier AND by the single-env-provider Lane-B path
#: (``_family_stamped_verifier``), which stamps NOTHING else. Byte-identical to
#: ``dna_cli._mcp_auth._DNA_PROVIDER_FAMILY_MARKER``. Read only as a FALLBACK for
#: the provider type — it is coarser (clerk and auth0 have no family), so the
#: type stamp always wins when present.
DNA_PROVIDER_FAMILY_MARKER = "_dna_provider_family"

#: Provider FAMILY → provider TYPE. The inverse of
#: ``dna_cli._mcp_auth._PROVIDER_FAMILY``. This is what makes the real consumer
#: lane work: ``workos_provider_from_env`` (dna-cloud's Lane B) stamps only the
#: family, so without this mapping a WorkOS person would have no namespace.
FAMILY_PROVIDER_TYPE: dict[str, str] = {
    "microsoft": "entra",
    "google": "google",
    "workos": "workos",
}

#: The generic account claim a plain token may carry directly.
DEFAULT_ACCOUNT_CLAIM = "tenant"

#: Well-known per-IdP account claims, probed IN ORDER when nothing else names
#: one. Mirrors ``_PROVIDER_TENANT_CLAIM_DEFAULT``. This is a fallback for a
#: token that reached us without a provider stamp; a configured deployment
#: always takes the stamped path above.
FALLBACK_ACCOUNT_CLAIMS: tuple[str, ...] = ("tid", "org_id", "hd")

#: Which provider an ORG claim name implies when no provider stamp arrived (the
#: offline / single-env-provider path). ``org_id`` is deliberately ABSENT: three
#: providers default to it, so it names no provider and falls to the generic
#: namespace rather than guessing one.
CLAIM_PROVIDER_HINT: dict[str, str] = {"tid": "entra", "hd": "google"}

#: The separator between the namespace and the provider's own value. A colon,
#: matching the ``personal:<family>:<sub>`` convention the memory partitioning
#: already uses.
ACCOUNT_NAMESPACE_SEPARATOR = ":"

#: The namespace used when the provider cannot be named. Still namespaced (an
#: unprefixed id would collide with everything), just honest about not knowing.
GENERIC_ORG_NAMESPACE = "tenant"


class AccountNamespace(NamedTuple):
    """How one provider names its two kinds of account.

    ``person``/``subject_claim`` are ``None`` for a provider with no durable,
    issuer-unique subject — that provider simply has no consumer lane, and a
    sign-in of its with no organization resolves to ``None`` (the Free floor).
    That is the fail-closed answer, and it is the right one: inventing an
    identifier is exactly how two humans end up sharing one subscription."""

    org: str
    person: str | None = None
    subject_claim: str | None = None


#: Provider type → its namespaces. Adding a provider here is the ONLY way it
#: gets a consumer lane, and doing so is a claim about that IdP's ``sub``:
#:
#: * ``workos`` — ``sub`` is the WorkOS user id (``user_...``), stable for the
#:   life of the user within the WorkOS environment. This is dna-cloud's Lane B.
#: * ``clerk``  — ``sub`` is the Clerk user id (``user_...``), stable per instance.
#: * ``auth0``  — ``sub`` is ``<connection>|<id>``, stable per tenant.
#: * ``google`` — ``sub`` is the Google account id, stable for the account.
#: * ``entra``  — **no person lane.** ``sub`` is PAIRWISE (per user *per app*), so
#:   it is not durable across DNA's own faces; the durable ``oid`` exists, but
#:   billing a personal Microsoft account is an untaken product decision. See the
#:   module docstring and :data:`MSA_SHARED_TENANT_ID`.
#: * ``oidc``/``generic`` — unknown IdP; no assumption is safe, so no person lane.
PROVIDER_ACCOUNT_NAMESPACES: dict[str, AccountNamespace] = {
    "entra": AccountNamespace(org="entra-org"),
    "workos": AccountNamespace(org="workos-org", person="workos-user",
                               subject_claim="sub"),
    "clerk": AccountNamespace(org="clerk-org", person="clerk-user",
                              subject_claim="sub"),
    "auth0": AccountNamespace(org="auth0-org", person="auth0-user",
                              subject_claim="sub"),
    "google": AccountNamespace(org="google-org", person="google-user",
                               subject_claim="sub"),
}

#: Microsoft's well-known **shared consumer tenant**. Every personal Microsoft
#: account (outlook.com, hotmail.com, live.com — an MSA, not an org member)
#: presents THIS as its ``tid``. It identifies the consumer lane itself, not any
#: one customer, so accepting it as an ``account_id`` would put every personal
#: Microsoft user on the planet into a SINGLE billing account: the first one to
#: subscribe would upgrade all of them, and their usage would meter against that
#: one payer. It is refused — such a sign-in has NO account and gets the Free
#: floor. The consumer lane that CAN be sold to is the person lane above, and
#: Entra is not in it (its ``sub`` is pairwise; see
#: :data:`PROVIDER_ACCOUNT_NAMESPACES`).
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
    """True when ``value`` is usable as the account-identifying part of an
    ``account_id`` — i.e. the RAW claim value, before it is namespaced.

    Rejects blanks and the placeholder/shared values in
    :data:`_NON_ACCOUNT_VALUES` — most importantly
    :data:`MSA_SHARED_TENANT_ID`, which is one tenant shared by every personal
    Microsoft account and would otherwise merge them all into one payer."""
    cleaned = _clean(value)
    if cleaned is None:
        return False
    return cleaned.lower() not in _NON_ACCOUNT_VALUES


def provider_type_from_claims(
    claims: dict[str, Any] | None, *, provider_type: str | None = None
) -> str | None:
    """Which IdP TYPE verified this token — ``None`` when unknowable.

    Order: an explicit argument, then the :data:`DNA_PROVIDER_TYPE_MARKER` stamp
    (the composite verifier's, exact), then the coarser
    :data:`DNA_PROVIDER_FAMILY_MARKER` stamp mapped back through
    :data:`FAMILY_PROVIDER_TYPE` (the single-env-provider Lane-B path stamps only
    this one).

    ``None`` is a legitimate answer and it is fail-closed: an unnamed provider
    gets the generic org namespace and NO person lane."""
    explicit = _clean(provider_type)
    if explicit:
        return explicit.lower()
    claims = claims or {}
    stamped = _clean(claims.get(DNA_PROVIDER_TYPE_MARKER))
    if stamped:
        return stamped.lower()
    family = _clean(claims.get(DNA_PROVIDER_FAMILY_MARKER))
    if family:
        return FAMILY_PROVIDER_TYPE.get(family.lower())
    return None


def namespaced_account_id(namespace: str, value: str) -> str:
    """``<namespace>:<value>`` — the one place the id is assembled, so the
    format has a single definition. The value is NEVER re-encoded or lowered: it
    is the IdP's own string and must stay byte-identical, because it is what a
    human will paste into Stripe or a support ticket."""
    return f"{namespace}{ACCOUNT_NAMESPACE_SEPARATOR}{value}"


def account_id_from_claims(
    claims: dict[str, Any] | None,
    *,
    claim_key: str | None = None,
    fallback_claims: Iterable[str] | None = None,
    provider_type: str | None = None,
) -> str | None:
    """The BILLING ACCOUNT id a set of VERIFIED token claims denotes.

    **Organization first, then person.** An organization claim always wins: a
    WorkOS user who belongs to an org bills to that org, not to themselves.

    Resolution order for the ORGANIZATION — the first that yields a usable value
    wins:

    1. an explicit ``claim_key`` (the caller knows its provider's config);
    2. the claim named by the stamped :data:`DNA_TENANT_CLAIM_MARKER` — the
       per-provider ``tenant_claim`` the verifier recorded on the token;
    3. the generic :data:`DEFAULT_ACCOUNT_CLAIM` (``tenant``);
    4. the well-known per-IdP claims in :data:`FALLBACK_ACCOUNT_CLAIMS`
       (``tid`` → ``org_id`` → ``hd``).

    The winner is returned namespaced: ``<provider>-org:<value>``, or
    ``tenant:<value>`` when the provider cannot be named.

    If NO organization resolves, the PERSON lane runs — but only for a provider
    named by :func:`provider_type_from_claims` AND present in
    :data:`PROVIDER_ACCOUNT_NAMESPACES` with a ``subject_claim``. Its durable
    subject becomes the account: ``<provider>-user:<sub>``. This is the consumer
    lane, and it is why an individual can now be sold to at all.

    Returns ``None`` when neither lane yields a value that passes
    :func:`is_account_id`. ``None`` is a legitimate, expected answer — it means
    "this sign-in belongs to no billing account", and every caller must treat it
    as the **Free floor**, never as a default plan and never as another
    account's plan.

    NOTE the values it returns are OPAQUE. The namespace prefix gives them
    uniqueness and legibility; it is not a parsing surface and nothing
    downstream may branch on it to decide authorization."""
    claims = claims or {}
    ptype = provider_type_from_claims(claims, provider_type=provider_type)
    ns = PROVIDER_ACCOUNT_NAMESPACES.get(ptype or "")

    # ── the ORGANIZATION lane ────────────────────────────────────────────────
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
            org_ns = None
            if ns is not None:
                org_ns = ns.org
            else:
                # No provider stamp (offline / single-env-provider). The claim
                # NAME that matched can still name the provider for the two
                # claims that belong to exactly one — `tid` and `hd`. `org_id`
                # names three providers, so it names none, and falls through to
                # the honest generic namespace rather than a guess.
                hinted = CLAIM_PROVIDER_HINT.get(key)
                hint_ns = PROVIDER_ACCOUNT_NAMESPACES.get(hinted or "")
                org_ns = hint_ns.org if hint_ns is not None else GENERIC_ORG_NAMESPACE
            return namespaced_account_id(org_ns, candidate)

    # ── the PERSON lane (the consumer wedge) ─────────────────────────────────
    # Reached only when the sign-in belongs to no organization. Requires a NAMED
    # provider with a documented durable subject — everything else stays None.
    if ns is not None and ns.person and ns.subject_claim:
        subject = _clean(claims.get(ns.subject_claim))
        if subject and is_account_id(subject):
            return namespaced_account_id(ns.person, subject)

    return None


__all__ = [
    "ACCOUNT_NAMESPACE_SEPARATOR",
    "AccountNamespace",
    "CLAIM_PROVIDER_HINT",
    "DEFAULT_ACCOUNT_CLAIM",
    "DNA_PROVIDER_FAMILY_MARKER",
    "DNA_PROVIDER_TYPE_MARKER",
    "DNA_TENANT_CLAIM_MARKER",
    "FALLBACK_ACCOUNT_CLAIMS",
    "FAMILY_PROVIDER_TYPE",
    "GENERIC_ORG_NAMESPACE",
    "MSA_SHARED_TENANT_ID",
    "PROVIDER_ACCOUNT_NAMESPACES",
    "account_id_from_claims",
    "is_account_id",
    "namespaced_account_id",
    "provider_type_from_claims",
]
