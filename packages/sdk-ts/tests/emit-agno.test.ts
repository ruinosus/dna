/**
 * `emit` — DNA → Agno emitter (code-first scaffold target; TS twin of
 * `test_emit_agno.py`, s-emit-agno).
 *
 * Pins case selection, the byte-equal invariant, the PRESERVED model coordinate
 * (Agno takes a `provider:model` string), and honest losses.
 */
import { describe, it, expect } from "bun:test";
import { join } from "node:path";

import { quickInstance } from "../src/bootstrap.js";
import { emitAgent, getEmitter, availableTargets, type EmitContext } from "../src/index.js";
import { AgnoEmitter } from "../src/emit/agno.js";
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

describe("agno scaffold emitter", () => {
  it("is registered as a ScaffoldEmitter", async () => {
    expect(await availableTargets()).toContain("agno");
    expect(await getEmitter("agno")).toBeInstanceOf(AgnoEmitter);
    expect(new AgnoEmitter()).toBeInstanceOf(ScaffoldEmitter);
  });

  it("with-tools: emitted INSTRUCTIONS equals buildPrompt", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const result = await emitAgent(mi, AGENT, "agno"); // concierge has a tool
    expect(result.filename).toBe("concierge.py");
    expect(result.artifact).toContain("from agno.agent import Agent");
    expect(result.artifact).toContain("def kb_search()");
    expect(result.artifact).toContain("instructions=INSTRUCTIONS");
    expect(result.artifact).toContain("tools=[kb_search]");
    expect(result.artifact).toContain("name=\"concierge\"");
    const emitter = await getEmitter("agno");
    expect(emitter.extractInstructions(result.artifact)).toBe(await mi.buildPrompt({ agent: AGENT }));
  });

  it("prompt-only: no tools kwarg, model coordinate PRESERVED", () => {
    const emitter = new AgnoEmitter();
    const result = emitter.emit(ctxOf({ name: "greeter", instructions: "Be brief.\nSay hi.", model: "openai:gpt-4o" }));
    expect(result.artifact).not.toContain("tools=");
    expect(result.artifact).toContain("model=\"openai:gpt-4o\"");
    expect(emitter.extractInstructions(result.artifact)).toBe("Be brief.\nSay hi.");
  });

  it("reports the tool body as a loss", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const result = await emitAgent(mi, AGENT, "agno");
    expect(result.losses.some((l) => l.includes("tool body"))).toBe(true);
  });
});
