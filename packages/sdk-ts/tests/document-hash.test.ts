// typescript/tests/document-hash.test.ts
import { describe, test, expect } from "bun:test";
import { documentHash } from "../src/kernel/lock";

const FIXTURES = [
  {
    doc: { kind: "Genome", name: "test", spec: { agents: ["bot"] } },
    expectedCanonical: '{"kind": "Genome", "name": "test", "spec": {"agents": ["bot"]}}',
  },
  {
    doc: { kind: "Agent", name: "bot", spec: { model: "gpt-4o", skills: ["search"] } },
    expectedCanonical: '{"kind": "Agent", "name": "bot", "spec": {"model": "gpt-4o", "skills": ["search"]}}',
  },
  {
    // Nested object with keys in non-alphabetical order
    doc: { spec: { description: "Web search" }, name: "search", kind: "Skill" },
    expectedCanonical: '{"kind": "Skill", "name": "search", "spec": {"description": "Web search"}}',
  },
  {
    // EDGE CASE: colon inside string value (URL) — must NOT be corrupted
    doc: { kind: "Agent", name: "api", spec: { endpoint: "https://api.example.com:8080/v1" } },
    expectedCanonical: '{"kind": "Agent", "name": "api", "spec": {"endpoint": "https://api.example.com:8080/v1"}}',
  },
  {
    // EDGE CASE: comma inside string value
    doc: { kind: "Agent", name: "tags", spec: { labels: "red, green, blue" } },
    expectedCanonical: '{"kind": "Agent", "name": "tags", "spec": {"labels": "red, green, blue"}}',
  },
  {
    // EDGE CASE: null, boolean, numeric values
    doc: { kind: "X", name: "types", spec: { flag: true, debug: false, count: 42, opt: null, temp: 0.7 } },
    expectedCanonical: '{"kind": "X", "name": "types", "spec": {"count": 42, "debug": false, "flag": true, "opt": null, "temp": 0.7}}',
  },
  {
    // EDGE CASE: deeply nested (3+ levels) + empty object/array
    doc: { kind: "X", name: "deep", spec: { a: { b: { c: "val" } }, empty_obj: {}, empty_arr: [] } },
    expectedCanonical: '{"kind": "X", "name": "deep", "spec": {"a": {"b": {"c": "val"}}, "empty_arr": [], "empty_obj": {}}}',
  },
];

describe("documentHash", () => {
  for (const { doc, expectedCanonical } of FIXTURES) {
    test(`${doc.kind}/${doc.name} matches Python hash`, () => {
      const encoder = new TextEncoder();
      const data = encoder.encode(expectedCanonical);
      const expected = Array.from(
        new Uint8Array(
          require("crypto").createHash("sha256").update(data).digest()
        )
      ).map(b => b.toString(16).padStart(2, "0")).join("");

      expect(documentHash(doc)).toBe(expected);
    });
  }

  test("key order does not affect hash", async () => {
    const a = { kind: "X", name: "y", spec: { b: 2, a: 1 } };
    const b = { name: "y", spec: { a: 1, b: 2 }, kind: "X" };
    expect(documentHash(a)).toBe(documentHash(b));
  });

  test("different content produces different hash", async () => {
    const a = { kind: "X", name: "y", spec: { value: 1 } };
    const b = { kind: "X", name: "y", spec: { value: 2 } };
    expect(documentHash(a)).not.toBe(documentHash(b));
  });
});
