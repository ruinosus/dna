/**
 * The shared CopilotKit frontend console scaffold (TS twin of the Chunk 5 slice
 * of `test_copilot_emit.py`).
 *
 * `buildCopilotContext` projects the Copilot's `frontend` + `hitl.approval_card`
 * blocks; `emitFrontendConsole` renders the shared CopilotKit v2 console (route +
 * console + approval-card + suggested-prompts) plus the ONE per-runtime resume-
 * adapter. A TS-only golden family (design §7): the emitted files are TypeScript,
 * governed by their own byte-stable golden, byte-identical to the Python emit.
 */
import { describe, it, expect } from "bun:test";
import { join } from "node:path";
import { readFileSync } from "node:fs";

import { quickInstance } from "../src/bootstrap.js";
import {
  buildCopilotContext,
  emitFrontendConsole,
  hasFrontend,
  type EmitContext,
  type EmitResult,
} from "../src/index.js";
import { AgnoEmitter } from "../src/emit/agno.js";

const ROOT = join(import.meta.dir, "..", "..", "..");
const BASE = join(ROOT, "examples", "emitting-to-a-runtime", ".dna");
const SCOPE = "concierge";

function readGolden(name: string): string {
  return readFileSync(join(import.meta.dir, "goldens", name), "utf-8");
}

function feFiles(res: EmitResult): Record<string, string> {
  return Object.fromEntries(res.artifacts.map((a) => [a.path, a.content]));
}

async function feCtx(copilot = "memory-copilot"): Promise<EmitContext> {
  const mi = await quickInstance(SCOPE, BASE);
  return buildCopilotContext(mi, copilot, { model: "azure/gpt-4o", provider: "azure" });
}

describe("buildCopilotContext — the frontend projection", () => {
  it("projects the Copilot.frontend block", async () => {
    const ctx = await feCtx();
    expect(ctx.frontendConsole).toBe("copilotkit");
    expect(ctx.frontendPanels).toEqual(["memory-timeline"]);
    expect(ctx.frontendSuggestedPrompts).toEqual(["What did I ask you to remember?"]);
  });

  it("projects the hitl.approval_card copy", async () => {
    const ctx = await feCtx();
    expect(ctx.hitlApprovalCard).toEqual({
      title: "Confirm write",
      details_from: "args.text",
      reason_from: "args.reason",
    });
  });

  it("carries null/empty + hasFrontend=false for a copilot with no frontend", async () => {
    const ctx = await feCtx("pure-action-copilot");
    expect(ctx.frontendConsole).toBeNull();
    expect(ctx.frontendPanels).toEqual([]);
    expect(ctx.frontendSuggestedPrompts).toEqual([]);
    expect(ctx.hitlApprovalCard).toBeNull();
    expect(hasFrontend(ctx)).toBe(false);
  });
});

describe("emitFrontendConsole — the shared console tree", () => {
  it("emits five role=frontend files at their target-relative paths", async () => {
    const res = emitFrontendConsole(await feCtx(), "agno");
    expect(new Set(res.artifacts.map((a) => a.role))).toEqual(new Set(["frontend"]));
    expect(new Set(Object.keys(feFiles(res)))).toEqual(
      new Set([
        "app/api/copilotkit/route.ts",
        "components/copilot/console.tsx",
        "components/copilot/approval-card.tsx",
        "components/copilot/suggested-prompts.tsx",
        "lib/copilot/resume-adapter.ts",
      ]),
    );
    expect(res.target).toBe("copilotkit-agno");
  });

  it("the route matches the golden", async () => {
    const files = feFiles(emitFrontendConsole(await feCtx(), "agno"));
    expect(files["app/api/copilotkit/route.ts"]).toBe(readGolden("frontend/route.ts"));
  });

  it("the console matches the golden", async () => {
    const files = feFiles(emitFrontendConsole(await feCtx(), "agno"));
    expect(files["components/copilot/console.tsx"]).toBe(readGolden("frontend/console.tsx"));
  });

  it("the approval card matches the golden", async () => {
    const files = feFiles(emitFrontendConsole(await feCtx(), "agno"));
    expect(files["components/copilot/approval-card.tsx"]).toBe(
      readGolden("frontend/approval-card.tsx"),
    );
  });

  it("the suggested prompts match the golden", async () => {
    const files = feFiles(emitFrontendConsole(await feCtx(), "agno"));
    expect(files["components/copilot/suggested-prompts.tsx"]).toBe(
      readGolden("frontend/suggested-prompts.tsx"),
    );
  });

  it("wires chat + provider + panels + prompts from the Copilot.frontend", async () => {
    const console = feFiles(emitFrontendConsole(await feCtx()))["components/copilot/console.tsx"];
    expect(console).toContain('const AGENT_ID = "memory-agent";');
    expect(console).toContain("<CopilotChat agentId={AGENT_ID} />");
    expect(console).toContain('runtimeUrl="/api/copilotkit"');
    expect(console).toContain('data-panel="memory-timeline"');
    expect(console).toContain('"What did I ask you to remember?"');
  });

  it("gates each write tool via useHumanInTheLoop with the approval_card copy", async () => {
    const console = feFiles(emitFrontendConsole(await feCtx()))["components/copilot/console.tsx"];
    expect(console).toContain('name: "remember",');
    expect(console).toContain('name: "forget",');
    expect(console).toContain('title="Confirm write"');
    expect(console).toContain('pick(args as Record<string, unknown>, "args.text")');
  });

  it("stamps three trusted tenant headers in the server route, not the browser", async () => {
    const files = feFiles(emitFrontendConsole(await feCtx()));
    const route = files["app/api/copilotkit/route.ts"];
    // three DNA tenancy dimensions, server-to-server (no license/namespace).
    expect(route).toContain('"X-DNA-Tenant"');
    expect(route).toContain('"X-DNA-Workspace"');
    expect(route).toContain('"X-Tenant-OID"');
    expect(route).toContain("buildAgent(AGENT_URL, dnaTenantHeaders())");
    expect(route).not.toContain("NEXT_PUBLIC");
    // the browser console forwards NO tenant headers.
    const console = files["components/copilot/console.tsx"];
    expect(console).not.toContain("dnaTenantHeaders");
    expect(console).not.toContain("headers={");
    for (const content of Object.values(files)) {
      expect(content).not.toContain("License");
      expect(content).not.toContain("Namespace");
    }
  });
});

describe("emitFrontendConsole — the per-runtime resume-adapter", () => {
  it("agno emits the native (identity) adapter — no payload rewrite", async () => {
    const adapter = feFiles(emitFrontendConsole(await feCtx(), "agno"))[
      "lib/copilot/resume-adapter.ts"
    ];
    expect(adapter).toBe(readGolden("frontend/resume-adapter.agno.ts"));
    expect(adapter).toContain("return new HttpAgent({ url, headers });");
    expect(adapter).not.toContain("body.resume");
  });

  it("agent-framework emits the {interrupts:[…]} bridge — the ONLY file that differs", async () => {
    const ctx = await feCtx();
    const res = emitFrontendConsole(ctx, "agent-framework");
    const msaf = feFiles(res);
    expect(msaf["lib/copilot/resume-adapter.ts"]).toBe(
      readGolden("frontend/resume-adapter.msaf.ts"),
    );
    expect(msaf["lib/copilot/resume-adapter.ts"]).toContain("interrupts:");
    expect(res.target).toBe("copilotkit-agent-framework");
    const agno = feFiles(emitFrontendConsole(ctx, "agno"));
    for (const path of Object.keys(agno)) {
      if (path !== "lib/copilot/resume-adapter.ts") {
        expect(msaf[path]).toBe(agno[path]);
      }
    }
  });

  it("rejects an unknown runtime and a copilot with no frontend", async () => {
    const ctx = await feCtx();
    expect(() => emitFrontendConsole(ctx, "carrier-pigeon")).toThrow();
    const bare = await feCtx("pure-action-copilot");
    expect(() => emitFrontendConsole(bare)).toThrow();
  });

  it("leaves the backend copilot emit unchanged (agent + serving only)", async () => {
    const res = new AgnoEmitter().emit(await feCtx());
    expect(new Set(res.artifacts.map((a) => a.role))).toEqual(new Set(["agent", "serving"]));
  });
});
