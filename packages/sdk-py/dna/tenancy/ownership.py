"""``dna.tenancy.ownership`` — the pure workspace-OWNERSHIP policy (Model B).

The decision layer shared by the two owner-bootstrap endpoints (feature
``f-ws-owner-provision``):

* ``POST /v1/workspaces/{id}/provision-owner`` — the FIRST-login bootstrap. It
  needs to know whether the workspace already has an active owner (idempotency /
  first-owner-only, so a later user does not auto-escalate).
* ``POST /v1/workspaces/{id}/members/revoke`` — Owner/Admin removes a member. It
  needs the RBAC gate PLUS the crown-jewel invariant that the **last remaining
  active owner can NEVER be revoked** (a workspace must never be orphaned).

Like ``resolution`` and ``invites`` this module is CORE — pure, no FastMCP / HTTP
/ kernel import — so it is transport-agnostic and has a byte-behavioral TypeScript
twin (``src/tenancy/ownership.ts``), gated by the shared parity fixtures at
``tests/parity-fixtures/workspace-ownership/``.

It sits ON TOP of ``dna.tenancy.resolution`` (an owner is just an ``active`` grant
whose ``role`` is ``owner``). Only ``active`` grants ever count as an owner — a
``pending`` owner invite authorizes nothing, exactly like everywhere else in the
Model B policy (fail-closed).

Security model:

* **``has_active_owner``** is the provision-owner first-owner probe: it is TRUE
  the moment any active owner exists, so provisioning is a NO-OP thereafter (a
  later user cannot auto-become owner of an already-founded workspace).
* **``is_last_active_owner``** is the revoke guard: a target grant that is the
  SOLE active owner of the workspace cannot be revoked — losing it would leave the
  workspace with no owner and nobody able to invite/manage. Fail-closed: when in
  doubt (the target IS an active owner and no OTHER active owner remains), deny.
* **``plan_revoke``** composes the two deny reasons an operator cares about — the
  RBAC deny (actor is not Owner/Admin) and the last-owner deny — into one
  decision, so both faces (and both languages) agree byte-for-byte.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from dna.tenancy.resolution import Membership, normalize_email

# The role that "owns" a workspace (the top of the ladder). An active grant with
# this role is what ``has_active_owner`` / ``is_last_active_owner`` count.
OWNER_ROLE = "owner"

# The workspace roles that may revoke a member (mirror ``invites.INVITE_ROLES`` —
# the same Owner/Admin management gate).
REVOKE_ROLES = ("owner", "admin")


def active_owners(
    workspace_id: str, memberships: Iterable[Membership]
) -> list[Membership]:
    """Every ACTIVE owner grant of ``workspace_id`` — in first-seen order.

    An owner is an ``active`` grant whose ``role`` is ``owner`` (a ``pending``
    owner invite does NOT count — it authorizes nothing). Scoped strictly to the
    given workspace."""
    out: list[Membership] = []
    for m in memberships:
        if (
            m.workspace_id == workspace_id
            and m.status == "active"
            and (m.role or "").lower() == OWNER_ROLE
        ):
            out.append(m)
    return out


def has_active_owner(workspace_id: str, memberships: Iterable[Membership]) -> bool:
    """True when ``workspace_id`` already has at least one active owner — the
    provision-owner first-owner probe (idempotency / no auto-escalation)."""
    return bool(active_owners(workspace_id, list(memberships)))


def _same_grant(a: Membership, b: Membership) -> bool:
    """Identity of a grant for the last-owner count: same workspace AND same
    subject (durable ``oid`` when both are bound, else the normalized email).

    Matching the subject — not object identity — means the count is correct even
    when the ``target`` was rebuilt from a spec dict rather than being the very
    object in ``memberships`` (the impl locates the target independently)."""
    if a.workspace_id != b.workspace_id:
        return False
    if a.identity_oid and b.identity_oid:
        return a.identity_oid == b.identity_oid
    return (
        bool(a.identity_email)
        and bool(b.identity_email)
        and normalize_email(a.identity_email) == normalize_email(b.identity_email)
    )


def is_last_active_owner(
    workspace_id: str, target: Membership, memberships: Iterable[Membership]
) -> bool:
    """True when revoking ``target`` would remove the LAST active owner of
    ``workspace_id`` — the fail-closed revoke guard.

    True iff ``target`` is itself an active owner of the workspace AND no OTHER
    active owner remains (an owner other than the target). Any pending owner is
    ignored (it cannot hold the workspace). If ``target`` is not an active owner,
    this is False (revoking a member/admin never orphans the workspace)."""
    owners = active_owners(workspace_id, list(memberships))
    target_is_owner = (
        target.workspace_id == workspace_id
        and target.status == "active"
        and (target.role or "").lower() == OWNER_ROLE
    )
    if not target_is_owner:
        return False
    # An OTHER active owner (a different subject) keeps the workspace safe.
    for o in owners:
        if not _same_grant(o, target):
            return False
    return True


@dataclass(frozen=True)
class RevokeDecision:
    """The pure decision for a revoke request. ``reason`` is a stable machine
    code the faces map to HTTP: ``ok`` (allowed), ``not_authorized`` (actor is
    not Owner/Admin → 403), ``last_owner`` (would orphan the workspace → 409),
    ``not_found`` (target holds no grant here → 404 / no-op)."""

    allowed: bool
    reason: str


def can_revoke_role(actor_role: str | None) -> bool:
    """True when ``actor_role`` may revoke a member (Owner or Admin)."""
    return actor_role in REVOKE_ROLES


def plan_revoke(
    actor_role: str | None,
    target: Membership | None,
    workspace_id: str,
    memberships: Iterable[Membership],
) -> RevokeDecision:
    """Decide a revoke — the single policy front door both faces call.

    Order of checks (fail-closed, deny wins):

    1. **RBAC** — ``actor_role`` must be Owner/Admin, else ``not_authorized``.
    2. **target present** — a ``None`` target (the identity holds no grant in this
       workspace) is ``not_found`` (a clear no-op, not an error to hide).
    3. **last-owner** — revoking the sole active owner is ``last_owner`` (denied),
       so the workspace is never orphaned.

    RBAC is checked BEFORE anything else so an unauthorized caller learns nothing
    about the target's membership (no existence oracle)."""
    if not can_revoke_role(actor_role):
        return RevokeDecision(allowed=False, reason="not_authorized")
    if target is None:
        return RevokeDecision(allowed=False, reason="not_found")
    if is_last_active_owner(workspace_id, target, memberships):
        return RevokeDecision(allowed=False, reason="last_owner")
    return RevokeDecision(allowed=True, reason="ok")


def membership_from_case(spec: dict[str, Any]) -> Membership:
    """Build a :class:`Membership` from a parity-fixture / spec dict (test seam —
    a thin alias of :meth:`Membership.from_spec` kept local so the ownership
    fixtures do not reach across modules)."""
    return Membership.from_spec(spec)
