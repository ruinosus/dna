// s-mif-passthrough-kind (feature f-portable-memory) — the MIF Memory
// passthrough Kind (`mif-spec.dev/v1 · Memory`, record plane).
// TS twin of tests/test_mif_memory_kind.py.
//
// Market-fidelity conformance (docs/concepts/market-fidelity.md — "the
// owner names the schema"): subjects are REAL examples lifted verbatim (or
// lightly extended, noted inline) from the actual MIF spec
// (github.com/modeled-information-format/MIF, SPECIFICATION.md §16), not
// invented data.
//
// Reads go through GenericBundleReader/GenericBundleWriter constructed
// straight from the registered Kind's own StorageDescriptor — the same
// classes the kernel wires in for every bundle-storage descriptor Kind at
// boot. This Kind is `plane: record` by design, so it deliberately never
// enters ManifestInstance.documents (the two-planes split); exercising the
// Reader/Writer directly is the most direct proof of parse/schema/serialize
// behavior.
import { describe, it, expect } from "bun:test";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { readFileSync, mkdtempSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import yaml from "js-yaml";

import { Kernel } from "../src/kernel/index.js";
import { GenericBundleReader, GenericBundleWriter } from "../src/kernel/generic-rw.js";
import { FilesystemBundleHandle } from "../src/kernel/bundle-handle.js";
import { MifExtension } from "../src/extensions/mif.js";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const FIXTURE_BASE = join(REPO_ROOT, "tests/parity-fixtures/mif/memories");

function splitFrontmatter(text: string): [Record<string, unknown>, string] {
  const m = text.match(/^---\n([\s\S]*?)\n---\n/);
  if (!m) throw new Error("expected a frontmatter block");
  const fm = (yaml.load(m[1]) ?? {}) as Record<string, unknown>;
  return [fm, text.slice(m[0].length)];
}

function kernelWithMif(): Kernel {
  const k = new Kernel();
  k.load(new MifExtension());
  return k;
}

describe("MIF Memory Kind (descriptor)", () => {
  it("registers from its descriptor", () => {
    const k = kernelWithMif();
    const kp = k.kindPortFor("Memory");
    expect(kp).not.toBeNull();
    expect(kp!.alias).toBe("mif-memory");
    expect((kp as any).apiVersion).toBe("mif-spec.dev/v1");
    expect(kp!.kind).toBe("Memory");
    expect((kp as any).origin).toBe("mif-spec.dev");
    expect((kp as any).plane).toBe("record");
    expect(kp!.storage.container).toBe("memories");
    expect(kp!.storage.marker).toBe("MEMORY.md");
    expect(kp!.storage.bodyField).toBe("content");
    expect((kp as any).__declarative__).toBe(true);
  });

  it("schema is strict except the extensions vault", () => {
    const k = kernelWithMif();
    const schema = k.kindPortFor("Memory")!.schema() as any;
    expect(schema.additionalProperties).toBe(false);
    expect(schema.required).toEqual(["id", "type", "content", "created"]);
    expect(schema.properties.extensions.additionalProperties).toBe(true);
  });

  it("injects no DNA-flavored field — every property traces to the real MIF spec", () => {
    const k = kernelWithMif();
    const schema = k.kindPortFor("Memory")!.schema() as any;
    const props = new Set(Object.keys(schema.properties));
    const mifFields = new Set([
      "id", "type", "content", "created", "title", "modified", "ontology",
      "namespace", "tags", "aliases", "entities", "relationships",
      "temporal", "provenance", "embedding", "citations", "summary",
      "compressed_at", "extensions",
    ]);
    expect(props).toEqual(mifFields);
  });

  it("detects the marker", () => {
    const k = kernelWithMif();
    const kp = k.kindPortFor("Memory")!;
    const reader = new GenericBundleReader(kp.storage, (kp as any).apiVersion, kp.kind);
    const bundle = new FilesystemBundleHandle(join(FIXTURE_BASE, "minimal-preference"));
    expect(reader.detect(bundle)).toBe(true);
  });

  // -------------------------------------------------------------------
  // Level 1 fixture — SPECIFICATION.md §16.1 "Minimal Memory", verbatim
  // -------------------------------------------------------------------

  it("Level 1 fixture validates without deformation", () => {
    const k = kernelWithMif();
    const kp = k.kindPortFor("Memory")!;
    const reader = new GenericBundleReader(kp.storage, (kp as any).apiVersion, kp.kind);
    const markerPath = join(FIXTURE_BASE, "minimal-preference", "MEMORY.md");
    const bundle = new FilesystemBundleHandle(join(FIXTURE_BASE, "minimal-preference"));
    const raw = reader.read(bundle);

    expect(raw.apiVersion).toBe("mif-spec.dev/v1");
    expect(raw.kind).toBe("Memory");

    const spec = raw.spec as Record<string, unknown>;
    const [fm, body] = splitFrontmatter(readFileSync(markerPath, "utf-8"));
    expect(spec).toEqual({
      id: fm.id,
      type: fm.type,
      created: fm.created,
      content: body.trim(),
    });
    expect(spec.id).toBe("550e8400-e29b-41d4-a716-446655440000");
    expect(spec.type).toBe("semantic");
    expect(spec.content).toBe("User prefers dark mode for all applications.");
  });

  // -------------------------------------------------------------------
  // Level 2 fixture — SPECIFICATION.md §16.2 "Decision Memory"
  // -------------------------------------------------------------------

  it("Level 2 fixture validates without deformation", () => {
    const k = kernelWithMif();
    const kp = k.kindPortFor("Memory")!;
    const reader = new GenericBundleReader(kp.storage, (kp as any).apiVersion, kp.kind);
    const markerPath = join(FIXTURE_BASE, "decision-react-over-vue", "MEMORY.md");
    const bundle = new FilesystemBundleHandle(join(FIXTURE_BASE, "decision-react-over-vue"));
    const raw = reader.read(bundle);
    const spec = raw.spec as Record<string, any>;

    const [fm, body] = splitFrontmatter(readFileSync(markerPath, "utf-8"));
    for (const [key, value] of Object.entries(fm)) {
      expect(spec[key]).toEqual(value);
    }
    expect(spec.content).toBe(body.trim());

    // Relationship types are real MIF core tokens (Appendix B), not the
    // draft's invented enum.
    const relTypes = new Set(spec.relationships.map((r: any) => r.type));
    expect(relTypes).toEqual(new Set(["relates-to", "supersedes"]));

    // Entities preserve the real EntityReference shape (Appendix C).
    const react = spec.entities.find((e: any) => e.name === "React");
    expect(react["@type"]).toBe("EntityReference");
    expect(react.entity["@id"]).toBe("urn:mif:entity:technology:react");
    expect(react.entityType).toBe("Technology");
  });

  it("extensions vault carries arbitrary DNA fields", () => {
    const k = kernelWithMif();
    const kp = k.kindPortFor("Memory")!;
    const reader = new GenericBundleReader(kp.storage, (kp as any).apiVersion, kp.kind);
    const bundle = new FilesystemBundleHandle(join(FIXTURE_BASE, "decision-react-over-vue"));
    const spec = reader.read(bundle).spec as Record<string, any>;
    expect(spec.extensions).toEqual({
      "x-dna": { confidence_score: 0.92, visibility: "shared" },
    });
  });

  // -------------------------------------------------------------------
  // Field-level round-trip (byte-faithful is explicitly out of scope —
  // see the descriptor's KNOWN OPEN ITEM comment)
  // -------------------------------------------------------------------

  for (const name of ["minimal-preference", "decision-react-over-vue"]) {
    it(`field-level round-trip: ${name}`, () => {
      const k = kernelWithMif();
      const kp = k.kindPortFor("Memory")!;
      const reader = new GenericBundleReader(kp.storage, (kp as any).apiVersion, kp.kind);
      const writer = new GenericBundleWriter(kp.storage, kp.kind);
      const bundle = new FilesystemBundleHandle(join(FIXTURE_BASE, name));
      const raw = reader.read(bundle);

      const files = writer.serialize(raw);
      expect(files.map((f) => f.relativePath)).toEqual(["MEMORY.md"]);

      const tmp = mkdtempSync(join(tmpdir(), "mif-roundtrip-"));
      const reemittedDir = join(tmp, name);
      mkdirSync(reemittedDir);
      writeFileSync(join(reemittedDir, "MEMORY.md"), files[0].content);
      const reRaw = reader.read(new FilesystemBundleHandle(reemittedDir));

      expect(reRaw.spec).toEqual(raw.spec);
    });
  }
});
