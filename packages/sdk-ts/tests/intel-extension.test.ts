// s-intel-portfolio-context — intel foundation Kinds (IntelSource + Insight).
// TS twin of tests/test_intel_kinds.py.
//
// Two record Kinds shipped as the `intel` extension (F3 descriptors, record
// plane, TENANTED — per-tenant user/generated data, NOT inheritable). The
// intel Insight registers as `IntelInsight` (NOT `Insight` — that name belongs
// to the SDLC oracle Kind `sdlc-insight`); the cross-stage contract is the
// alias `intel-insight`.
import { describe, it, expect } from "bun:test";
import { Kernel } from "../src/kernel/index.js";
import { TenantScope } from "../src/kernel/protocols.js";
import { IntelExtension } from "../src/extensions/intel.js";

// ---------------------------------------------------------------------------
// Kind registration (descriptors)
// ---------------------------------------------------------------------------

describe("IntelSource Kind (descriptor)", () => {
  it("registers from kinds/intel-source.kind.yaml", () => {
    const k = new Kernel();
    k.load(new IntelExtension());
    const kp = k.kindPortFor("IntelSource");
    expect(kp).not.toBeNull();
    expect(kp!.alias).toBe("intel-source");
    expect((kp as any).plane).toBe("record");
    // TENANTED — the tenant's OWN watchlist (per-tenant data), NOT inheritable.
    expect((kp as any).scope).toBe(TenantScope.TENANTED);
    expect(kp!.storage.container).toBe("intel-sources");
    expect((kp as any).__declarative__).toBe(true);
  });
});

describe("IntelInsight Kind (descriptor)", () => {
  it("registers from kinds/insight.kind.yaml", () => {
    const k = new Kernel();
    k.load(new IntelExtension());
    const kp = k.kindPortFor("IntelInsight");
    expect(kp).not.toBeNull();
    expect(kp!.alias).toBe("intel-insight");
    expect((kp as any).plane).toBe("record");
    expect((kp as any).scope).toBe(TenantScope.TENANTED);
    expect(kp!.storage.container).toBe("intel-insights");
    expect((kp as any).__declarative__).toBe(true);
    // Embeddable so a later dedup story can recall semantically similar insights.
    expect((kp as any).embedFields).toEqual(["title", "fact"]);
  });

  it("registers as IntelInsight, never the bare Insight (no i-195 collision)", () => {
    const k = new Kernel();
    k.load(new IntelExtension());
    expect(k.kindPortFor("IntelInsight")).not.toBeNull();
    // The bare `Insight` name belongs to the SDLC oracle Kind — loading only
    // the intel extension, it is absent.
    expect(k.kindPortFor("Insight")).toBeNull();
  });

  it("registers both intel Kinds", () => {
    const k = new Kernel();
    k.load(new IntelExtension());
    expect(k.kindPortFor("IntelSource")).not.toBeNull();
    expect(k.kindPortFor("IntelInsight")).not.toBeNull();
  });
});
