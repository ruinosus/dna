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

import { quickInstance } from "../src/bootstrap.js";
import { buildCopilotContext } from "../src/index.js";

const ROOT = join(import.meta.dir, "..", "..", "..");
const BASE = join(ROOT, "examples", "emitting-to-a-runtime", ".dna");
const SCOPE = "concierge";

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
