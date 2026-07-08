import { quickInstance, createKernelWithBuiltins } from "../src/bootstrap";
import { describe, test, expect } from "bun:test";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { mkdtempSync, rmSync } from "node:fs";
import { Kernel } from "../src/kernel/index.js";
import { writeLockfile, readLockfile, verifyLock } from "../src/kernel/lock.js";

const BASE_DIR = join(import.meta.dir, "..", "..", "..", "scopes", "open-swe", ".dna");

describe("writeLockfile + readLockfile roundtrip", () => {
  test("roundtrip preserves entries", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const lock = mi.generateLock();
    const tmp = mkdtempSync(join(tmpdir(), "lock-test-"));
    const path = join(tmp, ".dna.lock");
    writeLockfile(lock, path);
    const loaded = readLockfile(path);
    expect(loaded.documents.length).toBe(lock.documents.length);
    rmSync(tmp, { recursive: true });
  });

  test("read missing file returns empty", async () => {
    const lock = readLockfile("/nonexistent/.dna.lock");
    expect(lock.documents.length).toBe(0);
  });
});

describe("verifyLock", () => {
  test("passes when unchanged", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const lock = mi.generateLock();
    const tmp = mkdtempSync(join(tmpdir(), "verify-test-"));
    const path = join(tmp, ".dna.lock");
    writeLockfile(lock, path);
    const result = verifyLock(mi.documents, path);
    expect(result.ok).toBe(true);
    expect(result.added.length).toBe(0);
    expect(result.removed.length).toBe(0);
    expect(result.changed.length).toBe(0);
    rmSync(tmp, { recursive: true });
  });

  test("detects added doc", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const lock = mi.generateLock();
    lock.documents = lock.documents.slice(0, -1); // remove last
    const tmp = mkdtempSync(join(tmpdir(), "verify-test-"));
    const path = join(tmp, ".dna.lock");
    writeLockfile(lock, path);
    const result = verifyLock(mi.documents, path);
    expect(result.ok).toBe(false);
    expect(result.added.length).toBeGreaterThanOrEqual(1);
    rmSync(tmp, { recursive: true });
  });

  test("detects changed sha", async () => {
    const mi = await quickInstance("open-swe", BASE_DIR);
    const lock = mi.generateLock();
    lock.documents[0].sha256 = "0".repeat(64);
    const tmp = mkdtempSync(join(tmpdir(), "verify-test-"));
    const path = join(tmp, ".dna.lock");
    writeLockfile(lock, path);
    const result = verifyLock(mi.documents, path);
    expect(result.ok).toBe(false);
    expect(result.changed.length).toBeGreaterThanOrEqual(1);
    rmSync(tmp, { recursive: true });
  });
});
