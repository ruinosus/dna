/**
 * `emit` — DNA → Microsoft agent-framework emitter (TS twin of
 * `test_emit_agent_framework.py`). The pivot's first proof, cross-language:
 * DNA authors an agent ONCE and MATERIALIZES the runtime's native artifact.
 *
 * Pins the same claims as the Python twin (over the SAME example scope):
 *   1. byte-equal gate — emitted `instructions` == `mi.buildPrompt({agent})`.
 *   2. structural de-para — name→CamelCase, model→{id,provider}, tools→kind:function.
 *   3. pluggable registry — availableTargets / UnknownTarget / registerEmitter.
 *   4. honest losses.
 * Parity contract is the emitted OBJECT (toPromptAgent), not the YAML bytes
 * (js-yaml and PyYAML render differently — a rendering detail, not the de-para).
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
  registerEmitter,
  UnknownTarget,
  EmitError,
  type EmitContext,
} from "../src/index.js";
import { AgentFrameworkEmitter, camel, splitModel } from "../src/emit/agentFramework.js";

const ROOT = join(import.meta.dir, "..", "..", "..");
const BASE = join(ROOT, "examples", "emitting-to-a-runtime", ".dna");
const SCOPE = "concierge";
const AGENT = "concierge";

// ── 1. the byte-equal gate ────────────────────────────────────────────────

describe("byte-equal gate", () => {
  it("emitted instructions equal the DNA-composed prompt", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const result = await emitAgent(mi, AGENT, "agent-framework");
    const doc = yaml.load(result.artifact) as Record<string, unknown>;
    expect(doc.instructions).toBe(await mi.buildPrompt({ agent: AGENT }));
  });
});

// ── 2. the structural de-para ──────────────────────────────────────────────

describe("structural de-para", () => {
  it("maps the PromptAgent envelope", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const doc = yaml.load((await emitAgent(mi, AGENT, "agent-framework")).artifact) as any;
    expect(doc.kind).toBe("Prompt");
    expect(doc.name).toBe("Concierge");
    expect(doc.description).toContain("concierge grounded in runbooks");
  });

  it("splits the model into {id, provider}", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const doc = yaml.load((await emitAgent(mi, AGENT, "agent-framework")).artifact) as any;
    expect(doc.model).toEqual({ id: "gpt-4o", provider: "AzureOpenAI" });
  });

  it("maps tools as kind:function with the input JSON Schema", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const doc = yaml.load((await emitAgent(mi, AGENT, "agent-framework")).artifact) as any;
    expect(doc.tools).toHaveLength(1);
    expect(doc.tools[0].name).toBe("kb-search");
    expect(doc.tools[0].kind).toBe("function");
    expect(doc.tools[0].parameters.required).toEqual(["query"]);
  });

  it("provider override wins", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const result = await emitAgent(mi, AGENT, "agent-framework", {
      model: "my-deploy",
      provider: "OpenAI",
    });
    const doc = yaml.load(result.artifact) as any;
    expect(doc.model).toEqual({ id: "my-deploy", provider: "OpenAI" });
  });
});

// ── pure helpers + Py↔TS parity of the object ──────────────────────────────

describe("pure mapping", () => {
  it("camel-cases the slug", () => {
    expect(camel("concierge-grounded")).toBe("ConciergeGrounded");
    expect(camel("kb_search_bot")).toBe("KbSearchBot");
  });

  it("splits model coordinates", () => {
    expect(splitModel("openai:gpt-4o-mini")).toEqual({ id: "gpt-4o-mini", provider: "OpenAI" });
    expect(splitModel("azure/gpt-4o")).toEqual({ id: "gpt-4o", provider: "AzureOpenAI" });
    expect(splitModel("gpt-4o")).toEqual({ id: "gpt-4o", provider: "AzureOpenAI" });
    expect(splitModel("gpt-4o", "OpenAI")).toEqual({ id: "gpt-4o", provider: "OpenAI" });
    expect(splitModel(null)).toBeNull();
  });

  it("toPromptAgent produces the parity object the Python twin asserts", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const ctx = await buildEmitContext(mi, AGENT);
    const doc = new AgentFrameworkEmitter().toPromptAgent(ctx);
    expect(Object.keys(doc)).toEqual(["kind", "name", "description", "model", "tools", "instructions"]);
    expect(doc.kind).toBe("Prompt");
    expect(doc.name).toBe("Concierge");
    expect(doc.model).toEqual({ id: "gpt-4o", provider: "AzureOpenAI" });
    expect(doc.instructions).toBe(await mi.buildPrompt({ agent: AGENT }));
  });
});

// ── 3. the pluggable registry ──────────────────────────────────────────────

describe("registry", () => {
  it("has agent-framework registered", async () => {
    expect(await availableTargets()).toContain("agent-framework");
    expect(await getEmitter("agent-framework")).toBeInstanceOf(AgentFrameworkEmitter);
  });

  it("throws UnknownTarget with the available list", async () => {
    let err: unknown;
    try {
      await getEmitter("no-such-runtime"); // agent-framework/bedrock/vertex all exist now
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(UnknownTarget);
    expect((err as UnknownTarget).available).toContain("agent-framework");
  });

  it("register a new target additively", async () => {
    class EchoEmitter {
      readonly target = "echo-test-ts";
      readonly fileExtension = "txt";
      emit(ctx: EmitContext) {
        return { artifact: ctx.instructions, target: this.target, filename: `${ctx.name}.txt`, losses: [], mapping: {} };
      }
    }
    registerEmitter(new EchoEmitter());
    expect(await availableTargets()).toContain("echo-test-ts");
  });
});

// ── 4. honest losses ───────────────────────────────────────────────────────

describe("losses", () => {
  it("reports the DNA axes with no target slot", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const result = await emitAgent(mi, AGENT, "agent-framework");
    const joined = result.losses.join(" ");
    expect(joined).toContain("composition structure");
    expect(joined).toContain("tenant overlay");
    expect(joined).toContain("eval-as-contract");
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
