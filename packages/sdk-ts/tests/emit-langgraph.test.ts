/**
 * `emit` — DNA → LangGraph emitter (code-first scaffold target; TS twin of
 * `test_emit_langgraph.py`, s-emit-langgraph).
 *
 * Pins case selection, the byte-equal invariant, the PRESERVED model coordinate
 * (LangGraph resolves it via `init_chat_model`), and honest losses.
 */
import { describe, it, expect } from "bun:test";
import { join } from "node:path";

import { quickInstance } from "../src/bootstrap.js";
import { emitAgent, getEmitter, availableTargets, type EmitContext } from "../src/index.js";
import { LanggraphEmitter } from "../src/emit/langgraph.js";
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

describe("langgraph scaffold emitter", () => {
  it("is registered as a ScaffoldEmitter", async () => {
    expect(await availableTargets()).toContain("langgraph");
    expect(await getEmitter("langgraph")).toBeInstanceOf(LanggraphEmitter);
    expect(new LanggraphEmitter()).toBeInstanceOf(ScaffoldEmitter);
  });

  it("with-tools: emitted INSTRUCTIONS equals buildPrompt", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const result = await emitAgent(mi, AGENT, "langgraph"); // concierge has a tool
    expect(result.filename).toBe("concierge.py");
    expect(result.artifact).toContain("from langgraph.prebuilt import create_react_agent");
    expect(result.artifact).toContain("from langchain_core.tools import tool");
    expect(result.artifact).toContain("@tool");
    expect(result.artifact).toContain("def kb_search()");
    expect(result.artifact).toContain("prompt=INSTRUCTIONS");
    const emitter = await getEmitter("langgraph");
    expect(emitter.extractInstructions(result.artifact)).toBe(await mi.buildPrompt({ agent: AGENT }));
  });

  it("prompt-only: no tools, model coordinate PRESERVED", () => {
    const emitter = new LanggraphEmitter();
    const result = emitter.emit(ctxOf({ name: "greeter", instructions: "Be brief.\nSay hi.", model: "openai:gpt-4o" }));
    expect(result.artifact).not.toContain("@tool");
    expect(result.artifact).toContain("tools=[]");
    expect(result.artifact).toContain("model=\"openai:gpt-4o\"");
    expect(emitter.extractInstructions(result.artifact)).toBe("Be brief.\nSay hi.");
  });

  it("reports the tool body + model coordinate as losses", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const result = await emitAgent(mi, AGENT, "langgraph");
    expect(result.losses.some((l) => l.includes("tool body"))).toBe(true);
    expect(result.losses.some((l) => l.includes("model coordinate"))).toBe(true);
  });

  it("unbound model omits model= and reports it is required", () => {
    const result = new LanggraphEmitter().emit(ctxOf({ model: null }));
    expect(result.artifact).not.toContain("model=");
    expect(result.losses.some((l) => l.includes("model unbound") && l.includes("REQUIRES a model"))).toBe(true);
  });
});
