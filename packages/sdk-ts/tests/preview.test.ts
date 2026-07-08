/**
 * Tests for the kernel-level preview API: genericSpecDump fallback +
 * cross-document findConsumers scan. Per-extension preview() tests live
 * alongside their extension files.
 */
import { describe, it, expect } from "bun:test";
import {
  genericSpecDump,
  findConsumers,
  type PreviewBlock,
} from "../src/kernel/preview";
import type { Document } from "../src/kernel/document";
import type { ManifestInstance } from "../src/kernel/instance";

function makeDoc(
  kind: string,
  name: string,
  spec: Record<string, unknown> = {},
): Document {
  return {
    apiVersion: "test/v1",
    kind,
    name,
    spec,
    metadata: { name },
  } as unknown as Document;
}

// Known dep-field conventions for the mock. In the real kernel this
// knowledge lives in KindPort.depFilters(); here we replicate just
// enough so the findConsumers tests exercise the iterDocDeps path.
const MOCK_DEP_FIELDS: Record<string, Record<string, string>> = {
  Agent: {
    skills: "Skill",
    guardrails: "Guardrail",
    tools: "Tool",
    soul: "Soul",
    personas: "Persona",
    use_cases: "UseCase",
  },
};

function makeInstance(docs: Document[]): ManifestInstance {
  const inst = {
    documents: docs,
    one: (kind: string, name: string) =>
      docs.find((d) => d.kind === kind && d.name === name) ?? null,
    all: (kind: string) => docs.filter((d) => d.kind === kind),
    iterDocDeps: (doc: Document) => {
      const fieldMap = MOCK_DEP_FIELDS[doc.kind] ?? {};
      const spec = (doc.spec ?? {}) as Record<string, unknown>;
      return Object.entries(fieldMap).map(([label, targetKind]) => {
        const val = spec[label];
        let names: string[] = [];
        if (Array.isArray(val)) names = val.map(String);
        else if (typeof val === "string" && val) names = [val];
        return { label, targetKind, names };
      });
    },
  };
  return inst as unknown as ManifestInstance;
}

describe("genericSpecDump", () => {
  it("returns an empty block when the spec is empty", async () => {
    const doc = makeDoc("Mystery", "thing", {});
    const blocks: PreviewBlock[] = genericSpecDump(doc);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].kind).toBe("empty");
    expect(blocks[0].title.toLowerCase()).toContain("empty");
  });

  it("returns one code block with the spec serialized as JSON", async () => {
    const doc = makeDoc("Mystery", "thing", { foo: 1, bar: ["a", "b"] });
    const blocks = genericSpecDump(doc);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].kind).toBe("code");
    expect(blocks[0].language).toBe("json");
    expect(blocks[0].body).toContain('"foo"');
    expect(blocks[0].body).toContain('"bar"');
  });
});

describe("findConsumers", () => {
  it("returns empty when nothing references the target", async () => {
    const target = makeDoc("Skill", "lonely");
    const consumers = findConsumers(makeInstance([target]), {
      kind: "Skill",
      name: "lonely",
    });
    expect(consumers).toEqual([]);
  });

  it("finds an agent that lists the skill in spec.skills", async () => {
    const skill = makeDoc("Skill", "feedback-tone");
    const agent = makeDoc("Agent", "coach", {
      skills: ["feedback-tone"],
    });
    const consumers = findConsumers(makeInstance([skill, agent]), {
      kind: "Skill",
      name: "feedback-tone",
    });
    expect(consumers).toHaveLength(1);
    expect(consumers[0]).toEqual({ kind: "Agent", name: "coach" });
  });

  it("finds an agent that references a soul via spec.soul (scalar)", async () => {
    const soul = makeDoc("Soul", "brad");
    const agent = makeDoc("Agent", "coach", { soul: "brad" });
    const consumers = findConsumers(makeInstance([soul, agent]), {
      kind: "Soul",
      name: "brad",
    });
    expect(consumers).toHaveLength(1);
  });

  it("finds an agent that lists a guardrail in spec.guardrails", async () => {
    const g = makeDoc("Guardrail", "no-pii");
    const agent = makeDoc("Agent", "coach", { guardrails: ["no-pii"] });
    const consumers = findConsumers(makeInstance([g, agent]), {
      kind: "Guardrail",
      name: "no-pii",
    });
    expect(consumers).toHaveLength(1);
  });

  it("does not return the target itself", async () => {
    const skill = makeDoc("Skill", "feedback-tone");
    const consumers = findConsumers(makeInstance([skill]), {
      kind: "Skill",
      name: "feedback-tone",
    });
    expect(consumers).toEqual([]);
  });

  it("returns multiple consumers when several agents share the same skill", async () => {
    const skill = makeDoc("Skill", "concise");
    const a = makeDoc("Agent", "coach", { skills: ["concise"] });
    const b = makeDoc("Agent", "mentor", { skills: ["concise", "kind"] });
    const consumers = findConsumers(makeInstance([skill, a, b]), {
      kind: "Skill",
      name: "concise",
    });
    expect(consumers).toHaveLength(2);
  });
});
