// typescript/tests/post-save-emission.test.ts
import { describe, test, expect } from "bun:test";
import { Kernel } from "../src/kernel/index";
import type { HookContext } from "../src/kernel/hooks";
import type { WritableSourcePort } from "../src/kernel/protocols";
import { SD, type KindPort } from "../src/kernel/protocols";

// ---------------------------------------------------------------------------
// Stub KindPort — minimal YAML-storage kind for testing
// ---------------------------------------------------------------------------

function stubKindPort(kindName: string, pattern: "yaml" | "bundle" = "yaml"): KindPort {
  const sd = pattern === "yaml"
    ? SD.yaml("items")
    : SD.bundle("items", "ITEM.md");

  return {
    apiVersion: "test.io/v1",
    kind: kindName,
    alias: `test-${kindName.toLowerCase()}`,
    isRoot: false,
    isPromptTarget: false,
    promptTargetPriority: 0,
    flattenInContext: false,
    storage: sd,
    depFilters: () => null,
    getDefaultAgentName: () => null,
    getLayerPolicies: () => null,
    parse: (raw) => raw,
    describe: () => null,
    summary: () => null,
    promptTemplate: () => null,
  };
}

// ---------------------------------------------------------------------------
// Stub WritableSourcePort — document-level (post-Chunk 5)
// ---------------------------------------------------------------------------

function stubWritableSource(): WritableSourcePort & {
  saved: { scope: string; kind: string; name: string; raw: Record<string, unknown> }[];
  deleted: { scope: string; kind: string; name: string }[];
} {
  const stub = {
    saved: [] as { scope: string; kind: string; name: string; raw: Record<string, unknown> }[],
    deleted: [] as { scope: string; kind: string; name: string }[],
    supportsReaders: false,
    loadBootstrapDocs: async () => [],
    loadAll: () => [],
    resolveRef: () => "",
    loadLayer: () => [],
    async saveDocument(scope: string, kind: string, name: string, raw: Record<string, unknown>) {
      stub.saved.push({ scope, kind, name, raw });
      return "1";
    },
    async deleteDocument(scope: string, kind: string, name: string) {
      stub.deleted.push({ scope, kind, name });
    },
  };
  return stub;
}

// ---------------------------------------------------------------------------
// Tests — post_save on writeDocument
// ---------------------------------------------------------------------------

describe("post_save emission on writeDocument", () => {
  test("emits post_save with document_created on save", async () => {
    const k = new Kernel();
    k.kind(stubKindPort("Item"));

    const ws = stubWritableSource();
    k.writableSource(ws);

    const events: HookContext[] = [];
    k.on("post_save", (ctx) => events.push(ctx));

    await k.writeDocument("my-scope", "Item", "thing-1", {
      apiVersion: "test.io/v1",
      kind: "Item",
      metadata: { name: "thing-1" },
      spec: { value: 42 },
    });

    expect(events).toHaveLength(1);
    expect(events[0].scope).toBe("my-scope");
    expect(events[0].kind).toBe("Item");
    expect(events[0].name).toBe("thing-1");
    // Document-level path always reports is_update=false (adapters own
    // the notion of create-vs-update now).
    expect(events[0].data.event_type).toBe("document_created");
    expect(events[0].data.is_update).toBe(false);
    expect(events[0].data.author).toBe("sdk");
    expect(events[0].data.spec).toBeDefined();
  });

  test("does NOT emit post_save when skipHooks is true", async () => {
    const k = new Kernel();
    k.kind(stubKindPort("Item"));

    const ws = stubWritableSource();
    k.writableSource(ws);

    const events: HookContext[] = [];
    k.on("post_save", (ctx) => events.push(ctx));

    await k.writeDocument("my-scope", "Item", "thing-1", {
      apiVersion: "test.io/v1",
      kind: "Item",
      metadata: { name: "thing-1" },
      spec: {},
    }, { skipHooks: true });

    expect(events).toHaveLength(0);
    // But the save should still have happened
    expect(ws.saved.length).toBe(1);
  });

  test("includes custom author when provided", async () => {
    const k = new Kernel();
    k.kind(stubKindPort("Item"));

    const ws = stubWritableSource();
    k.writableSource(ws);

    const events: HookContext[] = [];
    k.on("post_save", (ctx) => events.push(ctx));

    await k.writeDocument("my-scope", "Item", "thing-1", {
      apiVersion: "test.io/v1",
      kind: "Item",
      metadata: { name: "thing-1" },
      spec: {},
    }, { author: "studio-ui" });

    expect(events).toHaveLength(1);
    expect(events[0].data.author).toBe("studio-ui");
  });
});

// ---------------------------------------------------------------------------
// Tests — post_delete on deleteDocument
// ---------------------------------------------------------------------------

describe("post_delete emission on deleteDocument", () => {
  test("emits post_delete (not post_save) on delete", async () => {
    const k = new Kernel();
    k.kind(stubKindPort("Item"));

    const ws = stubWritableSource();
    k.writableSource(ws);

    const saveEvents: HookContext[] = [];
    const deleteEvents: HookContext[] = [];
    k.on("post_save", (ctx) => saveEvents.push(ctx));
    k.on("post_delete", (ctx) => deleteEvents.push(ctx));

    await k.deleteDocument("my-scope", "Item", "thing-1");

    // Chunk 5: legacy post_save + DELETE_EVENT_TYPE emission is gone.
    // Only post_delete fires now.
    expect(saveEvents).toHaveLength(0);
    expect(deleteEvents).toHaveLength(1);
    expect(deleteEvents[0].scope).toBe("my-scope");
    expect(deleteEvents[0].kind).toBe("Item");
    expect(deleteEvents[0].name).toBe("thing-1");
  });

  test("does NOT emit post_delete when skipHooks is true", async () => {
    const k = new Kernel();
    k.kind(stubKindPort("Item"));

    const ws = stubWritableSource();
    k.writableSource(ws);

    const deleteEvents: HookContext[] = [];
    k.on("post_delete", (ctx) => deleteEvents.push(ctx));

    await k.deleteDocument("my-scope", "Item", "thing-1", { skipHooks: true });

    expect(deleteEvents).toHaveLength(0);
    // But the delete should still have happened
    expect(ws.deleted.length).toBe(1);
  });

  test("bundle kind delegates to port.deleteDocument", async () => {
    const k = new Kernel();
    k.kind(stubKindPort("Item", "bundle"));

    const ws = stubWritableSource();
    k.writableSource(ws);

    const deleteEvents: HookContext[] = [];
    k.on("post_delete", (ctx) => deleteEvents.push(ctx));

    await k.deleteDocument("my-scope", "Item", "my-item");

    expect(ws.deleted).toEqual([{ scope: "my-scope", kind: "Item", name: "my-item" }]);
    expect(deleteEvents).toHaveLength(1);
  });
});
