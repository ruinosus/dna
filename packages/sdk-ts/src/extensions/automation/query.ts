/**
 * Query helpers a host executor uses to read Automation docs.
 *
 * The SDK declares and validates automations; the HOST executes them (see
 * docs/concepts/builtin-kinds.md — the execution extension point). These
 * helpers are the read side of that contract, built strictly on the
 * blessed instance query surface (`instance.all`): no kernel method is
 * added — listing automations is extension domain knowledge, not
 * microkernel surface.
 *
 * Usage (host executor):
 *
 *   const mi = await kernel.instance("my-scope");
 *   for (const doc of automationsFor(mi, "cron")) {
 *     schedule(triggerKey(doc), doc.spec.runner, doc.spec);
 *   }
 *
 * 1:1 parity with Python `dna.extensions.automation.query`.
 */

import type { Document } from "../../kernel/document.js";

const KIND = "Automation";

/** The `on.type` discriminator vocabulary (mirrors the descriptor enum). */
export const TRIGGER_TYPES = ["cron", "hook", "tool"] as const;

export type TriggerType = (typeof TRIGGER_TYPES)[number];

/** The narrow instance surface the helpers read through. */
interface QueryableInstance {
  all(kind: string): Document[];
}

function specOf(doc: Document): Record<string, unknown> {
  const spec = (doc as { spec?: unknown }).spec;
  return typeof spec === "object" && spec !== null && !Array.isArray(spec)
    ? (spec as Record<string, unknown>)
    : {};
}

function onOf(spec: Record<string, unknown>): Record<string, unknown> {
  const on = spec.on;
  return typeof on === "object" && on !== null && !Array.isArray(on)
    ? (on as Record<string, unknown>)
    : {};
}

/**
 * List the scope's Automation docs, filtered for a host executor.
 *
 * - `triggerType` — keep only automations whose `on.type` matches
 *   (`"cron"` / `"hook"` / `"tool"`); `null`/omitted returns all.
 * - `enabledOnly` (default true) — drop docs with `enabled: false`
 *   (declared but paused; hosts must not fire them).
 *
 * `instance` is a `ManifestInstance` — the blessed query surface. Source
 * order is preserved (inherited `_lib` defaults resolve like any other
 * Kind; a tenant overlay wins per the layer policy).
 */
export function automationsFor(
  instance: QueryableInstance,
  triggerType: TriggerType | null = null,
  opts: { enabledOnly?: boolean } = {},
): Document[] {
  const enabledOnly = opts.enabledOnly ?? true;
  if (triggerType !== null && !TRIGGER_TYPES.includes(triggerType)) {
    throw new Error(
      `unknown triggerType ${JSON.stringify(triggerType)} — expected one ` +
        `of ${JSON.stringify(TRIGGER_TYPES)}`,
    );
  }
  const out: Document[] = [];
  for (const doc of instance.all(KIND)) {
    const spec = specOf(doc);
    const on = onOf(spec);
    if (triggerType !== null && on.type !== triggerType) continue;
    if (enabledOnly && spec.enabled === false) continue;
    out.push(doc);
  }
  return out;
}

/**
 * The trigger's identifying value: the cron expression (`cron`), the
 * hook name (`hook`) or the dispatch tool name (`tool`). Null when the
 * trigger is missing/unknown.
 */
export function triggerKey(doc: Document): string | null {
  const on = onOf(specOf(doc));
  const pick =
    on.type === "cron" ? on.cron
    : on.type === "hook" ? on.hook
    : on.type === "tool" ? on.tool_name
    : null;
  return typeof pick === "string" ? pick : null;
}
