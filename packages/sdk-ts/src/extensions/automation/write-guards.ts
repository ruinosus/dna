/**
 * Automation-owned write-path guards (s-tier-a-automation).
 *
 * One `pre_save` VETO hook that makes an Automation write *fully valid or
 * not persisted*, covering what is Automation's OWN:
 *
 * - **Semantics the schema cannot express:**
 *
 *    - **cron expression** (`on.type: cron`) — parsed by a zero-dependency
 *      5-field validator (documented decision: a cron lib would be a
 *      runtime dep for one field; the grammar below covers the standard
 *      crontab core — `*`, numbers, ranges, lists, steps — and rejects the
 *      rest loudly. Name aliases like `JAN`/`MON` are NOT supported.)
 *    - **hook name** (`on.type: hook`) — must belong to the kernel's typed
 *      hook vocabulary `KNOWN_HOOK_NAMES` (s-dna-typed-hook-names). The
 *      HookRegistry itself tolerates custom names (warn-once), but an
 *      Automation is DATA a host executor dispatches on: a misspelled hook
 *      would be declared, listed, and silently never fire — so here the
 *      unknown name is a veto, not a warning.
 *
 * The Python twin has one extra FIRST step this side does not need: PyYAML
 * reads a bare `on:` key as boolean `True` (YAML 1.1), so the Py guard
 * heals a top-level `True` spec key back to `"on"` before validating.
 * js-yaml keeps `on` a string — no trap, no step.
 *
 * Schema SHAPE at write time (originally this guard's step 1) is no longer
 * Automation-specific: `s-write-path-validation` (i-008) generalized it —
 * `WritePipeline.write` validates every doc's spec against the Kind's
 * declared `schema()` after the veto hooks run. This guard keeps only the
 * semantics JSON Schema cannot express.
 *
 * A throw from the guard vetoes the write (nothing is persisted). The hook
 * fires for EVERY `kernel.writeDocument` regardless of `skipHooks` — it is
 * an integrity gate, not a notification. 1:1 parity with Python
 * `dna.extensions.automation.write_guards`.
 */

import type { PreSaveContext } from "../../kernel/hooks.js";
import { KNOWN_HOOK_NAMES } from "../../kernel/hooks.js";

const KIND = "Automation";

// After helix (10/20/30) and SDLC bitemporal (40).
export const PRIORITY_TRIGGER_GUARD = 50;

// [label, lo, hi] per cron field, in order. dow accepts 0-7 (0 and 7 both
// mean Sunday, matching crontab).
const CRON_FIELDS: ReadonlyArray<readonly [string, number, number]> = [
  ["minute", 0, 59],
  ["hour", 0, 23],
  ["day-of-month", 1, 31],
  ["month", 1, 12],
  ["day-of-week", 0, 7],
];

function cronError(expr: string, detail: string): Error {
  return new Error(
    `invalid cron expression ${JSON.stringify(expr)}: ${detail}. Expected ` +
      `5 whitespace-separated fields 'min hour dom mon dow' (e.g. ` +
      `'0 10 * * 1,3,5'); each field is '*', a number, a range 'a-b', a ` +
      `list 'a,b,c' or a step '*/n' / 'a-b/n'. Name aliases (JAN/MON) ` +
      `are not supported.`,
  );
}

const DIGITS = /^\d+$/;

/**
 * Validate a 5-field cron expression. Throws on the first problem
 * (didactic message); returns void when valid.
 */
export function validateCronExpression(expr: string): void {
  const fields = expr.split(/\s+/).filter((f) => f.length > 0);
  if (fields.length !== 5) {
    throw cronError(expr, `expected 5 fields, got ${fields.length}`);
  }
  for (let i = 0; i < 5; i++) {
    const value = fields[i]!;
    const [label, lo, hi] = CRON_FIELDS[i]!;
    for (const item of value.split(",")) {
      if (!item) throw cronError(expr, `empty list item in ${label} field`);
      const slash = item.indexOf("/");
      const base = slash === -1 ? item : item.slice(0, slash);
      if (slash !== -1) {
        const step = item.slice(slash + 1);
        if (!DIGITS.test(step) || parseInt(step, 10) < 1) {
          throw cronError(
            expr,
            `step '/${step}' in ${label} field must be a positive integer`,
          );
        }
        if (base === "") {
          throw cronError(expr, `step without a base in ${label} field`);
        }
      }
      if (base === "*") continue;
      const dash = base.indexOf("-");
      const bounds = dash === -1
        ? [base]
        : [base.slice(0, dash), base.slice(dash + 1)];
      for (const bound of bounds) {
        if (!DIGITS.test(bound)) {
          throw cronError(
            expr,
            `${JSON.stringify(bound)} in ${label} field is not a number`,
          );
        }
        const n = parseInt(bound, 10);
        if (n < lo || n > hi) {
          throw cronError(expr, `${n} out of range ${lo}-${hi} for ${label}`);
        }
      }
      if (dash !== -1 && parseInt(bounds[0]!, 10) > parseInt(bounds[1]!, 10)) {
        throw cronError(
          expr,
          `inverted range ${JSON.stringify(base)} in ${label} field`,
        );
      }
    }
  }
}

/**
 * Veto an Automation write that is not fully valid.
 *
 * Checks the semantics JSON Schema cannot express (cron grammar,
 * hook-name vocabulary). Schema SHAPE is validated by the kernel's
 * generic write-path step (s-write-path-validation, i-008), which runs
 * after the veto hooks — this guard no longer duplicates it.
 */
export function automationTriggerGuard(ctx: PreSaveContext): void {
  if (ctx.kind !== KIND || typeof ctx.raw !== "object" || ctx.raw === null) {
    return;
  }
  const spec = (ctx.raw as Record<string, unknown>).spec;
  if (typeof spec !== "object" || spec === null) return;
  // Semantics the schema cannot express (shape itself is the kernel's
  // generic write-path validation, which runs after the veto hooks).
  const on = (spec as Record<string, unknown>).on;
  if (typeof on !== "object" || on === null) return;
  const onType = (on as Record<string, unknown>).type;
  if (onType === "cron") {
    const cron = (on as Record<string, unknown>).cron;
    if (typeof cron === "string") validateCronExpression(cron);
  } else if (onType === "hook") {
    const hook = (on as Record<string, unknown>).hook;
    if (typeof hook === "string" && !KNOWN_HOOK_NAMES.includes(hook as never)) {
      throw new Error(
        `Automation ${JSON.stringify(ctx.name)} declares on.hook=` +
          `${JSON.stringify(hook)}, which is not a kernel lifecycle hook. ` +
          `Known hooks: ${JSON.stringify([...KNOWN_HOOK_NAMES].sort())}. A ` +
          `misspelled hook would be declared but never fire — fix the name ` +
          `(the vocabulary is typed: HookName in kernel/hooks).`,
      );
    }
  }
}

/** The narrow host surface the guard registration needs. */
interface HookHost {
  hooks: {
    onVeto(
      hook: string,
      fn: (ctx: PreSaveContext) => void | Promise<void>,
      opts?: { priority?: number; key?: string },
    ): void;
  };
}

/**
 * Wire the Automation write guard as a `pre_save` veto hook.
 *
 * The key makes the registration idempotent (re-loading the extension
 * onto a shared HookRegistry replaces instead of stacking duplicates).
 */
export function registerWriteGuards(kernel: unknown): void {
  (kernel as HookHost).hooks.onVeto("pre_save", automationTriggerGuard, {
    priority: PRIORITY_TRIGGER_GUARD,
    key: "automation.trigger-guard",
  });
}
