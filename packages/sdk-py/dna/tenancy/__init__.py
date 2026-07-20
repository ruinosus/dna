"""``dna.tenancy`` — the DNA-native workspace tenancy layer (ADR "Model B").

The pure, transport-agnostic **workspace resolution** policy: a verified
identity (Entra ``oid`` + verified email + ``tid``-as-provenance) is mapped to a
``workspace_id`` via its active :class:`WorkspaceMembership` grants — never via
the Azure ``tid``. This is the crown-jewel authorization decision of Model B; it
lives in the CORE (no FastMCP / HTTP / kernel import) so it is fully
unit-testable, and is guarded by the golden fixtures at
``tests/golden-fixtures/workspace-resolution/``.
"""
from __future__ import annotations

import re

from dna.tenancy.invites import (
    AcceptResult,
    INVITE_ROLES,
    bindable_invites_for,
    can_invite,
    plan_accept,
    role_in_workspace,
    verified_email_from_claims,
)
from dna.tenancy.ownership import (
    OWNER_ROLE,
    REVOKE_ROLES,
    RevokeDecision,
    active_owners,
    can_revoke_role,
    has_active_owner,
    is_last_active_owner,
    plan_revoke,
)
from dna.tenancy.resolution import (
    CrossWorkspaceError,
    Identity,
    Membership,
    active_workspaces_for,
    identity_from_token,
    membership_matches_identity,
    normalize_email,
    resolve_workspace,
    workspace_for_identity,
)


def workspace_membership_name(workspace_id: str, email: str) -> str:
    """Stable composite doc name for a (workspace, identity) grant.

    Format ``{workspace_id}--{email-slugified}`` — the SAME key the F1 seed
    (``scripts/seed_workspace_one.py``) uses, so an invite of an already-seeded
    identity, a re-invite, and the accept-bind all converge on the ONE doc
    (idempotent upsert, never a duplicate)."""
    email_part = email.strip().lower().replace("@", "-at-").replace(".", "-")
    email_part = re.sub(r"[^a-z0-9-]", "-", email_part).strip("-")
    return f"{workspace_id}--{email_part}"


__all__ = [
    "CrossWorkspaceError",
    "Identity",
    "Membership",
    "active_workspaces_for",
    "identity_from_token",
    "membership_matches_identity",
    "normalize_email",
    "resolve_workspace",
    "workspace_for_identity",
    # invites (F3)
    "AcceptResult",
    "INVITE_ROLES",
    "bindable_invites_for",
    "can_invite",
    "plan_accept",
    "role_in_workspace",
    "verified_email_from_claims",
    "workspace_membership_name",
    # ownership (F-ws-owner-provision) — first-owner probe + revoke/last-owner
    "OWNER_ROLE",
    "REVOKE_ROLES",
    "RevokeDecision",
    "active_owners",
    "can_revoke_role",
    "has_active_owner",
    "is_last_active_owner",
    "plan_revoke",
]
