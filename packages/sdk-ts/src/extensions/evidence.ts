/**
 * EvidenceExtension — audit trail Kinds for the GAIA pipeline.
 *
 * Registers 2 KindPorts:
 *   - Evidence       (evidence-evidence)  — immutable audit event record
 *   - EvidencePolicy (evidence-policy)    — controls which events are auto-captured
 *
 * All use YAML storage with no custom reader/writer — the generic
 * machinery handles serialization. 1:1 parity with Python.
 */

import type { Extension, ExtensionHost } from "../kernel/protocols.js";
import { KindBase } from "../kernel/kind_base.js";
import { SD } from "../kernel/protocols.js";
import type { Document } from "../kernel/document.js";
import { makeEvidenceCaptureHandler } from "../kernel/evidence-capture.js";
import type { EvidenceCaptureHost } from "../kernel/evidence-capture.js";
// shouldCapture is generic policy-evaluation logic that now lives in the
// kernel (s-invert-evidence-capture-dep) so the microkernel's evidence-capture
// handler needs no extension import. Re-exported here as the extension's
// public API (index.ts + callers import it from this module).
import { loadDescriptors } from "../kernel/descriptor-loader.js";
export { shouldCapture } from "../kernel/evidence-capture.js";

const API_VERSION = "github.com/ruinosus/dna/evidence/v1";

// Evidence — F3 lote-3 (spec 2026-06-10-kinds-descriptor-f3): the twin
// EvidenceKind classes (Py+TS) were DELETED — synthesized from
// kinds/evidence.kind.yaml (parity-critical package data, byte-identical
// Py↔TS) via the loadDescriptors loop in register(). Equivalence with the
// extinct class frozen in test_lote3_descriptor_equivalence.py (golden:
// tests/goldens/lote3/Evidence.golden.json).

// ---------------------------------------------------------------------------
// EvidencePolicy Kind
// ---------------------------------------------------------------------------

class EvidencePolicyKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly kind = "EvidencePolicy";
  readonly alias = "evidence-policy";
  readonly origin = "github.com/ruinosus/dna/evidence";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly storage = SD.yaml("evidence-policies");
  readonly graphStyle = { fill: "#0891B2", stroke: "#0E7490", textColor: "#fff" };
  readonly asciiIcon = "📑";
  readonly displayLabel = "Evidence Policies";
  readonly docs =
    "An EvidencePolicy controls which event types are automatically " +
    "captured as Evidence documents. Declares the list of event types " +
    "to watch, whether auto-capture is enabled, and retention period.";

  dependencies() { return null; }
  schema() {
    return {
      type: "object",
      required: ["events"],
      additionalProperties: true,
      properties: {
        events: {
          type: "array",
          items: { type: "string" },
        },
        auto_capture: { type: "boolean", default: true },
        retention_days: { type: "integer", default: 365 },
      },
    };
  }
  summary(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      events: spec.events ?? [],
      auto_capture: spec.auto_capture ?? true,
      retention_days: spec.retention_days ?? 365,
    };
  }
}

// ---------------------------------------------------------------------------
// Extension
// ---------------------------------------------------------------------------

export class EvidenceExtension implements Extension {
  readonly name = "evidence";
  readonly version = "1.0.0";

  register(kernel: ExtensionHost): void {
    kernel.kind(new EvidencePolicyKind());
    // F3 lote-3: builtin record Kinds as descriptors (Evidence) —
    // kinds/*.kind.yaml package data through the same funnel as per-scope
    // KindDefinitions (plane lint + digest idempotency + conflict marker).
    for (const raw of loadDescriptors(import.meta.url, "evidence/kinds")) {
      kernel.kindFromDescriptor(raw);
    }

    // Register the evidence auto-capture handler when the host also
    // exposes the RUNTIME capabilities the handler closes over
    // (instance + writeDocument — the full Kernel does; a bare
    // ExtensionHost slice need not). Feature-test, then narrow to the
    // handler's own declared host contract.
    const cap = kernel as ExtensionHost & Partial<EvidenceCaptureHost>;
    if (typeof cap.instance === "function" && typeof cap.writeDocument === "function") {
      kernel.on("post_save", makeEvidenceCaptureHandler(cap as ExtensionHost & EvidenceCaptureHost));
    }
  }
}
