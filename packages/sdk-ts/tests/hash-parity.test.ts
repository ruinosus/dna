import { quickInstance, createKernelWithBuiltins } from "../src/bootstrap";
/**
 * Hash parity tests — ensures documentHash() produces identical results
 * in Node.js (node:crypto) and browser/webview (js-sha256).
 *
 * This prevents the sync bug where Tauri webview produced empty hashes
 * because node:crypto was unavailable.
 */
import { describe, test, expect } from "bun:test";
import { sha256 } from "js-sha256";
import { createHash } from "node:crypto";
import { documentHash } from "../src/kernel/lock";
import { Kernel } from "../src/index";

describe("documentHash parity", () => {
  test("js-sha256 matches node:crypto for ASCII strings", async () => {
    const inputs = ["", "hello", "test", "abc", '{"key": "value"}'];
    for (const input of inputs) {
      const fromCrypto = createHash("sha256").update(input).digest("hex");
      const fromJsSha = sha256(input);
      expect(fromJsSha).toBe(fromCrypto);
    }
  });

  test("js-sha256 matches node:crypto for UTF-8 strings", async () => {
    const inputs = [
      "Instrução para nomear branches",
      "日本語テスト",
      "emoji 🎉 test",
      "café résumé naïve",
    ];
    for (const input of inputs) {
      const fromCrypto = createHash("sha256").update(input).digest("hex");
      const fromJsSha = sha256(input);
      expect(fromJsSha).toBe(fromCrypto);
    }
  });

  test("documentHash produces non-empty strings", async () => {
    const raw = { apiVersion: "test/v1", kind: "Test", metadata: { name: "x" }, spec: {} };
    const hash = documentHash(raw);
    expect(hash.length).toBe(64);
    expect(hash).toMatch(/^[0-9a-f]{64}$/);
  });

  test("documentHash is deterministic", async () => {
    const raw = { apiVersion: "test/v1", kind: "Test", metadata: { name: "x" }, spec: { a: 1 } };
    expect(documentHash(raw)).toBe(documentHash(raw));
  });

  test("documentHash matches Python hash for real documents", async () => {
    // These hashes were verified against Python's document_hash()
    // If they change, TS↔Python sync will break.
    const mi = await quickInstance("open-swe", "../../scopes/open-swe/.dna");
    const hashes: Record<string, string> = {};
    for (const doc of mi.documents) {
      hashes[`${doc.kind}/${doc.name}`] = documentHash(doc.raw);
    }

    // Pinned hashes from Python await quickInstance() — golden values.
    // Phase 16 — Module → Genome migration changed the root doc hash.
    expect(hashes["Genome/open-swe"]).toBe("3876a66a32fa24e6a72c7b03d34712e58a4e98077120c6b3fb187fb50fd0343c");
    expect(hashes["Skill/branch-naming"]).toBe("4809b8dd5ff4c6d7a0159436af8c8e7711a9eec5d5ef2b73e83954291565bb8c");
    expect(hashes["Soul/swe-soul"]).toBe("eaa62b8b4815c5fee36c023c32318d7e33986203a7a7c5005ca4c1372d28e700");
  });
});
