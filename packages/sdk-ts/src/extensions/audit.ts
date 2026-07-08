/**
 * AuditExtension — RBAC audit-trail Kinds.
 *
 * 1:1 parity with Python dna.extensions.audit
 * (s-port-missing-ts-extensions). Registers:
 *   - AuditLog (audit-auditlog) — immutable record of a role-gated endpoint
 *     call. MIGRATED to a descriptor in expr batch A (plan
 *     2026-06-11-descriptor-expressiveness): the twin AuditLogKind classes
 *     (Py+TS) were DELETED — kinds/audit-log.kind.yaml is the single source,
 *     registered via the loadDescriptors loop in register(). The descriptor
 *     carries the D2 `ui:` block (now expressible Py↔TS), which the old TS
 *     class intentionally omitted — so the TS runtime now exposes the same
 *     Studio sidebar metadata the Python side always had.
 *   - UserRoleAssignment (audit-userroleassignment) — user→roles within a
 *     tenant (still a class).
 *
 * UserRoleAssignment is TENANTED (the KindBase default) with no reader/writer
 * (plain YAML).
 */
import type { ExtensionHost, Extension } from "../kernel/protocols.js";
import { KindBase } from "../kernel/kind_base.js";
import { SD } from "../kernel/protocols.js";
import { loadDescriptors } from "../kernel/descriptor-loader.js";

const API_VERSION = "github.com/ruinosus/dna/audit/v1";
const ORIGIN = "github.com/ruinosus/dna/audit";

// ---------------------------------------------------------------------------
// UserRoleAssignmentKind
// ---------------------------------------------------------------------------

class UserRoleAssignmentKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly kind = "UserRoleAssignment";
  readonly alias = "audit-userroleassignment";
  readonly origin = ORIGIN;
  readonly isPromptTarget = false;
  readonly isRuntimeArtifact = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly storage = SD.yaml("user-roles");
  readonly graphStyle = { fill: "#6366f1", stroke: "#4f46e5", textColor: "#fff" };
  readonly asciiIcon = "👥";
  readonly displayLabel = "User Role";
  readonly docs =
    "Persistent role assignment for a user inside a tenant. The doc name IS the " +
    "user_id. Roles list is the source of truth for require_role decorators when " +
    "Clerk webhook sync is enabled.";

  dependencies() { return null; }
  summary() { return null; }

  schema() {
    return {
      type: "object",
      required: ["user_id", "roles", "updated_at"],
      additionalProperties: true,
      properties: {
        user_id: { type: "string", description: "Identity claim (sub or email)." },
        email: { type: "string" },
        roles: {
          type: "array",
          items: { type: "string" },
          description:
            "Authoritative role list. Backend require_role reads claims.roles " +
            "which is set by Clerk via JWT — this Kind is the admin-managed " +
            "mirror for Clerk's org membership.",
        },
        note: { type: "string", description: "Free-form admin note (hire date, etc)." },
        updated_at: { type: "string", format: "date-time" },
      },
    };
  }
}

// ---------------------------------------------------------------------------
// Extension
// ---------------------------------------------------------------------------

export class AuditExtension implements Extension {
  readonly name = "audit";
  readonly version = "1.0.0";

  register(kernel: ExtensionHost): void {
    kernel.kind(new UserRoleAssignmentKind());
    // expr batch A: AuditLog as a descriptor — kinds/*.kind.yaml package data
    // registered through the SAME funnel as per-scope KindDefinitions.
    for (const raw of loadDescriptors(import.meta.url, "audit/kinds")) {
      kernel.kindFromDescriptor(raw);
    }
  }
}
