/**
 * s-dna-kindport-descriptor-schema — published KindDefinition JSON Schema
 * (TS side).
 *
 * The descriptor format's machine-readable contract is
 * `docs/schemas/kind-definition.schema.json` (draft 2020-12; byte-identical
 * runtime copy in sdk-py package data — the Py suite enforces the identity
 * and runs full jsonschema validation). The TS runtime validation IS the Zod
 * `KindDefinitionSpecSchema`; this suite locks the two against each other so
 * they can't drift:
 *
 * - every Zod spec key appears in the schema and vice versa (modulo the
 *   documented Py-only authoring fields + runtime-stamped volatile fields);
 * - every TS-side builtin descriptor parses through the Zod schema (the
 *   same corpus the Py suite validates against the JSON Schema — if both
 *   suites are green, the two validators agree on the whole real corpus).
 */
import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { Glob } from "bun";
import { load as parseYaml } from "js-yaml";

import {
  KindDefinitionSchema,
  KindDefinitionSpecSchema,
} from "../src/kernel/models.js";

const TS_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = join(TS_ROOT, "../..");

// Canonical published copy first; packaged sdk-py runtime copy as the
// fallback (extracted-repo layouts that don't ship docs/schemas/).
const SCHEMA_CANDIDATES = [
  join(REPO_ROOT, "docs/schemas/kind-definition.schema.json"),
  join(REPO_ROOT, "packages/sdk-py/dna/kernel/schemas/kind-definition.schema.json"),
];

// Py-only authoring fields: consumed by the Python reference
// implementation (schema-fragment merging), documented as such in the
// schema; the TS Zod object does not consume them yet.
const PY_ONLY_SPEC_FIELDS = new Set(["schema_fragments", "workitem_common"]);
// Runtime-stamped volatile fields (KindBase VOLATILE_SPEC_FIELDS) — the
// schema allows them so stamped documents keep validating; they are not
// part of the authored surface either side parses.
const VOLATILE_SPEC_FIELDS = new Set(["updated_at", "created_at", "version"]);

function loadSchema(): Record<string, any> {
  const path = SCHEMA_CANDIDATES.find((p) => existsSync(p));
  expect(path, `kind-definition.schema.json not found in: ${SCHEMA_CANDIDATES.join(", ")}`).toBeDefined();
  return JSON.parse(readFileSync(path!, "utf-8"));
}

describe("kind-definition schema ↔ Zod parity", () => {
  test("spec property keys match the Zod KindDefinitionSpecSchema shape", () => {
    const schema = loadSchema();
    const schemaKeys = new Set<string>(
      Object.keys(schema.properties.spec.properties).filter(
        (k) => !PY_ONLY_SPEC_FIELDS.has(k) && !VOLATILE_SPEC_FIELDS.has(k),
      ),
    );
    const zodKeys = new Set<string>(Object.keys(KindDefinitionSpecSchema.shape));

    const schemaOnly = [...schemaKeys].filter((k) => !zodKeys.has(k)).sort();
    const zodOnly = [...zodKeys].filter((k) => !schemaKeys.has(k)).sort();
    expect(
      schemaOnly,
      "field(s) in the published schema the Zod schema doesn't accept — " +
        "port them (or document as Py-only in PY_ONLY_SPEC_FIELDS)",
    ).toEqual([]);
    expect(
      zodOnly,
      "Zod field(s) missing from the published schema — a contributor's " +
        "editor won't autocomplete/validate them; add to docs/schemas/" +
        "kind-definition.schema.json (byte-identical sdk-py copy too)",
    ).toEqual([]);
  });

  test("envelope constants match the Zod literals", () => {
    const schema = loadSchema();
    expect(schema.properties.apiVersion.const).toBe(
      "github.com/ruinosus/dna/core/v1",
    );
    expect(schema.properties.kind.const).toBe("KindDefinition");
    expect(schema.required).toEqual(["apiVersion", "kind", "metadata", "spec"]);
  });

  test("every TS-side builtin descriptor parses through the Zod schema", () => {
    const glob = new Glob("src/extensions/*/kinds/*.kind.yaml");
    const files = [...glob.scanSync({ cwd: TS_ROOT })].sort();
    expect(files.length, "no TS descriptors found — glob broke?").toBeGreaterThan(0);
    for (const rel of files) {
      const raw = parseYaml(readFileSync(join(TS_ROOT, rel), "utf-8"));
      const parsed = KindDefinitionSchema.safeParse(raw);
      expect(
        parsed.success,
        `${rel} failed Zod parse: ${parsed.success ? "" : parsed.error.message}`,
      ).toBe(true);
    }
  });
});
