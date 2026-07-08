// F3 lote-3: the EvidenceKind class is extinct — the kind is synthesized
// from kinds/evidence.kind.yaml via the loadDescriptors loop in register();
// assertions read the PORT through the real funnel.
import { describe, test, expect } from "bun:test";
import { EvidenceExtension, shouldCapture } from "../../src/extensions/evidence.js";
import { Kernel } from "../../src/kernel/index.js";

function _env(spec: Record<string, unknown>) {
  return { apiVersion: "github.com/ruinosus/dna/evidence/v1", kind: "Evidence",
           metadata: { name: "ev-1" }, spec };
}

describe("EvidenceExtension", () => {
  const kernel = new Kernel();
  kernel.load(new EvidenceExtension());

  const evidenceKind = kernel.kindPortFor("Evidence")! as any;
  const policyKind = kernel.kindPortFor("EvidencePolicy")! as any;

  test("registers both kinds", async () => {
    expect(evidenceKind).toBeDefined();
    expect((evidenceKind as { __builtin_descriptor__?: boolean }).__builtin_descriptor__).toBe(true);
    expect(policyKind).toBeDefined();
  });

  test("extension metadata", async () => {
    const ext = new EvidenceExtension();
    expect(ext.name).toBe("evidence");
    expect(ext.version).toBe("1.0.0");
  });

  // ─── Evidence Kind ──────────────────────────────────────────────

  describe("EvidenceKind", () => {
    test("alias", async () => {
      expect(evidenceKind.alias).toBe("evidence-evidence");
    });

    test("apiVersion", async () => {
      expect(evidenceKind.apiVersion).toBe("github.com/ruinosus/dna/evidence/v1");
    });

    test("storage container", async () => {
      expect(evidenceKind.storage.container).toBe("evidence");
    });

    test("graph style", async () => {
      expect(evidenceKind.graphStyle.fill).toBe("#059669");
    });

    test("schema required fields", async () => {
      const schema = evidenceKind.schema();
      // s-evidence-schema-reconciliation: only event_type is in ALL 361 real
      // docs — the gaia-event shape (64) has no sha256/captured_at.
      expect(new Set(schema.required)).toEqual(new Set(["event_type"]));
    });

    test("schema event_type enum", async () => {
      const schema = evidenceKind.schema();
      const enumVals: string[] = schema.properties.event_type.enum;
      expect(enumVals).toContain("document_created");
      expect(enumVals).toContain("eval_run_completed");
      expect(enumVals).toContain("custom");
    });

    test("schema event_type enum includes gaia.* values", async () => {
      const enumVals: string[] = evidenceKind.schema().properties.event_type.enum;
      for (const ev of [
        "gaia.assessment.started", "gaia.assessment.completed",
        "gaia.assessment.failed", "gaia.pillar.completed",
        "gaia.pillar.threshold_breach", "gaia.report.issued",
      ]) {
        expect(enumVals).toContain(ev);
      }
    });

    test("schema declares the gaia-event shape properties", async () => {
      const props = evidenceKind.schema().properties;
      expect(props.payload.type).toBe("object");
      expect(props.source_kind.type).toBe("string");
      expect(props.source_name.type).toBe("string");
      expect(props.created_at.format).toBe("date-time");
    });

    test("validates by construction (descriptor-synthesized port)", async () => {
      // F3 lote-3: no validateOnParse knob — a DeclarativeKindPort with a
      // schema always validates the envelope spec.
      expect((evidenceKind as { __builtin_descriptor__?: boolean }).__builtin_descriptor__).toBe(true);
    });

    test("parse accepts the gaia event shape (no sha256 — the 64 docs that failed)", async () => {
      const raw = _env({
        event_type: "gaia.pillar.completed", created_at: "2026-06-07T00:00:00Z",
        payload: { score: 0.9 }, source_kind: "Assessment", source_name: "asmt-1",
      });
      expect(evidenceKind.parse(raw)).toBe(raw);
    });

    test("parse rejects a missing event_type", async () => {
      expect(() => evidenceKind.parse(_env({ sha256: "abc", captured_at: "2026-06-07T00:00:00Z" })))
        .toThrow(/event_type/);
    });

    test("parse rejects an unknown event_type", async () => {
      expect(() => evidenceKind.parse(_env({ event_type: "not.a.real.event" })))
        .toThrow(/validation failed/);
    });

    test("schema sha256", async () => {
      const schema = evidenceKind.schema();
      expect(schema.properties.sha256.type).toBe("string");
    });

    test("schema captured_at", async () => {
      const schema = evidenceKind.schema();
      expect(schema.properties.captured_at.format).toBe("date-time");
    });

    test("schema snapshot", async () => {
      const schema = evidenceKind.schema();
      expect(schema.properties.snapshot.type).toBe("object");
      expect(schema.properties.snapshot.additionalProperties).toBe(true);
    });

    test("parse returns raw (envelope — the shape the kernel always passes)", async () => {
      const raw = _env({ event_type: "custom", sha256: "abc", captured_at: "2026-01-01T00:00:00Z" });
      expect(evidenceKind.parse(raw)).toBe(raw);
    });

    test("is not root", async () => {
      expect(evidenceKind.isRoot).toBe(false);
    });
  });

  // ─── EvidencePolicy Kind ────────────────────────────────────────

  describe("EvidencePolicyKind", () => {
    test("alias", async () => {
      expect(policyKind.alias).toBe("evidence-policy");
    });

    test("apiVersion", async () => {
      expect(policyKind.apiVersion).toBe("github.com/ruinosus/dna/evidence/v1");
    });

    test("storage container", async () => {
      expect(policyKind.storage.container).toBe("evidence-policies");
    });

    test("graph style", async () => {
      expect(policyKind.graphStyle.fill).toBe("#0891B2");
    });

    test("schema required fields", async () => {
      const schema = policyKind.schema();
      expect(schema.required).toEqual(["events"]);
    });

    test("schema events is array", async () => {
      const schema = policyKind.schema();
      expect(schema.properties.events.type).toBe("array");
    });

    test("schema auto_capture default", async () => {
      const schema = policyKind.schema();
      expect(schema.properties.auto_capture.default).toBe(true);
    });

    test("schema retention_days default", async () => {
      const schema = policyKind.schema();
      expect(schema.properties.retention_days.default).toBe(365);
    });
  });
});

// ─── shouldCapture helper ───────────────────────────────────────────

describe("shouldCapture", () => {
  test("matches policy events", async () => {
    const policy = { events: ["eval_run_completed", "finding_created"], auto_capture: true };
    expect(shouldCapture(policy, "eval_run_completed")).toBe(true);
    expect(shouldCapture(policy, "document_created")).toBe(false);
  });

  test("disabled when auto_capture is false", async () => {
    const policy = { events: ["eval_run_completed"], auto_capture: false };
    expect(shouldCapture(policy, "eval_run_completed")).toBe(false);
  });

  test("defaults auto_capture to true", async () => {
    const policy = { events: ["finding_created"] };
    expect(shouldCapture(policy, "finding_created")).toBe(true);
  });
});
