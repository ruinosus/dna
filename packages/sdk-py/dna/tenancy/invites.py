"""``dna.tenancy.invites`` — the pure invite/accept policy (Model B, F3).

The cross-org JOIN half of ADR "Model B" (feature ``f-ws-invites``): a workspace
Owner/Admin invites a collaborator from ANY Azure org **by email**; the invitee's
first VERIFIED sign-in binds their durable ``oid`` to the pending grant and flips
it ``active``. This module is the CORE decision layer — pure, no FastMCP / HTTP /
kernel import — so it is transport-agnostic and has a byte-behavioral TS twin
(``src/tenancy/invites.ts``), gated by the shared parity fixtures at
``tests/parity-fixtures/workspace-invite/``.

It sits ON TOP of ``dna.tenancy.resolution`` (reusing :class:`Identity`,
:class:`Membership`, ``normalize_email`` and ``membership_matches_identity``): the
resolver decides *which workspace a request runs against*; this module decides
*who may invite* and *which pending invite a verified sign-in binds*.

Security model (impersonation-proof — the whole point):

* **Authorization to invite** is a role check on an ACTIVE grant the actor holds
  in *that* workspace (Owner/Admin only). A pending grant confers nothing, and a
  role in another workspace does not leak across the boundary.
* **Accepting an invite matches ONLY on a verified email claim.** The IdP vouches
  for the email — ``verified_email_from_claims`` accepts Entra's verified UPN
  (``preferred_username``/``upn``) always, and a bare ``email`` claim ONLY when the
  token also carries a truthy ``email_verified``. An unverified email → no match →
  no access (fail-closed). A caller-supplied field is never trusted.
* **The bind key is the durable ``oid``.** ``bindable_invites_for`` returns only
  grants whose ``identity_oid`` is still NULL (unbound). A grant already bound to
  an ``oid`` is NEVER returned — so a *different* ``oid`` sharing the invited email
  can NOT hijack an accepted membership. A token with no ``oid`` can bind nothing
  (there is no durable key to bind to).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from dna.tenancy.resolution import (
    Identity,
    Membership,
    identity_from_token,
    membership_matches_identity,
    normalize_email,
)

# The workspace-level roles that may invite / list members (the RBAC gate). A
# reference to the standard Role ladder (owner > admin > member > guest).
INVITE_ROLES = ("owner", "admin")

# Role ranks — highest-role-wins when an identity holds multiple active grants in
# one workspace (mirrors the portfolio ``_ROLE_RANKS``).
_ROLE_RANKS: dict[str, int] = {"owner": 40, "admin": 30, "member": 20, "guest": 10}

# The verified-identity email claims. Entra's ``preferred_username`` / ``upn`` are
# the verified UPN and are trusted as-is; a bare ``email`` claim is trusted ONLY
# when the token also asserts ``email_verified`` truthy (an IdP that does not
# verify email cannot be used to claim an invite by email — fail-closed).
_VERIFIED_UPN_CLAIMS = ("preferred_username", "upn")
DEFAULT_EMAIL_CLAIM = "email"
DEFAULT_EMAIL_VERIFIED_CLAIM = "email_verified"


def _clean(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _is_truthy(v: Any) -> bool:
    """Loose truthiness for an ``email_verified`` claim (bool, or the strings a
    JWT may carry: ``"true"`` / ``"1"`` / ``"yes"``)."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    if isinstance(v, (int, float)):
        return v == 1
    return False


def verified_email_from_claims(
    claims: dict[str, Any] | None,
    *,
    email_claim: str | None = None,
    email_verified_claim: str | None = None,
) -> str | None:
    """The IdP-VERIFIED email a token asserts, normalized — or ``None``.

    This is the single security gate for accepting an invite. It returns a
    normalized email ONLY when the claim is trustworthy:

    * a bare ``email`` claim wins WHEN the token also carries a truthy
      ``email_verified`` (the IdP verified the address);
    * else Entra's ``preferred_username`` / ``upn`` (the verified UPN) is used;
    * otherwise ``None`` — an unverified email cannot claim an invite (fail-closed).

    Never reads a caller-supplied field; the claims come from a verified token.
    """
    claims = claims or {}
    email_key = email_claim or DEFAULT_EMAIL_CLAIM
    verified_key = email_verified_claim or DEFAULT_EMAIL_VERIFIED_CLAIM

    email = _clean(claims.get(email_key))
    if email and _is_truthy(claims.get(verified_key)):
        return normalize_email(email)
    for key in _VERIFIED_UPN_CLAIMS:
        upn = _clean(claims.get(key))
        if upn:
            return normalize_email(upn)
    return None


def role_in_workspace(
    identity: Identity | None,
    workspace_id: str,
    memberships: Iterable[Membership],
) -> str | None:
    """The role ``identity`` holds via an ACTIVE grant in ``workspace_id`` —
    highest-role-wins across multiple grants, ``None`` when it holds none.

    Uses the resolver's ``membership_matches_identity`` (the oid-durable,
    verified-email-handle rule), so a bound grant matches on ``oid`` and an
    active-but-unbound grant matches on the verified email — a *pending* grant
    never matches (it authorizes nothing)."""
    if identity is None:
        return None
    best: str | None = None
    best_rank = -1
    for m in memberships:
        if m.workspace_id != workspace_id:
            continue
        if not membership_matches_identity(m, identity):
            continue
        rank = _ROLE_RANKS.get(m.role, 0)
        if rank > best_rank:
            best_rank = rank
            best = m.role
    return best


def can_invite(role: str | None) -> bool:
    """True when ``role`` may invite / list members (Owner or Admin)."""
    return role in INVITE_ROLES


def bindable_invites_for(
    identity: Identity | None,
    verified_email: str | None,
    memberships: Iterable[Membership],
) -> list[Membership]:
    """Every UNBOUND grant a verified sign-in may bind — the accept candidates.

    A grant is bindable iff its ``identity_oid`` is NULL (never yet bound) and its
    ``identity_email`` matches the ``verified_email`` (case-folded). Returns them
    in first-seen order (a user invited into several workspaces binds them all on
    one sign-in).

    Fail-closed pre-conditions (return ``[]``):

    * no durable ``oid`` on the identity → nothing to bind to;
    * no ``verified_email`` → the caller cannot prove the invite handle;
    * a grant already bound to some ``oid`` → skipped, so a different ``oid`` can
      never rebind (hijack) an accepted membership.
    """
    if identity is None or not identity.oid:
        return []
    if not verified_email:
        return []
    target = normalize_email(verified_email)
    out: list[Membership] = []
    for m in memberships:
        if m.identity_oid:  # already bound → not claimable via email (no hijack).
            continue
        if m.identity_email and normalize_email(m.identity_email) == target:
            out.append(m)
    return out


@dataclass(frozen=True)
class AcceptResult:
    """The decision for one bound grant: which workspace, and whether the bind
    also ACTIVATED it (a ``pending`` invite → ``active``; an already-active
    unbound seed just captures the oid, ``activated=False``)."""

    workspace_id: str
    role: str
    activated: bool


def plan_accept(
    claims: dict[str, Any] | None,
    memberships: Iterable[Membership],
) -> list[AcceptResult]:
    """Pure accept plan for a verified token's ``claims`` — the grants a sign-in
    binds and whether each is newly activated. Empty when nothing is claimable
    (unverified email, no oid, no matching unbound invite). The write side
    (``accept_invites_impl``) turns this into idempotent ``kernel.write_document``
    upserts."""
    identity = identity_from_token(claims)
    verified_email = verified_email_from_claims(claims)
    grants = bindable_invites_for(identity, verified_email, list(memberships))
    return [
        AcceptResult(
            workspace_id=m.workspace_id,
            role=m.role,
            activated=(m.status == "pending"),
        )
        for m in grants
    ]
