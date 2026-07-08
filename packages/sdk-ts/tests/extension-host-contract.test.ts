/**
 * ExtensionHost — explicit registration-time contract
 * (s-dna-extension-host-contract).
 *
 * Guards three things:
 *
 * 1. `kernel.load()` fail-loud validates the WHOLE Extension contract
 *    (name: non-empty string, version: string, register: callable) with a
 *    clear `ExtensionLoadError` — not just `typeof register`.
 * 2. The real `Kernel` structurally satisfies the `ExtensionHost`
 *    interface (the registration vocabulary extensions are typed against).
 * 3. Every builtin extension passes the gate.
 *
 * Py twin: tests/test_extension_host_contract.py.
 */
import { describe, expect, test } from "bun:test";

import { Kernel } from "../src/kernel/index.js";
import { ExtensionLoadError } from "../src/kernel/errors.js";
import { HookRegistry } from "../src/kernel/hooks.js";
import { createKernelWithBuiltins } from "../src/bootstrap.js";
import type { Extension, ExtensionHost } from "../src/kernel/protocols.js";

// ---------------------------------------------------------------------------
// 2. Kernel satisfies ExtensionHost — STATIC assertion. If the Kernel ever
//    loses a member of the registration surface (or drifts a signature),
//    this file stops compiling (`bun run typecheck`).
// ---------------------------------------------------------------------------

const _staticHostCheck: ExtensionHost = new Kernel();
void _staticHostCheck;

// And the inverse direction of the wiring: a fully-typed extension is a
// valid `Extension` (register takes the host slice, not `unknown`).
const _staticExtCheck: Extension = {
  name: "static-check",
  version: "0.0.0",
  register(kernel: ExtensionHost): void {
    void kernel;
  },
};
void _staticExtCheck;

describe("ExtensionHost contract", () => {
  test("Kernel exposes the full registration surface at runtime", () => {
    const k = new Kernel();
    for (const method of [
      "kind",
      "kindFromDescriptor",
      "reader",
      "writer",
      "on",
      "onVeto",
      "tool",
      "compositionProfile",
    ] as const) {
      expect(typeof k[method]).toBe("function");
    }
    expect(k.hooks).toBeInstanceOf(HookRegistry);
  });

  test("all builtin extensions pass the load() gate", () => {
    // Throws ExtensionLoadError if ANY builtin lacks name/version/register.
    expect(() => createKernelWithBuiltins()).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// 1. load() gate — fail-loud on structurally invalid extensions
// ---------------------------------------------------------------------------

describe("kernel.load() extension gate", () => {
  const register = () => {};

  test("accepts a valid extension", () => {
    const k = new Kernel();
    expect(() =>
      k.load({ name: "good-ext", version: "1.0.0", register }),
    ).not.toThrow();
  });

  test("rejects a missing register()", () => {
    const k = new Kernel();
    expect(() =>
      k.load({ name: "no-register", version: "1.0.0" } as unknown as Extension),
    ).toThrow(ExtensionLoadError);
    expect(() =>
      k.load({ name: "no-register", version: "1.0.0" } as unknown as Extension),
    ).toThrow(/no callable register/);
  });

  test("rejects a missing name", () => {
    const k = new Kernel();
    expect(() =>
      k.load({ version: "1.0.0", register } as unknown as Extension),
    ).toThrow(/no valid `name`/);
  });

  test("rejects a blank name", () => {
    const k = new Kernel();
    expect(() =>
      k.load({ name: "   ", version: "1.0.0", register } as unknown as Extension),
    ).toThrow(/no valid `name`/);
  });

  test("rejects a non-string name", () => {
    const k = new Kernel();
    expect(() =>
      k.load({ name: 42, version: "1.0.0", register } as unknown as Extension),
    ).toThrow(/no valid `name`/);
  });

  test("rejects a missing version — and names the extension", () => {
    const k = new Kernel();
    expect(() =>
      k.load({ name: "no-version", register } as unknown as Extension),
    ).toThrow(/no valid `version`/);
    expect(() =>
      k.load({ name: "no-version", register } as unknown as Extension),
    ).toThrow(/no-version/);
  });

  test("gate fires BEFORE register() runs", () => {
    const k = new Kernel();
    let ran = false;
    expect(() =>
      k.load({
        version: "1.0.0",
        register: () => {
          ran = true;
        },
      } as unknown as Extension),
    ).toThrow(ExtensionLoadError);
    expect(ran).toBe(false);
  });

  test("gate errors are NOT swallowed by the extension_error hook", () => {
    // The hook path is for RUNTIME registration errors; a structurally
    // invalid extension is a configuration problem and must propagate.
    const k = new Kernel();
    const errors: string[] = [];
    k.on("extension_error", (ctx) => {
      errors.push(String(ctx.data.error));
    });
    expect(() =>
      k.load({ version: "1.0.0", register } as unknown as Extension),
    ).toThrow(ExtensionLoadError);
    expect(errors).toEqual([]);
  });
});
