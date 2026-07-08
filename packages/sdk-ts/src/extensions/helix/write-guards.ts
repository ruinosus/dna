/**
 * Helix-owned write-path guards (s-write-path-despecialize).
 *
 * These rules used to live inline in `Kernel.writeDocument` as
 * `kind === "Agent"` special-cases — extension domain knowledge
 * leaked into the microkernel. They are now `pre_save` VETO hooks
 * registered by `HelixExtension.register` (the Agent owner):
 *
 * - platform-agent fork guard (priority 10) — no per-tenant overlay of a
 *   `_lib` Agent (JARVIS 16384 outage, 2026-05-29).
 * - Kind-Writer contract      (priority 30) — a Agent declaring
 *   `writes_kind` must satisfy the slot↔schema contract at write time.
 *
 * (The Python twin also registers a prompt-budget guard at priority 20 —
 * the TS kernel has no prompt-budget machinery yet, so that guard has no
 * TS twin. The priority number stays reserved.)
 *
 * A throw from a guard vetoes the write (nothing is persisted). The hooks
 * fire for EVERY `kernel.writeDocument` regardless of `skipHooks` — they
 * are integrity gates, not notifications.
 *
 * 1:1 parity with Python dna.extensions.helix.write_guards.
 */

import type { PreSaveContext } from "../../kernel/hooks.js";
import { TenantNotAllowed } from "../../kernel/protocols.js";
import type { ExtensionHost } from "../../kernel/protocols.js";
import { DEFAULT_BASE_SCOPE } from "../../kernel/index.js";

const KIND = "Agent";

// Ordered ahead of other extensions' guards (Py: SDLC bitemporal = 40).
export const PRIORITY_FORK_GUARD = 10;
export const PRIORITY_KIND_WRITER = 30;

/**
 * Block per-tenant overlays of `_lib` Agents.
 *
 * The `_lib` scope is the shared baseline (jarvis + the 12 transversais);
 * its Agents are edited in git + `dna doc apply --scope _lib` (base
 * only). A per-tenant overlay silently FORKS the persona and shadows the
 * base for that tenant's reads — the root cause of the JARVIS 16384 outage
 * (2026-05-29) and the stale-persona bug (2026-06-14). Veto it loudly.
 */
export function platformAgentForkGuard(ctx: PreSaveContext): void {
  if (ctx.scope === DEFAULT_BASE_SCOPE && ctx.kind === KIND && ctx.tenant) {
    throw new TenantNotAllowed(
      `refusing a per-tenant overlay of the _lib agent ${JSON.stringify(ctx.name)} ` +
        `(tenant=${JSON.stringify(ctx.tenant)}). _lib agents are base-only — ` +
        `edit in git + \`dna doc apply --scope _lib\`. A tenant fork shadows the ` +
        `base persona for that tenant (JARVIS 16384 outage).`,
    );
  }
}

/**
 * Validate a Kind-Writer Agent's slot↔schema contract.
 *
 * A Agent that declares `writes_kind` emits a structured doc of the
 * target Kind; validate the contract at write time (fail early), not at
 * runtime (feat/kind-writer-pilot, Task 2).
 */
/** The Kernel helper the Kind-Writer guard delegates to at WRITE time.
 *  `PreSaveContext.kernel` is typed `unknown` (the hook context crosses
 *  module boundaries); this named contract is the guard's narrowing —
 *  the generic slot↔schema validation stays a kernel helper, the
 *  TRIGGER is Helix-owned. */
interface KindWriterValidatorHost {
  _validateKindWriter(spec: Record<string, unknown>): void;
}

export function kindWriterContractGuard(ctx: PreSaveContext): void {
  if (ctx.kind !== KIND || !ctx.raw || typeof ctx.raw !== "object") return;
  const spec = ctx.raw.spec;
  if (
    spec &&
    typeof spec === "object" &&
    ((spec as Record<string, unknown>).writes_kind ||
      (spec as Record<string, unknown>).writes_kinds)
  ) {
    // The contract logic is generic (validates against the Kind registry)
    // so it stays a kernel helper; the TRIGGER is Helix-owned.
    (ctx.kernel as KindWriterValidatorHost)._validateKindWriter(
      spec as Record<string, unknown>,
    );
  }
}

/**
 * Wire the Helix write guards as `pre_save` veto hooks. Keys make the
 * registration idempotent (re-loading the extension onto a shared
 * HookRegistry replaces instead of stacking duplicates). Takes the
 * `ExtensionHost` slice (s-dna-extension-host-contract) — registration
 * goes through `kernel.hooks.onVeto` for the `key` idempotency.
 */
export function registerWriteGuards(kernel: ExtensionHost): void {
  kernel.hooks.onVeto("pre_save", platformAgentForkGuard, {
    priority: PRIORITY_FORK_GUARD, key: "helix.platform-agent-fork-guard",
  });
  kernel.hooks.onVeto("pre_save", kindWriterContractGuard, {
    priority: PRIORITY_KIND_WRITER, key: "helix.kind-writer-contract",
  });
}
