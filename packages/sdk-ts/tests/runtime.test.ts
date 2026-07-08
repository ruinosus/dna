import { describe, expect, test } from "bun:test";
import path from "node:path";
import { Runtime } from "../src/kernel/runtime.js";
import { Kernel } from "../src/kernel/index.js";
import { createRuntimeWithBuiltins, quickManifest } from "../src/bootstrap.js";
import { FilesystemSource } from "../src/adapters/filesystem/source.js";
import { FilesystemCache } from "../src/adapters/filesystem/cache.js";

const BASE_DIR = path.resolve(import.meta.dir, "../../../scopes/open-swe/.dna");

describe("Runtime", () => {
  test("Runtime extends Kernel", async () => {
    const rt = new Runtime();
    expect(rt).toBeInstanceOf(Runtime);
    expect(rt).toBeInstanceOf(Kernel);
    // Has both old and new API
    expect(typeof rt.source).toBe("function");
    expect(typeof rt.storage).toBe("function");
    expect(typeof rt.instance).toBe("function");
    expect(typeof rt.manifest).toBe("function");
  });

  test("createRuntimeWithBuiltins() returns Runtime with kinds", async () => {
    const rt = createRuntimeWithBuiltins();
    expect(rt).toBeInstanceOf(Runtime);
    expect(rt._kinds.size).toBeGreaterThan(0);
  });

  test("await quickManifest() loads a manifest", async () => {
    const m = await quickManifest("open-swe", BASE_DIR);
    expect(m.documents.length).toBeGreaterThan(0);
    expect(m.scope).toBe("open-swe");
  });

  test("manifest() and instance() return same result", async () => {
    const rt = createRuntimeWithBuiltins();
    rt.storage(new FilesystemSource(BASE_DIR));
    rt.cache(new FilesystemCache(BASE_DIR));

    const m1 = await rt.manifest("open-swe");
    const m2 = await rt.instance("open-swe");

    expect(m1.documents.length).toBe(m2.documents.length);
    expect(m1.scope).toBe(m2.scope);
  });
});
