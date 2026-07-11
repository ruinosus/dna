/**
 * Contract test for the AGENT.md frontmatter passthrough on TS.
 *
 * The helix reader uses ``SPEC_FIELDS`` (an allowlist) to decide
 * which top-level frontmatter keys flow into ``raw.spec``.
 * Historically the allowlist was hand-maintained and silently
 * drifted from ``AgentSpecSchema``, dropping new fields at
 * parse time — 2026-05-08 hit this with ``codegraph`` /
 * ``tool_groups`` / ``tests`` (and the Py twin earlier with
 * ``shell_sandbox``).
 *
 * The reader now derives the allowlist from
 * ``Object.keys(AgentSpecSchema.shape)`` directly, so a new
 * field opens automatically. These tests pin that contract behaviorally
 * by writing AGENT.md with each declared field and asserting the
 * value lands in ``raw.spec`` after parse.
 */
import { describe, test, expect } from "bun:test";
import { mkdtempSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import yaml from "js-yaml";

import { AgentReader } from "../src/extensions/helix.js";
import { AgentSpecSchema } from "../src/kernel/models.js";
import { FilesystemBundleHandle } from "../src/kernel/bundle-handle.js";

function makeTmpDir(): string {
  return mkdtempSync(join(tmpdir(), "agent-spec-contract-"));
}

function buildAgentMd(frontmatter: Record<string, unknown>): string {
  return `---\n${yaml.dump(frontmatter, { sortKeys: false })}---\nbody text\n`;
}

describe("AGENT.md frontmatter passthrough — contract", () => {
  // Sample values per declared field; values are kept simple but
  // type-faithful to the Zod schema so YAML stringify produces clean
  // input. ``instruction`` is intentionally absent — body owns it.
  const samples: Record<string, unknown> = {
    instruction_file: null, // mutually exclusive with body — covered separately
    objective: "demo",
    model: "openai:gpt-4o-mini",
    type: "agent",
    soul: "demo-soul",
    skills: ["s1"],
    tools: ["t1"],
    team_members: ["sub-1"],
    tags: ["demo"],
    guardrails: ["g1"],
    promptTemplate: "Hello {{name}}",
    layout: "persona-first", // s-dx-named-layouts
    tool_groups: ["manifest"],
    // s-mcp-servers-on-agent — string shorthand + per-agent override.
    mcp_servers: [
      "drawio",
      { ref: "web-search", allowed_tools: ["search"], timeout_s: 20 },
    ],
    shell_sandbox: true,
    prompt_format: "toon",
    max_turns: 25,
    agent_kind: "deepagent",
    mandatory_tool_calls: ["create_status_report"],
    input_schema: { type: "object", properties: { x: { type: "string" } } },
    invoked_by_engine: "oracle-risk-insight",
    // Fields added in earlier Stories that were missing samples here:
    reflect_before_write: true,
    locale_strings: { "pt-br": { hello: "olá" } },
    target_scopes: ["hr-screening", "open-swe"],
    // Kind-Writer mode (feat/kind-writer-pilot).
    writes_kind: "StatusReport",
    creative_slots: ["verdict"],
    system_slots: { insight: "input.oracle_id" },
    // Multi-Kind mode (feat/kind-writer-multikind).
    writes_kinds: {
      ADR: {
        creative_slots: ["title", "context", "decision"],
        system_slots: { status: "accepted" },
      },
      Retrospective: {
        creative_slots: ["title", "what_went_well"],
        system_slots: { period_start: "input.period_start" },
      },
    },
    // Declarative reads (feat/scribe-migrate-6).
    reads: { oracle_verdicts: { n: 3 }, engrams: { n: 5 } },
    // Declarative delegation-target opt-in (s-delegation-declarative).
    delegation_target_for: {
      agents: ["jarvis"],
      format: "slug",
      typical_seconds: 10,
      use_when: "user asks for an elaborate HTML mockup",
      purpose: "Generate elaborate HTML mockups",
    },
    // JARVIS — voice-first opt-in block (s-jarvis-voice-persona-schema-ts).
    voice_persona: {
      voice: "cedar",
      style: "concise, dry-wit",
      archetype: "jarvis",
      interruption_tolerance: "high",
      preamble: true,
      mcp_egress: true,
      wake_word: "hey jefferson",
      budget: 5.0,
    },
  };

  test("every Zod-declared field except 'instruction' has a sample", () => {
    const declared = new Set(Object.keys(AgentSpecSchema.shape));
    declared.delete("instruction");
    const missingSamples = [...declared].filter((k) => !(k in samples));
    expect(missingSamples).toEqual([]);
  });

  test("'instruction' is not in the passthrough — it comes from the body", () => {
    const reader = new AgentReader();
    const dir = makeTmpDir();
    writeFileSync(
      join(dir, "AGENT.md"),
      buildAgentMd({ name: "agent-x", instruction: "FROM_FRONTMATTER" }) + "FROM_BODY",
    );
    const raw = reader.read(new FilesystemBundleHandle(dir));
    // The body owns spec.instruction; a frontmatter ``instruction:``
    // must NOT be picked up (otherwise it would silently shadow the
    // body content).
    expect((raw as { spec: { instruction: string } }).spec.instruction).not.toBe(
      "FROM_FRONTMATTER",
    );
  });

  test("each declared field round-trips frontmatter → spec", () => {
    const reader = new AgentReader();
    for (const [field, value] of Object.entries(samples)) {
      if (field === "instruction_file") continue; // mutual-exclusion path
      const dir = makeTmpDir();
      writeFileSync(
        join(dir, "AGENT.md"),
        buildAgentMd({ name: "smoke-agent", description: "round-trip", [field]: value }),
      );
      const raw = reader.read(new FilesystemBundleHandle(dir)) as {
        spec: Record<string, unknown>;
      };
      expect(raw.spec[field], `field '${field}' missing from spec`).toEqual(value);
    }
  });
});
