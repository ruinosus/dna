/**
 * IntelExtension — DNA intelligence-layer data foundation.
 *
 * 1:1 parity with Python `dna.extensions.intel`.
 *
 * Registers 2 record Kinds, from descriptors (F3 — record Kinds are data, not
 * classes):
 *
 *   - IntelSource (`intel-source`) — a watched portfolio source (the
 *     "Direction" stage: what the DNA observes). One doc per source (a repo, a
 *     scope, or an external URL) carrying its research cadence, actionability
 *     threshold, Priority Intelligence Requirements (PIRs) and mute state.
 *     TENANTED — a source is the tenant's OWN watchlist (per-tenant user
 *     data), NOT a shared `_lib` default. It is deliberately NOT inheritable
 *     (never in DEFAULT_INHERITABLE_KINDS_V1), so TENANTED is correct.
 *   - Insight (`intel-insight`, kind name `IntelInsight`) — the
 *     dissemination unit: a ranked, actionable insight that the
 *     ranker/digest/dedup/feedback stages reference. TENANTED for the same
 *     reason (per-tenant generated data). Embeddable (`embed: [title, fact]`)
 *     so a later dedup story can do semantic recall.
 *
 * This is the foundation ONLY — the research/ranker/digest/feedback stages
 * land in later stories; here we ship just the two data Kinds.
 */

import type { ExtensionHost, Extension } from "../kernel/protocols.js";
import { loadDescriptors } from "../kernel/descriptor-loader.js";

export class IntelExtension implements Extension {
  name = "intel";
  version = "1.0.0";

  register(kernel: ExtensionHost) {
    // F3: both Kinds ship as kinds/*.kind.yaml package data (byte-identical
    // Py↔TS mirror), registered through the SAME funnel as per-scope
    // KindDefinitions (plane lint + digest idempotency + builtin conflict
    // marker).
    for (const raw of loadDescriptors(import.meta.url, "intel/kinds")) {
      kernel.kindFromDescriptor(raw);
    }
  }
}
