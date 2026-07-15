"""``dna.tenancy`` — the DNA-native workspace tenancy layer (ADR "Model B").

The pure, transport-agnostic **workspace resolution** policy: a verified
identity (Entra ``oid`` + verified email + ``tid``-as-provenance) is mapped to a
``workspace_id`` via its active :class:`WorkspaceMembership` grants — never via
the Azure ``tid``. This is the crown-jewel authorization decision of Model B; it
lives in the CORE (no FastMCP / HTTP / kernel import) so it is fully
unit-testable and has a byte-behavioral TypeScript twin
(``packages/sdk-ts/src/tenancy/resolution.ts``), guarded by the shared parity
fixtures at ``tests/parity-fixtures/workspace-resolution/``.
"""
from __future__ import annotations

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
]
