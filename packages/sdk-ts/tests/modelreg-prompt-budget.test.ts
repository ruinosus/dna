// s-tier-a-modelprofile — ModelProfile Kind + prompt-budget write guard.
// TS twin of tests/test_modelreg_prompt_budget.py (+ the estimator units
// from tests/test_prompt_budget.py).
//
// Never hardcode token caps: every cap below lives in a ModelProfile DOC
// (the registry the guard reads through kernel.modelProfile), never in a
// literal in the production code.
import { describe, it, expect, beforeEach, afterEach } from "bun:test";
import { Kernel } from "../src/kernel/index.js";
import { TenantScope } from "../src/kernel/protocols.js";
import {
  estimateTokens,
  evaluateInstructionBudget,
  PromptBudgetExceededError,
} from "../src/kernel/prompt-budget.js";
import { HelixExtension } from "../src/extensions/helix.js";
import { ModelRegExtension } from "../src/extensions/modelreg.js";

// ---------------------------------------------------------------------------
// Estimator units (twin of tests/test_prompt_budget.py)
// ---------------------------------------------------------------------------

describe("prompt-budget estimator", () => {
  it("over-counts (60488 chars >= the real 17269 tokens)", () => {
    expect(estimateTokens(60488)).toBeGreaterThanOrEqual(17269);
  });

  it("under cap → not exceeded", () => {
    const v = evaluateInstructionBudget("short", { cap: 16384 });
    expect(v.exceeded).toBe(false);
  });

  it("over cap → exceeded with estimate", () => {
    const v = evaluateInstructionBudget("x".repeat(80000), { cap: 16384 });
    expect(v.exceeded).toBe(true);
    expect(v.estimatedTokens).toBeGreaterThan(16384);
  });

  it("error carries didactic context", () => {
    const e = new PromptBudgetExceededError({
      modelId: "gpt-realtime-2",
      estimatedTokens: 17269,
      cap: 16384,
      agentName: "talker",
    });
    expect(e.message).toContain("talker");
    expect(e.message).toContain("16384");
    expect(e.message).toContain("never hardcode caps");
  });
});

// ---------------------------------------------------------------------------
// Kind registration (descriptor) + registry resolution
// ---------------------------------------------------------------------------

describe("ModelProfile Kind (descriptor)", () => {
  it("registers from kinds/model-profile.kind.yaml", () => {
    const k = new Kernel();
    k.load(new ModelRegExtension());
    const kp = k.kindPortFor("ModelProfile");
    expect(kp).not.toBeNull();
    // Generated-convention alias (<owner>-<kebab(kind)>) declared verbatim
    // in the descriptor — the explicit-alias class ratchet is untouched.
    expect(kp!.alias).toBe("modelreg-model-profile");
    expect((kp as any).plane).toBe("record");
    // GLOBAL — a shared base registry, no per-tenant override.
    expect((kp as any).scope).toBe(TenantScope.GLOBAL);
    expect(kp!.storage.container).toBe("model-profiles");
  });
});

// ---------------------------------------------------------------------------
// Guard paths through the REAL kernel write path. The fake source serves
// ModelProfile docs for the `_lib` scope (kernel.modelProfile resolves them
// for real) and records persists.
// ---------------------------------------------------------------------------

function profileRaw(
  name: string,
  opts: { realtime: boolean; cap?: number | null; aliases?: string[] },
) {
  return {
    apiVersion: "github.com/ruinosus/dna/modelreg/v1",
    kind: "ModelProfile",
    metadata: { name },
    spec: {
      model_id: name,
      provider: "test",
      realtime: opts.realtime,
      context_window: 32768,
      instruction_token_cap: opts.cap === undefined ? 100 : opts.cap,
      aliases: opts.aliases ?? [],
    },
  };
}

function agentRaw(name: string, spec: Record<string, unknown>) {
  return {
    apiVersion: "github.com/ruinosus/dna/v1",
    kind: "Agent",
    metadata: { name },
    spec,
  };
}

const OVER_CAP = "x".repeat(1000); // ~286 tokens at chars/3.5 — over cap 100
const UNDER_CAP = "hi there";

function guardKernel(): { k: Kernel; saved: string[] } {
  const libDocs = [
    profileRaw("voice-strict", { realtime: true, aliases: ["voice-strict-preview"] }),
    profileRaw("chat-friendly", { realtime: false }),
  ];
  const saved: string[] = [];
  const src: any = {
    async saveDocument(_s: string, _k: string, name: string) {
      saved.push(name);
      return "v1";
    },
    async deleteDocument() {},
    async loadBootstrapDocs() { return []; },
    async loadDocument() { return null; },
    async loadAll(scope: string) { return scope === "_lib" ? libDocs : []; },
    async loadLayer() { return []; },
    async listVersions() { return []; },
    async listScopes() { return ["_lib"]; },
  };
  const k = new Kernel();
  k.load(new HelixExtension());
  k.load(new ModelRegExtension());
  k.source(src);
  k.writableSource(src);
  // instance() (which modelProfile rides) requires a cache port.
  k.cache({
    has: async () => false,
    store: async () => {},
    loadKey: async () => [],
    loadAll: async () => [],
  } as any);
  return { k, saved };
}

let envBefore: string | undefined;
beforeEach(() => {
  envBefore = process.env.DNA_PROMPT_BUDGET_ENFORCE;
  delete process.env.DNA_PROMPT_BUDGET_ENFORCE;
});
afterEach(() => {
  if (envBefore === undefined) delete process.env.DNA_PROMPT_BUDGET_ENFORCE;
  else process.env.DNA_PROMPT_BUDGET_ENFORCE = envBefore;
});

describe("prompt-budget guard — VETO path", () => {
  it("voice Agent over cap is vetoed, nothing persisted", async () => {
    const { k, saved } = guardKernel();
    await expect(
      k.writeDocument("proj", "Agent", "talker", agentRaw("talker", {
        instruction: OVER_CAP,
        voice_persona: { model: "voice-strict" },
      })),
    ).rejects.toThrow(PromptBudgetExceededError);
    expect(saved).not.toContain("talker");
  });

  it("chat Agent on a realtime profile is also strict", async () => {
    const { k, saved } = guardKernel();
    await expect(
      k.writeDocument("proj", "Agent", "sneaky", agentRaw("sneaky", {
        instruction: OVER_CAP,
        model: "voice-strict",
      })),
    ).rejects.toThrow(PromptBudgetExceededError);
    expect(saved).not.toContain("sneaky");
  });

  it("DNA_PROMPT_BUDGET_ENFORCE=0 downgrades the veto to a warn", async () => {
    process.env.DNA_PROMPT_BUDGET_ENFORCE = "0";
    const { k, saved } = guardKernel();
    await k.writeDocument("proj", "Agent", "talker", agentRaw("talker", {
      instruction: OVER_CAP,
      voice_persona: { model: "voice-strict" },
    }));
    expect(saved).toContain("talker");
  });
});

describe("prompt-budget guard — WARN path", () => {
  it("chat Agent over cap writes (over-budget tolerated but loud)", async () => {
    const { k, saved } = guardKernel();
    await k.writeDocument("proj", "Agent", "chatty", agentRaw("chatty", {
      instruction: OVER_CAP,
      model: "chat-friendly",
    }));
    expect(saved).toContain("chatty");
  });
});

describe("prompt-budget guard — PASS path", () => {
  it("Agent without a model passes untouched", async () => {
    const { k, saved } = guardKernel();
    await k.writeDocument("proj", "Agent", "plain",
      agentRaw("plain", { instruction: OVER_CAP }));
    expect(saved).toContain("plain");
  });

  it("chat Agent with an unregistered model passes (opt-in by data)", async () => {
    const { k, saved } = guardKernel();
    await k.writeDocument("proj", "Agent", "mystery",
      agentRaw("mystery", { instruction: OVER_CAP, model: "not-registered" }));
    expect(saved).toContain("mystery");
  });

  it("voice Agent under cap passes", async () => {
    const { k, saved } = guardKernel();
    await k.writeDocument("proj", "Agent", "brief", agentRaw("brief", {
      instruction: UNDER_CAP,
      voice_persona: { model: "voice-strict" },
    }));
    expect(saved).toContain("brief");
  });
});

describe("kernel.modelProfile registry resolution", () => {
  it("resolves by model_id then aliases[]", async () => {
    const { k } = guardKernel();
    const byId = await k.modelProfile("voice-strict");
    expect(byId).not.toBeNull();
    expect((byId!.spec as any).instruction_token_cap).toBe(100);
    const byAlias = await k.modelProfile("voice-strict-preview");
    expect(byAlias).not.toBeNull();
    expect((byAlias!.spec as any).model_id).toBe("voice-strict");
    expect(await k.modelProfile("no-such-model")).toBeNull();
  });
});

describe("kernel._DEFAULT_REALTIME_MODEL (parity with Python)", () => {
  it("falls back to the literal and reads the env at access time", () => {
    const before = process.env.DNA_VOICE_REALTIME_MODEL;
    delete process.env.DNA_VOICE_REALTIME_MODEL;
    try {
      const k = new Kernel();
      expect(k._DEFAULT_REALTIME_MODEL).toBe("gpt-realtime-2");
      process.env.DNA_VOICE_REALTIME_MODEL = "gpt-realtime-2-pinned";
      expect(k._DEFAULT_REALTIME_MODEL).toBe("gpt-realtime-2-pinned");
    } finally {
      if (before === undefined) delete process.env.DNA_VOICE_REALTIME_MODEL;
      else process.env.DNA_VOICE_REALTIME_MODEL = before;
    }
  });
});
