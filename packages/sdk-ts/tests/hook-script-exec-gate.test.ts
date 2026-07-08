/**
 * s-kernel-sandbox-hook-exec — ManifestInstance.applyHooks must NOT build a
 * `new Function(...)` from a Hook doc's spec.body by default (an unauthenticated
 * RCE: a Hook is reachable via the normal doc-write path). Gated behind the
 * explicit DNA_ALLOW_HOOK_SCRIPT_EXEC=1 flag. 1:1 with the Python twin.
 */
import { describe, expect, test, afterEach } from "bun:test";
import { ManifestInstance } from "../src/kernel/instance.js";
import { Document } from "../src/kernel/document.js";

function fakeKernel() {
  const used: Array<[string, unknown]> = [];
  const oned: Array<[string, unknown]> = [];
  return {
    used,
    oned,
    hooks: {
      use: (h: string, fn: unknown) => used.push([h, fn]),
      on: (h: string, fn: unknown) => oned.push([h, fn]),
    },
  };
}

function miWithHook(spec: Record<string, unknown>, kernel: unknown): ManifestInstance {
  const doc = new Document({
    apiVersion: "github.com/ruinosus/dna/v1",
    kind: "Hook",
    name: "evil",
    spec,
  });
  return new ManifestInstance({ scope: "t", documents: [doc], kinds: new Map(), kernel });
}

const SCRIPT_BODY = "(ctx) => ctx";

afterEach(() => {
  delete process.env.DNA_ALLOW_HOOK_SCRIPT_EXEC;
});

describe("applyHooks script-exec gate", () => {
  test("middleware action='script' is NOT registered by default", () => {
    delete process.env.DNA_ALLOW_HOOK_SCRIPT_EXEC;
    const k = fakeKernel();
    miWithHook({ type: "middleware", target: "pre_build_prompt", action: "script", body: SCRIPT_BODY }, k).applyHooks();
    expect(k.used.length).toBe(0); // exec path never reached
  });

  test("event action='script' is NOT registered by default", () => {
    delete process.env.DNA_ALLOW_HOOK_SCRIPT_EXEC;
    const k = fakeKernel();
    miWithHook({ type: "event", target: "post_tool", action: "script", body: SCRIPT_BODY }, k).applyHooks();
    expect(k.oned.length).toBe(0);
  });

  test("DNA_ALLOW_HOOK_SCRIPT_EXEC=1 re-enables exec (opt-in)", () => {
    process.env.DNA_ALLOW_HOOK_SCRIPT_EXEC = "1";
    const k = fakeKernel();
    miWithHook({ type: "middleware", target: "pre_build_prompt", action: "script", body: SCRIPT_BODY }, k).applyHooks();
    expect(k.used.length).toBe(1);
    expect(k.used[0]![0]).toBe("pre_build_prompt");
  });

  test("declarative inject_fields works regardless of the flag", () => {
    delete process.env.DNA_ALLOW_HOOK_SCRIPT_EXEC;
    const k = fakeKernel();
    miWithHook({ type: "middleware", target: "pre_build_prompt", action: "inject_fields", fields: { foo: "bar" } }, k).applyHooks();
    expect(k.used.length).toBe(1);
  });
});
