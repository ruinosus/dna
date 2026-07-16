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
    expect(ctx.knowledge).toEqual(["knowledge-base"]);
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

  // ── persistence / knowledge.store / hosting projection (the foundation) ────
  it("projects the persistence block (checkpoint/memory/cache each {backend, ref})", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const ctx = await buildCopilotContext(mi, "memory-copilot", { model: "azure/gpt-4o" });
    expect(ctx.persistence).toEqual({
      checkpoint: { backend: "postgres", ref: "primary-pg" },
      memory: { backend: "postgres", ref: "primary-pg" },
      cache: { backend: null, ref: null },
    });
  });

  it("projects knowledge.store as {backend, ref, embed}", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const ctx = await buildCopilotContext(mi, "memory-copilot", { model: "azure/gpt-4o" });
    expect(ctx.knowledgeStore).toEqual({
      backend: "pgvector",
      ref: "primary-pg",
      embed: { model: "text-embedding-3-small", dims: 1536 },
    });
    // the corpus list is untouched (back-compat).
    expect(ctx.knowledge).toEqual(["knowledge-base"]);
  });

  it("projects the hosting block fully (mode/target/resources/image/env/stores)", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const ctx = await buildCopilotContext(mi, "memory-copilot", { model: "azure/gpt-4o" });
    expect(ctx.hosting).toEqual({
      mode: "self-hosted",
      target: "foundry",
      resources: { cpu: "0.5", memory: "1Gi" },
      image: { registry_hint: "acr", remote_build: true, base_image: null, port: null },
      env: { LOG_LEVEL: "info" },
      stores: { postgres: "required", redis: "required" },
    });
  });

  it("leaves persistence/knowledgeStore/hosting null for a pure-action copilot", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const ctx = await buildCopilotContext(mi, "pure-action-copilot", { model: "azure/gpt-4o" });
    expect(ctx.persistence).toBeNull();
    expect(ctx.knowledgeStore).toBeNull();
    expect(ctx.hosting).toBeNull();
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
      workflow: [],
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

/**
 * The Microsoft Agent Framework `copilot` scaffold case (TS twin of the Chunk 6
 * slice of `test_copilot_emit.py`) — the SECOND per-runtime copilot case
 * (f-copilot-agentframework-target). `buildCopilotContext` (the SAME ctx the Agno
 * case reads) → `AgentFrameworkEmitter().emit(ctx)` renders TWO artifacts
 * (agent + serving) governed by byte-equal goldens; a Copilot with a
 * `workflow.chain` emits the WorkflowBuilder variant. Rendered literals differ
 * from Python only in quote style (JSON string literals — the shared convention).
 */
import { AgentFrameworkEmitter } from "../src/emit/agentFramework.js";

describe("AgentFrameworkEmitter — the servable `copilot` case (MS Agent Framework)", () => {
  async function ctxFor(copilot: string): Promise<EmitContext> {
    const mi = await quickInstance(SCOPE, BASE);
    return buildCopilotContext(mi, copilot, { model: "azure/gpt-4o", provider: "azure" });
  }

  it("emits two artifacts (agent + serving) at the mounted agent's module paths", async () => {
    const res = new AgentFrameworkEmitter().emit(await ctxFor("memory-copilot"));
    expect(new Set(res.artifacts.map((a) => a.role))).toEqual(new Set(["agent", "serving"]));
    expect(res.target).toBe("agent-framework");
    const paths = Object.fromEntries(res.artifacts.map((a) => [a.role, a.path]));
    expect(paths.agent).toBe("memory_agent.py");
    expect(paths.serving).toBe("memory_agent_serve.py");
  });

  it("the agent artifact matches the golden", async () => {
    const res = new AgentFrameworkEmitter().emit(await ctxFor("memory-copilot"));
    expect(res.artifactFor("agent")).toBe(readGolden("agent_framework/copilot_agent.py"));
  });

  it("the serving artifact matches the golden", async () => {
    const res = new AgentFrameworkEmitter().emit(await ctxFor("memory-copilot"));
    expect(res.artifactFor("serving")).toBe(readGolden("agent_framework/copilot_serve.py"));
  });

  it("carries the byte-equal instruction via the emitter method (role=agent)", async () => {
    const ctx = await ctxFor("memory-copilot");
    const emitter = new AgentFrameworkEmitter();
    const res = emitter.emit(ctx);
    expect(emitter.extractInstructions(res.artifactFor("agent"))).toBe(ctx.instructions);
  });

  it("builds via FoundryChatClient.as_agent and serves /agui via the fastapi endpoint", async () => {
    const res = new AgentFrameworkEmitter().emit(await ctxFor("memory-copilot"));
    const agent = res.artifactFor("agent");
    const serving = res.artifactFor("serving");
    expect(agent).toContain("from agent_framework.foundry import FoundryChatClient");
    expect(agent).toContain("return client.as_agent(");
    expect(serving).toContain(
      "from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint",
    );
    expect(serving).toContain('path="/agui",');
  });

  it("mounts MCPStreamableHTTPTool with allowed_tools + approval_mode tool-level HITL", async () => {
    const agent = new AgentFrameworkEmitter().emit(await ctxFor("memory-copilot")).artifactFor("agent");
    expect(agent).toContain("from agent_framework import MCPStreamableHTTPTool");
    expect(agent).toContain('name="mcp_dna-mcp",');
    expect(agent).toContain('url="https://mcp.dna.example/agui",');
    expect(agent).toContain('allowed_tools=["forget", "recall", "remember"],');
    expect(agent).toContain(
      'approval_mode={"always_require_approval": ["forget", "remember"], ' +
        '"never_require_approval": ["recall"]},',
    );
  });

  it("derives inbound tenant from DNA-native headers only (no license/namespace)", async () => {
    const res = new AgentFrameworkEmitter().emit(await ctxFor("memory-copilot"));
    const agent = res.artifactFor("agent");
    const serving = res.artifactFor("serving");
    expect(agent).toContain("contextvars.ContextVar");
    expect(agent).toContain("def _tenant_header_provider(_existing: dict) -> dict:");
    // DNA tenancy = three dimensions: tenant (tid) + workspace + user oid.
    expect(agent).toContain('"X-DNA-Tenant"');
    expect(agent).toContain('"X-DNA-Workspace"');
    expect(agent).toContain('"X-Tenant-OID"');
    expect(serving).toContain('@app.middleware("http")');
    for (const forbidden of ["X-DNA-License-ID", "X-DNA-Namespace-ID", "license_id", "namespace_id"]) {
      expect(agent).not.toContain(forbidden);
      expect(serving).not.toContain(forbidden);
    }
  });

  it("emits the WorkflowBuilder chain + request_info escalation for a workflow copilot", async () => {
    const ctx = await ctxFor("workflow-copilot");
    expect(ctx.workflow).toEqual(["triage", "retrieve", "resolve"]);
    const res = new AgentFrameworkEmitter().emit(ctx);
    const agent = res.artifactFor("agent");
    expect(agent).toBe(readGolden("agent_framework/copilot_workflow_agent.py"));
    expect(agent).toContain("class EscalationExecutor(Executor):");
    expect(agent).toContain("await ctx.request_info(request_data=text, response_type=bool)");
    expect(agent).toContain(".add_chain([triage, retrieve, resolve, escalate])");
    // writes gated at the workflow level → MCP mount uses never_require.
    expect(agent).toContain('approval_mode="never_require",');
    expect(agent).not.toContain("approval_mode={");
    const serving = res.artifactFor("serving");
    expect(serving).toBe(readGolden("agent_framework/copilot_workflow_serve.py"));
    expect(serving).toContain("agent=AgentFrameworkWorkflow(workflow_factory=build_workflow),");
  });

  it("a plain agent (no copilot signals) stays the single-artifact PromptAgent YAML", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const res = await emitAgent(mi, "concierge", "agent-framework");
    expect(res.artifacts.map((a) => a.role)).toEqual(["agent"]);
    expect(res.filename.endsWith("agent.yaml")).toBe(true);
    expect(res.artifact).toContain("kind: Prompt");
    expect(res.artifact).not.toContain("FoundryChatClient");
  });
});

/**
 * The LangGraph `copilot` scaffold case (TS twin of the Chunk 7 slice of
 * `test_copilot_emit.py`) — the THIRD per-runtime copilot case
 * (f-copilot-langgraph-target). `buildCopilotContext` (the SAME ctx the Agno +
 * MS-AF cases read) → `LanggraphEmitter().emit(ctx)` renders TWO artifacts
 * (a `StateGraph` agent module + the AG-UI LangGraph serving module) governed by
 * byte-equal goldens; a Copilot with a `workflow.chain` emits the graph-native
 * node chain. Rendered literals differ from Python only in quote style (JSON
 * string literals — the shared convention). This makes it 3 runtime targets —
 * the emitter fully runtime-agnostic.
 */
import { LanggraphEmitter } from "../src/emit/langgraph.js";

describe("LanggraphEmitter — the servable `copilot` case (StateGraph CoAgent)", () => {
  async function ctxFor(copilot: string): Promise<EmitContext> {
    const mi = await quickInstance(SCOPE, BASE);
    return buildCopilotContext(mi, copilot, { model: "azure/gpt-4o", provider: "azure" });
  }

  it("emits two artifacts (agent + serving) at the mounted agent's module paths", async () => {
    const res = new LanggraphEmitter().emit(await ctxFor("memory-copilot"));
    expect(new Set(res.artifacts.map((a) => a.role))).toEqual(new Set(["agent", "serving"]));
    expect(res.target).toBe("langgraph");
    const paths = Object.fromEntries(res.artifacts.map((a) => [a.role, a.path]));
    expect(paths.agent).toBe("memory_agent.py");
    expect(paths.serving).toBe("memory_agent_serve.py");
  });

  it("the agent artifact matches the golden", async () => {
    const res = new LanggraphEmitter().emit(await ctxFor("memory-copilot"));
    expect(res.artifactFor("agent")).toBe(readGolden("langgraph/copilot_agent.py"));
  });

  it("the serving artifact matches the golden", async () => {
    const res = new LanggraphEmitter().emit(await ctxFor("memory-copilot"));
    expect(res.artifactFor("serving")).toBe(readGolden("langgraph/copilot_serve.py"));
  });

  it("carries the byte-equal instruction via the inherited scaffold method (role=agent)", async () => {
    const ctx = await ctxFor("memory-copilot");
    const emitter = new LanggraphEmitter();
    const res = emitter.emit(ctx);
    expect(emitter.extractInstructions(res.artifactFor("agent"))).toBe(ctx.instructions);
  });

  it("builds a StateGraph CoAgent and serves /agui via the LangGraph AG-UI adapter", async () => {
    const res = new LanggraphEmitter().emit(await ctxFor("memory-copilot"));
    const agent = res.artifactFor("agent");
    const serving = res.artifactFor("serving");
    // runtime-delta vs Agno/MS-AF: a StateGraph compiled to a CoAgent.
    expect(agent).toContain("from langgraph.graph import END, START, StateGraph");
    expect(agent).toContain("graph = StateGraph(State)");
    expect(agent).toContain("return graph.compile(checkpointer=MemorySaver())");
    expect(serving).toContain(
      "from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint",
    );
    expect(serving).toContain("agent=LangGraphAgent(name=\"memory-agent\", graph=build_agent()),");
    expect(serving).toContain('path="/agui",');
  });

  it("mounts MCP via MultiServerMCPClient + ToolNode", async () => {
    const agent = new LanggraphEmitter().emit(await ctxFor("memory-copilot")).artifactFor("agent");
    expect(agent).toContain("from langchain_mcp_adapters.client import MultiServerMCPClient");
    expect(agent).toContain("from langgraph.prebuilt import ToolNode");
    expect(agent).toContain('"mcp_dna-mcp": {');
    expect(agent).toContain('"url": "https://mcp.dna.example/agui",');
    expect(agent).toContain('"transport": "streamable_http",');
    expect(agent).toContain("ToolNode(await _mcp_client().get_tools())");
  });

  it("gates writes via the graph-enforced interrupt() review node (HITL)", async () => {
    const ctx = await ctxFor("memory-copilot");
    expect(ctx.toolsRequiringConfirmation).toEqual(new Set(["remember", "forget"]));
    const agent = new LanggraphEmitter().emit(ctx).artifactFor("agent");
    expect(agent).toContain("from langgraph.types import interrupt");
    expect(agent).toContain('_CONFIRM_TOOLS = ["forget", "remember"]');
    expect(agent).toContain("def _review_node(state: State) -> dict:");
    expect(agent).toContain('interrupt({"awaiting_approval": gated})');
    expect(agent).toContain('graph.add_node("review", _review_node)');
  });

  it("carries tenant IN the graph state + DNA-native headers only (no license/namespace)", async () => {
    const res = new LanggraphEmitter().emit(await ctxFor("memory-copilot"));
    const agent = res.artifactFor("agent");
    const serving = res.artifactFor("serving");
    // tenant is the LangGraph-native carrier — it rides in the graph state.
    expect(agent).toContain("class State(TypedDict):");
    expect(agent).toContain("tenant: dict");
    expect(agent).toContain('tenant = state.get("tenant") or _CURRENT_TENANT.get()');
    // ContextVar bridge for the outbound MCP headers, DNA-native only.
    expect(agent).toContain("contextvars.ContextVar");
    expect(agent).toContain('"X-DNA-Tenant"');
    expect(agent).toContain('"X-DNA-Workspace"');
    expect(agent).toContain('"X-Tenant-OID"');
    expect(serving).toContain('@app.middleware("http")');
    for (const forbidden of ["X-DNA-License-ID", "X-DNA-Namespace-ID", "license_id", "namespace_id"]) {
      expect(agent).not.toContain(forbidden);
      expect(serving).not.toContain(forbidden);
    }
  });

  it("emits the graph-native node chain + interrupt() review node for a workflow copilot", async () => {
    const ctx = await ctxFor("workflow-copilot");
    expect(ctx.workflow).toEqual(["triage", "retrieve", "resolve"]);
    const res = new LanggraphEmitter().emit(ctx);
    const agent = res.artifactFor("agent");
    expect(agent).toBe(readGolden("langgraph/copilot_workflow_agent.py"));
    expect(agent).toContain("async def _triage_node(state: State) -> dict:");
    expect(agent).toContain("def build_workflow():");
    expect(agent).toContain('graph.add_node("triage", _triage_node)');
    expect(agent).toContain('graph.add_edge("triage", "retrieve")');
    expect(agent).toContain('graph.add_edge("resolve", "review")');
    // workflow-level HITL: a dedicated interrupt() review node, no ReAct _route.
    expect(agent).toContain('interrupt({"awaiting_approval": summary})');
    expect(agent).not.toContain("def _route(");
    const serving = res.artifactFor("serving");
    expect(serving).toBe(readGolden("langgraph/copilot_workflow_serve.py"));
    expect(serving).toContain("from memory_agent import build_workflow");
    expect(serving).toContain("graph=build_workflow())");
  });

  it("a plain agent (no copilot signals) stays the single-artifact create_react_agent scaffold", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const res = await emitAgent(mi, "concierge", "langgraph");
    expect(res.artifacts.map((a) => a.role)).toEqual(["agent"]);
    expect(res.filename.endsWith(".py")).toBe(true);
    expect(res.artifact).toContain("create_react_agent(");
    expect(res.artifact).not.toContain("StateGraph");
    expect(res.artifact).not.toContain("add_langgraph_fastapi_endpoint");
  });
});
