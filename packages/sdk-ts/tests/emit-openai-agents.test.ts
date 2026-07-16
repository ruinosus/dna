/**
 * `emit` — DNA → OpenAI Agents SDK emitter (the first CODE-FIRST target; TS twin
 * of `test_emit_openai_agents.py`, s-emit-port-contract).
 *
 * The scaffold flavor: a code-first runtime has no declarative agent format, so
 * the emitter fills a curated `{framework × case}` template. Pins:
 *   1. case selection — `selectScaffold` routes from ctx signals (tools →
 *      with-tools; none → prompt-only). Selection + fill, never codegen.
 *   2. byte-equal invariant — the emitted `INSTRUCTIONS` constant equals
 *      buildPrompt (recovered via the contract's `extractInstructions`), both cases.
 *   3. honest losses — tool bodies are stubs; the DNA-only axes have no slot.
 */
import { describe, it, expect } from "bun:test";
import { join } from "node:path";

import { quickInstance } from "../src/bootstrap.js";
import { emitAgent, getEmitter, availableTargets, type EmitContext } from "../src/index.js";
import { OpenAIAgentsEmitter, bareModelId } from "../src/emit/openaiAgents.js";
import {
  selectScaffold,
  classifyCase,
  ScaffoldEmitter,
  resolveScaffold,
  setScaffoldResolver,
  PackageDataScaffoldResolver,
  type ScaffoldResolver,
} from "../src/emit/scaffold.js";

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
    mcpServers: [],
    toolsRequiringConfirmation: new Set<string>(),
    tenantPropagate: false,
    knowledge: [],
    ...partial,
  };
}

// ── 1. case selection ───────────────────────────────────────────────────────

describe("scaffold case selection", () => {
  it("classifies the case from DNA signals", () => {
    expect(classifyCase(ctxOf({}))).toBe("prompt-only");
    expect(classifyCase(ctxOf({ tools: [{ name: "t", description: "d", parameters: {} }] }))).toBe(
      "with-tools",
    );
    expect(classifyCase(ctxOf({ outputSchema: { type: "object" } }))).toBe("structured-output");
  });

  it("picks with-tools when tools are present", () => {
    const choice = selectScaffold(
      "openai-agents",
      ctxOf({ tools: [{ name: "t", description: "d", parameters: {} }] }),
    );
    expect(choice.case).toBe("with-tools");
    expect(choice.template).toContain("function_tool");
  });

  it("picks prompt-only without tools", () => {
    const choice = selectScaffold("openai-agents", ctxOf({}));
    expect(choice.case).toBe("prompt-only");
    expect(choice.template).not.toContain("function_tool");
  });

  it("structured-output falls back and records a loss", () => {
    const ctx = ctxOf({
      tools: [{ name: "t", description: "d", parameters: {} }],
      outputSchema: { type: "object" },
    });
    const choice = selectScaffold("openai-agents", ctx);
    expect(choice.requested).toBe("structured-output");
    expect(choice.case).toBe("with-tools");
    const result = new OpenAIAgentsEmitter().emit(ctx);
    expect(result.losses.some((l) => l.includes("scaffold case"))).toBe(true);
  });
});

// ── 2. byte-equal invariant, both cases ─────────────────────────────────────

describe("scaffold byte-equal invariant", () => {
  it("with-tools: emitted INSTRUCTIONS equals buildPrompt", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const result = await emitAgent(mi, AGENT, "openai-agents"); // concierge has a tool
    expect(result.filename).toBe("concierge.py");
    expect(result.artifact).toContain("from agents import Agent, function_tool");
    expect(result.artifact).toContain("def kb_search()");
    const emitter = await getEmitter("openai-agents");
    expect(emitter.extractInstructions(result.artifact)).toBe(await mi.buildPrompt({ agent: AGENT }));
  });

  it("prompt-only: emitted INSTRUCTIONS equals the context prompt", () => {
    const emitter = new OpenAIAgentsEmitter();
    const result = emitter.emit(ctxOf({ name: "greeter", instructions: "Be brief.\nSay hi.", model: "openai:gpt-4o" }));
    expect(result.artifact).not.toContain("function_tool");
    expect(result.artifact).toContain('model="gpt-4o"');
    expect(emitter.extractInstructions(result.artifact)).toBe("Be brief.\nSay hi.");
  });
});

// ── 3. registry + losses + helpers ──────────────────────────────────────────

describe("scaffold registry + losses", () => {
  it("openai-agents is registered", async () => {
    expect(await availableTargets()).toContain("openai-agents");
    expect(await getEmitter("openai-agents")).toBeInstanceOf(OpenAIAgentsEmitter);
    expect(new OpenAIAgentsEmitter()).toBeInstanceOf(ScaffoldEmitter);
  });

  it("reports the tool body as a loss", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const result = await emitAgent(mi, AGENT, "openai-agents");
    expect(result.losses.some((l) => l.includes("tool body"))).toBe(true);
  });

  it("strips DNA provider tokens from the model id", () => {
    expect(bareModelId("openai:gpt-4o")).toBe("gpt-4o");
    expect(bareModelId("azure/gpt-4o")).toBe("gpt-4o");
    expect(bareModelId("gpt-4o")).toBe("gpt-4o");
    expect(bareModelId(null)).toBeNull();
  });
});

// ── the resolution seam (package-data today; Scaffold Kind tomorrow) ─────────

describe("scaffold resolution seam", () => {
  it("the default resolver reads package-data", () => {
    expect(new PackageDataScaffoldResolver()).toBeInstanceOf(PackageDataScaffoldResolver);
    const tmpl = resolveScaffold("openai-agents", "prompt-only");
    expect(tmpl).toContain("from agents import Agent");
    expect(resolveScaffold("openai-agents", "does-not-exist")).toBeNull();
  });

  it("a custom resolver plugs in without touching the emitter", () => {
    const inMemory: ScaffoldResolver = {
      resolve(framework, kase) {
        return framework === "openai-agents" && kase === "prompt-only"
          ? "from agents import Agent\n\nINSTRUCTIONS = {{{instructions_literal}}}\n"
          : null;
      },
    };
    const restore = new PackageDataScaffoldResolver();
    try {
      setScaffoldResolver(inMemory);
      const result = new OpenAIAgentsEmitter().emit(ctxOf({ instructions: "hi" }));
      expect(result.artifact).toContain("INSTRUCTIONS =");
      expect(new OpenAIAgentsEmitter().extractInstructions(result.artifact)).toBe("hi");
    } finally {
      setScaffoldResolver(restore);
    }
  });
});
