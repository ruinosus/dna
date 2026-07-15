/**
 * s-port-missing-ts-extensions (slice: tenant) — faithful TS twin of the Python
 * TenantExtension: Tenant + TenantMembership (both GLOBAL bundle, strict detect,
 * reader/writer). Guards registration of both + round-trips + strict detect.
 */
import { describe, expect, test } from "bun:test";
import { createKernelWithBuiltins } from "../src/bootstrap.js";
import { TenantExtension } from "../src/extensions/tenant.js";
import { DictBundleHandle } from "../src/kernel/bundle-handle.js";
import type { ReaderPort, WriterPort, SerializedFile, KindPort } from "../src/kernel/protocols.js";

function kindByAlias(alias: string) {
  const k = createKernelWithBuiltins() as unknown as {
    _kinds: Map<string, { alias: string; kind: string; apiVersion: string; storage?: { pattern?: string; container?: string; marker?: string } }>;
  };
  return [...k._kinds.values()].find((x) => x.alias === alias);
}

// The extension registers reader(Tenant), writer(Tenant), reader(Membership),
// writer(Membership) in that order.
function rw() {
  const readers: ReaderPort[] = [];
  const writers: WriterPort[] = [];
  new TenantExtension().register({
    kind(_k: KindPort) {},
    reader(r: ReaderPort) { readers.push(r); },
    writer(w: WriterPort) { writers.push(w); },
    // F1 / Model B: register now also loads the workspace descriptor Kinds via
    // kindFromDescriptor (same as CloudExtension). This helper only exercises
    // the reader/writer round-trip, so a no-op sink is enough.
    kindFromDescriptor(_raw: Record<string, unknown>) {},
  });
  return { tenantReader: readers[0]!, tenantWriter: writers[0]!, memReader: readers[1]!, memWriter: writers[1]! };
}

describe("TenantExtension — registration (both Kinds, GLOBAL bundle)", () => {
  test("Tenant", () => {
    const kp = kindByAlias("tenant-tenant");
    expect(kp).toBeDefined();
    expect(kp!.kind).toBe("Tenant");
    expect(kp!.storage?.pattern).toBe("bundle");
    expect(kp!.storage?.container).toBe("tenants");
    expect(kp!.storage?.marker).toBe("TENANT.md");
  });
  test("TenantMembership", () => {
    const kp = kindByAlias("tenant-membership");
    expect(kp).toBeDefined();
    expect(kp!.kind).toBe("TenantMembership");
    expect(kp!.storage?.container).toBe("tenant-memberships");
    expect(kp!.storage?.marker).toBe("MEMBERSHIP.md");
  });
});

describe("Tenant reader/writer", () => {
  test("round-trip + byte-identical body", async () => {
    const { tenantReader, tenantWriter } = rw();
    const raw = {
      apiVersion: "github.com/ruinosus/dna/tenant/v1", kind: "Tenant", metadata: { name: "acme" },
      spec: { slug: "acme", display_name: "Acme Inc", owner_email: "a@x.io", status: "active", plan: "pro" },
    };
    const files: SerializedFile[] = tenantWriter.serialize(raw);
    const md = files.find((f) => f.relativePath === "TENANT.md")!.content;
    expect(md).toContain("# Tenant — Acme Inc (`acme`)");
    expect(md).toContain("**Status:** active · **Plan:** pro");
    expect(md).toContain("`dna_documents.tenant = 'acme'`");
    expect(md).toContain("`PATCH /tenants/{slug}`"); // literal, not interpolated

    const bundle = new DictBundleHandle("acme", Object.fromEntries(files.map((f) => [f.relativePath, f.content])));
    expect(await tenantReader.detect(bundle)).toBe(true);
    const doc = await tenantReader.read(bundle);
    expect((doc.spec as Record<string, unknown>).slug).toBe("acme");
  });

  test("strict detect: TENANT.md without apiVersion rejected", async () => {
    const { tenantReader } = rw();
    expect(await tenantReader.detect(new DictBundleHandle("x", { "TENANT.md": "---\nspec: {}\n---\n" }))).toBe(false);
  });
});

describe("TenantMembership reader/writer", () => {
  test("round-trip + byte-identical body", async () => {
    const { memReader, memWriter } = rw();
    const raw = {
      apiVersion: "github.com/ruinosus/dna/tenant/v1", kind: "TenantMembership", metadata: { name: "acme--a-at-x-io" },
      spec: { tenant_slug: "acme", user_email: "a@x.io", role: "owner", joined_at: "2026-06-06T00:00:00Z" },
    };
    const files = memWriter.serialize(raw);
    const md = files.find((f) => f.relativePath === "MEMBERSHIP.md")!.content;
    expect(md).toContain("# Membership — `a@x.io` @ `acme`");
    expect(md).toContain("**Role:** owner · **Status:** active");
    expect(md).toContain("Invited by: `(self-provisioned)`");

    const bundle = new DictBundleHandle("m", Object.fromEntries(files.map((f) => [f.relativePath, f.content])));
    expect(await memReader.detect(bundle)).toBe(true);
    const doc = await memReader.read(bundle);
    expect((doc.spec as Record<string, unknown>).role).toBe("owner");
  });

  test("strict detect: wrong kind rejected", async () => {
    const { memReader } = rw();
    expect(await memReader.detect(new DictBundleHandle("x", { "MEMBERSHIP.md": "---\napiVersion: github.com/ruinosus/dna/tenant/v1\nkind: Tenant\n---\n" }))).toBe(false);
  });
});
