/**
 * `dna.tenancy.invites` — the pure invite/accept policy (Model B, F3).
 *
 * 1:1 behavioral parity with Python `dna/tenancy/invites.py`. The cross-org JOIN
 * half of ADR "Model B" (feature `f-ws-invites`): a workspace Owner/Admin invites
 * a collaborator from ANY Azure org BY EMAIL; the invitee's first VERIFIED sign-in
 * binds their durable `oid` to the pending grant and flips it `active`.
 *
 * CORE (no transport / kernel import) — only the decision. Guard: the shared
 * parity fixtures at `tests/parity-fixtures/workspace-invite/` drive both this and
 * the Python twin, so a divergence fails a suite.
 *
 * Security model (impersonation-proof):
 * - Authorization to invite is a role check on an ACTIVE grant the actor holds in
 *   THAT workspace (Owner/Admin only); a pending grant / a role in another
 *   workspace confers nothing.
 * - Accepting matches ONLY on a verified email claim: `verifiedEmailFromClaims`
 *   trusts Entra's verified UPN (`preferred_username`/`upn`) always, and a bare
 *   `email` claim ONLY with a truthy `email_verified`. Unverified → no match.
 * - The bind key is the durable `oid`: `bindableInvitesFor` returns only UNBOUND
 *   grants, so a grant already bound to an `oid` can NEVER be hijacked by a
 *   different `oid` sharing the invited email; a token with no `oid` binds nothing.
 */
import {
  identityFromToken,
  membershipMatchesIdentity,
  normalizeEmail,
  type Identity,
  type Membership,
} from "./resolution.js";

/** Workspace roles that may invite / list members (the RBAC gate). */
export const INVITE_ROLES = ["owner", "admin"] as const;

/** Role ranks — highest-role-wins across multiple active grants in one workspace. */
const ROLE_RANKS: Record<string, number> = { owner: 40, admin: 30, member: 20, guest: 10 };

/** Entra verified-UPN claims (trusted as-is, no flag required). */
const VERIFIED_UPN_CLAIMS = ["preferred_username", "upn"] as const;
export const DEFAULT_EMAIL_CLAIM = "email";
export const DEFAULT_EMAIL_VERIFIED_CLAIM = "email_verified";

function cleanStr(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  const s = String(v).trim();
  return s || null;
}

/** Loose truthiness for an `email_verified` claim (bool, or JWT strings). */
function isTruthy(v: unknown): boolean {
  if (typeof v === "boolean") return v;
  if (typeof v === "string") return ["true", "1", "yes"].includes(v.trim().toLowerCase());
  if (typeof v === "number") return v === 1;
  return false;
}

/**
 * The IdP-VERIFIED email a token asserts, normalized — or `null`. The single
 * security gate for accepting an invite: a bare `email` claim wins with a truthy
 * `email_verified`; else the verified UPN (`preferred_username`/`upn`); else
 * `null` (unverified email cannot claim an invite — fail-closed).
 */
export function verifiedEmailFromClaims(
  claims: Record<string, unknown> | null | undefined,
  opts: { emailClaim?: string; emailVerifiedClaim?: string } = {},
): string | null {
  const c = claims ?? {};
  const emailKey = opts.emailClaim ?? DEFAULT_EMAIL_CLAIM;
  const verifiedKey = opts.emailVerifiedClaim ?? DEFAULT_EMAIL_VERIFIED_CLAIM;

  const email = cleanStr(c[emailKey]);
  if (email && isTruthy(c[verifiedKey])) return normalizeEmail(email);
  for (const key of VERIFIED_UPN_CLAIMS) {
    const upn = cleanStr(c[key]);
    if (upn) return normalizeEmail(upn);
  }
  return null;
}

/**
 * The role `identity` holds via an ACTIVE grant in `workspaceId` —
 * highest-role-wins, `null` when it holds none. Uses the resolver's
 * oid-durable/verified-email matching (a pending grant never matches).
 */
export function roleInWorkspace(
  identity: Identity | null,
  workspaceId: string,
  memberships: Iterable<Membership>,
): string | null {
  if (identity === null) return null;
  let best: string | null = null;
  let bestRank = -1;
  for (const m of memberships) {
    if (m.workspace_id !== workspaceId) continue;
    if (!membershipMatchesIdentity(m, identity)) continue;
    const rank = ROLE_RANKS[m.role] ?? 0;
    if (rank > bestRank) {
      bestRank = rank;
      best = m.role;
    }
  }
  return best;
}

/** True when `role` may invite / list members (Owner or Admin). */
export function canInvite(role: string | null): boolean {
  return role !== null && (INVITE_ROLES as readonly string[]).includes(role);
}

/**
 * Every UNBOUND grant a verified sign-in may bind — the accept candidates, in
 * first-seen order. Fail-closed to `[]` when: the identity has no durable `oid`;
 * there is no `verifiedEmail`; or a grant is already bound (skipped, so a
 * different `oid` can never rebind/hijack it).
 */
export function bindableInvitesFor(
  identity: Identity | null,
  verifiedEmail: string | null,
  memberships: Iterable<Membership>,
): Membership[] {
  if (identity === null || !identity.oid) return [];
  if (!verifiedEmail) return [];
  const target = normalizeEmail(verifiedEmail);
  const out: Membership[] = [];
  for (const m of memberships) {
    if (m.identity_oid) continue; // already bound → not claimable via email.
    if (m.identity_email && normalizeEmail(m.identity_email) === target) out.push(m);
  }
  return out;
}

/** One bound grant's decision (mirror of Python `AcceptResult`). */
export interface AcceptResult {
  workspace_id: string;
  role: string;
  activated: boolean;
}

/**
 * Pure accept plan for a verified token's `claims` — the grants a sign-in binds
 * and whether each is newly activated (`pending`→`active`; an already-active
 * unbound seed just captures the oid, `activated=false`). Empty when nothing is
 * claimable.
 */
export function planAccept(
  claims: Record<string, unknown> | null | undefined,
  memberships: Iterable<Membership>,
): AcceptResult[] {
  const identity = identityFromToken(claims);
  const verifiedEmail = verifiedEmailFromClaims(claims);
  return bindableInvitesFor(identity, verifiedEmail, memberships).map((m) => ({
    workspace_id: m.workspace_id,
    role: m.role,
    activated: m.status === "pending",
  }));
}
