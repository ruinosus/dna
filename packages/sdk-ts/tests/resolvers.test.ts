import { describe, test, expect } from "bun:test";
import { HttpResolver } from "../src/adapters/resolvers/http.js";
import { GitHubResolver } from "../src/adapters/resolvers/github.js";

describe("HttpResolver", () => {
  test("cacheKey is deterministic", async () => {
    const r = new HttpResolver();
    expect(r.cacheKey("http://example.com/deps")).toBe(r.cacheKey("http://example.com/deps"));
  });
  test("cacheKey sanitizes special chars", async () => {
    const r = new HttpResolver();
    const key = r.cacheKey("https://registry.example.com/v1/packages");
    expect(key).not.toContain(":");
    expect(key).not.toContain("/");
  });
  test("cacheKey is prefixed with http-", async () => {
    const r = new HttpResolver();
    expect(r.cacheKey("https://example.com/pkg")).toMatch(/^http-/);
  });
  test("cacheKey is truncated to 120 chars", async () => {
    const r = new HttpResolver();
    const longUri = "https://" + "a".repeat(200);
    expect(r.cacheKey(longUri).length).toBeLessThanOrEqual(120);
  });
});

describe("GitHubResolver", () => {
  test("cacheKey is deterministic", async () => {
    const r = new GitHubResolver();
    expect(r.cacheKey("github:org/repo")).toBe(r.cacheKey("github:org/repo"));
  });
  test("cacheKey includes ref", async () => {
    const r = new GitHubResolver();
    const k1 = r.cacheKey("github:org/repo@main");
    const k2 = r.cacheKey("github:org/repo@v2");
    expect(k1).not.toBe(k2);
  });
  test("cacheKey is prefixed with github-", async () => {
    const r = new GitHubResolver();
    expect(r.cacheKey("github:org/repo")).toMatch(/^github-/);
  });
  test("cacheKey sanitizes special chars", async () => {
    const r = new GitHubResolver();
    const key = r.cacheKey("github:org/repo@v1.2.3");
    expect(key).not.toContain(":");
    expect(key).not.toContain("/");
  });
});
