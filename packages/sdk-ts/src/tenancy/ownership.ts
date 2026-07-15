/**
 * `dna.tenancy.ownership` — the pure workspace-OWNERSHIP policy (Model B).
 *
 * 1:1 behavioral parity with Python `dna/tenancy/ownership.py`. The decision
 * layer shared by the two owner-bootstrap endpoints (feature
 * `f-ws-owner-provision`):
 * - `POST /v1/workspaces/{id}/provision-owner` needs the first-owner probe
 *   (`hasActiveOwner`) so provisioning is a NO-OP once an owner exists (a later
 *   user never auto-escalates).
 * - `POST /v1/workspaces/{id}/members/revoke` needs the RBAC gate PLUS the
 *   crown-jewel invariant that the LAST active owner can never be revoked (a
 *   workspace must never be orphaned).
 *
 * CORE (no transport / kernel import) — only the decision. Guard: the shared
 * parity fixtures at `tests/parity-fixtures/workspace-ownership/` drive both this
 * and the Python twin, so a divergence fails a suite. Only `active` grants count
 * as an owner — a `pending` owner invite authorizes nothing (fail-closed).
 */
import { normalizeEmail, type Membership } from "./resolution.js";

/** The role that "owns" a workspace (top of the ladder). */
export const OWNER_ROLE = "owner";

/** Workspace roles that may revoke a member (mirror `INVITE_ROLES`). */
export const REVOKE_ROLES = ["owner", "admin"] as const;

/**
 * Every ACTIVE owner grant of `workspaceId`, in first-seen order. An owner is an
 * `active` grant whose `role` is `owner` (a pending owner invite does not count).
 */
export function activeOwners(
  workspaceId: string,
  memberships: Iterable<Membership>,
): Membership[] {
  const out: Membership[] = [];
  for (const m of memberships) {
    if (
      m.workspace_id === workspaceId &&
      m.status === "active" &&
      (m.role ?? "").toLowerCase() === OWNER_ROLE
    ) {
      out.push(m);
    }
  }
  return out;
}

/** True when `workspaceId` already has at least one active owner (the provision probe). */
export function hasActiveOwner(
  workspaceId: string,
  memberships: Iterable<Membership>,
): boolean {
  return activeOwners(workspaceId, memberships).length > 0;
}

/**
 * Identity of a grant for the last-owner count: same workspace AND same subject
 * (durable `oid` when both bound, else the normalized email) — so the count is
 * correct even when `target` was rebuilt from a spec rather than being the very
 * object in `memberships`.
 */
function sameGrant(a: Membership, b: Membership): boolean {
  if (a.workspace_id !== b.workspace_id) return false;
  if (a.identity_oid && b.identity_oid) return a.identity_oid === b.identity_oid;
  return (
    !!a.identity_email &&
    !!b.identity_email &&
    normalizeEmail(a.identity_email) === normalizeEmail(b.identity_email)
  );
}

/**
 * True when revoking `target` would remove the LAST active owner of
 * `workspaceId` — the fail-closed revoke guard. True iff `target` is itself an
 * active owner AND no OTHER active owner remains. A non-owner target is never the
 * last owner.
 */
export function isLastActiveOwner(
  workspaceId: string,
  target: Membership,
  memberships: Iterable<Membership>,
): boolean {
  const targetIsOwner =
    target.workspace_id === workspaceId &&
    target.status === "active" &&
    (target.role ?? "").toLowerCase() === OWNER_ROLE;
  if (!targetIsOwner) return false;
  for (const o of activeOwners(workspaceId, memberships)) {
    if (!sameGrant(o, target)) return false;
  }
  return true;
}

/**
 * The pure decision for a revoke request. `reason` is a stable machine code the
 * faces map to HTTP: `ok` (allowed), `not_authorized` (not Owner/Admin → 403),
 * `last_owner` (would orphan → 409), `not_found` (no grant here → 404 / no-op).
 */
export interface RevokeDecision {
  allowed: boolean;
  reason: "ok" | "not_authorized" | "last_owner" | "not_found";
}

/** True when `actorRole` may revoke a member (Owner or Admin). */
export function canRevokeRole(actorRole: string | null): boolean {
  return actorRole !== null && (REVOKE_ROLES as readonly string[]).includes(actorRole);
}

/**
 * Decide a revoke — the single policy front door both faces call. Order
 * (fail-closed, deny wins): RBAC (not Owner/Admin → `not_authorized`), target
 * present (`null` → `not_found`), last-owner (sole active owner → `last_owner`).
 * RBAC is checked first so an unauthorized caller learns nothing about the target
 * (no existence oracle).
 */
export function planRevoke(
  actorRole: string | null,
  target: Membership | null,
  workspaceId: string,
  memberships: Iterable<Membership>,
): RevokeDecision {
  if (!canRevokeRole(actorRole)) return { allowed: false, reason: "not_authorized" };
  if (target === null) return { allowed: false, reason: "not_found" };
  if (isLastActiveOwner(workspaceId, target, memberships)) {
    return { allowed: false, reason: "last_owner" };
  }
  return { allowed: true, reason: "ok" };
}
