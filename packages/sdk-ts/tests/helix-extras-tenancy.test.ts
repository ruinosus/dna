/**
 * helix_extras tenancy parity (i-180). The TS Kinds had NO scope declaration
 * while the Py twin declared GLOBAL (Setting) and TENANTED
 * (UserProfile/Canvas) — a latent bug: undeclared = permissive, so TS would let
 * per-tenant data (UserProfile/Canvas) be written to the _lib base. This
 * locks the TS side to the Py-correct values.
 */
import { describe, expect, test } from "bun:test";
import { TenantScope } from "../src/kernel/protocols.js";
import {
  SettingKind, ThemeKind, UserProfileKind, CanvasKind,
} from "../src/extensions/helix_extras.js";

describe("helix_extras tenancy parity (i-180)", () => {
  test("Setting is GLOBAL (platform-uniform)", () => {
    expect(new SettingKind().scope).toBe(TenantScope.GLOBAL);
  });

  test("UserProfile/Canvas are TENANTED (per-tenant data, never base)", () => {
    expect(new UserProfileKind().scope).toBe(TenantScope.TENANTED);
    expect(new CanvasKind().scope).toBe(TenantScope.TENANTED);
  });

  test("Theme is permissive (inheritable _lib default, no scope decl)", () => {
    expect(new ThemeKind().scope).toBeUndefined();
  });
});
