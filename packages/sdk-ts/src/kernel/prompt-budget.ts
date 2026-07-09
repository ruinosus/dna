/**
 * Prompt-budget estimation + enforcement helpers.
 *
 * 1:1 parity with Python `dna/kernel/prompt_budget.py`.
 *
 * Conservative token estimator + instruction-budget evaluator used by the
 * write-path guard (`src/extensions/helix/write-guards.ts` ::
 * promptBudgetGuard) that blocks a strict/voice Agent whose instruction
 * exceeds its model's `instruction_token_cap`.
 *
 * CONTRACT — never hardcode token caps: the cap the evaluator receives
 * ALWAYS comes from the ModelProfile registry
 * (`kernel.modelProfile(idOrAlias)`), never from a literal in code.
 * Motivated by a real outage: a 17269-token voice persona silently
 * exceeded the realtime model's 16384-token session-instructions cap.
 */

/** Conservative (over-counts); mirrors the Python CHARS_PER_TOKEN. */
export const CHARS_PER_TOKEN = 3.5;

export class PromptBudgetExceededError extends Error {
  readonly modelId: string;
  readonly estimatedTokens: number;
  readonly cap: number;
  readonly agentName: string;

  constructor(opts: {
    modelId: string;
    estimatedTokens: number;
    cap: number;
    agentName: string;
  }) {
    super(
      `Agent '${opts.agentName}' instruction is ~${opts.estimatedTokens} tokens, ` +
        `over the ${opts.cap}-token instruction cap of model '${opts.modelId}'. ` +
        `Trim the instruction or move detail to tool-discoverable docs. ` +
        `(The cap comes from the model's ModelProfile doc — update the ` +
        `profile if the model's real cap changed; never hardcode caps.)`,
    );
    this.name = "PromptBudgetExceededError";
    this.modelId = opts.modelId;
    this.estimatedTokens = opts.estimatedTokens;
    this.cap = opts.cap;
    this.agentName = opts.agentName;
  }
}

export function estimateTokens(charCount: number): number {
  return Math.ceil(charCount / CHARS_PER_TOKEN);
}

export interface BudgetVerdict {
  exceeded: boolean;
  estimatedTokens: number;
  cap: number;
}

export function evaluateInstructionBudget(
  instruction: string,
  opts: { cap: number },
): BudgetVerdict {
  const tok = estimateTokens((instruction ?? "").length);
  return { exceeded: tok > opts.cap, estimatedTokens: tok, cap: opts.cap };
}
