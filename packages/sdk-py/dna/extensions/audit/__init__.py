"""AuditExtension — RBAC audit trail Kind.

Registers 1 KindPort:
  - AuditLog (audit-auditlog) — immutable record of every role-gated
    HTTP endpoint invocation. Distinct from Evidence (github.com/ruinosus/dna/evidence),
    which captures content-level events (document writes, eval runs)
    via the EvidencePolicy → hook pipeline.

Why a separate Kind?
  - Different capture point: AuditLog fires at the auth boundary
    (require_role decorator success), Evidence fires at the storage
    boundary (post_save hooks).
  - Different querying: "who tried to write KindDefinition this week"
    is an AuditLog question; "what changed in the system" is an
    Evidence question.
  - Different retention: AuditLog is compliance-critical and forever-
    retained; Evidence is content-coupled.

Storage: YAML at ``.dna/<scope>/audit-log/<id>.yaml``. Path-only-
write semantics — once written, MUST NOT be modified or deleted by
non-admin roles. Enforced via LayerPolicy LOCKED on this Kind.

F1.2 of f-multi-role (2026-05-15).
"""
from __future__ import annotations

from typing import Any

from dna.kernel.descriptor_loader import load_descriptors
from dna.kernel.protocols import ExtensionHost, StorageDescriptor
from dna.kernel.kind_base import KindBase
from dna.kernel.protocols import TenantScope


_API_VERSION = "github.com/ruinosus/dna/audit/v1"
_ORIGIN = "github.com/ruinosus/dna/audit"

# AuditLog migrated to a descriptor in expr batch A (plan
# 2026-06-11-descriptor-expressiveness): the twin AuditLogKind classes (Py+TS)
# were DELETED — kinds/audit-log.kind.yaml is the single source, registered
# through the load_descriptors loop in register(). It was the first builtin
# Kind to carry the new D2 `ui:` descriptor field. This comment used to
# claim equivalence with the extinct class was frozen in
# tests/test_expr_batch_a_equivalence.py — that file has never existed in
# this repository's history. No equivalence golden guards AuditLog today;
# tests/test_audit_extension.py covers registration + round-trip.


class UserRoleAssignmentKind(KindBase):
    """Maps a user identity to a role list within a tenant.

    F1.6 of f-multi-role. Backs the Admin UI's /admin/users endpoint.
    Distinct from AuditLog (which records ops) — this stores the
    persistent role state.

    Today written manually by tenant-admin via PUT
    /admin/users/{user_id}/roles. Future: synced from Clerk org
    membership webhook (deferred — see s-admin-clerk-sync).
    """

    api_version = _API_VERSION
    kind = "UserRoleAssignment"
    alias = "audit-userroleassignment"
    model = dict
    origin = _ORIGIN
    storage = StorageDescriptor.yaml("user-roles")
    scope = TenantScope.TENANTED
    graph_style = {
        "fill": "#6366f1",
        "stroke": "#4f46e5",
        "text_color": "#fff",
    }
    ascii_icon = "\U0001f465"  # 👥
    display_label = "User Role"
    is_prompt_target = False
    is_runtime_artifact = False
    prompt_target_priority = 0
    flatten_in_context = False
    docs = (
        "Persistent role assignment for a user inside a tenant. "
        "The doc name IS the user_id. Roles list is the source of "
        "truth for require_role decorators when Clerk webhook sync "
        "is enabled."
    )

    def schema(self) -> dict[str, Any] | None:
        return {
            "type": "object",
            "required": ["user_id", "roles", "updated_at"],
            "additionalProperties": True,
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Identity claim (sub or email).",
                },
                "email": {"type": "string"},
                "roles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Authoritative role list. Backend require_role "
                        "reads claims.roles which is set by Clerk via "
                        "JWT — this Kind is the admin-managed mirror "
                        "for Clerk's org membership."
                    ),
                },
                "note": {
                    "type": "string",
                    "description": "Free-form admin note (hire date, etc).",
                },
                "updated_at": {
                    "type": "string",
                    "format": "date-time",
                },
            },
        }


class AuditExtension:
    """Registers the AuditLog + UserRoleAssignment Kinds."""

    name = "audit"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        kernel.kind(UserRoleAssignmentKind())
        # expr batch A: AuditLog as a descriptor — kinds/*.kind.yaml package
        # data registered through the SAME funnel as per-scope KindDefinitions
        # (plane lint + digest idempotency + builtin conflict marker).
        for raw in load_descriptors("dna.extensions.audit"):
            kernel.kind_from_descriptor(raw)
