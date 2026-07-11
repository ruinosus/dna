/**
 * Scope-as-package-data — TS twin of tests/test_scope_as_package_data.py
 * (`s-scope-as-package-data` + `s-pkg-source-scheme`).
 *
 * The bug: a deployed app makes its scope travel by hand — a brittle
 * `path.resolve(__dirname, "../..")` plus a manual `COPY .dna`. The image is
 * the app, not the repo; CWD is not the repo; forget the copy and the app
 * boots with no scope.
 *
 * The heart is the "resolves from an installed package, from a different CWD"
 * test: the example package is materialized in `node_modules` (an unpacked
 * dependency), the process CWD is switched to an empty dir, and the scope
 * resolves by package NAME via `anchor` / `pkg://` — no path navigation, no
 * `.dna` in the CWD.
 */
import { afterAll, afterEach, beforeAll, describe, expect, test } from "bun:test";
import { cpSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import {
  anchorScopesRoot,
  PackageScopeNotFound,
} from "../src/package-scope.js";
import { loadPrompts } from "../src/prompts.js";
import { sourceFromUrl, UnsupportedSourceScheme } from "../src/adapters/source-url.js";

// examples/shipping-a-scope/acme_support_bot — the example app package.
const PKG_SRC = path.resolve(
  import.meta.dir,
  "../../../examples/shipping-a-scope/acme_support_bot",
);
// Materialize it as an INSTALLED dependency: packages/sdk-ts/node_modules/…,
// so `require.resolve("acme-support-bot/package.json")` (anchored at the SDK
// module) finds it by name — exactly how it resolves in a real app whose
// node_modules holds both the SDK and the app package.
const INSTALLED = path.resolve(import.meta.dir, "../node_modules/acme-support-bot");

let origCwd: string;

beforeAll(() => {
  rmSync(INSTALLED, { recursive: true, force: true });
  cpSync(PKG_SRC, INSTALLED, { recursive: true });
  origCwd = process.cwd();
});

afterAll(() => {
  rmSync(INSTALLED, { recursive: true, force: true });
});

afterEach(() => {
  process.chdir(origCwd);
});

function emptyCwd(): string {
  const dir = mkdtempSync(path.join(tmpdir(), "container-workdir-"));
  process.chdir(dir); // like a Docker WORKDIR /app — no .dna here
  return dir;
}

describe("anchor resolution", () => {
  test("anchorScopesRoot resolves the embedded .dna by package name", () => {
    const root = anchorScopesRoot("acme-support-bot");
    expect(root.endsWith(path.join("acme-support-bot", ".dna"))).toBe(true);
  });

  test("loadPrompts(anchor) composes the scope from an empty CWD", async () => {
    emptyCwd();
    const prompts = await loadPrompts("support", { anchor: "acme-support-bot" });
    const text = await prompts.get("triage");
    expect(text).toContain("ACME support triage agent");
  });

  test("bad anchor fails loud with a packaging-oriented message", () => {
    expect(() => anchorScopesRoot("no_such_package_xyz")).toThrow(
      PackageScopeNotFound,
    );
  });
});

describe("pkg:// source scheme", () => {
  test("sourceFromUrl(pkg://…) reads the embedded scope from an empty CWD", async () => {
    emptyCwd();
    const src = (await sourceFromUrl("pkg://acme-support-bot")) as unknown as {
      baseDir: string;
    };
    // Resolves to the package's .dna — independent of CWD, no path nav.
    expect(src.baseDir.endsWith(path.join("acme-support-bot", ".dna"))).toBe(true);
  });

  test("pkg:// with an explicit subpath is honored", async () => {
    const src = (await sourceFromUrl("pkg://acme-support-bot/.dna")) as unknown as {
      baseDir: string;
    };
    expect(src.baseDir.endsWith(path.join("acme-support-bot", ".dna"))).toBe(true);
  });

  test("pkg:// missing a package name fails loud", async () => {
    await expect(sourceFromUrl("pkg://")).rejects.toThrow(UnsupportedSourceScheme);
  });
});

describe("precedence: baseDir > env > anchor > default", () => {
  const ENV = "DNA_BASE_DIR";

  afterEach(() => {
    delete process.env[ENV];
  });

  test("explicit baseDir wins over anchor (anchor never consulted)", async () => {
    // A bogus anchor would throw if consulted; baseDir short-circuits it.
    const base = anchorScopesRoot("acme-support-bot"); // reuse a real scopes root
    const prompts = await loadPrompts("support", { anchor: "bogus", baseDir: base });
    expect(await prompts.get("triage")).toContain("ACME support triage agent");
  });

  test("DNA_BASE_DIR wins over anchor", async () => {
    process.env[ENV] = anchorScopesRoot("acme-support-bot");
    const prompts = await loadPrompts("support", { anchor: "bogus" });
    expect(await prompts.get("triage")).toContain("ACME support triage agent");
  });
});
