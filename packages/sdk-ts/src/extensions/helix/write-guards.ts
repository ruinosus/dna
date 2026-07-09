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
 * - prompt-budget enforcement (priority 20) — an Agent whose instruction
 *   exceeds its model's `instruction_token_cap` (read from the
 *   ModelProfile registry — never hardcode token caps) is blocked when
 *   the model is strict (voice persona / `realtime: true` profile) and
 *   warned when it is a chat model (fail-open on unknown model / missing
 *   cap / instruction_file).
 * - Kind-Writer contract      (priority 30) — a Agent declaring
 *   `writes_kind` must satisfy the slot↔schema contract at write time.
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
import {
  evaluateInstructionBudget,
  PromptBudgetExceededError,
} from "../../kernel/prompt-budget.js";

const KIND = "Agent";

// Ordered ahead of other extensions' guards (Py: SDLC bitemporal = 40).
export const PRIORITY_FORK_GUARD = 10;
export const PRIORITY_PROMPT_BUDGET = 20;
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

/** The Kernel surface the prompt-budget guard reads through.
 *  `PreSaveContext.kernel` is typed `unknown` (the hook context crosses
 *  module boundaries); this named contract is the guard's narrowing. */
interface PromptBudgetHost {
  modelProfile(
    idOrAlias: string,
  ): Promise<{ spec?: Record<string, unknown> } | null>;
  _DEFAULT_REALTIME_MODEL: string;
}

/**
 * Enforce the Agent instruction budget against the ModelProfile registry.
 *
 * CONTRACT — never hardcode token caps: the cap ALWAYS comes from the
 * ModelProfile registry (`kernel.modelProfile(idOrAlias)` → the
 * `modelreg-model-profile` Kind in `_lib`), never from a literal in code.
 *
 * Three paths (s-tier-a-modelprofile):
 * - VETO — strict model (voice persona, or `realtime: true` profile) and
 *   the instruction estimate exceeds `instruction_token_cap`.
 * - WARN — a chat Agent (`spec.model` declared, non-realtime profile)
 *   exceeds the cap: tolerated but logged loud.
 * - PASS — no model declared, no profile found, no cap, or within budget.
 *   Enforcement is opt-in by DATA: writing a profile with a cap arms it.
 *
 * Fail-open on uncounted text (instruction_file / non-string body).
 * `DNA_PROMPT_BUDGET_ENFORCE=0` downgrades the veto to a warn.
 *
 * 1:1 parity with Python `prompt_budget_guard`.
 */
export async function promptBudgetGuard(ctx: PreSaveContext): Promise<void> {
  if (ctx.kind !== KIND || !ctx.raw || typeof ctx.raw !== "object") return;
  const spec = ctx.raw.spec;
  if (!spec || typeof spec !== "object") return;
  const s = spec as Record<string, unknown>;
  const vp = s.voice_persona;
  const isVoice = vp !== undefined && vp !== null;
  const kernel = ctx.kernel as PromptBudgetHost;
  let modelId: string;
  if (isVoice) {
    const vpModel =
      vp && typeof vp === "object"
        ? (vp as Record<string, unknown>).model
        : null;
    // s-realtime-model-single-default — the kernel getter reads
    // DNA_VOICE_REALTIME_MODEL at access-time so the cap and the minted
    // voice session can't drift to different realtime models.
    modelId =
      (typeof vpModel === "string" && vpModel) || kernel._DEFAULT_REALTIME_MODEL;
  } else {
    const declared = s.model;
    if (!declared || typeof declared !== "string") {
      return; // PASS — no model declared, nothing to enforce against.
    }
    modelId = declared;
  }
  const profile = await kernel.modelProfile(modelId);
  let instruction = typeof s.instruction === "string" ? s.instruction : "";
  // v1 limitation: no cheap kernel helper resolves instruction_file here;
  // if the body lives in a file, warn + fail-open (don't block on
  // uncounted text).
  if (!instruction && s.instruction_file) {
    console.warn(
      `[prompt-budget] agent '${ctx.name}' uses instruction_file; ` +
        `token budget NOT checked (v1 limitation)`,
    );
  }
  const cap = (profile?.spec ?? {})["instruction_token_cap"];
  if (profile === null || typeof cap !== "number" || !instruction) {
    // PASS — enforcement is opt-in: no profile / no cap / uncounted text
    // never blocks. Voice stays LOUD (the outage class this guard exists
    // for); a chat model without a profile is the common case and stays
    // quiet.
    if (isVoice) {
      console.warn(
        `[prompt-budget] no ModelProfile/cap for model '${modelId}' ` +
          `(agent '${ctx.name}'); cap not enforced`,
      );
    }
    return;
  }
  const verdict = evaluateInstructionBudget(instruction, { cap });
  if (!verdict.exceeded) return; // PASS — within budget.
  const strict =
    isVoice || Boolean((profile.spec ?? {})["realtime"]);
  if (strict && process.env.DNA_PROMPT_BUDGET_ENFORCE !== "0") {
    throw new PromptBudgetExceededError({
      modelId,
      estimatedTokens: verdict.estimatedTokens,
      cap,
      agentName: ctx.name,
    });
  }
  // WARN — chat model over budget, or strict veto downgraded by the
  // kill-switch. Loud either way: the cap came from the ModelProfile
  // registry, the fix is trimming the instruction (or updating the
  // profile if the model's real cap changed — never a hardcoded number).
  console.warn(
    `[prompt-budget] agent '${ctx.name}' instruction is ~` +
      `${verdict.estimatedTokens} tokens, over the ${cap}-token ` +
      `instruction_token_cap of model '${modelId}' (ModelProfile registry)` +
      (strict ? " — VETO downgraded to WARN (DNA_PROMPT_BUDGET_ENFORCE=0)" : "") +
      `. Trim the instruction or move detail to tool-discoverable docs.`,
  );
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
  kernel.hooks.onVeto("pre_save", promptBudgetGuard, {
    priority: PRIORITY_PROMPT_BUDGET, key: "helix.prompt-budget",
  });
  kernel.hooks.onVeto("pre_save", kindWriterContractGuard, {
    priority: PRIORITY_KIND_WRITER, key: "helix.kind-writer-contract",
  });
}
