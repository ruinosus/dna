/**
 * `dna.tenancy.resolution` — the pure workspace-resolution policy (Model B).
 *
 * 1:1 behavioral parity with python `dna/tenancy/resolution.py`. The heart of
 * ADR "Model B" (feature `f-ws-resolution`, F2): resolve the DNA tenancy
 * dimension (a `workspace_id`) from the caller's VERIFIED identity +
 * WorkspaceMembership, NOT from the Azure `tid`.
 *
 *   > INVARIANT. Every read/write executes against exactly one workspace id, and
 *   > is served ONLY if the request's verified identity holds an `active`
 *   > WorkspaceMembership in that workspace; otherwise it is denied
 *   > (fail-closed). The workspace is resolved from the verified identity +
 *   > membership BEFORE the source is touched — never from an unverified caller
 *   > argument (an explicit `requested` workspace is only ever a *selector among
 *   > the identity's own memberships*, re-verified against membership).
 *
 * This module is CORE (no transport / kernel import) — only the decision. Guard:
 * the shared parity fixtures at `tests/parity-fixtures/workspace-resolution/`
 * drive both this and the Python twin, so a divergence fails a suite.
 *
 * Security: `identityFromToken` reads ONLY verified Entra claims; the email is
 * IdP-vouched (impersonation-proof). `oid` is the durable key — a bound grant
 * matches only on `oid` (no email-hijack); an active-but-unbound grant (the F1
 * founder seed) matches on the verified email until its oid is captured. Only
 * `active` grants authorize; `tid` is provenance only, never the tenant.
 */

/** The Entra claims an identity is read from (mirror the Python defaults). */
export const DEFAULT_OID_CLAIM = "oid";
export const DEFAULT_EMAIL_CLAIMS = ["email", "preferred_username", "upn"] as const;
export const DEFAULT_TID_CLAIM = "tid";

/**
 * A verified identity tried to reach a workspace it holds no active membership
 * in (or holds none). The fail-closed half of the Model B tenancy contract.
 */
export class CrossWorkspaceError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CrossWorkspaceError";
  }
}

/** Case-fold + trim an email into its canonical comparison form (`""` for nullish). */
export function normalizeEmail(email: string | null | undefined): string {
  if (!email) return "";
  return String(email).trim().toLowerCase();
}

/** A VERIFIED caller identity distilled from an IdP token. `tid` = provenance only. */
export interface Identity {
  oid: string | null;
  email: string | null;
  tid: string | null;
}

/** One identity→workspace grant — the pure-policy view of a WorkspaceMembership. */
export interface Membership {
  workspace_id: string;
  identity_email: string | null;
  identity_oid: string | null;
  role: string;
  status: string;
}

/** Build a Membership from a WorkspaceMembership doc `spec` (the kernel row). */
export function membershipFromSpec(spec: Record<string, unknown>): Membership {
  return {
    workspace_id: String((spec.workspace_id as string) ?? ""),
    identity_email: (spec.identity_email as string | null) ?? null,
    identity_oid: (spec.identity_oid as string | null) ?? null,
    role: String((spec.role as string) ?? "member"),
    status: String((spec.status as string) ?? "pending"),
  };
}

function cleanStr(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  const s = String(v).trim();
  return s || null;
}

/**
 * Distill a verified token's `claims` into an Identity. Reads ONLY verified
 * claims: the durable `oid`, the email from the first present of `emailClaims`,
 * and the `tid` (provenance). Missing claims become `null`.
 */
export function identityFromToken(
  claims: Record<string, unknown> | null | undefined,
  opts: {
    oidClaim?: string;
    emailClaims?: readonly string[];
    tidClaim?: string;
  } = {},
): Identity {
  const c = claims ?? {};
  const oidKey = opts.oidClaim ?? DEFAULT_OID_CLAIM;
  const tidKey = opts.tidClaim ?? DEFAULT_TID_CLAIM;
  const emailKeys = opts.emailClaims ?? DEFAULT_EMAIL_CLAIMS;

  const oid = cleanStr(c[oidKey]);
  const tid = cleanStr(c[tidKey]);
  let email: string | null = null;
  for (const key of emailKeys) {
    const candidate = cleanStr(c[key]);
    if (candidate) {
      email = candidate;
      break;
    }
  }
  return { oid, email, tid };
}

/**
 * True when `m` is an ACTIVE grant that belongs to `identity`:
 * - a non-`active` grant never matches (pending invites authorize nothing);
 * - a bound grant (`identity_oid` set) matches ONLY the same verified `oid`
 *   (no email-hijack of a bound membership);
 * - an active-but-UNBOUND grant matches on the VERIFIED email (the handle)
 *   until its oid is captured (the F1 founder seed contract).
 */
export function membershipMatchesIdentity(m: Membership, identity: Identity): boolean {
  if (m.status !== "active") return false;
  if (m.identity_oid) {
    return !!identity.oid && m.identity_oid === identity.oid;
  }
  if (!identity.email || !m.identity_email) return false;
  return normalizeEmail(m.identity_email) === normalizeEmail(identity.email);
}

/**
 * The workspace ids `identity` holds an active membership in — ordered,
 * de-duplicated (first-seen order preserved for a deterministic sole/default).
 */
export function activeWorkspacesFor(
  identity: Identity,
  memberships: Iterable<Membership>,
): string[] {
  const seen: string[] = [];
  const set = new Set<string>();
  for (const m of memberships) {
    if (m.workspace_id && membershipMatchesIdentity(m, identity) && !set.has(m.workspace_id)) {
      set.add(m.workspace_id);
      seen.push(m.workspace_id);
    }
  }
  return seen;
}

/**
 * Resolve the single workspace this request runs against — fail-closed. See the
 * Python twin's `workspace_for_identity` for the full rule ladder.
 */
export function workspaceForIdentity(args: {
  identity: Identity;
  requestedWorkspace: string | null;
  memberships: Iterable<Membership>;
}): string {
  const active = activeWorkspacesFor(args.identity, args.memberships);
  if (active.length === 0) {
    throw new CrossWorkspaceError(
      "identity holds no active workspace membership — access denied",
    );
  }
  if (args.requestedWorkspace !== null && args.requestedWorkspace !== undefined) {
    if (!active.includes(args.requestedWorkspace)) {
      throw new CrossWorkspaceError(
        `identity is not an active member of workspace '${args.requestedWorkspace}' — access denied`,
      );
    }
    return args.requestedWorkspace;
  }
  if (active.length === 1) return active[0]!;
  throw new CrossWorkspaceError(
    "identity belongs to multiple workspaces and named none — select one " +
      "(e.g. the per-workspace .../w/<workspace-id>/mcp URL); access denied",
  );
}

/**
 * Reconcile the effective workspace for a request — the policy front door.
 * `tokenPresent=false` (stdio/OSS) → `requested` passes through unchanged.
 */
export function resolveWorkspace(args: {
  tokenPresent: boolean;
  identity: Identity | null;
  requested: string | null;
  memberships: Iterable<Membership>;
}): string | null {
  if (!args.tokenPresent) return args.requested;
  return workspaceForIdentity({
    identity: args.identity ?? { oid: null, email: null, tid: null },
    requestedWorkspace: args.requested,
    memberships: args.memberships,
  });
}
