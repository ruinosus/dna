/**
 * s-ws-invite-create / s-ws-invite-accept — the pure Model B invite/accept policy
 * (`src/tenancy/invites.ts`), TS twin of `dna/tenancy/invites.py`.
 *
 * Layer 1: the SHARED parity fixtures at
 * `tests/parity-fixtures/workspace-invite/cases.json` (repo root) — the SAME cases
 * the Python suite runs. Identical cases → identical outcomes gate Py↔TS parity.
 * Layer 2: TS-side security edges (anti-impersonation) asserted as hard as golden.
 */
import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import {
  bindableInvitesFor,
  canInvite,
  planAccept,
  roleInWorkspace,
  verifiedEmailFromClaims,
} from "../src/tenancy/invites.js";
import { membershipFromSpec, type Identity, type Membership } from "../src/tenancy/resolution.js";

const FIXTURES = join(
  import.meta.dir, "..", "..", "..",
  "tests", "parity-fixtures", "workspace-invite", "cases.json",
);

interface AuthCase {
  id: string;
  identity: { oid: string | null; email: string | null; tid: string | null } | null;
  workspace_id: string;
  memberships: Record<string, unknown>[];
  expect: { role: string | null; can_invite: boolean };
}
interface AcceptCase {
  id: string;
  claims: Record<string, unknown>;
  memberships: Record<string, unknown>[];
  expect: { bound: { workspace_id: string; activated: boolean }[] };
}

function load(): { authorize: AuthCase[]; accept: AcceptCase[] } {
  return JSON.parse(readFileSync(FIXTURES, "utf-8"));
}

function toIdentity(raw: AuthCase["identity"]): Identity | null {
  return raw ? { oid: raw.oid, email: raw.email, tid: raw.tid } : null;
}

// ── the shared parity fixtures (the Py↔TS guard) ───────────────────────────

describe("workspace-invite parity fixtures", () => {
  const data = load();

  test("fixture families are non-empty (guard the guard)", () => {
    expect(data.authorize.length).toBeGreaterThanOrEqual(5);
    expect(data.accept.length).toBeGreaterThanOrEqual(8);
  });

  for (const c of data.authorize) {
    test(`authorize: ${c.id}`, () => {
      const memberships: Membership[] = c.memberships.map(membershipFromSpec);
      const role = roleInWorkspace(toIdentity(c.identity), c.workspace_id, memberships);
      expect(role).toBe(c.expect.role);
      expect(canInvite(role)).toBe(c.expect.can_invite);
    });
  }

  for (const c of data.accept) {
    test(`accept: ${c.id}`, () => {
      const memberships: Membership[] = c.memberships.map(membershipFromSpec);
      const results = planAccept(c.claims, memberships);
      const got = results.map((r) => ({ workspace_id: r.workspace_id, activated: r.activated }));
      expect(got).toEqual(c.expect.bound);
    });
  }
});

// ── verified_email_from_claims: the accept security gate ───────────────────

describe("verifiedEmailFromClaims", () => {
  test("bare email requires email_verified truthy", () => {
    expect(verifiedEmailFromClaims({ email: "a@x.com" })).toBeNull();
    expect(verifiedEmailFromClaims({ email: "a@x.com", email_verified: false })).toBeNull();
    expect(verifiedEmailFromClaims({ email: "A@X.com", email_verified: true })).toBe("a@x.com");
    expect(verifiedEmailFromClaims({ email: "a@x.com", email_verified: "true" })).toBe("a@x.com");
  });
  test("Entra UPN claims are trusted without a flag", () => {
    expect(verifiedEmailFromClaims({ preferred_username: "P@X.com" })).toBe("p@x.com");
    expect(verifiedEmailFromClaims({ upn: "U@X.com" })).toBe("u@x.com");
  });
  test("no usable claim → null", () => {
    expect(verifiedEmailFromClaims({})).toBeNull();
    expect(verifiedEmailFromClaims(null)).toBeNull();
  });
});

// ── bindable: the anti-impersonation core ──────────────────────────────────

const m = (o: Partial<Membership>): Membership =>
  membershipFromSpec({
    workspace_id: "ws", identity_email: null, identity_oid: null,
    role: "member", status: "active", ...o,
  } as Record<string, unknown>);

describe("bindableInvitesFor security", () => {
  test("a bound grant is not hijackable by a different oid", () => {
    const ms = [m({ workspace_id: "ws-a", identity_email: "partner@p.com", identity_oid: "oid-partner", status: "active" })];
    const attacker: Identity = { oid: "oid-attacker", email: "partner@p.com", tid: "org-evil" };
    expect(bindableInvitesFor(attacker, "partner@p.com", ms)).toEqual([]);
  });
  test("no verified email → nothing bound", () => {
    const ms = [m({ workspace_id: "ws-a", identity_email: "partner@p.com", identity_oid: null, status: "pending" })];
    const partner: Identity = { oid: "oid-partner", email: "partner@p.com", tid: null };
    expect(bindableInvitesFor(partner, null, ms)).toEqual([]);
  });
  test("no oid → nothing bound", () => {
    const ms = [m({ workspace_id: "ws-a", identity_email: "partner@p.com", identity_oid: null, status: "pending" })];
    const noOid: Identity = { oid: null, email: "partner@p.com", tid: null };
    expect(bindableInvitesFor(noOid, "partner@p.com", ms)).toEqual([]);
  });
});
