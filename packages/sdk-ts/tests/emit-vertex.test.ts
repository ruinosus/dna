/**
 * `emit` — DNA → Google ADK Agent Config emitter (TS twin of
 * `test_emit_vertex.py`). The portability proof's THIRD runtime, cross-language:
 * the SAME concierge DNA source that emits a Microsoft agent-framework PromptAgent
 * and an AWS CloudFormation `AWS::Bedrock::Agent` also emits a Google ADK Agent
 * Config YAML (an `LlmAgent`).
 *
 * Pins the same claims as the Python twin (over the SAME example scope):
 *   1. byte-equal gate — emitted `instruction` == `mi.buildPrompt({agent})`, and
 *      identical across all three runtimes.
 *   2. structural de-para — agent_class/name/description/model/instruction/tools.
 *   3. credential-free structural validation against the documented schema.
 *   4. pluggable registry — vertex registered additively.
 *   5. honest losses.
 * Parity contract is the emitted OBJECT (toAgentConfig); the composed `instruction`
 * comes from buildPrompt (a separate subsystem) and is only asserted per-language.
 */
import { describe, it, expect } from "bun:test";
import { join } from "node:path";
import yaml from "js-yaml";

import { quickInstance } from "../src/bootstrap.js";
import {
  emitAgent,
  buildEmitContext,
  availableTargets,
  getEmitter,
  EmitError,
  type EmitContext,
} from "../src/index.js";
import {
  VertexEmitter,
  snake,
  vertexModelId,
  isGemini,
} from "../src/emit/vertex.js";

const ROOT = join(import.meta.dir, "..", "..", "..");
const BASE = join(ROOT, "examples", "emitting-to-a-runtime", ".dna");
const SCOPE = "concierge";
const AGENT = "concierge";

const IDENT = /^[A-Za-z_][A-Za-z0-9_]*$/;
const SCHEMA_HEADER =
  "# yaml-language-server: $schema=https://raw.githubusercontent.com/google/adk-python";

async function config(opts?: { model?: string | null }): Promise<any> {
  const mi = await quickInstance(SCOPE, BASE);
  return yaml.load((await emitAgent(mi, AGENT, "vertex", opts)).artifact);
}

// ── 1. the byte-equal gate (and the 3-runtime identity) ─────────────────────

describe("byte-equal gate", () => {
  it("emitted instruction equals the DNA-composed prompt", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const c: any = yaml.load((await emitAgent(mi, AGENT, "vertex")).artifact);
    expect(c.instruction).toBe(await mi.buildPrompt({ agent: AGENT }));
  });

  it("instruction is identical across agent-framework, bedrock, and vertex", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const composed = await mi.buildPrompt({ agent: AGENT });
    const af: any = yaml.load((await emitAgent(mi, AGENT, "agent-framework")).artifact);
    const bd = JSON.parse((await emitAgent(mi, AGENT, "bedrock")).artifact);
    const vx: any = yaml.load((await emitAgent(mi, AGENT, "vertex")).artifact);
    const bdInstruction = bd.Resources.ConciergeAgent.Properties.Instruction;
    expect(af.instructions).toBe(composed);
    expect(bdInstruction).toBe(composed);
    expect(vx.instruction).toBe(composed);
  });
});

// ── 2. the structural de-para ──────────────────────────────────────────────

describe("structural de-para", () => {
  it("maps the Agent Config fields", async () => {
    const c = await config();
    expect(c.agent_class).toBe("LlmAgent");
    expect(c.name).toBe("concierge");
    expect(c.description).toContain("concierge grounded in runbooks");
    expect(c.model).toBe("gpt-4o"); // azure/gpt-4o → provider stripped
    expect(Object.keys(c)).toEqual([
      "agent_class", "name", "description", "model", "instruction", "tools",
    ]);
  });

  it("leads with the yaml-language-server schema header", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const artifact = (await emitAgent(mi, AGENT, "vertex")).artifact;
    const header = artifact.split("\n")[0]!;
    expect(header.startsWith(SCHEMA_HEADER)).toBe(true);
    expect(header.endsWith("AgentConfig.json")).toBe(true);
  });

  it("maps tools as name-only code references", async () => {
    const c = await config();
    expect(c.tools).toEqual([{ name: "kb-search" }]);
  });

  it("model override: bare Gemini passes through, known provider token stripped", async () => {
    expect((await config({ model: "gemini-2.0-flash" })).model).toBe("gemini-2.0-flash");
    expect((await config({ model: "vertex/gemini-1.5-pro" })).model).toBe("gemini-1.5-pro");
    expect((await config({ model: "google:gemini-2.5-flash" })).model).toBe("gemini-2.5-flash");
  });
});

// ── 3. credential-free structural validation ───────────────────────────────

describe("schema conformance (no GCP call)", () => {
  it("conforms to the documented ADK LlmAgentConfig schema", async () => {
    const c = await config();
    expect(c.name).toMatch(IDENT); // ADK: name must be a valid Python identifier
    expect(c.agent_class).toBe("LlmAgent");
    expect(typeof c.instruction).toBe("string");
    expect(c.instruction.length).toBeGreaterThan(0);
    for (const entry of c.tools ?? []) {
      expect(Object.keys(entry)).toEqual(["name"]);
      expect(typeof entry.name).toBe("string");
    }
  });
});

// ── pure helpers + parity of the emitted object ────────────────────────────

describe("pure mapping", () => {
  it("snake-cases the slug to a valid identifier", () => {
    expect(snake("concierge-grounded")).toBe("concierge_grounded");
    expect(snake("KB Search Bot")).toBe("kb_search_bot");
    expect(snake("2fast")).toBe("_2fast");
    expect(snake("concierge-grounded")).toMatch(IDENT);
  });

  it("projects the ADK model id", () => {
    expect(vertexModelId("azure/gpt-4o")).toBe("gpt-4o");
    expect(vertexModelId("vertex/gemini-2.0-flash")).toBe("gemini-2.0-flash");
    expect(vertexModelId("openai:gpt-4o-mini")).toBe("gpt-4o-mini");
    expect(vertexModelId("gemini-1.5-pro")).toBe("gemini-1.5-pro");
    expect(vertexModelId("some-registry/model-x")).toBe("some-registry/model-x");
    expect(vertexModelId(null)).toBeNull();
  });

  it("detects native Gemini ids", () => {
    expect(isGemini("gemini-2.0-flash")).toBe(true);
    expect(isGemini("gpt-4o")).toBe(false);
    expect(isGemini(null)).toBe(false);
  });

  it("toAgentConfig produces the parity object the Python twin asserts", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const ctx = await buildEmitContext(mi, AGENT);
    const c = new VertexEmitter().toAgentConfig(ctx) as any;
    expect(Object.keys(c)).toEqual([
      "agent_class", "name", "description", "model", "instruction", "tools",
    ]);
    expect(c.instruction).toBe(await mi.buildPrompt({ agent: AGENT }));
    expect(c.tools).toEqual([{ name: "kb-search" }]);
  });
});

// ── 4. the pluggable registry ──────────────────────────────────────────────

describe("registry", () => {
  it("has vertex registered", async () => {
    expect(await availableTargets()).toContain("vertex");
    expect(await getEmitter("vertex")).toBeInstanceOf(VertexEmitter);
  });
});

// ── 5. honest losses ───────────────────────────────────────────────────────

describe("losses", () => {
  it("reports the DNA axes with no Agent Config slot", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const joined = (await emitAgent(mi, AGENT, "vertex")).losses.join(" ");
    expect(joined).toContain("composition structure");
    expect(joined).toContain("tenant overlay");
    expect(joined).toContain("eval-as-contract");
    expect(joined).toContain("tool binding");
    expect(joined).toContain("model coordinate");
  });

  it("reports the unbound-model loss and omits model/tools", () => {
    const ctx: EmitContext = {
      name: "bare", description: "", instructions: "x".repeat(40),
      model: null, tools: [], outputSchema: null, scope: null, options: {},
    };
    const result = new VertexEmitter().emit(ctx);
    const c: any = yaml.load(result.artifact);
    expect(c.model).toBeUndefined();
    expect(c.tools).toBeUndefined();
    const joined = result.losses.join(" ");
    expect(joined).toContain("model unbound");
    expect(joined).not.toContain("tool binding");
  });

  it("a native Gemini id reports no model-coordinate loss", () => {
    const ctx: EmitContext = {
      name: "g", description: "", instructions: "x".repeat(40),
      model: "gemini-2.0-flash", tools: [], outputSchema: null, scope: null, options: {},
    };
    const joined = new VertexEmitter().emit(ctx).losses.join(" ");
    expect(joined).not.toContain("model coordinate");
    expect(joined).not.toContain("model unbound");
  });

  it("reports output_schema as a loss", () => {
    const ctx: EmitContext = {
      name: "o", description: "", instructions: "x".repeat(40), model: "gemini-2.0-flash",
      tools: [], outputSchema: { type: "object" }, scope: null, options: {},
    };
    expect(new VertexEmitter().emit(ctx).losses.join(" ")).toContain("output_schema");
  });

  it("fails loud on a missing agent", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    let err: unknown;
    try {
      await buildEmitContext(mi, "does-not-exist");
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(EmitError);
  });
});
