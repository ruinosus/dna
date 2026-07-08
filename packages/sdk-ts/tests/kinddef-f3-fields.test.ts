/**
 * F3: campos novos do KindDefinitionSpec (spec D2) — TS twin of
 * packages/sdk-py/tests/test_kinddef_f3_fields.py.
 */
import { describe, it, expect } from "bun:test";
import { KindBase } from "../src/kernel/kind_base.js";
import { DeclarativeKindPort } from "../src/kernel/meta.js";
import { KindDefinitionSchema } from "../src/kernel/models.js";
import { TenantScope } from "../src/kernel/protocols.js";
import { RAW_FULL, minimalRaw } from "./fixtures/kinddef-f3-raw.js";

describe("KindDefinitionSpec F3 fields (spec D2)", () => {
  it("parses all the F3 fields", () => {
    const t = KindDefinitionSchema.parse(RAW_FULL);
    const s = t.spec;
    expect(s.plane).toBe("record");
    expect(s.tenant_scope).toBe("global");
    expect(s.tenant_scope_declared).toBe(true);
    expect(s.summary).toEqual({ status: "observed", work_item: "", labels: [] });
    expect(s.embed).toEqual(["body", "labels"]);
    expect(s.is_runtime_artifact).toBe(true);
    expect(s.prompt_target_priority).toBe(0);
    expect(s.scope_inheritable).toBe(false);
    expect(s.is_overlayable).toBe(false);
    expect(s.volatile_spec_fields).toEqual(["updated_at", "closed_at"]);
  });

  it("applies back-compat defaults when the F3 fields are absent", () => {
    const s = KindDefinitionSchema.parse(minimalRaw()).spec;
    expect(s.plane).toBe("composition"); // default = today's behavior
    expect(s.tenant_scope).toBe("tenanted");
    expect(s.tenant_scope_declared).toBe(false);
    expect(s.summary).toBeNull();
    expect(s.embed == null).toBe(true);
    expect(s.is_runtime_artifact).toBe(false);
    expect(s.prompt_target_priority).toBe(5); // preserves the old hardcode
    expect(s.scope_inheritable).toBe(true);
    expect(s.is_overlayable).toBe(true);
    expect(s.volatile_spec_fields == null).toBe(true);
  });

  it("normalizes the list form of summary to a dict with per-type defaults", () => {
    const raw = {
      ...RAW_FULL,
      spec: { ...(RAW_FULL.spec as Record<string, unknown>), summary: ["status", "labels"] },
    };
    const s = KindDefinitionSchema.parse(raw).spec;
    expect(s.summary).toEqual({ status: "", labels: [] });
  });
});

// ---------------------------------------------------------------------------
// DeclarativeKindPort consumes the F3 fields
// ---------------------------------------------------------------------------

describe("DeclarativeKindPort F3 fields (spec D2)", () => {
  it("consumes the F3 fields", () => {
    const port = DeclarativeKindPort.fromTyped(KindDefinitionSchema.parse(RAW_FULL));
    expect(port.plane).toBe("record");
    // tenant_scope declared → port mirrors the class `scope` attribute
    // (e.g. KaizenKind: `scope = TenantScope.GLOBAL`)
    expect(port.scope).toBe(TenantScope.GLOBAL);
    expect(port.embedFields).toEqual(["body", "labels"]);
    expect(port.isRuntimeArtifact).toBe(true);
    expect(port.promptTargetPriority).toBe(0);
    expect(port.scopeInheritable).toBe(false);
    expect(port.isOverlayable).toBe(false);
    // declared ∪ KindBase defaults
    for (const f of ["updated_at", "closed_at", "version", "created_at"]) {
      expect(port.volatileSpecFields.has(f)).toBe(true);
    }
  });

  it("summary() projects declared fields — present from spec, absent = default", () => {
    const port = DeclarativeKindPort.fromTyped(KindDefinitionSchema.parse(RAW_FULL));
    const doc = { spec: { status: "routed" } } as never;
    expect(port.summary(doc)).toEqual({ status: "routed", work_item: "", labels: [] });
  });

  it("defaults preserve today's behavior", () => {
    const port = DeclarativeKindPort.fromTyped(KindDefinitionSchema.parse(minimalRaw()));
    expect(port.plane).toBe("composition");
    expect(port.summary({ spec: { status: "x" } } as never)).toBeNull();
    expect(port.embedFields).toBeNull();
    expect(port.isRuntimeArtifact).toBe(false);
    expect(port.promptTargetPriority).toBe(5);
    expect(port.scopeInheritable).toBe(true);
    expect(port.isOverlayable).toBe(true);
    // tenant_scope NOT declared → permissive (Phase 1 back-compat:
    // Kernel reads kp.scope ?? undefined)
    expect(port.scope == null).toBe(true);
    expect([...port.volatileSpecFields].sort()).toEqual(
      ["created_at", "updated_at", "version"],
    );
  });

  it("KindBase declares embedFields default null (D4 covers still-class kinds)", () => {
    class MinimalKind extends KindBase {
      readonly apiVersion = "test/v1";
      readonly kind = "Minimal";
      readonly alias = "test-minimal";
    }
    expect(new MinimalKind().embedFields).toBeNull();
  });
});
