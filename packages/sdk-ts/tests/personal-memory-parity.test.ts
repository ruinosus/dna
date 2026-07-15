/**
 * Personal / private per-user memory — TypeScript parity (s-personal-memory-ts-parity).
 *
 * 1:1 twin of the Python suites `test_personal_memory.py` +
 * `test_personal_memory_privacy.py`: the pure resolver
 * (`resolveMemoryTenant`), the reserved-scheme helpers, the
 * `validateTenantSlug` namespace reservation (INV-PERSONAL layer 3) + the
 * `allowPersonal` write bypass, the raw-override rejection (layer 4), and the
 * FS-segment encoding parity. Keeps Py↔TS behavioral parity per CLAUDE.md.
 */
import { describe, expect, test } from "bun:test";
import { Kernel } from "../src/kernel/index.js";
import {
  InvalidTenantSlug,
  validateTenantSlug,
  RESERVED_TENANT_SCHEMES,
} from "../src/kernel/protocols.js";
import {
  PERSONAL_TENANT_PREFIX,
  PERSONAL_TENANT_SCHEME,
  PersonalIdentityRequired,
  PersonalOverrideRejected,
  assertNoPersonalOverride,
  isPersonalTenant,
  personalTenant,
  resolveMemoryTenant,
  tenantScheme,
} from "../src/memory/personal.js";
import { fsTenantSegment } from "../src/adapters/filesystem/source.js";

const OID_A = "11111111-1111-1111-1111-aaaaaaaaaaaa";
const OID_B = "22222222-2222-2222-2222-bbbbbbbbbbbb";
const WORKSPACE = "99999999-9999-9999-9999-cccccccccccc";

describe("personal partition helpers", () => {
  test("personalTenant builds the reserved value", () => {
    expect(personalTenant(OID_A)).toBe(`${PERSONAL_TENANT_PREFIX}${OID_A}`);
    expect(personalTenant(OID_A)).toBe(`personal:${OID_A}`);
  });

  test("personalTenant rejects a blank identity", () => {
    for (const blank of ["", "   "]) {
      expect(() => personalTenant(blank)).toThrow(PersonalIdentityRequired);
    }
  });

  test("isPersonalTenant + tenantScheme", () => {
    expect(isPersonalTenant(personalTenant(OID_A))).toBe(true);
    expect(isPersonalTenant(WORKSPACE)).toBe(false);
    expect(isPersonalTenant("")).toBe(false);
    expect(isPersonalTenant(null)).toBe(false);
    expect(tenantScheme(personalTenant(OID_A))).toBe("personal");
    expect(tenantScheme(WORKSPACE)).toBeNull();
  });
});

describe("resolveMemoryTenant (ADR §5)", () => {
  test("workspace is identity over the workspace tenant", () => {
    expect(
      resolveMemoryTenant({ memoryScope: "workspace", oid: OID_A, workspaceTenant: WORKSPACE }),
    ).toBe(WORKSPACE);
    expect(
      resolveMemoryTenant({ memoryScope: "workspace", oid: null, workspaceTenant: null }),
    ).toBeNull();
  });

  test("personal maps to personal:<oid>, workspace-independent", () => {
    for (const ws of [null, WORKSPACE, "some-other-workspace"]) {
      expect(
        resolveMemoryTenant({ memoryScope: "personal", oid: OID_A, workspaceTenant: ws }),
      ).toBe(personalTenant(OID_A));
    }
  });

  test("personal fails closed without an identity", () => {
    for (const missing of [null, undefined, "", "   "]) {
      expect(() =>
        resolveMemoryTenant({ memoryScope: "personal", oid: missing, workspaceTenant: WORKSPACE }),
      ).toThrow(PersonalIdentityRequired);
    }
  });
});

describe("INV-PERSONAL layer 3 — namespace reservation", () => {
  test("scheme is reserved", () => {
    expect(RESERVED_TENANT_SCHEMES.has(PERSONAL_TENANT_SCHEME)).toBe(true);
  });

  test("validateTenantSlug rejects a personal: workspace name", () => {
    expect(() => validateTenantSlug("personal:whatever")).toThrow(InvalidTenantSlug);
    expect(() => validateTenantSlug(personalTenant(OID_A))).toThrow(InvalidTenantSlug);
  });

  test("validateTenantSlug allows personal for an authorized write", () => {
    expect(() => validateTenantSlug(personalTenant(OID_A), { allowPersonal: true })).not.toThrow();
  });

  test("ordinary tenants are unaffected", () => {
    expect(() => validateTenantSlug(WORKSPACE)).not.toThrow();
    expect(() => validateTenantSlug("acme")).not.toThrow();
    expect(() => validateTenantSlug(null)).not.toThrow();
  });

  test("withTenant rejects personal without authorization, allows with", () => {
    const k = new Kernel();
    expect(() => k.withTenant(personalTenant(OID_A))).toThrow(InvalidTenantSlug);
    const bound = k.withTenant(personalTenant(OID_A), { allowPersonal: true });
    expect(bound.tenant).toBe(personalTenant(OID_A));
    expect(bound._allowPersonal).toBe(true);
  });
});

describe("INV-PERSONAL layer 4 — raw override rejection", () => {
  test("assertNoPersonalOverride", () => {
    expect(() => assertNoPersonalOverride(null)).not.toThrow();
    expect(() => assertNoPersonalOverride(WORKSPACE)).not.toThrow();
    expect(() => assertNoPersonalOverride(personalTenant(OID_B))).toThrow(PersonalOverrideRejected);
  });
});

describe("FS segment encoding parity", () => {
  test("percent-encodes the ':' sigil, no-op for ordinary tenants", () => {
    expect(fsTenantSegment(personalTenant(OID_A))).toBe(`personal%3A${OID_A}`);
    expect(fsTenantSegment(WORKSPACE)).toBe(WORKSPACE);
    expect(fsTenantSegment("acme")).toBe("acme");
  });
});
