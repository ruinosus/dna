// s-write-path-despecialize — the kernel write path has NO Kind-name
// special-cases; extension-owned rules ride the `pre_save` veto channel.
// TS twin of tests/test_write_path_despecialize.py.
//
// 1. Source ratchet — no concrete Kind-name string literal inside
//    `writeDocument` (generic dispatch by KindPort attribute is fine).
// 2. Veto-channel mechanics — priority order, key idempotency, propagation.
// 3. Write-path regressions for the migrated rules (platform-agent fork
//    guard now registered by HelixExtension).
import { describe, it, expect } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Kernel, DEFAULT_BASE_SCOPE } from "../src/kernel/index.js";
import { HookRegistry, type PreSaveContext } from "../src/kernel/hooks.js";
import { TenantNotAllowed } from "../src/kernel/protocols.js";
import { HelixExtension } from "../src/extensions/helix.js";

function fakeSource(): any {
  return {
    saveCalls: [] as unknown[],
    async saveDocument(scope: string, kind: string, name: string) {
      this.saveCalls.push([scope, kind, name]);
      return "v1";
    },
    async deleteDocument() {},
    async loadBootstrapDocs() { return []; },
    async loadDocument() { return null; },
    async loadLayer() { return []; },
    async listVersions() { return []; },
    async listScopes() { return []; },
  };
}

function ctx(partial?: Partial<PreSaveContext>): PreSaveContext {
  return {
    scope: "s", kind: "K", name: "n", raw: {}, tenant: null, kernel: null,
    ...partial,
  };
}

// ---------------------------------------------------------------------------
// 1. Source ratchet — writeDocument is Kind-name agnostic
// ---------------------------------------------------------------------------

const FORBIDDEN_KIND_LITERALS = ["Agent", "LessonLearned", "Genome"];

/** Extract the body of `async writeDocument(...)` by brace counting. */
function writeDocumentBody(): string {
  const src = readFileSync(
    join(import.meta.dir, "..", "src", "kernel", "index.ts"), "utf-8",
  );
  const start = src.indexOf("async writeDocument(");
  expect(start).toBeGreaterThan(-1);
  let depth = 0;
  let bodyStart = -1;
  for (let i = start; i < src.length; i++) {
    const ch = src[i];
    if (ch === "{") {
      if (bodyStart === -1) bodyStart = i;
      depth++;
    } else if (ch === "}") {
      depth--;
      if (bodyStart !== -1 && depth === 0) {
        return src.slice(bodyStart, i + 1);
      }
    }
  }
  throw new Error("unbalanced braces extracting writeDocument");
}

describe("write path is Kind-name agnostic (ratchet)", () => {
  it("writeDocument contains no hardcoded Kind names", () => {
    const body = writeDocumentBody();
    // Strip comments — narrating a Kind in prose is fine; branching on it
    // in code is the leak this ratchet blocks.
    const code = body
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/[^\n]*/g, "");
    const offenders = FORBIDDEN_KIND_LITERALS.filter((k) =>
      new RegExp(`["'\`]${k}["'\`]`).test(code),
    );
    expect(offenders).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// 2. Veto channel mechanics
// ---------------------------------------------------------------------------

describe("HookRegistry veto channel", () => {
  it("runs listeners in ascending priority (sync + async mix)", async () => {
    const reg = new HookRegistry();
    const calls: string[] = [];
    reg.onVeto("pre_save", async () => { calls.push("late"); }, { priority: 50 });
    reg.onVeto("pre_save", () => { calls.push("early"); }, { priority: 10 });
    expect(reg.hasVeto("pre_save")).toBe(true);
    expect(reg.has("pre_save")).toBe(true);
    await reg.emitVeto("pre_save", ctx());
    expect(calls).toEqual(["early", "late"]);
  });

  it("propagates a throw and aborts the chain (the veto)", async () => {
    const reg = new HookRegistry();
    const calls: string[] = [];
    reg.onVeto("pre_save", () => {
      calls.push("guard");
      throw new Error("vetoed");
    }, { priority: 1 });
    reg.onVeto("pre_save", () => { calls.push("never"); }, { priority: 2 });
    await expect(reg.emitVeto("pre_save", ctx())).rejects.toThrow("vetoed");
    expect(calls).toEqual(["guard"]);
  });

  it("key-based registration is idempotent (replace, not stack)", async () => {
    const reg = new HookRegistry();
    const calls: string[] = [];
    reg.onVeto("pre_save", () => { calls.push("v1"); }, { key: "ext.rule" });
    reg.onVeto("pre_save", () => { calls.push("v2"); }, { key: "ext.rule" });
    await reg.emitVeto("pre_save", ctx());
    expect(calls).toEqual(["v2"]);
  });
});

// ---------------------------------------------------------------------------
// 3. Write-path regressions for the migrated rules
// ---------------------------------------------------------------------------

function uaRaw(name: string): Record<string, unknown> {
  return {
    apiVersion: "github.com/ruinosus/dna/v1",
    kind: "Agent",
    metadata: { name },
    spec: { instruction: "you are jarvis" },
  };
}

describe("platform-agent fork guard (HelixExtension pre_save hook)", () => {
  function makeKernel(): { k: Kernel; src: any } {
    const k = new Kernel();
    k.load(new HelixExtension());
    const src = fakeSource();
    k.source(src);
    k.writableSource(src);
    return { k, src };
  }

  it("blocks a per-tenant overlay of a _lib Agent", async () => {
    const { k, src } = makeKernel();
    await expect(
      k.writeDocument(DEFAULT_BASE_SCOPE, "Agent", "jarvis", uaRaw("jarvis"), {
        tenant: "acme",
      }),
    ).rejects.toThrow(TenantNotAllowed);
    expect(src.saveCalls).toEqual([]); // veto → nothing persisted
  });

  it("allows the base write of a _lib agent", async () => {
    const { k } = makeKernel();
    await k.writeDocument(DEFAULT_BASE_SCOPE, "Agent", "jarvis", uaRaw("jarvis"));
  });

  it("allows a tenant overlay of a non-_lib scope agent", async () => {
    const { k } = makeKernel();
    await k.writeDocument("acme-app", "Agent", "helper", uaRaw("helper"), {
      tenant: "acme",
    });
  });

  it("fires even with skipHooks (integrity gate, not notification)", async () => {
    const { k } = makeKernel();
    await expect(
      k.writeDocument(DEFAULT_BASE_SCOPE, "Agent", "jarvis", uaRaw("jarvis"), {
        tenant: "acme", skipHooks: true,
      }),
    ).rejects.toThrow(TenantNotAllowed);
  });
});
