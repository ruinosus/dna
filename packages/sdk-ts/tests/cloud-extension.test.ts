// s-dna-cloud-plans — Tier Kind (DNA Cloud pricing plans) + kernel.tier().
// TS twin of tests/test_cloud_tier_kind.py.
//
// Never hardcode caps: every cap below lives in a Tier DOC (the registry
// kernel.tier reads), never in a literal in the production code. NOT named
// `Plan` — that alias belongs to the SDLC implementation-plan Kind.
import { describe, it, expect } from "bun:test";
import { Kernel } from "../src/kernel/index.js";
import { TenantScope } from "../src/kernel/protocols.js";
import { CloudExtension } from "../src/extensions/cloud.js";

// ---------------------------------------------------------------------------
// Kind registration (descriptor)
// ---------------------------------------------------------------------------

describe("Tier Kind (descriptor)", () => {
  it("registers from kinds/tier.kind.yaml", () => {
    const k = new Kernel();
    k.load(new CloudExtension());
    const kp = k.kindPortFor("Tier");
    expect(kp).not.toBeNull();
    // Explicit alias `cloud-tier` — NOT `Plan` (that alias belongs to SDLC).
    expect(kp!.alias).toBe("cloud-tier");
    expect((kp as any).plane).toBe("record");
    // GLOBAL — a shared base registry, no per-tenant override.
    expect((kp as any).scope).toBe(TenantScope.GLOBAL);
    expect(kp!.storage.container).toBe("tiers");
  });

  it("registers Tier, not Plan (no collision with the SDLC Plan Kind)", () => {
    const k = new Kernel();
    k.load(new CloudExtension());
    expect(k.kindPortFor("Tier")).not.toBeNull();
    expect(k.kindPortFor("Plan")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Resolution — caps come from the DOC. A fake source serves Tier docs for
// the `_lib` scope so kernel.tier resolves them for real.
// ---------------------------------------------------------------------------

function tierRaw(
  tierId: string,
  opts: {
    displayName: string;
    price: number;
    callsPerDay: number | null;
    memoryMode: string;
    aliases?: string[];
  },
) {
  return {
    apiVersion: "github.com/ruinosus/dna/cloud/v1",
    kind: "Tier",
    metadata: { name: tierId },
    spec: {
      tier_id: tierId,
      display_name: opts.displayName,
      price_usd_month: opts.price,
      calls_per_day: opts.callsPerDay,
      rate_per_sec: 1,
      max_tenants: 1,
      feature_families: ["definitions", "sdlc", "memory"],
      memory_mode: opts.memoryMode,
      aliases: opts.aliases ?? [],
    },
  };
}

function tierKernel(): { k: Kernel; libDocs: unknown[] } {
  // Mutable so a test can edit a cap and prove the re-read reflects it.
  const libDocs: unknown[] = [
    tierRaw("free", {
      displayName: "Free", price: 0, callsPerDay: 100,
      memoryMode: "read", aliases: ["starter"],
    }),
    tierRaw("pro", {
      displayName: "Pro", price: 29, callsPerDay: 10000, memoryMode: "write",
    }),
  ];
  const src: any = {
    async saveDocument() { return "v1"; },
    async deleteDocument() {},
    async loadBootstrapDocs() { return []; },
    async loadDocument() { return null; },
    async loadAll(scope: string) { return scope === "_lib" ? libDocs : []; },
    async loadLayer() { return []; },
    async listVersions() { return []; },
    async listScopes() { return ["_lib"]; },
  };
  const k = new Kernel();
  k.load(new CloudExtension());
  k.source(src);
  k.writableSource(src);
  // instance() (which tier rides) requires a cache port.
  k.cache({
    has: async () => false,
    store: async () => {},
    loadKey: async () => [],
    loadAll: async () => [],
  } as any);
  return { k, libDocs };
}

describe("kernel.tier — caps come from the doc", () => {
  it("resolves free/pro with the caps declared in the doc", async () => {
    const { k } = tierKernel();

    const free = await k.tier("free");
    expect(free).not.toBeNull();
    expect((free!.spec as any).calls_per_day).toBe(100);
    expect((free!.spec as any).memory_mode).toBe("read");
    expect((free!.spec as any).price_usd_month).toBe(0);

    const pro = await k.tier("pro");
    expect(pro).not.toBeNull();
    expect((pro!.spec as any).calls_per_day).toBe(10000);
    expect((pro!.spec as any).memory_mode).toBe("write");
    expect((pro!.spec as any).price_usd_month).toBe(29);
  });

  it("resolves by alias (pass 2)", async () => {
    const { k } = tierKernel();
    const byAlias = await k.tier("starter"); // alias of `free`
    expect(byAlias).not.toBeNull();
    expect((byAlias!.spec as any).tier_id).toBe("free");
  });

  it("returns null for an unknown tier", async () => {
    const { k } = tierKernel();
    expect(await k.tier("nonexistent")).toBeNull();
  });

  it("cap is data, not code — editing the doc changes the re-read", async () => {
    const { k, libDocs } = tierKernel();
    expect(((await k.tier("free"))!.spec as any).calls_per_day).toBe(100);
    // Edit the Free plan's daily quota — a data edit, no redeploy.
    (libDocs[0] as any).spec.calls_per_day = 250;
    expect(((await k.tier("free"))!.spec as any).calls_per_day).toBe(250);
  });
});

// ---------------------------------------------------------------------------
// WorkspacePlan Kind + kernel.workspacePlan — the billing→enforcement bridge
// (ADR "Model B" — billing keys on the WORKSPACE, not an identity/Azure org).
// The assignment lives in a WorkspacePlan DOC (which dna-cloud's Stripe webhook
// writes); the SDK only reads it. TS twin of tests/test_cloud_workspace_plan_kind.py.
// ---------------------------------------------------------------------------

describe("WorkspacePlan Kind (descriptor)", () => {
  it("registers from kinds/workspace-plan.kind.yaml", () => {
    const k = new Kernel();
    k.load(new CloudExtension());
    const kp = k.kindPortFor("WorkspacePlan");
    expect(kp).not.toBeNull();
    expect(kp!.alias).toBe("cloud-workspace-plan");
    expect((kp as any).plane).toBe("record");
    // GLOBAL — a shared base registry, no per-tenant override.
    expect((kp as any).scope).toBe(TenantScope.GLOBAL);
    expect(kp!.storage.container).toBe("workspace-plans");
  });

  it("registers both Tier and WorkspacePlan, never Plan or the old TenantPlan", () => {
    const k = new Kernel();
    k.load(new CloudExtension());
    expect(k.kindPortFor("Tier")).not.toBeNull();
    expect(k.kindPortFor("WorkspacePlan")).not.toBeNull();
    expect(k.kindPortFor("TenantPlan")).toBeNull();
    expect(k.kindPortFor("Plan")).toBeNull();
  });
});

function workspacePlanRaw(workspaceId: string, tierId: string) {
  return {
    apiVersion: "github.com/ruinosus/dna/cloud/v1",
    kind: "WorkspacePlan",
    metadata: { name: workspaceId },
    spec: { workspace_id: workspaceId, tier_id: tierId, source: "stripe", status: "active" },
  };
}

function workspacePlanKernel(): { k: Kernel; libDocs: unknown[] } {
  const libDocs: unknown[] = [workspacePlanRaw("acme", "pro")];
  const src: any = {
    async saveDocument() { return "v1"; },
    async deleteDocument() {},
    async loadBootstrapDocs() { return []; },
    async loadDocument() { return null; },
    async loadAll(scope: string) { return scope === "_lib" ? libDocs : []; },
    async loadLayer() { return []; },
    async listVersions() { return []; },
    async listScopes() { return ["_lib"]; },
  };
  const k = new Kernel();
  k.load(new CloudExtension());
  k.source(src);
  k.writableSource(src);
  k.cache({
    has: async () => false,
    store: async () => {},
    loadKey: async () => [],
    loadAll: async () => [],
  } as any);
  return { k, libDocs };
}

describe("kernel.workspacePlan — the assignment comes from the doc", () => {
  it("resolves a workspace to its assigned tier_id", async () => {
    const { k } = workspacePlanKernel();
    const plan = await k.workspacePlan("acme");
    expect(plan).not.toBeNull();
    expect((plan!.spec as any).tier_id).toBe("pro");
    expect((plan!.spec as any).workspace_id).toBe("acme");
  });

  it("returns null for an unknown workspace (guard falls to Free floor)", async () => {
    const { k } = workspacePlanKernel();
    expect(await k.workspacePlan("globex")).toBeNull();
  });

  it("assignment is data, not code — rewriting the doc changes the re-read", async () => {
    const { k, libDocs } = workspacePlanKernel();
    expect(((await k.workspacePlan("acme"))!.spec as any).tier_id).toBe("pro");
    // dna-cloud's Stripe webhook downgrades acme to free on cancel — a data edit.
    (libDocs[0] as any).spec.tier_id = "free";
    expect(((await k.workspacePlan("acme"))!.spec as any).tier_id).toBe("free");
  });

  it("the plan key is an opaque workspace id of any shape", async () => {
    // Decision D5 made workspace ids server-generated (`ws-<base32>`), so the ids
    // arriving here changed shape. The lookup never parses or validates the
    // string, which is also why the founder's legacy GUID id (once his Azure tid)
    // keeps resolving — it is one more opaque string, not a special case.
    // Parity twin of sdk-py `test_workspace_plan_key_is_an_opaque_id_of_any_shape`.
    const { k, libDocs } = workspacePlanKernel();
    for (const wsId of ["c5b891f7", "ws-mfrggzdfmztwq2lknnwg23th"]) {
      (libDocs as unknown[]).push(workspacePlanRaw(wsId, "enterprise"));
      const plan = await k.workspacePlan(wsId);
      expect(plan).not.toBeNull();
      expect((plan!.spec as any).tier_id).toBe("enterprise");
    }
  });
});
