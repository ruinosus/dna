/**
 * `emit` — DNA → DeepAgents emitter (code-first scaffold target; TS twin of
 * `test_emit_deepagents.py`, s-emit-deepagents).
 *
 * Pins case selection, the byte-equal invariant (INSTRUCTIONS is a PREFIX of the
 * effective system prompt), the PRESERVED model coordinate, and honest losses
 * (harness prompt / no name slot).
 */
import { describe, it, expect } from "bun:test";
import { join } from "node:path";

import { quickInstance } from "../src/bootstrap.js";
import { emitAgent, getEmitter, availableTargets, type EmitContext } from "../src/index.js";
import { DeepAgentsEmitter } from "../src/emit/deepagents.js";
import { ScaffoldEmitter } from "../src/emit/scaffold.js";

const ROOT = join(import.meta.dir, "..", "..", "..");
const BASE = join(ROOT, "examples", "emitting-to-a-runtime", ".dna");
const SCOPE = "concierge";
const AGENT = "concierge";

function ctxOf(partial: Partial<EmitContext>): EmitContext {
  return {
    name: "a",
    description: "",
    instructions: "x",
    model: null,
    tools: [],
    outputSchema: null,
    scope: null,
    options: {},
    ...partial,
  };
}

describe("deepagents scaffold emitter", () => {
  it("is registered as a ScaffoldEmitter", async () => {
    expect(await availableTargets()).toContain("deepagents");
    expect(await getEmitter("deepagents")).toBeInstanceOf(DeepAgentsEmitter);
    expect(new DeepAgentsEmitter()).toBeInstanceOf(ScaffoldEmitter);
  });

  it("with-tools: emitted INSTRUCTIONS equals buildPrompt", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const result = await emitAgent(mi, AGENT, "deepagents"); // concierge has a tool
    expect(result.filename).toBe("concierge.py");
    expect(result.artifact).toContain("from deepagents import create_deep_agent");
    expect(result.artifact).toContain("def kb_search()");
    expect(result.artifact).toContain("system_prompt=INSTRUCTIONS");
    expect(result.artifact).toContain("tools=[kb_search]");
    const emitter = await getEmitter("deepagents");
    expect(emitter.extractInstructions(result.artifact)).toBe(await mi.buildPrompt({ agent: AGENT }));
  });

  it("prompt-only: no tools, model coordinate PRESERVED", () => {
    const emitter = new DeepAgentsEmitter();
    const result = emitter.emit(ctxOf({ name: "greeter", instructions: "Be brief.\nSay hi.", model: "anthropic:claude-sonnet-4" }));
    expect(result.artifact).toContain("tools=[]");
    expect(result.artifact).toContain("model=\"anthropic:claude-sonnet-4\"");
    expect(emitter.extractInstructions(result.artifact)).toBe("Be brief.\nSay hi.");
  });

  it("reports the harness prompt + missing name slot as losses", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const result = await emitAgent(mi, AGENT, "deepagents");
    expect(result.losses.some((l) => l.includes("harness prompt"))).toBe(true);
    expect(result.losses.some((l) => l.includes("metadata.name"))).toBe(true);
  });

  it("unbound model omits model= and falls back to the default", () => {
    const result = new DeepAgentsEmitter().emit(ctxOf({ model: null }));
    expect(result.artifact).not.toContain("model=");
    expect(result.losses.some((l) => l.includes("model unbound") && l.includes("default deep-agent model"))).toBe(true);
  });
});
