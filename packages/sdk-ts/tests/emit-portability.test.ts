/**
 * `emit` — the PORTABILITY proof: ONE DNA source → SEVEN runtimes, the composed
 * instruction byte-identical in every emitted artifact (TS twin of
 * `test_emit_portability.py`, s-emit-deepagents).
 *
 * DNA-as-Terraform made a test: author `concierge` ONCE and `dna emit` materializes
 * the native artifact for every registered runtime — three config-declarative
 * (agent-framework / bedrock / vertex) and four code-first scaffolds (openai-agents /
 * langgraph / agno / deepagents) — the DNA-composed prompt carried byte-equal in all.
 */
import { describe, it, expect } from "bun:test";
import { join } from "node:path";

import { quickInstance } from "../src/bootstrap.js";
import { emitAgent, getEmitter, availableTargets } from "../src/index.js";

const ROOT = join(import.meta.dir, "..", "..", "..");
const BASE = join(ROOT, "examples", "emitting-to-a-runtime", ".dna");
const SCOPE = "concierge";
const AGENT = "concierge";

/** The seven runtimes the one `concierge` source emits to. */
const SEVEN_RUNTIMES = [
  "agent-framework", // config-declarative — Microsoft PromptAgent YAML
  "bedrock", // config-declarative — AWS::Bedrock::Agent CloudFormation
  "vertex", // config-declarative — Google ADK Agent Config
  "openai-agents", // code-first scaffold — OpenAI Agents SDK
  "langgraph", // code-first scaffold — LangGraph create_react_agent
  "agno", // code-first scaffold — Agno Agent
  "deepagents", // code-first scaffold — LangChain DeepAgents
];

describe("portability — one source, seven runtimes", () => {
  it("all seven runtimes are registered", async () => {
    const targets = new Set(await availableTargets());
    for (const t of SEVEN_RUNTIMES) expect(targets.has(t)).toBe(true);
    expect(SEVEN_RUNTIMES.length).toBe(7);
  });

  it("the composed instruction is byte-identical across all seven artifacts", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const expected = await mi.buildPrompt({ agent: AGENT });
    const recovered: Record<string, string> = {};
    for (const target of SEVEN_RUNTIMES) {
      const result = await emitAgent(mi, AGENT, target);
      const emitter = await getEmitter(target);
      const got = emitter.extractInstructions(result.artifact);
      expect(got, `${target} carries no recoverable instruction`).not.toBeNull();
      recovered[target] = got as string;
    }
    for (const [target, got] of Object.entries(recovered)) {
      expect(got, `${target} instruction drifted from buildPrompt`).toBe(expected);
    }
    // one prompt, seven artifacts
    expect(new Set(Object.values(recovered)).size).toBe(1);
  });
});
