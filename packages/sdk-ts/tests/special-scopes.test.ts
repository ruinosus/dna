// packages/sdk-ts/tests/special-scopes.test.ts
import { describe, expect, test } from "bun:test";
import {
  DEFAULT_BASE_SCOPE, SYSTEM_SCOPE,
  MODEL_REGISTRY_SCOPE, VOICE_POLICY_SCOPE, Kernel,
} from "../src/kernel/index.js";

describe("special scopes (i-112 ph1)", () => {
  test("DEFAULT_BASE_SCOPE is _lib", () => { expect(DEFAULT_BASE_SCOPE).toBe("_lib"); });
  test("SYSTEM_SCOPE is _lib", () => { expect(SYSTEM_SCOPE).toBe("_lib"); });
  test("existing scope constants derive from the single source", () => {
    expect(MODEL_REGISTRY_SCOPE).toBe(SYSTEM_SCOPE);
    expect(VOICE_POLICY_SCOPE).toBe(SYSTEM_SCOPE);
    expect(Kernel.INHERIT_PARENT_SCOPE).toBe(DEFAULT_BASE_SCOPE);
  });
});
