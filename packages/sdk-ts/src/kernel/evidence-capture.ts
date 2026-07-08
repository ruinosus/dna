/**
 * Evidence capture handler — creates Evidence documents with SHA-256 hashes.
 *
 * ``computeContentHash`` produces a deterministic SHA-256 digest of
 * canonical JSON (recursively sorted keys, no whitespace) so that key
 * ordering never affects the hash.
 *
 * 1:1 parity with Python dna.extensions.evidence.builder.
 */

import type { HookContext } from "./hooks.js";

const EVAL_KINDS = new Set(["EvalRun", "EvalBaseline", "Finding"]);

// ---------------------------------------------------------------------------
// Policy evaluation
// ---------------------------------------------------------------------------

/**
 * Check whether *eventType* should be auto-captured per *policySpec*.
 *
 * Generic policy-evaluation logic (reads a plain EvidencePolicy spec dict),
 * kernel-owned so the microkernel's capture handler needs no extension
 * import (s-invert-evidence-capture-dep). EvidenceExtension re-exports this
 * as its public API.
 */
export function shouldCapture(
  policySpec: Record<string, unknown>,
  eventType: string,
): boolean {
  if (policySpec.auto_capture === false) return false;
  const events = policySpec.events;
  if (!Array.isArray(events)) return false;
  return events.includes(eventType);
}

// ---------------------------------------------------------------------------
// Canonical JSON helpers
// ---------------------------------------------------------------------------

/** Recursively sort object keys for canonical JSON (Python parity). */
function sortDeep(val: unknown): unknown {
  if (val === null || val === undefined || typeof val !== "object") return val;
  if (Array.isArray(val)) return val.map(sortDeep);
  const sorted: Record<string, unknown> = {};
  for (const key of Object.keys(val as Record<string, unknown>).sort()) {
    sorted[key] = sortDeep((val as Record<string, unknown>)[key]);
  }
  return sorted;
}

/**
 * SHA-256 of canonical JSON (async, browser-compatible).
 *
 * Uses Web Crypto API (available in Node 18+, Bun, and all browsers).
 * Matches Python: ``json.dumps(sort_keys=True, separators=(",", ":"))``
 */
export async function computeContentHash(content: unknown): Promise<string> {
  const canonical = JSON.stringify(sortDeep(content));
  const data = new TextEncoder().encode(canonical);
  const hashBuffer = await globalThis.crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

// ---------------------------------------------------------------------------
// Suite extraction
// ---------------------------------------------------------------------------

/**
 * Derive the suite name from kind + spec, with explicit override.
 *
 * - EvalRun  -> spec.suite
 * - Finding  -> spec.source
 * - Explicit parameter always wins.
 * - Non-eval kinds return null.
 */
export function extractSuite(
  kind: string,
  spec: Record<string, unknown>,
  explicit: string | null,
): string | null {
  if (explicit) return explicit;
  if (!EVAL_KINDS.has(kind)) return null;
  // The spec may be flat ({suite: "x"}) or nested ({spec: {suite: "x"}})
  // depending on whether the caller passed the raw doc or just the spec field.
  const inner = (spec.spec as Record<string, unknown>) ?? spec;
  return (inner.suite as string) || (inner.source as string) || null;
}

// ---------------------------------------------------------------------------
// Evidence document builder
// ---------------------------------------------------------------------------

export async function buildEvidenceDoc(opts: {
  eventType: string;
  kind: string;
  name: string;
  spec: Record<string, unknown>;
  author: string;
  suite?: string | null;
}): Promise<Record<string, unknown>> {
  const now = new Date();
  const suite = extractSuite(opts.kind, opts.spec, opts.suite ?? null);
  const sha256 = await computeContentHash(opts.spec);
  return {
    apiVersion: "github.com/ruinosus/dna/evidence/v1",
    kind: "Evidence",
    metadata: { name: `ev-${opts.eventType}-${sha256.slice(0, 12)}` },
    spec: {
      event_type: opts.eventType,
      sha256,
      captured_at: now.toISOString(),
      author: opts.author,
      document_ref: `${opts.kind}:${opts.name}`,
      suite,
      snapshot: opts.spec,
    },
  };
}

// ---------------------------------------------------------------------------
// Post-save hook handler factory
// ---------------------------------------------------------------------------

/**
 * The runtime capabilities the evidence-capture handler needs from the
 * kernel it captures — a read surface (`instance()._all()`, the MI internal non-deprecated twin) plus the write
 * path. Narrower than the full Kernel on purpose; the EvidenceExtension
 * feature-tests these members before wiring the handler
 * (s-dna-extension-host-contract).
 */
export interface EvidenceCaptureHost {
  instance(scope: string): { _all(kind: string): { spec: Record<string, unknown> }[] };
  writeDocument(
    scope: string,
    kind: string,
    name: string,
    raw: Record<string, unknown>,
    options?: { skipHooks?: boolean; author?: string },
  ): Promise<void>;
}

/**
 * Create a ``post_save`` handler that auto-captures Evidence documents.
 *
 * The handler inspects EvidencePolicy documents in the current scope to
 * decide whether to capture. Evidence documents themselves are skipped
 * to avoid infinite loops, and the resulting write uses ``skipHooks: true``.
 */
export function makeEvidenceCaptureHandler(kernel: EvidenceCaptureHost) {
  return (ctx: HookContext): void => {
    const { kind, name, data } = ctx;
    const eventType = (data.event_type as string) || "";

    // Never capture evidence about evidence (avoids infinite loop)
    if (kind === "Evidence") return;

    const mi = kernel.instance(ctx.scope);
    const policies = mi._all("EvidencePolicy");
    if (!policies.some((p) => shouldCapture(p.spec as Record<string, unknown>, eventType)))
      return;

    // Async: build doc then write (fire-and-forget from hook perspective)
    buildEvidenceDoc({
      eventType,
      kind: kind || "",
      name: name || "",
      spec: (data.spec as Record<string, unknown>) || {},
      author: (data.author as string) || "unknown",
      suite: data.suite as string | undefined,
    })
      .then((doc) => {
        const evidenceName = (doc.metadata as Record<string, string>).name;
        return kernel.writeDocument(ctx.scope, "Evidence", evidenceName, doc, {
          skipHooks: true,
          author: "evidence-capture",
        });
      })
      .catch((e) =>
        console.warn(`Evidence capture failed for ${kind}:${name}:`, e),
      );
  };
}
