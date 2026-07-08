// Kind-Writer contract validation at Kernel.writeDocument (Task 2 of the
// Kind-Writer pilot, feat/kind-writer-pilot). TS twin of
// tests/test_kind_writer_validation.py.
//
// A Agent that declares writes_kind is a "Kind-Writer" — it emits a
// structured document of the target Kind. Validate the slot↔schema contract
// at write time (fail early). StatusReport (sdlc extension) is the
// schema-bearing fixture: required = [insight, verdict, confidence].
import { describe, it, expect } from "bun:test";
import { Kernel } from "../src/kernel/index.js";
import { HelixExtension } from "../src/extensions/helix.js";
import { SdlcExtension } from "../src/extensions/sdlc.js";

function fakeSource(): any {
  return {
    async saveDocument() { return "v1"; },
    async deleteDocument() {},
    async loadBootstrapDocs() { return []; },
    async loadDocument() { return null; },
    async loadLayer() { return []; },
    async capabilities() { return {}; },
    async listVersions() { return []; },
    async getVersion() { return null; },
    async publish() { return "v1"; },
    async loadDrafts() { return []; },
    async listScopes() { return []; },
    async saveManifest() { return "v1"; },
  };
}

function makeKernel(): Kernel {
  const k = new Kernel();
  // s-write-path-despecialize — the Kind-Writer contract is a pre_save veto
  // hook registered by the Helix extension (the Agent owner).
  k.load(new HelixExtension());
  k.load(new SdlcExtension());
  const src = fakeSource();
  k.source(src);
  k.writableSource(src);
  return k;
}

function uaRaw(spec: Record<string, unknown>): Record<string, unknown> {
  return {
    apiVersion: "github.com/ruinosus/dna/v1",
    kind: "Agent",
    metadata: { name: "kw-smoke" },
    spec: { instruction: "do the thing", ...spec },
  };
}

describe("Kind-Writer contract validation (writeDocument)", () => {
  it("rejects writes_kind pointing at an unknown/schema-less Kind", async () => {
    const k = makeKernel();
    const raw = uaRaw({ writes_kind: "NoSuchKind", creative_slots: ["x"] });
    await expect(
      k.writeDocument("scope-x", "Agent", "kw-smoke", raw),
    ).rejects.toThrow(/schema/i);
  });

  it("rejects a creative_slot that is not a schema property", async () => {
    const k = makeKernel();
    const raw = uaRaw({
      writes_kind: "StatusReport",
      creative_slots: ["not_a_real_field"],
      system_slots: { insight: "input.x", confidence: "input.y" },
    });
    await expect(
      k.writeDocument("scope-x", "Agent", "kw-smoke", raw),
    ).rejects.toThrow(/not_a_real_field/);
  });

  it("rejects an unmapped required field", async () => {
    const k = makeKernel();
    const raw = uaRaw({
      writes_kind: "StatusReport",
      creative_slots: [],
      system_slots: { insight: "input.x", confidence: "input.y" },
    });
    await expect(
      k.writeDocument("scope-x", "Agent", "kw-smoke", raw),
    ).rejects.toThrow(/unmapped.*verdict|verdict.*unmapped/i);
  });

  it("accepts a valid Kind-Writer (all required covered)", async () => {
    const k = makeKernel();
    const raw = uaRaw({
      writes_kind: "StatusReport",
      creative_slots: ["verdict"],
      system_slots: { insight: "input.oracle_id", confidence: "input.conf" },
    });
    const v = await k.writeDocument("scope-x", "Agent", "kw-smoke", raw);
    expect(v).toBe("v1");
  });

  it("leaves a plain Agent (no writes_kind) untouched", async () => {
    const k = makeKernel();
    const raw = uaRaw({});
    const v = await k.writeDocument("scope-x", "Agent", "kw-smoke", raw);
    expect(v).toBe("v1");
  });
});

// Multi-Kind validation parity (feat/kind-writer-multikind). writes_kinds maps
// each Kind to its own {creative_slots, system_slots}; each entry is validated
// the same way as a single writes_kind. Story (required title/status) +
// StatusReport (required insight/verdict/confidence) are the schema-bearing
// fixtures.
describe("Kind-Writer MULTI contract validation (writeDocument)", () => {
  it("accepts a valid writes_kinds covering every Kind's required", async () => {
    const k = makeKernel();
    const raw = uaRaw({
      writes_kinds: {
        Story: {
          creative_slots: ["description"],
          system_slots: { status: "todo" },
        },
        StatusReport: {
          creative_slots: ["verdict"],
          system_slots: { insight: "input.x", confidence: "input.y" },
        },
      },
    });
    const v = await k.writeDocument("scope-x", "Agent", "kw-smoke", raw);
    expect(v).toBe("v1");
  });

  it("rejects a writes_kinds entry pointing at an unknown Kind", async () => {
    const k = makeKernel();
    const raw = uaRaw({
      writes_kinds: { Ghost: { creative_slots: ["title"] } },
    });
    await expect(
      k.writeDocument("scope-x", "Agent", "kw-smoke", raw),
    ).rejects.toThrow(/schema/i);
  });

  it("rejects a writes_kinds entry with an uncovered required field", async () => {
    const k = makeKernel();
    // Story requires description + status; cover description but leave status
    // uncovered → must raise on the uncovered required field.
    const raw = uaRaw({
      writes_kinds: {
        Story: { creative_slots: ["description"], system_slots: {} },
      },
    });
    await expect(
      k.writeDocument("scope-x", "Agent", "kw-smoke", raw),
    ).rejects.toThrow(/unmapped.*status|status.*unmapped/i);
  });

  it("rejects a writes_kinds creative_slot that is not a schema property", async () => {
    const k = makeKernel();
    const raw = uaRaw({
      writes_kinds: {
        Story: {
          creative_slots: ["title", "not_a_field"],
          system_slots: { status: "todo" },
        },
      },
    });
    await expect(
      k.writeDocument("scope-x", "Agent", "kw-smoke", raw),
    ).rejects.toThrow(/not_a_field/);
  });
});
