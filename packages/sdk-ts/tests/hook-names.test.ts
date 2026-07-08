/**
 * s-dna-typed-hook-names (TS twin of Py tests/test_hook_names.py) — the
 * hook-name vocabulary is typed + fail-loud.
 *
 * Hook names used to be magic strings: `on("pre_saev", fn)` compiled, ran,
 * and the listener never fired — silently. Now:
 *
 * 1. `HookName` (union) + `KNOWN_HOOK_NAMES` are the single vocabulary,
 *    locked to the shared fixture `tests/parity-fixtures/
 *    port-surface-parity.json` (section `hook_names`) — drift vs the Py
 *    twin (dna/kernel/hooks.py) turns both suites red.
 * 2. Registering or emitting an UNKNOWN name console.warns (once per
 *    registry+name) — fail-loud, never fail-closed (custom names stay
 *    legal, back-compat).
 * 3. The veto channel is typed: `emitVeto` carries a `PreSaveContext` and
 *    the real guards consume its fields (scope/kind/name/raw/tenant/kernel).
 */
import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  HookRegistry,
  KNOWN_HOOK_NAMES,
  type HookContext,
  type PreSaveContext,
} from "../src/kernel/hooks.js";
import { platformAgentForkGuard } from "../src/extensions/helix/write-guards.js";
import { TenantNotAllowed } from "../src/kernel/protocols.js";
import { DEFAULT_BASE_SCOPE } from "../src/kernel/index.js";

const FIXTURE_PATH = join(
  dirname(fileURLToPath(import.meta.url)),
  "../../../tests/parity-fixtures/port-surface-parity.json",
);

function ctx(): HookContext {
  return { scope: "s", data: {} };
}

function presave(over: Partial<PreSaveContext> = {}): PreSaveContext {
  return {
    scope: "s", kind: "K", name: "n", raw: {}, tenant: null, kernel: null,
    ...over,
  };
}

/** Capture console.warn for the duration of `fn`. */
function captureWarns(fn: () => void): string[] {
  const warns: string[] = [];
  const orig = console.warn;
  console.warn = (...args: unknown[]) => { warns.push(String(args[0])); };
  try {
    fn();
  } finally {
    console.warn = orig;
  }
  return warns;
}

describe("hook-name vocabulary (s-dna-typed-hook-names)", () => {
  test("vocabulary matches the parity fixture (TS side of the gate)", () => {
    const fixture = JSON.parse(readFileSync(FIXTURE_PATH, "utf-8"));
    expect([...KNOWN_HOOK_NAMES]).toEqual(fixture.hook_names.names);
  });

  test("no duplicate names", () => {
    expect(new Set(KNOWN_HOOK_NAMES).size).toBe(KNOWN_HOOK_NAMES.length);
  });

  test("every builtin emit-site name is in the vocabulary", () => {
    for (const name of [
      "pre_build_prompt", "post_build_prompt", "pre_save", "post_save",
      "post_delete", "kinddef_conflict", "parse_error", "extension_error",
    ]) {
      expect(KNOWN_HOOK_NAMES).toContain(name);
    }
  });
});

describe("unknown-name warning — fail-loud, not fail-closed", () => {
  test("a typo in on() warns and names the vocabulary", () => {
    const reg = new HookRegistry();
    const warns = captureWarns(() => {
      reg.on("pre_saev", () => {});
    });
    expect(warns.length).toBe(1);
    expect(warns[0]).toContain('unknown hook name "pre_saev"');
    expect(warns[0]).toContain("pre_save");
    // Back-compat: the (mis)named listener is still registered.
    expect(reg.has("pre_saev")).toBe(true);
  });

  test("every registration + emit surface warns on an unknown name", async () => {
    for (const call of [
      (r: HookRegistry) => r.use("not_a_hook", (c) => c),
      (r: HookRegistry) => r.on("not_a_hook", () => {}),
      (r: HookRegistry) => r.onAsync("not_a_hook", async () => {}),
      (r: HookRegistry) => r.onVeto("not_a_hook", () => {}),
      (r: HookRegistry) => r.emit("not_a_hook", ctx()),
      (r: HookRegistry) => r.runMiddleware("not_a_hook", ctx()),
    ]) {
      const warns = captureWarns(() => call(new HookRegistry()));
      expect(warns.filter((w) => w.includes("unknown hook name")).length).toBe(1);
    }
    // Async surfaces.
    const reg = new HookRegistry();
    const orig = console.warn;
    const warns: string[] = [];
    console.warn = (...args: unknown[]) => { warns.push(String(args[0])); };
    try {
      await reg.emitAsync("not_a_hook", ctx());
      await reg.emitVeto("not_a_hook_either", presave());
    } finally {
      console.warn = orig;
    }
    expect(warns.filter((w) => w.includes("unknown hook name")).length).toBe(2);
  });

  test("valid names never warn", () => {
    const reg = new HookRegistry();
    const warns = captureWarns(() => {
      for (const name of KNOWN_HOOK_NAMES) {
        reg.use(name, (c) => c);
        reg.on(name, () => {});
        reg.onVeto(name, () => {});
        reg.emit(name, ctx());
        reg.runMiddleware(name, ctx());
      }
    });
    expect(warns.filter((w) => w.includes("unknown hook name"))).toEqual([]);
  });

  test("warns once per (registry, name); a fresh registry warns again", () => {
    const reg = new HookRegistry();
    const warns = captureWarns(() => {
      reg.on("typo_hook", () => {});
      reg.on("typo_hook", () => {}); // same name → deduped
      reg.emit("typo_hook", ctx());
      reg.on("other_typo", () => {}); // new name → new warning
    });
    expect(warns.filter((w) => w.includes("unknown hook name")).length).toBe(2);
    const again = captureWarns(() => {
      new HookRegistry().on("typo_hook", () => {});
    });
    expect(again.filter((w) => w.includes("unknown hook name")).length).toBe(1);
  });
});

describe("typed veto ctx — the REAL guard consumes PreSaveContext fields", () => {
  test("PreSaveContext drives the platform-agent fork guard", async () => {
    const reg = new HookRegistry();
    reg.onVeto("pre_save", platformAgentForkGuard, { priority: 10 });
    // Base write (no tenant) passes.
    await reg.emitVeto("pre_save", presave({
      scope: DEFAULT_BASE_SCOPE, kind: "Agent", name: "jarvis",
    }));
    // Per-tenant overlay of a _lib Agent is vetoed.
    await expect(reg.emitVeto("pre_save", presave({
      scope: DEFAULT_BASE_SCOPE, kind: "Agent", name: "jarvis",
      tenant: "acme",
    }))).rejects.toThrow(TenantNotAllowed);
  });
});
