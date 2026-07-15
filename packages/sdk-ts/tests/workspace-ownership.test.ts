/**
 * s-ws-provision-owner-endpoint / s-ws-revoke-endpoint — the pure Model B
 * workspace-ownership policy (`src/tenancy/ownership.ts`), TS twin of
 * `dna/tenancy/ownership.py`.
 *
 * Layer 1: the SHARED parity fixtures at
 * `tests/parity-fixtures/workspace-ownership/cases.json` (repo root) — the SAME
 * cases the Python suite runs. Identical cases → identical outcomes gate Py↔TS
 * parity. Layer 2: TS-side security edges (last-owner + RBAC) asserted as hard as
 * golden.
 */
import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import {
  activeOwners,
  canRevokeRole,
  hasActiveOwner,
  isLastActiveOwner,
  planRevoke,
} from "../src/tenancy/ownership.js";
import { membershipFromSpec, type Membership } from "../src/tenancy/resolution.js";

const FIXTURES = join(
  import.meta.dir, "..", "..", "..",
  "tests", "parity-fixtures", "workspace-ownership", "cases.json",
);

interface OwnersCase {
  id: string;
  workspace_id: string;
  memberships: Record<string, unknown>[];
  expect: { owners: string[]; has_active_owner: boolean };
}
interface RevokeCase {
  id: string;
  workspace_id: string;
  actor_role: string | null;
  target: Record<string, unknown> | null;
  memberships: Record<string, unknown>[];
  expect: { allowed: boolean; reason: string };
}

function load(): { owners: OwnersCase[]; revoke: RevokeCase[] } {
  return JSON.parse(readFileSync(FIXTURES, "utf-8"));
}

// ── the shared parity fixtures (the Py↔TS guard) ───────────────────────────

describe("workspace-ownership parity fixtures", () => {
  const data = load();

  test("fixture families are non-empty (guard the guard)", () => {
    expect(data.owners.length).toBeGreaterThanOrEqual(5);
    expect(data.revoke.length).toBeGreaterThanOrEqual(6);
  });

  for (const c of data.owners) {
    test(`owners: ${c.id}`, () => {
      const memberships: Membership[] = c.memberships.map(membershipFromSpec);
      const emails = activeOwners(c.workspace_id, memberships).map((m) => m.identity_email);
      expect(emails).toEqual(c.expect.owners);
      expect(hasActiveOwner(c.workspace_id, memberships)).toBe(c.expect.has_active_owner);
    });
  }

  for (const c of data.revoke) {
    test(`revoke: ${c.id}`, () => {
      const memberships: Membership[] = c.memberships.map(membershipFromSpec);
      const target = c.target ? membershipFromSpec(c.target) : null;
      const decision = planRevoke(c.actor_role, target, c.workspace_id, memberships);
      expect(decision.allowed).toBe(c.expect.allowed);
      expect(decision.reason).toBe(c.expect.reason);
    });
  }
});

// ── ownership + last-owner security edges ──────────────────────────────────

const m = (o: Partial<Membership>): Membership =>
  membershipFromSpec({
    workspace_id: "ws", identity_email: null, identity_oid: null,
    role: "member", status: "active", ...o,
  } as Record<string, unknown>);

describe("ownership security", () => {
  test("a pending owner is not an active owner", () => {
    const ms = [m({ workspace_id: "ws-a", identity_email: "o@a.com", role: "owner", status: "pending" })];
    expect(activeOwners("ws-a", ms)).toEqual([]);
    expect(hasActiveOwner("ws-a", ms)).toBe(false);
  });

  test("the last active owner cannot be revoked", () => {
    const owner = m({ workspace_id: "ws-a", identity_email: "o@a.com", identity_oid: "oid-o", role: "owner" });
    const ms = [owner, m({ workspace_id: "ws-a", identity_email: "x@a.com", identity_oid: "oid-x" })];
    expect(isLastActiveOwner("ws-a", owner, ms)).toBe(true);
    expect(planRevoke("owner", owner, "ws-a", ms).reason).toBe("last_owner");
  });

  test("one of two owners is revocable", () => {
    const a = m({ workspace_id: "ws-a", identity_email: "a@a.com", identity_oid: "oid-a", role: "owner" });
    const b = m({ workspace_id: "ws-a", identity_email: "b@a.com", identity_oid: "oid-b", role: "owner" });
    expect(isLastActiveOwner("ws-a", a, [a, b])).toBe(false);
    expect(planRevoke("owner", a, "ws-a", [a, b]).allowed).toBe(true);
  });

  test("last-owner match survives a target rebuilt from spec (subject identity, not object)", () => {
    const owner = m({ workspace_id: "ws-a", identity_email: "O@a.com", identity_oid: "oid-o", role: "owner" });
    const rebuilt = membershipFromSpec({
      workspace_id: "ws-a", identity_email: "o@a.com", identity_oid: "oid-o",
      role: "owner", status: "active",
    });
    expect(isLastActiveOwner("ws-a", rebuilt, [owner])).toBe(true);
  });

  test("RBAC: only owner/admin may revoke", () => {
    expect(canRevokeRole("member")).toBe(false);
    expect(canRevokeRole(null)).toBe(false);
    expect(canRevokeRole("owner")).toBe(true);
    expect(canRevokeRole("admin")).toBe(true);
  });

  test("RBAC deny precedes target existence (no oracle)", () => {
    expect(planRevoke("member", null, "ws-a", []).reason).toBe("not_authorized");
    expect(planRevoke("owner", null, "ws-a", []).reason).toBe("not_found");
  });
});
