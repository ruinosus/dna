import { describe, it, expect } from "bun:test";
import type { HookContext } from "../src/kernel/hooks";

describe("HookContext layer field", () => {
  it("accepts optional layer tuple", async () => {
    const ctx: HookContext = {
      scope: "s",
      kind: "K",
      name: "n",
      data: {},
      layer: ["tenant", "T1"],
    };
    expect(ctx.layer).toEqual(["tenant", "T1"]);
  });

  it("defaults to undefined when absent", async () => {
    const ctx: HookContext = {
      scope: "s",
      kind: "K",
      name: "n",
      data: {},
    };
    expect(ctx.layer).toBeUndefined();
  });
});
