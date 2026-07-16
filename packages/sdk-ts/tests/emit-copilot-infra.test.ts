/**
 * Copilot → Terraform infra inputs (f-copilot-infra-binding; TS twin of
 * `test_copilot_infra.py`).
 *
 * `buildCopilotContext` → `emitInfra` renders ONE `role="infra"` artifact — a
 * `<agent>.tfvars.json` declaring the resources the declared `persistence` /
 * `knowledge.store` / `hosting` need, deduped by `ref`, plus the `env_injection`
 * map. The emitted JSON is byte-identical to the Python twin.
 */
import { describe, it, expect } from "bun:test";
import { join } from "node:path";

import { quickInstance } from "../src/bootstrap.js";
import { buildCopilotContext, EmitContext } from "../src/index.js";
import { emitInfra, hasInfra } from "../src/emit/infra.js";

const ROOT = join(import.meta.dir, "..", "..", "..");
const BASE = join(ROOT, "examples", "emitting-to-a-runtime", ".dna");
const SCOPE = "concierge";

async function infraCtx(): Promise<EmitContext> {
  const mi = await quickInstance(SCOPE, BASE);
  return buildCopilotContext(mi, "memory-copilot", { model: "azure/gpt-4o", provider: "azure" });
}

function tfvars(res: { artifacts: Array<{ content: string }> }): any {
  return JSON.parse(res.artifacts[0].content);
}

describe("emitInfra — the Terraform infra closure", () => {
  it("gates on declared infra", async () => {
    const ctx = await infraCtx();
    expect(hasInfra(ctx)).toBe(true);
    const mi = await quickInstance(SCOPE, BASE);
    const bare = await buildCopilotContext(mi, "pure-action-copilot", { model: "azure/gpt-4o" });
    expect(hasInfra(bare)).toBe(false);
    expect(() => emitInfra(bare)).toThrow();
  });

  it("emits one tfvars.json artifact tagged role=infra", async () => {
    const res = emitInfra(await infraCtx());
    expect(res.target).toBe("terraform");
    expect(res.artifacts.map((a) => a.role)).toEqual(["infra"]);
    expect(res.artifacts[0].path).toBe("memory_agent.tfvars.json");
    expect(res.artifacts[0].content.endsWith("\n")).toBe(true);
    JSON.parse(res.artifacts[0].content); // parseable
  });

  it("dedups postgres by ref and coalesces pgvector", async () => {
    const tf = tfvars(emitInfra(await infraCtx()));
    expect(tf.postgres.length).toBe(1);
    const pg = tf.postgres[0];
    expect(pg.ref).toBe("primary-pg");
    expect(pg.pgvector).toBe(true);
    expect(pg.used_by).toEqual([
      "knowledge.store",
      "persistence.checkpoint",
      "persistence.memory",
    ]);
    expect(pg.output_env).toBe("DNA_PG_URI_PRIMARY_PG");
    expect(tf.mongo).toEqual([]);
  });

  it("maps ref output → copilot env (env_injection)", async () => {
    const tf = tfvars(emitInfra(await infraCtx()));
    expect(tf.env_injection.DNA_PG_URI_PRIMARY_PG).toEqual({
      from: "postgres['primary-pg'].connection_string",
      secret: true,
    });
  });

  it("emits the Foundry module inputs", async () => {
    const tf = tfvars(emitInfra(await infraCtx()));
    const h = tf.hosting;
    expect(h.target).toBe("foundry");
    expect(h.image.container_port).toBe(8088);
    expect(h.foundry.model_deployment).toBe("azure/gpt-4o");
    expect(h.foundry.rbac).toEqual([
      { principal: "project_identity", role: "AcrPull" },
      { principal: "agent_identity", role: "Azure AI User" },
    ]);
    expect(h.note).toContain("post-provision");
  });

  it("synthesizes langgraph stores into postgres/redis resources", () => {
    const ctx: EmitContext = {
      name: "lg-copilot",
      description: "",
      instructions: "x",
      model: "azure/gpt-4o",
      tools: [],
      outputSchema: null,
      scope: null,
      options: {},
      mcpServers: [],
      toolsRequiringConfirmation: new Set(),
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
        target: "langgraph-platform",
        resources: { cpu: "1", memory: "2Gi" },
        image: { registry_hint: "ghcr", remote_build: false, base_image: null, port: null },
        env: null,
        stores: { postgres: "required", redis: "required" },
      },
    };
    const tf = tfvars(emitInfra(ctx));
    expect(tf.hosting.image.container_port).toBe(8123);
    expect(tf.hosting.langgraph_platform.secret_env).toEqual(["LANGGRAPH_CLOUD_LICENSE_KEY"]);
    expect(tf.postgres.map((p: any) => p.ref)).toEqual(["lg_copilot-pg"]);
    expect(tf.redis.map((r: any) => r.ref)).toEqual(["lg_copilot-redis"]);
    expect(tf.env_injection.LANGGRAPH_CLOUD_LICENSE_KEY).toBeDefined();
  });
});
