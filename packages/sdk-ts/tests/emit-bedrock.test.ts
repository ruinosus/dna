/**
 * `emit` — DNA → Amazon Bedrock Agent emitter (TS twin of
 * `test_emit_bedrock.py`). The portability proof's SECOND runtime, cross-language:
 * the SAME concierge DNA source that emits a Microsoft agent-framework PromptAgent
 * also emits an AWS CloudFormation `AWS::Bedrock::Agent` template.
 *
 * Pins the same claims as the Python twin (over the SAME example scope):
 *   1. byte-equal gate — emitted `Instruction` == `mi.buildPrompt({agent})`.
 *   2. structural de-para — name→AgentName, model→FoundationModel, tools→FunctionSchema.
 *   3. credential-free structural validation against the documented schema.
 *   4. pluggable registry — bedrock registered additively.
 *   5. honest losses.
 * Parity contract is the emitted OBJECT (toTemplate); the composed `Instruction`
 * comes from buildPrompt (a separate subsystem) and is only asserted per-language.
 */
import { describe, it, expect } from "bun:test";
import { join } from "node:path";

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
  BedrockEmitter,
  camel,
  bedrockModelId,
  emitParameters,
} from "../src/emit/bedrock.js";

const ROOT = join(import.meta.dir, "..", "..", "..");
const BASE = join(ROOT, "examples", "emitting-to-a-runtime", ".dna");
const SCOPE = "concierge";
const AGENT = "concierge";

const NAME_PATTERN = /^([0-9a-zA-Z][_-]?){1,100}$/;
const PARAM_TYPES = new Set(["string", "number", "integer", "boolean", "array"]);

async function template(opts?: { model?: string | null }): Promise<any> {
  const mi = await quickInstance(SCOPE, BASE);
  return JSON.parse((await emitAgent(mi, AGENT, "bedrock", opts)).artifact);
}
function props(t: any): any {
  return Object.values(t.Resources)[0]!.Properties;
}

// ── 1. the byte-equal gate ────────────────────────────────────────────────

describe("byte-equal gate", () => {
  it("emitted Instruction equals the DNA-composed prompt", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const t = JSON.parse((await emitAgent(mi, AGENT, "bedrock")).artifact);
    expect(props(t).Instruction).toBe(await mi.buildPrompt({ agent: AGENT }));
  });
});

// ── 2. the structural de-para ──────────────────────────────────────────────

describe("structural de-para", () => {
  it("maps the CloudFormation envelope", async () => {
    const t = await template();
    expect(t.AWSTemplateFormatVersion).toBe("2010-09-09");
    const [logicalId] = Object.keys(t.Resources);
    expect(logicalId).toBe("ConciergeAgent");
    expect(t.Resources[logicalId].Type).toBe("AWS::Bedrock::Agent");
  });

  it("maps the agent properties", async () => {
    const p = props(await template());
    expect(p.AgentName).toBe("concierge");
    expect(p.Description).toContain("concierge grounded in runbooks");
    expect(p.FoundationModel).toBe("gpt-4o"); // azure/gpt-4o → provider stripped
    expect(p.AutoPrepare).toBe(true);
    expect(Object.keys(p)).toEqual([
      "AgentName", "Description", "FoundationModel", "Instruction", "ActionGroups", "AutoPrepare",
    ]);
  });

  it("maps tools as a FunctionSchema action group", async () => {
    const p = props(await template());
    expect(p.ActionGroups).toHaveLength(1);
    const group = p.ActionGroups[0];
    expect(group.ActionGroupName).toBe("concierge-actions");
    expect(group.ActionGroupExecutor).toEqual({ CustomControl: "RETURN_CONTROL" });
    const fns = group.FunctionSchema.Functions;
    expect(fns).toHaveLength(1);
    expect(fns[0].Name).toBe("kb-search");
    expect(fns[0].Parameters.query.Type).toBe("string");
    expect(fns[0].Parameters.query.Required).toBe(true);
    expect(fns[0].Parameters.top_k.Type).toBe("integer");
    expect(fns[0].Parameters.top_k.Required).toBe(false);
  });

  it("model override: bedrock-native id + ARN pass through, slash coord stripped", async () => {
    expect(props(await template({ model: "anthropic.claude-3-5-sonnet-20240620-v1:0" })).FoundationModel)
      .toBe("anthropic.claude-3-5-sonnet-20240620-v1:0");
    expect(props(await template({ model: "bedrock/anthropic.claude-v2" })).FoundationModel)
      .toBe("anthropic.claude-v2");
    const arn = "arn:aws:bedrock:us-east-1:1:inference-profile/us.anthropic.claude-v2";
    expect(props(await template({ model: arn })).FoundationModel).toBe(arn);
  });
});

// ── 3. credential-free structural validation ───────────────────────────────

describe("schema conformance (no AWS call)", () => {
  it("conforms to the documented AWS::Bedrock::Agent schema", async () => {
    const t = await template();
    expect(Object.keys(t)).toContain("Resources");
    const p = props(t);
    expect(p.AgentName).toMatch(NAME_PATTERN);
    expect(p.Instruction.length).toBeGreaterThanOrEqual(40);
    for (const group of p.ActionGroups ?? []) {
      expect(group.ActionGroupName).toMatch(NAME_PATTERN);
      expect(Object.keys(group.ActionGroupExecutor).every((k) => ["Lambda", "CustomControl"].includes(k))).toBe(true);
      for (const fn of group.FunctionSchema.Functions) {
        expect(fn.Name).toMatch(NAME_PATTERN);
        for (const detail of Object.values(fn.Parameters ?? {}) as any[]) {
          expect(PARAM_TYPES.has(detail.Type)).toBe(true);
          expect(typeof detail.Required).toBe("boolean");
        }
      }
    }
  });
});

// ── pure helpers + parity of the emitted object ────────────────────────────

describe("pure mapping", () => {
  it("camel-cases the slug", () => {
    expect(camel("concierge-grounded")).toBe("ConciergeGrounded");
    expect(camel("kb_search_bot")).toBe("KbSearchBot");
  });

  it("projects the Bedrock model id", () => {
    expect(bedrockModelId("azure/gpt-4o")).toBe("gpt-4o");
    expect(bedrockModelId("openai:gpt-4o-mini")).toBe("gpt-4o-mini");
    expect(bedrockModelId("anthropic.claude-v2")).toBe("anthropic.claude-v2");
    expect(bedrockModelId("anthropic.claude-3-v1:0")).toBe("anthropic.claude-3-v1:0");
    expect(bedrockModelId("arn:aws:bedrock:x:1:foundation-model/y")).toBe("arn:aws:bedrock:x:1:foundation-model/y");
    expect(bedrockModelId(null)).toBeNull();
  });

  it("flattens unsupported parameter types to string + flags it", () => {
    const { params, coerced } = emitParameters({
      type: "object",
      required: ["a"],
      properties: { a: { type: "string", description: "kept" }, b: { type: "object" } },
    });
    expect(coerced).toBe(true);
    expect(params.a).toEqual({ Type: "string", Description: "kept", Required: true });
    expect(params.b).toEqual({ Type: "string", Required: false });
  });

  it("toTemplate produces the parity object the Python twin asserts", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const ctx = await buildEmitContext(mi, AGENT);
    const t = new BedrockEmitter().toTemplate(ctx) as any;
    expect(Object.keys(t)).toEqual(["AWSTemplateFormatVersion", "Description", "Resources"]);
    const p = t.Resources.ConciergeAgent.Properties;
    expect(Object.keys(p)).toEqual([
      "AgentName", "Description", "FoundationModel", "Instruction", "ActionGroups", "AutoPrepare",
    ]);
    expect(p.Instruction).toBe(await mi.buildPrompt({ agent: AGENT }));
  });
});

// ── 4. the pluggable registry ──────────────────────────────────────────────

describe("registry", () => {
  it("has bedrock registered", async () => {
    expect(await availableTargets()).toContain("bedrock");
    expect(await getEmitter("bedrock")).toBeInstanceOf(BedrockEmitter);
  });
});

// ── 5. honest losses ───────────────────────────────────────────────────────

describe("losses", () => {
  it("reports the DNA axes with no Bedrock slot", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const joined = (await emitAgent(mi, AGENT, "bedrock")).losses.join(" ");
    expect(joined).toContain("composition structure");
    expect(joined).toContain("tenant overlay");
    expect(joined).toContain("eval-as-contract");
    expect(joined).toContain("tool parameter depth");
    expect(joined).toContain("model coordinate");
  });

  it("reports the unbound-model loss and omits FoundationModel/ActionGroups", () => {
    const ctx: EmitContext = {
      name: "bare", description: "", instructions: "x".repeat(40),
      model: null, tools: [], outputSchema: null, scope: null, options: {}, mcpServers: [], toolsRequiringConfirmation: new Set<string>(), tenantPropagate: false, knowledge: [],
    };
    const result = new BedrockEmitter().emit(ctx);
    const p = props(JSON.parse(result.artifact));
    expect(p.FoundationModel).toBeUndefined();
    expect(p.ActionGroups).toBeUndefined();
    const joined = result.losses.join(" ");
    expect(joined).toContain("model unbound");
    expect(joined).not.toContain("tool parameter depth");
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
