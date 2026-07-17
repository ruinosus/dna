/**
 * P2 — family-namespaced personal partition key (dual-lane, back-compat).
 * 1:1 twin of `test_personal_dual_key.py`: Lane A (Entra) keeps bare
 * `personal:<oid>` (zero migration, D6); Lane B (Google) gets
 * `personal:google:<sub>`; both stay under the reserved `personal:` scheme.
 */
import { describe, expect, test } from "bun:test";
import {
  isPersonalTenant,
  PersonalIdentityRequired,
  personalTenant,
} from "../src/memory/personal.js";

describe("personalTenant — dual-lane family namespacing", () => {
  test("entra stays bare (back-compat)", () => {
    expect(personalTenant("oid123")).toBe("personal:oid123");
    expect(personalTenant("oid123", "entra")).toBe("personal:oid123");
  });

  test("google is family-namespaced", () => {
    expect(personalTenant("sub456", "google")).toBe("personal:google:sub456");
  });

  test("families never collide", () => {
    expect(personalTenant("X", "entra")).not.toBe(personalTenant("X", "google"));
  });

  test("google partition still recognized as personal", () => {
    expect(isPersonalTenant(personalTenant("sub456", "google"))).toBe(true);
  });

  test("blank identity fails closed for any family", () => {
    expect(() => personalTenant("", "google")).toThrow(PersonalIdentityRequired);
    expect(() => personalTenant("   ", "entra")).toThrow(PersonalIdentityRequired);
  });
});
