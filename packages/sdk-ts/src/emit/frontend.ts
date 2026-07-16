/**
 * DNA → **CopilotKit frontend console** scaffold (TS-only golden family; TS twin
 * of python `dna.emit.frontend`).
 *
 * Where the backend emitters materialize a servable AG-UI *backend* (agno / MS
 * Agent Framework), this module materializes the **frontend** that drives it: one
 * shared CopilotKit v2 console + a **tiny per-runtime resume-adapter**. It is the
 * concrete form of the design's §6.2 decision — *both reference consoles are ~95%
 * generic CopilotKit + `HttpAgent`; the only per-runtime seam is how a paused run
 * resumes* — so DNA emits ONE console and swaps just the resume-adapter file.
 *
 * Emitted files (all tagged `role="frontend"`):
 *   - `app/api/copilotkit/route.ts`            the CopilotRuntime `HttpAgent` bridge
 *   - `components/copilot/console.tsx`         chat + canvas panels + HITL + prompts
 *   - `components/copilot/approval-card.tsx`   the HITL card (generic)
 *   - `components/copilot/suggested-prompts.tsx` the starter-prompt chips (generic)
 *   - `lib/copilot/resume-adapter.ts`          the ONE per-runtime file
 *
 * Parameterization comes ENTIRELY from the neutral {@link EmitContext} (filled by
 * {@link buildCopilotContext} from the Copilot's `frontend` + `hitl` blocks).
 *
 * **TS-only golden family (design §7):** the emitted files are TypeScript, so this
 * family has no Py↔TS twin-diff — it is governed by its own byte-stable golden.
 * The emitter has a 1:1 Py/TS twin rendering byte-identical templates, so both
 * SDKs emit the same console. NOT a registered {@link EmitterPort} — a console
 * carries no byte-equal instruction and is outside the `buildPrompt` contract.
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import Mustache from "mustache";

import { pyIdentifier } from "./scaffold.js";
import { EmitError, EmitResult, type EmitArtifact, type EmitContext } from "./index.js";

const HERE = dirname(fileURLToPath(import.meta.url));

/** Target runtime → its resume-adapter template basename. The ONE per-runtime
 *  file: agno resumes `external_execution` gates natively (identity HttpAgent);
 *  MS Agent Framework rewrites the AG-UI `resume` array into `{interrupts:[…]}`. */
const RESUME_ADAPTERS: Record<string, string> = {
  agno: "resume-adapter.agno.ts.tmpl",
  "agent-framework": "resume-adapter.msaf.ts.tmpl",
};

/** The shared console files: [template basename, target-relative output path]. */
const SHARED: Array<[string, string]> = [
  ["route.ts.tmpl", "app/api/copilotkit/route.ts"],
  ["console.tsx.tmpl", "components/copilot/console.tsx"],
  ["approval-card.tsx.tmpl", "components/copilot/approval-card.tsx"],
  ["suggested-prompts.tsx.tmpl", "components/copilot/suggested-prompts.tsx"],
];

/** Where the emitted resume-adapter lands (its content is per-runtime). */
const ADAPTER_PATH = "lib/copilot/resume-adapter.ts";

/** Sorted runtimes with a resume-adapter (`agno`, `agent-framework`). */
export function availableFrontendRuntimes(): string[] {
  return Object.keys(RESUME_ADAPTERS).sort();
}

/** Whether `ctx` carries a `Copilot.frontend` block (a console to emit). Keyed on
 *  `frontendConsole` — a copilot with no `frontend` emits none (backend-only). */
export function hasFrontend(ctx: EmitContext): boolean {
  return ctx.frontendConsole !== null;
}

function readTemplate(name: string): string {
  const path = join(HERE, "scaffolds", "copilotkit", name);
  if (!existsSync(path)) throw new EmitError(`missing CopilotKit frontend template '${name}'`);
  return readFileSync(path, "utf-8");
}

/** Render `value` as a TS string literal (JSON string syntax is a valid TS
 *  literal). Emitted through triple-mustache so it is NOT HTML-escaped. */
function tsLiteral(value: string): string {
  return JSON.stringify(value);
}

/** Template variables for the console, projected from the neutral ctx. Every list
 *  is ordered deterministically so the golden is byte-stable. */
function frontendContext(ctx: EmitContext): Record<string, unknown> {
  const gated = [...ctx.toolsRequiringConfirmation].sort();
  const card = ctx.hitlApprovalCard;
  return {
    agent_id: ctx.name,
    agent_id_literal: tsLiteral(ctx.name),
    // the emitted backend module name (`<module>_serve.py`) — matches the Agno
    // backend scaffold's `pyIdentifier(ctx.name)` module.
    agent_module: pyIdentifier(ctx.name),
    has_panels: ctx.frontendPanels.length > 0,
    panels: ctx.frontendPanels.map((p) => ({ name: p, name_literal: tsLiteral(p) })),
    prompts: ctx.frontendSuggestedPrompts.map((p) => ({ text_literal: tsLiteral(p) })),
    gated_tools: gated.map((t) => ({ name: t, name_literal: tsLiteral(t) })),
    approval_title_literal: tsLiteral(card?.title ?? "Confirm write"),
    details_from_literal: tsLiteral(card?.details_from ?? ""),
    reason_from_literal: tsLiteral(card?.reason_from ?? ""),
    tenant_propagate: ctx.tenantPropagate,
  };
}

function frontendLosses(ctx: EmitContext): string[] {
  const out = [
    "panel bodies — each `frontend.panels` entry renders the agent's shared " +
      "state as JSON; wire the real per-panel UI to your domain (the panel " +
      "names are hints, not components)",
    "inbound-tenant values — the console forwards `X-DNA-Tenant` from the app " +
      "session and the `/agui` backend derives `X-Tenant-OID` server-side from " +
      "the verified token; the scaffold marks WHERE, the auth store is per-app",
  ];
  if (ctx.toolsRequiringConfirmation.size === 0) {
    out.push(
      "approval card — no gated write tool, so the console mounts no HITL hook; " +
        "the card component ships anyway for a later gated tool",
    );
  }
  return out;
}

/** Render the shared CopilotKit console + the `runtime` resume-adapter.
 *
 * `ctx` is an enriched copilot context ({@link buildCopilotContext}) carrying a
 * `frontend` block. `runtime` selects the ONE per-runtime file (`agno` — native
 * resume; `agent-framework` — the `{interrupts:[…]}` bridge). Returns an
 * {@link EmitResult} whose artifacts are all tagged `role="frontend"`. */
export function emitFrontendConsole(ctx: EmitContext, runtime = "agno"): EmitResult {
  if (!hasFrontend(ctx)) {
    throw new EmitError(
      `copilot '${ctx.name}' declares no \`frontend\` block — nothing to emit ` +
        "(a pure-action/back-end-only copilot has no console)",
    );
  }
  const adapterTmpl = RESUME_ADAPTERS[runtime];
  if (adapterTmpl === undefined) {
    throw new EmitError(
      `no frontend resume-adapter for runtime '${runtime}'; ` +
        `available: ${availableFrontendRuntimes().join(", ")}`,
    );
  }
  const variables = frontendContext(ctx);
  const artifacts: EmitArtifact[] = [];
  for (const [tmplName, outPath] of SHARED) {
    artifacts.push({
      path: outPath,
      content: Mustache.render(readTemplate(tmplName), variables),
      role: "frontend",
    });
  }
  artifacts.push({
    path: ADAPTER_PATH,
    content: Mustache.render(readTemplate(adapterTmpl), variables),
    role: "frontend",
  });

  return new EmitResult({
    target: `copilotkit-${runtime}`,
    artifacts,
    losses: frontendLosses(ctx),
    mapping: {
      "Copilot.frontend.console": "CopilotKit v2 console (CopilotChat + canvas)",
      "Copilot.frontend.panels[]": "components/copilot/console.tsx canvas panels",
      "Copilot.frontend.suggested_prompts[]": "SUGGESTED_PROMPTS (anti-blank-box chips)",
      "Copilot.hitl.approval_card": "components/copilot/approval-card.tsx (via useHumanInTheLoop)",
      "Tool.requires_confirmation": "useHumanInTheLoop({name}) HITL write-gate",
      "Copilot.tenant.propagate": "X-DNA-Tenant header forwarding (oid server-derived)",
      [`serving runtime = ${runtime}`]: "lib/copilot/resume-adapter.ts",
    },
  });
}
