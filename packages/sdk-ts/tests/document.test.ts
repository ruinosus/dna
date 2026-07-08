import { describe, test, expect } from "bun:test";
import { Document } from "../src/kernel/document.js";

describe("Document.spec returns Record<string, unknown>", () => {
  test("spec from raw dict", async () => {
    const doc = Document.fromRaw({
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Agent",
      metadata: { name: "brad", description: "test agent" },
      spec: { instruction: "Be helpful", soul: "brad" },
    });
    const spec = doc.spec;
    expect(spec.instruction).toBe("Be helpful");
    expect(spec.soul).toBe("brad");
  });

  test("metadata from raw dict", async () => {
    const doc = Document.fromRaw({
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Agent",
      metadata: { name: "brad", description: "test agent" },
      spec: {},
    });
    const meta = doc.metadata;
    expect(meta.name).toBe("brad");
    expect(meta.description).toBe("test agent");
  });

  test("spec from typed model", async () => {
    const raw = {
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Agent",
      metadata: { name: "brad" },
      spec: { instruction: "Be helpful", soul: "brad", skills: ["greet"] },
    };
    const typed = { metadata: { name: "brad" }, spec: { instruction: "Be helpful", soul: "brad", skills: ["greet"] } };
    const doc = Document.fromRaw(raw, typed);
    const spec = doc.spec;
    expect(spec.instruction).toBe("Be helpful");
    expect(spec.skills).toEqual(["greet"]);
  });

  test("spec missing returns empty object", async () => {
    const doc = Document.fromRaw({ apiVersion: "v1", kind: "X", metadata: { name: "t" } });
    expect(doc.spec).toEqual({});
  });

  test("typed still accessible", async () => {
    const typed = { metadata: { name: "x" }, spec: { instruction: "y" } };
    const doc = Document.fromRaw({ apiVersion: "v1", kind: "X", metadata: { name: "x" }, spec: {} }, typed);
    expect(doc.typed).toBe(typed);
  });
});
