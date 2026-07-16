// DNA-emitted resume-adapter — Agno target (memory-agent).
//
// Agno 2.7.x resumes `external_execution` HITL gates NATIVELY inside its AG-UI
// router, so no payload rewrite is needed — the adapter is the identity
// `HttpAgent` factory. (The MS Agent Framework target emits a different
// resume-adapter that rewrites the AG-UI `resume` array into the
// agent-framework `{ interrupts: [...] }` dict.) This is the ONLY per-runtime
// file in the console scaffold; everything else is shared.
import { HttpAgent } from "@ag-ui/client";

export function buildAgent(url: string, headers?: Record<string, string>): HttpAgent {
  return new HttpAgent({ url, headers });
}
