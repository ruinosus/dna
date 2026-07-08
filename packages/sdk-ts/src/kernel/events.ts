/**
 * Derive event types from Kind + update status for HookRegistry post_save.
 * 1:1 parity with Python dna.kernel.events.
 */

export const DELETE_EVENT_TYPE = "document_deleted";

const FIXED_EVENTS: Record<string, string> = {
  EvalRun: "eval_run_completed",
  EvalBaseline: "baseline_pinned",
};

const SPLIT_EVENTS: Record<string, [string, string]> = {
  Finding: ["finding_created", "finding_status_changed"],
};

export function deriveEventType(kind: string, isUpdate: boolean): string {
  const fixed = FIXED_EVENTS[kind];
  if (fixed) return fixed;
  const split = SPLIT_EVENTS[kind];
  if (split) return isUpdate ? split[1] : split[0];
  return isUpdate ? "document_modified" : "document_created";
}
