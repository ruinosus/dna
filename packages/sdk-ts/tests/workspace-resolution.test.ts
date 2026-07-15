/**
 * s-ws-res-lookup / s-ws-res-parity — the pure Model B workspace resolver
 * (`src/tenancy/resolution.ts`), TS twin of `dna/tenancy/resolution.py`.
 *
 * Two layers:
 * 1. The SHARED parity fixtures at
 *    `tests/parity-fixtures/workspace-resolution/cases.json` (repo root) — the
 *    SAME cases the Python suite runs. Identical cases → identical outcomes gate
 *    Py↔TS behavioral parity: a divergence here fails this suite.
 * 2. TS-side unit coverage of the matching helpers + fail-closed edges.
 *
 * The resolver is the crown-jewel authorization decision (a bug = cross-workspace
 * leak) so deny paths are asserted as hard as the golden.
 */
import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import {
  CrossWorkspaceError,
  activeWorkspacesFor,
  identityFromToken,
  membershipFromSpec,
  membershipMatchesIdentity,
  normalizeEmail,
  resolveWorkspace,
  workspaceForIdentity,
  type Identity,
  type Membership,
} from "../src/tenancy/resolution.js";

const FIXTURES = join(
  import.meta.dir, "..", "..", "..",
  "tests", "parity-fixtures", "workspace-resolution", "cases.json",
);

interface Case {
  id: string;
  token_present: boolean;
  identity: { oid: string | null; email: string | null; tid: string | null } | null;
  requested: string | null;
  memberships: Record<string, unknown>[];
  expect: { workspace?: string | null; deny?: string };
}

function loadCases(): Case[] {
  return JSON.parse(readFileSync(FIXTURES, "utf-8")).cases as Case[];
}

// ── the shared parity fixtures (the Py↔TS guard) ───────────────────────────

describe("workspace-resolution parity fixtures", () => {
  const cases = loadCases();

  test("fixture file is non-empty (guard the guard)", () => {
    expect(cases.length).toBeGreaterThanOrEqual(10);
  });

  for (const c of cases) {
    test(c.id, () => {
      const identity: Identity | null = c.identity
        ? { oid: c.identity.oid, email: c.identity.email, tid: c.identity.tid }
        : null;
      const memberships: Membership[] = c.memberships.map(membershipFromSpec);
      const run = () =>
        resolveWorkspace({
          tokenPresent: c.token_present,
          identity,
          requested: c.requested,
          memberships,
        });

      if (c.expect.deny !== undefined) {
        expect(run).toThrow(CrossWorkspaceError);
        try {
          run();
        } catch (e) {
          expect((e as Error).message).toContain(c.expect.deny);
        }
      } else {
        expect(run()).toBe(c.expect.workspace ?? null);
      }
    });
  }
});

// ── identity_from_token: verified claims only ──────────────────────────────

describe("identityFromToken", () => {
  test("reads Entra claims (oid/email/tid), ignores others", () => {
    const id = identityFromToken({ oid: "abc", email: "A@B.com", tid: "org-1", sub: "x" });
    expect(id.oid).toBe("abc");
    expect(id.email).toBe("A@B.com"); // preserved; matching case-folds.
    expect(id.tid).toBe("org-1");
  });

  test("email fallback order: email > preferred_username > upn", () => {
    expect(identityFromToken({ preferred_username: "p@x.com" }).email).toBe("p@x.com");
    expect(identityFromToken({ upn: "u@x.com" }).email).toBe("u@x.com");
    expect(identityFromToken({ email: "e@x.com", upn: "u@x.com" }).email).toBe("e@x.com");
  });

  test("missing claims are null", () => {
    const id = identityFromToken({});
    expect(id.oid).toBeNull();
    expect(id.email).toBeNull();
    expect(identityFromToken(null).oid).toBeNull();
  });
});

test("normalizeEmail folds case + trims", () => {
  expect(normalizeEmail("  Foo@Bar.COM ")).toBe("foo@bar.com");
  expect(normalizeEmail(null)).toBe("");
  expect(normalizeEmail("")).toBe("");
});

// ── membershipMatchesIdentity: oid-durable, email-handle ───────────────────

function m(over: Partial<Membership> = {}): Membership {
  return {
    workspace_id: "ws",
    identity_email: null,
    identity_oid: null,
    role: "member",
    status: "active",
    ...over,
  };
}

describe("membershipMatchesIdentity", () => {
  test("bound grant matches on oid only (no email hijack)", () => {
    const grant = m({ identity_oid: "oid-1", identity_email: "a@x.com" });
    expect(membershipMatchesIdentity(grant, { oid: "oid-1", email: "a@x.com", tid: null })).toBe(true);
    expect(membershipMatchesIdentity(grant, { oid: "oid-2", email: "a@x.com", tid: null })).toBe(false);
  });

  test("unbound active grant matches verified email (case-insensitive)", () => {
    const grant = m({ identity_oid: null, identity_email: "Founder@X.com" });
    expect(membershipMatchesIdentity(grant, { oid: "oid-new", email: "founder@x.com", tid: null })).toBe(true);
    expect(membershipMatchesIdentity(grant, { oid: "oid-new", email: "other@x.com", tid: null })).toBe(false);
  });

  test("pending never matches", () => {
    const grant = m({ identity_oid: "oid-1", identity_email: "a@x.com", status: "pending" });
    expect(membershipMatchesIdentity(grant, { oid: "oid-1", email: "a@x.com", tid: null })).toBe(false);
  });
});

test("activeWorkspacesFor dedups + preserves order", () => {
  const identity: Identity = { oid: "oid-1", email: "a@x.com", tid: null };
  const ms = [
    m({ workspace_id: "ws-a", identity_oid: "oid-1" }),
    m({ workspace_id: "ws-b", identity_oid: "oid-1" }),
    m({ workspace_id: "ws-a", identity_oid: "oid-1" }),
    m({ workspace_id: "ws-c", identity_oid: "oid-OTHER" }),
  ];
  expect(activeWorkspacesFor(identity, ms)).toEqual(["ws-a", "ws-b"]);
});

// ── workspaceForIdentity + resolveWorkspace edges ──────────────────────────

describe("workspaceForIdentity fail-closed", () => {
  test("deny when no membership", () => {
    expect(() =>
      workspaceForIdentity({ identity: { oid: "x", email: null, tid: null }, requestedWorkspace: null, memberships: [] }),
    ).toThrow(/no active workspace membership/);
  });

  test("deny cross-workspace requested", () => {
    const ms = [m({ workspace_id: "ws-a", identity_oid: "oid-1" })];
    expect(() =>
      workspaceForIdentity({
        identity: { oid: "oid-1", email: "a@x.com", tid: null },
        requestedWorkspace: "ws-b",
        memberships: ms,
      }),
    ).toThrow(/not an active member/);
  });

  test("stdio passthrough ignores memberships", () => {
    expect(
      resolveWorkspace({ tokenPresent: false, identity: null, requested: "whatever", memberships: [] }),
    ).toBe("whatever");
  });
});
