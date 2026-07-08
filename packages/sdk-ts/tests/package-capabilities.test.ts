import { describe, expect, test } from "bun:test";
import { GenomeSpecSchema } from "../src/kernel/models.js";

describe("Genome capabilities manifest (i-112 catalog ph2)", () => {
  test("defaults to empty array", () => {
    expect(GenomeSpecSchema.parse({}).capabilities).toEqual([]);
  });
  test("preserves declared capabilities", () => {
    const caps = [{ kind: "soulspec-soul", name: "voice-policy", location: "souls/voice-policy.yaml" }];
    const s = GenomeSpecSchema.parse({ capabilities: caps });
    expect(s.capabilities).toEqual(caps);
  });
});
