/**
 * s-kernel-fail-soft-audit (TS twin of Py test_hooks_fail_loud.py) —
 * the sync-emit async-listener skip is LOUD: counted per hook, warned
 * once per (hook, listener), and `strict: true` throws.
 */
import { describe, expect, test } from "bun:test";
import { HookRegistry, type HookContext } from "../src/kernel/hooks.js";

function ctx(): HookContext {
  return { scope: "s", data: {} };
}

describe("HookRegistry fail-loud sync emit", () => {
  test("emit runs sync listeners and counts async skips", () => {
    const reg = new HookRegistry();
    const hits: string[] = [];
    reg.on("post_build_prompt", () => { hits.push("sync"); });
    reg.on("post_build_prompt", async function asyncListener() { hits.push("async"); });

    const warns: string[] = [];
    const orig = console.warn;
    console.warn = (...args: unknown[]) => { warns.push(String(args[0])); };
    try {
      reg.emit("post_build_prompt", ctx());
      reg.emit("post_build_prompt", ctx());
    } finally {
      console.warn = orig;
    }

    expect(hits).toEqual(["sync", "sync"]);
    expect(reg.skippedAsyncEmits.get("post_build_prompt")).toBe(2);
    // Once per (hook, listener), not per emit.
    const skips = warns.filter((w) => w.includes("SKIPPED"));
    expect(skips.length).toBe(1);
    expect(skips[0]).toContain("asyncListener");
  });

  test("strict emit throws on async listeners", () => {
    const reg = new HookRegistry();
    reg.on("post_build_prompt", async function l1() {});
    expect(() => reg.emit("post_build_prompt", ctx(), { strict: true })).toThrow(/emitAsync/);
  });

  test("strict emit is a no-op without async listeners", () => {
    const reg = new HookRegistry();
    const hits: string[] = [];
    reg.on("post_build_prompt", () => { hits.push("sync"); });
    reg.emit("post_build_prompt", ctx(), { strict: true });
    expect(hits).toEqual(["sync"]);
  });
});
