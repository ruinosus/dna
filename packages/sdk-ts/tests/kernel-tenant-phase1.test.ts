/**
 * Phase 1 — Tenant first-class on Kernel (TypeScript parity).
 *
 * Mirrors python/tests/test_kernel_tenant_phase1.py to keep the SDKs in
 * sync per the cross-language parity rule in CLAUDE.md.
 */
import { describe, expect, test } from "bun:test";
import { Kernel } from "../src/kernel/index.js";
import {
  TenantScope,
  TenantRequired,
  TenantNotAllowed,
  InvalidTenantSlug,
  validateTenantSlug,
  RESERVED_TENANT_SLUGS,
} from "../src/kernel/protocols.js";

describe("Kernel(tenant) constructor binding", () => {
  test("binds tenant", async () => {
    const k = new Kernel({ tenant: "acme" });
    expect(k.tenant).toBe("acme");
  });

  test("default tenant is null", async () => {
    const k = new Kernel();
    expect(k.tenant).toBeNull();
  });

  test("rejects reserved slug", async () => {
    expect(() => new Kernel({ tenant: "_global" })).toThrow(InvalidTenantSlug);
  });
});

describe("Kernel.withTenant() per-call override", () => {
  test("returns copy, original unchanged", async () => {
    const k = new Kernel({ tenant: "acme" });
    const other = k.withTenant("globex");
    expect(k.tenant).toBe("acme");
    expect(other.tenant).toBe("globex");
    expect(other).not.toBe(k);
  });

  test("withTenant(null) unbinds", async () => {
    const k = new Kernel({ tenant: "acme" });
    const other = k.withTenant(null);
    expect(other.tenant).toBeNull();
  });

  test("rejects reserved slug", async () => {
    const k = new Kernel();
    expect(() => k.withTenant("_legacy")).toThrow(InvalidTenantSlug);
  });
});

describe("validateTenantSlug", () => {
  test("accepts uppercase (Phase 1 permissive)", async () => {
    expect(() => validateTenantSlug("Acme")).not.toThrow();
    expect(() => validateTenantSlug("T1")).not.toThrow();
  });

  test("rejects too long", async () => {
    expect(() => validateTenantSlug("a".repeat(254))).toThrow(InvalidTenantSlug);
  });

  test("accepts up to 253 chars", async () => {
    expect(() => validateTenantSlug("a".repeat(253))).not.toThrow();
  });

  test("null is OK", async () => {
    expect(() => validateTenantSlug(null)).not.toThrow();
    expect(() => validateTenantSlug(undefined)).not.toThrow();
  });

  test("reserved slugs rejected", async () => {
    for (const r of RESERVED_TENANT_SLUGS) {
      expect(() => validateTenantSlug(r)).toThrow(InvalidTenantSlug);
    }
  });
});

describe("TenantScope enum + exception types", () => {
  test("TenantScope values match Python", async () => {
    expect(TenantScope.TENANTED).toBe("tenanted");
    expect(TenantScope.GLOBAL).toBe("global");
  });

  test("TenantRequired is throwable Error", async () => {
    const err = new TenantRequired("test");
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe("TenantRequired");
  });

  test("TenantNotAllowed is throwable Error", async () => {
    const err = new TenantNotAllowed("test");
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe("TenantNotAllowed");
  });

  test("RESERVED_TENANT_SLUGS matches Python", async () => {
    const expected = new Set<string>(["_global", "_legacy", "_system", ""]);
    expect(RESERVED_TENANT_SLUGS).toEqual(expected);
  });
});
