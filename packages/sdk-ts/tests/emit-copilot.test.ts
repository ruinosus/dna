/**
 * `buildCopilotContext` — the Copilot → EmitContext seam (TS twin of the Chunk 3
 * slice of `test_copilot_emit.py`).
 *
 * A live filesystem scope (`examples/emitting-to-a-runtime/.dna`) carries the
 * copilot fixtures: `memory-copilot` mounts `memory-agent` (an MCP-mounted,
 * HITL-gated agent) and `pure-action-copilot` mounts `pure-action-agent` (one
 * local tool, no MCP, no RAG). `buildCopilotContext` resolves each Copilot doc
 * to the mounted agent's base EmitContext and enriches it.
 */
import { describe, it, expect } from "bun:test";
import { join } from "node:path";
import { readFileSync } from "node:fs";

import { quickInstance } from "../src/bootstrap.js";
import { buildCopilotContext, emitAgent, type EmitContext } from "../src/index.js";
import { AgnoEmitter } from "../src/emit/agno.js";

const ROOT = join(import.meta.dir, "..", "..", "..");
const BASE = join(ROOT, "examples", "emitting-to-a-runtime", ".dna");
const SCOPE = "concierge";

function readGolden(name: string): string {
  return readFileSync(join(import.meta.dir, "goldens", name), "utf-8");
}

describe("buildCopilotContext — the Copilot → EmitContext seam", () => {
  // ── Task 3a: resolve the mounted agent's base ctx ─────────────────────────
  it("resolves to the mounted agent's base EmitContext", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const ctx = await buildCopilotContext(mi, "memory-copilot", { model: "azure/gpt-4o", provider: "azure" });
    // The base ctx is the MOUNTED agent's — name + instructions come from it,
    // unchanged (byte-equal instruction contract intact).
    expect(ctx.name).toBe("memory-agent");
    expect(ctx.instructions).toBe(await mi.buildPrompt({ agent: "memory-agent" }));
  });

  // ── Task 3b: enrich the ctx ───────────────────────────────────────────────
  it("projects mcp_servers from the mounted agent's federations", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const ctx = await buildCopilotContext(mi, "memory-copilot", { model: "azure/gpt-4o" });
    expect(ctx.mcpServers.length).toBe(1);
    const fed = ctx.mcpServers[0];
    expect(fed.ref).toBe("dna-mcp");
    expect(fed.transport).toBe("streamable-http"); // normalized from streamable_http
    expect(fed.url).toBe("https://mcp.dna.example/agui");
    expect(fed.auth).toEqual({ kind: "bearer_env", env: "DNA_MCP_TOKEN" });
    expect(fed.allowedTools).toEqual(["remember", "forget", "recall"]);
    expect(fed.propagateTenant).toBe(true);
  });

  it("projects the HITL-write intent (requires_confirmation tools)", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const ctx = await buildCopilotContext(mi, "memory-copilot", { model: "azure/gpt-4o" });
    expect(ctx.toolsRequiringConfirmation).toEqual(new Set(["remember", "forget"]));
  });

  it("projects inbound-tenant propagation + knowledge refs", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const ctx = await buildCopilotContext(mi, "memory-copilot", { model: "azure/gpt-4o" });
    expect(ctx.tenantPropagate).toBe(true);
    expect(ctx.knowledge).toEqual(["aap-knowledge-base"]);
  });

  // ── negatives: everything optional is empty when undeclared ───────────────
  it("leaves knowledge/mcp/hitl/tenant empty for a pure-action copilot", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const ctx = await buildCopilotContext(mi, "pure-action-copilot", { model: "azure/gpt-4o" });
    expect(ctx.knowledge).toEqual([]);
    expect(ctx.mcpServers).toEqual([]);
    expect(ctx.toolsRequiringConfirmation).toEqual(new Set<string>());
    expect(ctx.tenantPropagate).toBe(false);
  });
});

/**
 * Chunk 4 · the Agno `copilot` scaffold case (TS twin of the Chunk 4 slice of
 * `test_copilot_emit.py`). `buildCopilotContext` → `AgnoEmitter().emit(ctx)`
 * renders TWO artifacts (agent + serving) governed by byte-equal goldens. The
 * templates are byte-identical to Python's; rendered literals differ only in
 * quote style (JSON string literals — the shared scaffold convention).
 */
describe("AgnoEmitter — the servable `copilot` case", () => {
  async function ctxFor(copilot: string): Promise<EmitContext> {
    const mi = await quickInstance(SCOPE, BASE);
    return buildCopilotContext(mi, copilot, { model: "azure/gpt-4o", provider: "azure" });
  }

  // ── Task 4a: agent + /agui serving ──────────────────────────────────────
  it("emits two artifacts (agent + serving) at the mounted agent's module paths", async () => {
    const res = new AgnoEmitter().emit(await ctxFor("memory-copilot"));
    expect(new Set(res.artifacts.map((a) => a.role))).toEqual(new Set(["agent", "serving"]));
    expect(res.target).toBe("agno");
    const paths = Object.fromEntries(res.artifacts.map((a) => [a.role, a.path]));
    expect(paths.agent).toBe("memory_agent.py");
    expect(paths.serving).toBe("memory_agent_serve.py");
  });

  it("the agent artifact matches the golden", async () => {
    const res = new AgnoEmitter().emit(await ctxFor("memory-copilot"));
    expect(res.artifactFor("agent")).toBe(readGolden("agno/copilot_agent.py"));
  });

  it("the serving artifact matches the golden", async () => {
    const res = new AgnoEmitter().emit(await ctxFor("memory-copilot"));
    expect(res.artifactFor("serving")).toBe(readGolden("agno/copilot_serve.py"));
  });

  it("carries the byte-equal instruction via the emitter method (role=agent)", async () => {
    const ctx = await ctxFor("memory-copilot");
    const emitter = new AgnoEmitter();
    const res = emitter.emit(ctx);
    expect(emitter.extractInstructions(res.artifactFor("agent"))).toBe(ctx.instructions);
  });

  it("the serving artifact wires AgentOS + AGUI → /agui", async () => {
    const serving = new AgnoEmitter().emit(await ctxFor("memory-copilot")).artifactFor("serving");
    expect(serving).toContain("from agno.os import AgentOS");
    expect(serving).toContain("from agno.os.interfaces.agui import AGUI");
    expect(serving).toContain("app = agent_os.get_app()");
    expect(serving).toContain("from memory_agent import build_agent");
  });

  // ── Task 4b: MCP-tool mount ─────────────────────────────────────────────
  it("mounts MCPTools(url, transport) from ctx.mcpServers", async () => {
    const agent = new AgnoEmitter().emit(await ctxFor("memory-copilot")).artifactFor("agent");
    expect(agent).toContain("from agno.tools.mcp import MCPTools");
    expect(agent).toContain('url="https://mcp.dna.example/agui"');
    expect(agent).toContain('transport="streamable-http"');
    expect(agent).toContain("tools=_mcp_tools()");
  });

  // ── Task 4c: inbound-tenant derivation ──────────────────────────────────
  it("derives inbound tenant when tenantPropagate is set", async () => {
    const serving = new AgnoEmitter().emit(await ctxFor("memory-copilot")).artifactFor("serving");
    expect(serving).toContain("class TenantAGUI(AGUI):");
    expect(serving).toContain("def tenant_from_request(request: Request)");
    expect(serving).toContain('run_input.state["tenant"] = tenant');
    expect(serving).toContain("from agno.os.interfaces.agui.router import run_entity");
    expect(serving).toContain("interfaces=[TenantAGUI(agent=agent)]");
  });

  it("serves the plain AGUI when tenant is not propagated", () => {
    const ctx: EmitContext = {
      name: "kb-copilot",
      description: "",
      instructions: "Answer from the KB.",
      model: "azure/gpt-4o",
      tools: [],
      outputSchema: null,
      scope: null,
      options: {},
      mcpServers: [],
      toolsRequiringConfirmation: new Set<string>(),
      tenantPropagate: false,
      knowledge: ["some-collection"], // copilot signal, no tenant/mcp/hitl
    };
    const serving = new AgnoEmitter().emit(ctx).artifactFor("serving");
    expect(serving).not.toContain("TenantAGUI");
    expect(serving).toContain("interfaces=[AGUI(agent=agent)]");
  });

  // ── Task 4d: HITL gate-remote-directly (Spike 0A) ───────────────────────
  it("gates the write tools directly on the remote MCP tool", async () => {
    const ctx = await ctxFor("memory-copilot");
    expect(ctx.toolsRequiringConfirmation).toEqual(new Set(["remember", "forget"]));
    const agent = new AgnoEmitter().emit(ctx).artifactFor("agent");
    expect(agent).toContain('external_execution_required_tools=["forget", "remember"]');
    expect(agent).not.toContain("def remember(");
    expect(agent).not.toContain("def forget(");
  });

  // ── back-compat: a plain agent stays single-artifact ────────────────────
  it("a plain agent (no copilot signals) still emits a single artifact", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const res = await emitAgent(mi, "concierge", "agno");
    expect(res.artifacts.map((a) => a.role)).toEqual(["agent"]);
    expect(res.artifact).not.toContain("AgentOS");
  });
});
