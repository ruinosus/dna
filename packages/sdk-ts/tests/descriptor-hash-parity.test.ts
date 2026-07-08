/**
 * F3 (spec D3): builtin Kind descriptors are parity-critical package data.
 *
 * TS twin of sdk-py tests/test_descriptor_hash_parity.py — every
 * `kinds/*.kind.yaml` must exist on BOTH sides and be byte-identical
 * (sha256 over raw bytes). Vacuous until the first descriptor lands
 * (kaizen.kind.yaml, F3 P2 pilot); the set-equality guard makes a
 * one-sided file a nominal failure, not a skip.
 *
 * Also unit-tests `loadDescriptors` (kernel/descriptor-loader.ts).
 */
import { describe, test, expect } from "bun:test";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, readdirSync, writeFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { mkdtempSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { loadDescriptors } from "../src/kernel/descriptor-loader";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const PY_EXT = join(ROOT, "packages/sdk-py/dna/extensions");
const TS_EXT = join(ROOT, "packages/sdk-ts/src/extensions");

/** Map `<extension>/<file>.kind.yaml` → absolute path. */
function descriptorSet(extRoot: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const ext of readdirSync(extRoot, { withFileTypes: true })) {
    if (!ext.isDirectory()) continue;
    const kindsDir = join(extRoot, ext.name, "kinds");
    let entries: string[];
    try {
      entries = readdirSync(kindsDir);
    } catch {
      continue;
    }
    for (const f of entries.sort()) {
      if (f.endsWith(".kind.yaml")) out.set(`${ext.name}/${f}`, join(kindsDir, f));
    }
  }
  return out;
}

describe("descriptor hash parity (kinds/*.kind.yaml, Py ↔ TS)", () => {
  test("descriptor sets are identical across languages", () => {
    const py = descriptorSet(PY_EXT);
    const ts = descriptorSet(TS_EXT);
    const onlyPy = [...py.keys()].filter((k) => !ts.has(k)).sort();
    const onlyTs = [...ts.keys()].filter((k) => !py.has(k)).sort();
    expect(
      { onlyPy, onlyTs },
      "kinds/*.kind.yaml must exist on BOTH sides (byte-identical mirrors)",
    ).toEqual({ onlyPy: [], onlyTs: [] });
  });

  test("descriptors are byte-identical across languages", () => {
    const py = descriptorSet(PY_EXT);
    const ts = descriptorSet(TS_EXT);
    for (const [rel, pyPath] of py) {
      const tsPath = ts.get(rel);
      if (!tsPath) continue; // set test reports it
      const pySha = createHash("sha256").update(readFileSync(pyPath)).digest("hex");
      const tsSha = createHash("sha256").update(readFileSync(tsPath)).digest("hex");
      expect(tsSha, `descriptor ${rel} diverged — edit one side, copy byte-for-byte`).toBe(pySha);
    }
  });
});

describe("loadDescriptors", () => {
  function tmpModuleUrl(): { url: string; dir: string } {
    const dir = mkdtempSync(join(tmpdir(), "f3-desc-"));
    // loadDescriptors resolves relative to the MODULE file's dirname.
    const fakeModule = join(dir, "ext.ts");
    writeFileSync(fakeModule, "// fake module anchor");
    return { url: pathToFileURL(fakeModule).href, dir };
  }

  const DESCRIPTOR = (kind: string) => `apiVersion: github.com/ruinosus/dna/core/v1
kind: KindDefinition
metadata:
  name: ${kind.toLowerCase()}
spec:
  target_api_version: github.com/ruinosus/dna/test/v1
  target_kind: ${kind}
  alias: test-${kind.toLowerCase()}
  origin: github.com/ruinosus/dna/test
  storage:
    type: yaml
    container: ${kind.toLowerCase()}s
`;

  test("parses *.kind.yaml sorted by filename, ignoring other files", () => {
    const { url, dir } = tmpModuleUrl();
    try {
      mkdirSync(join(dir, "kinds"));
      writeFileSync(join(dir, "kinds", "zeta.kind.yaml"), DESCRIPTOR("Zeta"));
      writeFileSync(join(dir, "kinds", "alpha.kind.yaml"), DESCRIPTOR("Alpha"));
      writeFileSync(join(dir, "kinds", "README.md"), "not a descriptor");
      const raws = loadDescriptors(url, "kinds");
      expect(raws.map((r) => (r.spec as Record<string, unknown>).target_kind)).toEqual([
        "Alpha",
        "Zeta",
      ]);
      expect(raws.every((r) => r.kind === "KindDefinition")).toBe(true);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("missing kinds dir → []", () => {
    const { url, dir } = tmpModuleUrl();
    try {
      expect(loadDescriptors(url, "kinds")).toEqual([]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("non-mapping YAML throws", () => {
    const { url, dir } = tmpModuleUrl();
    try {
      mkdirSync(join(dir, "kinds"));
      writeFileSync(join(dir, "kinds", "broken.kind.yaml"), "- just\n- a list\n");
      expect(() => loadDescriptors(url, "kinds")).toThrow(/broken\.kind\.yaml/);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
