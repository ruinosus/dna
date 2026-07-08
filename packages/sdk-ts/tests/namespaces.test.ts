/**
 * Namespace API tests — verify that the new namespace classes
 * (prompt, composition, nav, lock) return identical results
 * to the existing ManifestInstance methods they extract.
 */

import { describe, expect, test, beforeAll } from "bun:test";
import { quickInstance } from "../src/bootstrap.js";
import path from "node:path";

const BASE_DIR = path.resolve(import.meta.dir, "../../../scopes/open-swe/.dna");

describe("Namespace API", () => {
  let mi: Awaited<ReturnType<typeof quickInstance>>;
  beforeAll(async () => { mi = await quickInstance("open-swe", BASE_DIR); });

  describe("prompt", () => {
    test("prompt.build() equals buildPrompt()", async () => {
      const old = await mi.buildPrompt();
      const neu = await mi.prompt.build();
      expect(neu).toBe(old);
    });

    test("prompt.build({ agent }) works", async () => {
      const agents = mi.all("Agent");
      if (agents.length > 0) {
        const name = agents[0].name;
        const old = await mi.buildPrompt({ agent: name });
        const neu = await mi.prompt.build({ agent: name });
        expect(neu).toBe(old);
      }
    });
  });

  describe("composition", () => {
    test("composition.validate() equals compositionResult", async () => {
      const old = mi.compositionResult;
      const neu = mi.composition.validate();
      expect(neu).toEqual(old);
    });

    test("composition.consumersOf() works", async () => {
      const skills = mi.all("Skill");
      if (skills.length > 0) {
        const s = skills[0];
        const old = mi.consumersOf(s.kind, s.name);
        const neu = mi.composition.consumersOf(s.kind, s.name);
        expect(neu).toEqual(old);
      }
    });

    test("composition.dependencyTree() works", async () => {
      const old = mi.dependencyTree();
      const neu = mi.composition.dependencyTree();
      expect(neu).toEqual(old);
    });
  });

  describe("nav", () => {
    test("nav.describe() equals describe()", async () => {
      const agents = mi.all("Agent");
      if (agents.length > 0) {
        const a = agents[0];
        const old = mi.describe(a.kind, a.name);
        const neu = mi.nav.describe(a.kind, a.name);
        expect(neu).toBe(old);
      }
    });

    test("nav.summary() equals summary()", async () => {
      expect(mi.nav.summary()).toBe(mi.summary());
    });

    test("nav.inventory() equals inventory()", async () => {
      expect(mi.nav.inventory()).toEqual(mi.inventory());
    });

    test("inventory() composition shape includes deferred key", () => {
      const inv = mi.inventory();
      expect(inv.composition).toHaveProperty("deferred");
      expect(Array.isArray(inv.composition.deferred)).toBe(true);
    });

    test("nav.renderDoc() equals renderDoc()", async () => {
      const agents = mi.all("Agent");
      if (agents.length > 0) {
        const a = agents[0];
        expect(mi.nav.renderDoc(a.kind, a.name)).toEqual(mi.renderDoc(a.kind, a.name));
      }
    });
  });

  describe("lock", () => {
    test("lock.generate() equals generateLock()", async () => {
      const old = mi.generateLock();
      const neu = mi.lock.generate();
      expect(neu.scope).toBe(old.scope);
      expect(neu.documents).toEqual(old.documents);
      expect(neu.lockVersion).toBe(old.lockVersion);
    });
  });
});
