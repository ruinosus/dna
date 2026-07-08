import { describe, expect, test } from "bun:test";
import { createKernelWithBuiltins, createRuntimeWithBuiltins } from "../src/bootstrap.js";

// s-export-unwired-ts-extensions: the bootstrap is the TS auto-loader. These 9
// extensions had a class but were never exported, and Community/Research/Sdlc
// were loaded by NEITHER bootstrap. Guard both the registration and the
// no-drift invariant between the two bootstrap paths.

function aliases(target: { _kinds: Map<string, { alias: string }> }): Set<string> {
  return new Set([...target._kinds.values()].map((kp) => kp.alias));
}

const NEWLY_WIRED = [
  
  
  
  
  
  
  
  
  "federation-mcp",
];

describe("bootstrap builtins", () => {
  test("previously-unwired extensions register their Kinds", () => {
    const got = aliases(createKernelWithBuiltins() as never);
    for (const alias of NEWLY_WIRED) {
      expect(got.has(alias)).toBe(true);
    }
  });

  test("kernel and runtime bootstraps register the SAME kinds (no drift)", () => {
    const k = aliases(createKernelWithBuiltins() as never);
    const rt = aliases(createRuntimeWithBuiltins() as never);
    expect([...k].sort()).toEqual([...rt].sort());
  });
});
