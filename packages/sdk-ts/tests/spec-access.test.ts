import { describe, it, expect } from "bun:test";
import {
  readSpecString,
  readSpecStringArray,
  readSpecRecord,
  readSpecRecordArray,
} from "../src/kernel/spec-access.js";

describe("spec-access helpers", () => {
  it("readSpecString returns the string or undefined", async () => {
    const doc = { spec: { name: "foo", count: 3 } } as any;
    expect(readSpecString(doc, "name")).toBe("foo");
    expect(readSpecString(doc, "missing")).toBeUndefined();
  });
  it("readSpecString throws on type mismatch", async () => {
    const doc = { spec: { count: 3 } } as any;
    expect(() => readSpecString(doc, "count")).toThrow(/expected string/);
  });
  it("readSpecStringArray returns []", async () => {
    const doc = { spec: { tags: ["a", "b"] } } as any;
    expect(readSpecStringArray(doc, "tags")).toEqual(["a", "b"]);
    expect(readSpecStringArray(doc, "missing")).toEqual([]);
  });
  it("readSpecRecord returns the object or {}", async () => {
    const doc = { spec: { meta: { k: 1 } } } as any;
    expect(readSpecRecord(doc, "meta")).toEqual({ k: 1 });
    expect(readSpecRecord(doc, "missing")).toEqual({});
  });
  it("readSpecRecordArray returns the array or []", async () => {
    const doc = { spec: { items: [{ a: 1 }, { b: 2 }] } } as any;
    expect(readSpecRecordArray(doc, "items")).toEqual([{ a: 1 }, { b: 2 }]);
    expect(readSpecRecordArray(doc, "missing")).toEqual([]);
  });
});
