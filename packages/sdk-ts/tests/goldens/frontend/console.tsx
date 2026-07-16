"use client";

// DNA-emitted CopilotKit console for memory-agent.
//
// The shared, runtime-agnostic console the DNA copilot emit produces from a
// `Copilot.frontend` block: a chat (`CopilotChat`) beside a canvas of panels
// driven by the agent's shared state (`useAgent`), starter prompts, and — when
// the copilot gates write tools — an approval card per gated tool
// (`useHumanInTheLoop`). Wire each panel's body to your domain UI; everything
// here is emitted from the declarative Copilot. Never hand-edit: re-emit.
import {
  CopilotChat,
  CopilotKitProvider,
  useAgent,
  useHumanInTheLoop,
} from "@copilotkit/react-core/v2";
import "@copilotkit/react-core/v2/styles.css";
import { z } from "zod";

import { ApprovalCard } from "@/components/copilot/approval-card";
import { SuggestedPrompts } from "@/components/copilot/suggested-prompts";

const AGENT_ID = "memory-agent";

// Starter prompts from the Copilot's `frontend.suggested_prompts`.
const SUGGESTED_PROMPTS: string[] = [
  "What did I ask you to remember?",
];

// Read a dotted path (e.g. "args.text") out of a paused tool's args.
function pick(args: Record<string, unknown>, path: string): string {
  const value = path
    .split(".")
    .filter((p) => p !== "args")
    .reduce<unknown>((cur, key) => (cur as Record<string, unknown> | undefined)?.[key], args);
  return value == null ? "" : String(value);
}

function Console() {
  const { agent } = useAgent({ agentId: AGENT_ID });

  // HITL write-gate: `forget` pauses the run for human approval.
  useHumanInTheLoop({
    name: "forget",
    description: "Approve the forget write before it runs.",
    parameters: z.object({}).passthrough(),
    render: ({ args, status, respond }) => (
      <ApprovalCard
        title="Confirm write"
        details={pick(args as Record<string, unknown>, "args.text")}
        reason={pick(args as Record<string, unknown>, "args.reason")}
        status={status as "inProgress" | "executing" | "complete"}
        respond={respond as (decision: { approved: boolean; edits?: string }) => void}
      />
    ),
  });
  // HITL write-gate: `remember` pauses the run for human approval.
  useHumanInTheLoop({
    name: "remember",
    description: "Approve the remember write before it runs.",
    parameters: z.object({}).passthrough(),
    render: ({ args, status, respond }) => (
      <ApprovalCard
        title="Confirm write"
        details={pick(args as Record<string, unknown>, "args.text")}
        reason={pick(args as Record<string, unknown>, "args.reason")}
        status={status as "inProgress" | "executing" | "complete"}
        respond={respond as (decision: { approved: boolean; edits?: string }) => void}
      />
    ),
  });
  return (
    <div className="dna-console">
      <main className="dna-console-main">
        <SuggestedPrompts agentId={AGENT_ID} prompts={SUGGESTED_PROMPTS} />
        <div className="dna-canvas">
          <section className="dna-panel" data-panel="memory-timeline">
            <h3>memory-timeline</h3>
            <pre>
              {JSON.stringify(
                (agent.state as Record<string, unknown> | undefined)?.["memory-timeline"] ?? null,
                null,
                2,
              )}
            </pre>
          </section>
        </div>
      </main>
      <aside className="dna-console-chat">
        <CopilotChat agentId={AGENT_ID} />
      </aside>
    </div>
  );
}
// Inbound tenant headers the /agui backend derives into run-state. DNA's tenant
// model is `tenant` (the workspace / Entra `tid`) + `personal:<oid>` (per-user
// memory, `oid` server-derived). Only `X-DNA-Tenant` is set here from the app's
// session; `X-Tenant-OID` is added server-side from the verified access token
// (never trust a client-supplied oid). No license/namespace dimension exists.
function dnaTenantHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const tenant = process.env.NEXT_PUBLIC_DNA_TENANT;
  if (tenant) headers["X-DNA-Tenant"] = tenant;
  return headers;
}
export function CopilotConsole() {
  return (
    <CopilotKitProvider runtimeUrl="/api/copilotkit" headers={dnaTenantHeaders()}>
      <Console />
    </CopilotKitProvider>
  );
}
