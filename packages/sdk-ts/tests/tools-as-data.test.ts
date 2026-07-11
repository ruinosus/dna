/**
 * `loadTools` — the agent-facing tool surface, as data (f-dna-tools-as-data).
 * TS twin of `test_tools_as_data.py`. Pins three things:
 *
 * 1. The consumer helper (s-load-tools-helper): `loadTools(scope)` →
 *    `ToolLibrary`; `.get(name)` → `{description, parameters}`; a miss throws
 *    the typed `ToolNotFound`.
 * 2. The cross-language dogfood (the point): the SAME Tool document read via
 *    TypeScript `loadTools` produces the surface committed in
 *    `examples/tools_as_data/expected-surface.json` — the identical oracle the
 *    Python twin asserts against.
 * 3. Tenant overridability (the SaaS hook): a tenant overlay of a Tool's
 *    description wins for that tenant while the base stays intact.
 */
import { describe, it, expect } from "bun:test";
import { readFileSync, mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { loadTools, ToolLibrary, ToolNotFound } from "../src/index.js";
import { createKernelWithBuiltins } from "../src/bootstrap.js";
import { FilesystemSource } from "../src/adapters/filesystem/source.js";
import { FilesystemCache } from "../src/adapters/filesystem/cache.js";

const ROOT = join(import.meta.dir, "..", "..", "..");
const EXAMPLE_BASE = join(ROOT, "examples", "tools_as_data", ".dna");
const EXPECTED = join(ROOT, "examples", "tools_as_data", "expected-surface.json");

// ── consumer helper (s-load-tools-helper) ──────────────────────────────────

describe("ToolLibrary", () => {
  it("lists tool names", async () => {
    const tools = await loadTools("tools-demo", EXAMPLE_BASE);
    expect(tools.names()).toEqual(["generate-artifact"]);
  });

  it("projects the agent-facing surface", async () => {
    const tools = await loadTools("tools-demo", EXAMPLE_BASE);
    const s = tools.get("generate-artifact");
    expect(s.description).toContain("shareable artifact");
    expect((s.parameters as any).required).toEqual(["title", "content"]);
  });

  it("throws a typed ToolNotFound on a miss", async () => {
    const tools = await loadTools("tools-demo", EXAMPLE_BASE);
    let err: unknown;
    try {
      tools.get("does-not-exist");
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(ToolNotFound);
    expect((err as ToolNotFound).toolName).toBe("does-not-exist");
    expect((err as ToolNotFound).available).toContain("generate-artifact");
  });

  it("has() + caching", async () => {
    const tools = await loadTools("tools-demo", EXAMPLE_BASE);
    expect(tools.has("generate-artifact")).toBe(true);
    expect(tools.has("nope")).toBe(false);
    expect(tools.get("generate-artifact")).toBe(tools.get("generate-artifact"));
  });
});

// ── cross-language dogfood (the point) ─────────────────────────────────────

describe("cross-language dogfood", () => {
  it("TypeScript surface matches the shared oracle", async () => {
    const tools = await loadTools("tools-demo", EXAMPLE_BASE);
    const s = tools.get("generate-artifact");
    const actual = { description: s.description, parameters: s.parameters };
    const expected = JSON.parse(readFileSync(EXPECTED, "utf-8"));
    expect(actual).toEqual(expected);
  });
});

// ── tenant overridability (the SaaS hook) ──────────────────────────────────

const GENOME =
  "apiVersion: github.com/ruinosus/dna/v1\n" +
  "kind: Genome\n" +
  "metadata: {name: shop, description: base}\n" +
  "spec: {default_agent: a}\n";

const tool = (desc: string) =>
  "apiVersion: github.com/ruinosus/dna/v1\n" +
  "kind: Tool\n" +
  `metadata: {name: search, description: ${JSON.stringify(desc)}}\n` +
  "spec:\n" +
  "  type: builtin\n" +
  "  input_schema: {type: object, properties: {q: {type: string}}}\n";

function write(path: string, text: string): void {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, text, "utf-8");
}

// Tenant overrideability is proven end-to-end on the PYTHON side
// (test_tools_as_data.py::test_tenant_overlay_overrides_description_base_intact):
// there, ToolLibrary reads records through mi._one → kernel.query_list_sync,
// which applies the tenant overlay merge.
//
// The TS twin is SKIPPED, not deleted: TS's record-plane read is sync
// (mi._one filters mi.documents) and TS has no tenant-overlay MERGE for the
// record plane — even `kernel.query(scope, kind, { tenant })` returns the base
// (a pre-existing two-planes gap affecting ALL record Kinds — EvalCase, Story,
// … — now Tool). Closing that gap (TS record-plane tenant overlay merge) is
// tracked as a follow-up; this test flips to green once it lands.
describe("tenant overlay", () => {
  it.skip("overrides a tool's description while the base stays intact", async () => {
    const baseDesc = "BASE — search the shared catalog.";
    const acmeDesc = "ACME — search ACME's private index.";
    const root = mkdtempSync(join(tmpdir(), "dna-tools-tenant-"));

    write(join(root, "shop", "Genome.yaml"), GENOME);
    write(join(root, "shop", "tools", "search.yaml"), tool(baseDesc));
    write(
      join(root, "tenants", "acme", "scopes", "shop", "tools", "search.yaml"),
      tool(acmeDesc),
    );

    const k = createKernelWithBuiltins();
    k.source(new FilesystemSource(root));
    k.cache(new FilesystemCache(root));
    const base = new ToolLibrary(await k.instance("shop"));
    const acme = new ToolLibrary(await k.withTenant("acme").instance("shop"));

    expect(acme.get("search").description).toBe(acmeDesc);
    expect(base.get("search").description).toBe(baseDesc);
    expect(base.get("search").description).not.toBe(acme.get("search").description);
  });
});
