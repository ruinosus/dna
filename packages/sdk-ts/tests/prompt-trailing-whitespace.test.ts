/**
 * i-013 — trailing newline in bundle bodies must not leak into prompts.
 *
 * Twin of packages/sdk-py/tests/test_prompt_trailing_whitespace.py.
 *
 * A SOUL.md saved with a trailing newline (every editor re-adds one)
 * leaked `\n\n\n` into the composed prompt — the body's own trailing
 * newline stacked on the template's `\n\n` joiner. The strip lives ONLY
 * at the composition boundary (stripPromptBlock); storage stays
 * byte-faithful (rw conformance kit enforces WRITE round-trips).
 */

import { describe, expect, test } from "bun:test";

import { Document } from "../src/kernel/document.js";
import { ManifestInstance } from "../src/kernel/instance.js";
import { stripPromptBlock } from "../src/kernel/_text.js";
import type { KindPort } from "../src/kernel/protocols.js";

const AGENT_BODY = "# Pilot agent\n\nDo the pilot things.\n";
const SOUL_BODY = "## Personality\n\nCalm, precise, direct.\n";

function makeKindPort(
  overrides: Partial<KindPort> & Pick<KindPort, "apiVersion" | "kind" | "alias">,
): KindPort {
  return {
    origin: "test",
    isRoot: false,
    isPromptTarget: false,
    promptTargetPriority: 0,
    flattenInContext: false,
    storage: { container: "test", pattern: "yaml" },
    depFilters: () => null,
    getDefaultAgentName: () => null,
    getLayerPolicies: () => null,
    parse: (raw) => raw,
    describe: () => null,
    summary: () => null,
    promptTemplate: () => null,
    ...overrides,
  } as KindPort;
}

function makeMi(): ManifestInstance {
  const kinds = new Map<string, KindPort>();
  kinds.set(
    "github.com/ruinosus/dna/v1\0Agent",
    makeKindPort({
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Agent",
      alias: "helix-agent",
      isPromptTarget: true,
      promptTargetPriority: 2,
      // Mirrors the helix template joiner shape that leaked in the pilot.
      promptTemplate: () => "{{{agent.instruction}}}\n\n{{{soul_content}}}\n\n",
    }),
  );
  kinds.set(
    "soulspec.org/v1\0Soul",
    makeKindPort({
      apiVersion: "soulspec.org/v1",
      kind: "Soul",
      alias: "soulspec-soul",
      isPromptTarget: true,
      promptTargetPriority: 1,
      flattenInContext: true,
    }),
  );
  const docs = [
    Document.fromRaw({
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Agent",
      metadata: { name: "pilot-agent" },
      spec: { instruction: AGENT_BODY }, // trailing \n — editor default
    }),
    Document.fromRaw({
      apiVersion: "soulspec.org/v1",
      kind: "Soul",
      metadata: { name: "pilot-soul" },
      spec: { soul_content: SOUL_BODY }, // trailing \n — editor default
    }),
  ];
  return new ManifestInstance({ scope: "pilot-scope", documents: docs, kinds });
}

describe("i-013 — trailing newline leak (composition-only strip)", () => {
  test("soul trailing newline does not leak \\n\\n\\n into the prompt", async () => {
    const mi = makeMi();
    const prompt = await mi.buildPrompt({ agent: "pilot-agent" });
    expect(prompt).toContain("Calm, precise, direct.");
    expect(prompt).not.toContain("\n\n\n");
  });

  test("agent instruction (AGENT.md body) is normalized in context", async () => {
    const mi = makeMi();
    const agentDoc = mi.findAgent("pilot-agent")!;
    const ctx = await (mi.prompt as any)._buildContext(agentDoc, undefined);
    expect(ctx.agent.instruction).toBe(AGENT_BODY.trimEnd());
    expect(ctx.soul_content).toBe(SOUL_BODY.trimEnd());
  });

  test("storage stays byte-faithful — raw spec keeps the trailing newline", () => {
    const mi = makeMi();
    const soul = mi.documents.find((d) => d.kind === "Soul")!;
    expect(soul.spec.soul_content).toBe(SOUL_BODY); // trailing \n intact
  });

  test("stripPromptBlock strips trailing whitespace only", () => {
    expect(stripPromptBlock("body\n")).toBe("body");
    expect(stripPromptBlock("body\n\n  ")).toBe("body");
    expect(stripPromptBlock("  lead kept\nbody")).toBe("  lead kept\nbody");
  });
});
