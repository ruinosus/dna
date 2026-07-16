/**
 * Copilot → **hosted-variant** deployment artifacts (f-copilot-hosting; TS twin of
 * `test_copilot_hosting.py`).
 *
 * `buildCopilotContext` → `emitHosting` renders the HOSTED variant (design §2
 * variant selector), gated on `ctx.hosting.mode === "hosted"`. Foundry is
 * first-class (Dockerfile/main.py/requirements/azure.yaml); langgraph/agentos are
 * documented. The emitted files are byte-identical to the Python emit.
 */
import { describe, it, expect } from "bun:test";
import { join } from "node:path";
import { readFileSync } from "node:fs";

import { quickInstance } from "../src/bootstrap.js";
import { buildCopilotContext, emitHosting, hasHosting, type EmitContext } from "../src/index.js";
import { AgnoEmitter } from "../src/emit/agno.js";

const ROOT = join(import.meta.dir, "..", "..", "..");
const BASE = join(ROOT, "examples", "emitting-to-a-runtime", ".dna");
const SCOPE = "concierge";

function readGolden(name: string): string {
  return readFileSync(join(import.meta.dir, "goldens", "hosting", name), "utf-8");
}

function files(res: { artifacts: Array<{ path: string; content: string }> }): Record<string, string> {
  return Object.fromEntries(res.artifacts.map((a) => [a.path, a.content]));
}

async function hostedCtx(): Promise<EmitContext> {
  const mi = await quickInstance(SCOPE, BASE);
  return buildCopilotContext(mi, "hosted-copilot", { model: "azure/gpt-4o", provider: "azure" });
}

function synthetic(target: string, name: string): EmitContext {
  return {
    name,
    description: "",
    instructions: "Answer.",
    model: "azure/gpt-4o",
    tools: [],
    outputSchema: null,
    scope: null,
    options: {},
    mcpServers: [],
    toolsRequiringConfirmation: new Set<string>(),
    tenantPropagate: false,
    knowledge: [],
    workflow: [],
    frontendConsole: null,
    frontendPanels: [],
    frontendSuggestedPrompts: [],
    hitlApprovalCard: null,
    persistence: null,
    knowledgeStore: null,
    hosting: {
      mode: "hosted",
      target,
      resources: { cpu: "1", memory: "2Gi" },
      image: { registry_hint: "ghcr", remote_build: false, base_image: null, port: null },
      env: null,
      stores: { postgres: "required", redis: "required" },
    },
  } as EmitContext;
}

describe("hasHosting — gates on mode === hosted", () => {
  it("is true for the hosted variant", async () => {
    expect(hasHosting(await hostedCtx())).toBe(true);
  });

  it("is false for a self-hosted copilot and throws on emit", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const ctx = await buildCopilotContext(mi, "memory-copilot", { model: "azure/gpt-4o" });
    expect(ctx.hosting?.mode).toBe("self-hosted");
    expect(hasHosting(ctx)).toBe(false);
    expect(() => emitHosting(ctx)).toThrow();
  });

  it("is false when no hosting block is declared", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const ctx = await buildCopilotContext(mi, "pure-action-copilot", { model: "azure/gpt-4o" });
    expect(ctx.hosting).toBeNull();
    expect(hasHosting(ctx)).toBe(false);
  });
});

describe("emitHosting — Foundry (first-class)", () => {
  it("emits four role=hosting artifacts", async () => {
    const res = emitHosting(await hostedCtx());
    expect(res.target).toBe("foundry-hosted");
    expect(new Set(res.artifacts.map((a) => a.role))).toEqual(new Set(["hosting"]));
    expect(new Set(Object.keys(files(res)))).toEqual(
      new Set(["Dockerfile", "main.py", "requirements.txt", "azure.yaml"]),
    );
  });

  it("matches the Dockerfile golden (byte-identical to Python)", async () => {
    expect(files(emitHosting(await hostedCtx()))["Dockerfile"]).toBe(readGolden("foundry/Dockerfile"));
  });

  it("matches the main.py golden (byte-identical to Python)", async () => {
    expect(files(emitHosting(await hostedCtx()))["main.py"]).toBe(readGolden("foundry/main.py"));
  });

  it("matches the requirements.txt golden", async () => {
    expect(files(emitHosting(await hostedCtx()))["requirements.txt"]).toBe(
      readGolden("foundry/requirements.txt"),
    );
  });

  it("matches the azure.yaml golden", async () => {
    expect(files(emitHosting(await hostedCtx()))["azure.yaml"]).toBe(readGolden("foundry/azure.yaml"));
  });

  it("Dockerfile serves 8088 on linux/amd64 with CMD python main.py", async () => {
    const df = files(emitHosting(await hostedCtx()))["Dockerfile"];
    expect(df).toContain("FROM python:3.12-slim");
    expect(df).toContain("EXPOSE 8088");
    expect(df).toContain("linux/amd64");
    expect(df).toContain('CMD ["python", "main.py"]');
  });

  it("main.py uses ResponsesHostServer + reuses the MS-AF agent build", async () => {
    const main = files(emitHosting(await hostedCtx()))["main.py"];
    expect(main).toContain("from agent_framework_foundry_hosting import ResponsesHostServer");
    expect(main).toContain("ResponsesHostServer(build_agent()).run()");
    expect(main).toContain("from agent_framework.foundry import FoundryChatClient");
    expect(main).toContain("return client.as_agent(");
  });

  it("DEGRADES the per-user concerns (no OBO/HITL/tenant)", async () => {
    const ctx = await hostedCtx();
    expect(ctx.toolsRequiringConfirmation).toEqual(new Set(["remember", "forget"]));
    expect(ctx.tenantPropagate).toBe(true); // the self-hosted variant wires it; hosted drops it
    const main = files(emitHosting(ctx))["main.py"];
    expect(main).toContain("DefaultAzureCredential()");
    expect(main).not.toContain("approval_mode=");
    expect(main).not.toContain("header_provider=");
    expect(main).not.toContain("contextvars");
    expect(main).not.toContain("X-DNA-Tenant");
    expect(main).toContain("PostgresVectorStore("); // single-identity RAG survives
  });

  it("azure.yaml is the non-deprecated azure.ai.agent service block", async () => {
    const y = files(emitHosting(await hostedCtx()))["azure.yaml"];
    expect(y).toContain("host: azure.ai.agent");
    expect(y).toContain("remoteBuild: true");
    expect(y).toContain("startupCommand: python main.py");
    expect(y).toContain('cpu: "0.5"');
    expect(y).toContain("  memory-agent:");
  });

  it("requirements include hosting + persistence deps", async () => {
    const req = files(emitHosting(await hostedCtx()))["requirements.txt"].split("\n");
    expect(req).toContain("agent-framework");
    expect(req).toContain("agent-framework-foundry-hosting");
    expect(req).toContain("agent-framework-postgres");
  });
});

describe("emitHosting — documented targets", () => {
  it("throws on an unknown target", () => {
    const ctx = synthetic("heroku", "weird");
    expect(() => emitHosting(ctx)).toThrow();
  });

  it("langgraph-platform emits json + note (byte-identical to Python)", () => {
    const res = emitHosting(synthetic("langgraph-platform", "lg-copilot"));
    expect(res.target).toBe("langgraph-platform");
    const f = files(res);
    expect(new Set(Object.keys(f))).toEqual(new Set(["langgraph.json", "HOSTING.md"]));
    expect(f["langgraph.json"]).toBe(readGolden("langgraph/langgraph.json"));
    expect(f["HOSTING.md"]).toBe(readGolden("langgraph/HOSTING.md"));
    expect(JSON.parse(f["langgraph.json"]).graphs).toBeDefined();
    expect(f["HOSTING.md"]).toContain("langgraph build");
  });

  it("agentos emits app + compose + note (byte-identical to Python)", () => {
    const res = emitHosting(synthetic("agentos", "ao-copilot"));
    expect(res.target).toBe("agentos");
    const f = files(res);
    expect(new Set(Object.keys(f))).toEqual(new Set(["main.py", "compose.yaml", "HOSTING.md"]));
    expect(f["main.py"]).toBe(readGolden("agentos/main.py"));
    expect(f["compose.yaml"]).toBe(readGolden("agentos/compose.yaml"));
    expect(f["HOSTING.md"]).toBe(readGolden("agentos/HOSTING.md"));
    expect(f["compose.yaml"]).toContain('"7777:7777"');
  });
});

describe("back-compat — the self-hosted emit is unchanged", () => {
  it("the agno self-hosted emit for the same agent matches its golden", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const ctx = await buildCopilotContext(mi, "memory-copilot", { model: "azure/gpt-4o", provider: "azure" });
    const res = new AgnoEmitter().emit(ctx);
    const golden = readFileSync(join(import.meta.dir, "goldens", "agno", "copilot_agent.py"), "utf-8");
    expect(res.artifacts.find((a) => a.role === "agent")?.content).toBe(golden);
  });
});
