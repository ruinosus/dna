import { describe, expect, test } from "bun:test";
import { GenomeSpecSchema } from "../src/kernel/models.js";

describe("Genome mandatory/global (i-112 catalog ph1)", () => {
  test("defaults false", () => {
    const s = GenomeSpecSchema.parse({});
    expect(s.mandatory).toBe(false);
    expect(s.global_scope).toBe(false);
  });
  test("roundtrip true", () => {
    const s = GenomeSpecSchema.parse({ mandatory: true, global_scope: true });
    expect(s.mandatory).toBe(true);
    expect(s.global_scope).toBe(true);
  });
});
