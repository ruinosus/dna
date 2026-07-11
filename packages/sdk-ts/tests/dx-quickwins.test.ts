/**
 * DX quick-wins (e-dna-dx) — TS twin of tests/test_dx_quickwins.py.
 *
 *   1. s-dx-build-prompt-fail-loud   — buildPrompt throws AgentNotFound
 *   2. s-dx-clean-composition-output — buildPrompt output has no trailing newline
 *   3. s-dx-load-prompts-helper      — loadPrompts collapses the shim
 *   4. s-dx-kernel-from-config       — fromConfig + dna.config.yaml
 *
 * Read-path tests run against the real scopes/open-swe scope.
 */
import { afterEach, describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { quickInstance, fromConfig } from "../src/bootstrap.js";
import { loadConfig } from "../src/config.js";
import { AgentNotFound } from "../src/kernel/errors.js";
import { PromptLibrary, loadPrompts } from "../src/prompts.js";

const BASE_DIR = path.resolve(import.meta.dir, "../../../scopes/open-swe/.dna");

const tmpDirs: string[] = [];
function mkConfig(contents: string): string {
  const dir = mkdtempSync(path.join(tmpdir(), "dna-dx-"));
  tmpDirs.push(dir);
  const p = path.join(dir, "dna.config.yaml");
  writeFileSync(p, contents);
  return p;
}
afterEach(() => {
  while (tmpDirs.length) rmSync(tmpDirs.pop()!, { recursive: true, force: true });
});

// ── 1. fail-loud ────────────────────────────────────────────────────────────

describe("s-dx-build-prompt-fail-loud", () => {
  test("missing agent throws AgentNotFound with .agent set", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    let err: unknown;
    try {
      await mi.buildPrompt({ agent: "does-not-exist" });
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(AgentNotFound);
    expect((err as AgentNotFound).agent).toBe("does-not-exist");
  });
});

// ── 2. clean output ──────────────────────────────────────────────────────────

describe("s-dx-clean-composition-output", () => {
  test("buildPrompt output has no trailing newlines", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const text = await mi.buildPrompt({ agent: "swe-agent" });
    expect(text.length).toBeGreaterThan(0);
    expect(text.endsWith("\n")).toBe(false);
    expect(text).toBe(text.replace(/\n+$/, ""));
  });
});

// ── 3. loadPrompts ────────────────────────────────────────────────────────────

describe("s-dx-load-prompts-helper", () => {
  test("returns a clean composed prompt", async () => {
    const prompts = await loadPrompts("open-swe", BASE_DIR);
    expect(prompts).toBeInstanceOf(PromptLibrary);
    const text = await prompts.get("swe-agent");
    expect(text.length).toBeGreaterThan(0);
    expect(text.endsWith("\n")).toBe(false);
  });

  test("missing agent rejects with AgentNotFound", async () => {
    const prompts = await loadPrompts("open-swe", BASE_DIR);
    await expect(prompts.get("ghost")).rejects.toThrow(AgentNotFound);
  });

  test("mapping surface: has / names / cache", async () => {
    const prompts = await loadPrompts("open-swe", BASE_DIR);
    expect(prompts.has("swe-agent")).toBe(true);
    expect(prompts.has("ghost")).toBe(false);
    const names = prompts.names();
    expect(names).toContain("swe-agent");
    expect([...names]).toEqual([...names].sort());
    // cached: two gets return identical strings
    expect(await prompts.get("swe-agent")).toBe(await prompts.get("swe-agent"));
  });

  test("the mini-consumer: the shim in two lines", async () => {
    const prompts = await loadPrompts("open-swe", BASE_DIR);
    const SWE = await prompts.get("swe-agent");
    expect(SWE).toBeTruthy();
    expect(SWE).toBe(SWE.replace(/\n+$/, ""));
  });
});

// ── 4. fromConfig ─────────────────────────────────────────────────────────────

describe("s-dx-kernel-from-config", () => {
  test("file:// source", async () => {
    const cfg = mkConfig(`source: file://${BASE_DIR}\n`);
    const k = await fromConfig(cfg);
    const mi = await k.instance("open-swe");
    expect(await mi.buildPrompt({ agent: "swe-agent" })).toBeTruthy();
  });

  test("plain path source (no scheme)", async () => {
    const cfg = mkConfig(`source: ${BASE_DIR}\n`);
    const k = await fromConfig(cfg);
    expect(await (await k.instance("open-swe")).buildPrompt({ agent: "swe-agent" })).toBeTruthy();
  });

  test("no config file falls back to default", async () => {
    const prev = process.env.DNA_BASE_DIR;
    process.env.DNA_BASE_DIR = BASE_DIR;
    try {
      const k = await fromConfig(); // none present → default fs
      expect(await (await k.instance("open-swe")).buildPrompt({ agent: "swe-agent" })).toBeTruthy();
    } finally {
      if (prev === undefined) delete process.env.DNA_BASE_DIR;
      else process.env.DNA_BASE_DIR = prev;
    }
  });

  test("sqlite:// fails loud (Python-only)", async () => {
    const cfg = mkConfig(`source: sqlite:///tmp/x.db\n`);
    await expect(fromConfig(cfg)).rejects.toThrow(/Python-only/);
  });

  test("unknown scheme fails loud", async () => {
    const cfg = mkConfig(`source: mysql://nope\n`);
    await expect(fromConfig(cfg)).rejects.toThrow(/unsupported source URL scheme/);
  });

  test("missing --config path is an error", async () => {
    await expect(fromConfig("/no/such/dna.config.yaml")).rejects.toThrow(/not found/);
  });

  test("unknown key fails loud", async () => {
    const cfg = mkConfig(`source: file://${BASE_DIR}\nbogus: 1\n`);
    await expect(fromConfig(cfg)).rejects.toThrow(/unknown key/);
  });

  test("bad search enum fails loud", async () => {
    const cfg = mkConfig(`source: file://${BASE_DIR}\nsearch: faiss\n`);
    await expect(fromConfig(cfg)).rejects.toThrow(/faiss/);
  });

  test("auth section is an opaque passthrough (MCP IdP layer)", async () => {
    // The `auth:` section is accepted + carried opaquely; the SDK does not
    // interpret it (its consumer, the CLI, owns the provider schema).
    const cfg = mkConfig(
      `source: file://${BASE_DIR}\nauth:\n  providers:\n    - type: entra\n`,
    );
    const parsed = loadConfig(cfg);
    expect(parsed).not.toBeNull();
    expect(typeof parsed!.auth).toBe("object");
    expect((parsed!.auth as { providers: { type: string }[] }).providers[0].type)
      .toBe("entra");
  });

  test("auth must be a mapping", async () => {
    const cfg = mkConfig(`source: file://${BASE_DIR}\nauth: nope\n`);
    expect(() => loadConfig(cfg)).toThrow(/must be a mapping/);
  });
});
