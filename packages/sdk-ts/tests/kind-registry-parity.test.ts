import { describe, expect, test } from "bun:test";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load as yamlLoad } from "js-yaml";
import { createKernelWithBuiltins } from "../src/bootstrap.js";
import parity from "../kind-registry-parity.json";

// s-kind-registry-parity-test — this locks the TS SIDE: the set of Kind aliases
// registered by the TS builtins must equal `ts_aliases` (hand-maintained,
// class-based Kinds) ∪ the DERIVED descriptor aliases (i-132, F3 lote-2):
// builtin Kinds expressed as `*/kinds/*.kind.yaml` package data exist in BOTH
// runtimes by construction (byte-identical mirrors, descriptor-hash-parity),
// so they are scanned at test time instead of hand-listed in the manifest.
// Adding/removing a TS CLASS Kind requires updating the manifest; adding a
// descriptor Kind requires NO registry edit. Drift → red.

const EXTENSIONS_DIR = join(dirname(fileURLToPath(import.meta.url)), "../src/extensions");

function descriptorAliases(): string[] {
  const aliases: string[] = [];
  for (const ext of readdirSync(EXTENSIONS_DIR, { withFileTypes: true })) {
    if (!ext.isDirectory()) continue;
    const kindsDir = join(EXTENSIONS_DIR, ext.name, "kinds");
    if (!existsSync(kindsDir)) continue;
    for (const name of readdirSync(kindsDir).sort()) {
      if (!name.endsWith(".kind.yaml")) continue;
      const raw = yamlLoad(readFileSync(join(kindsDir, name), "utf-8")) as {
        spec?: { alias?: string };
      };
      const alias = raw?.spec?.alias;
      if (!alias) throw new Error(`descriptor without spec.alias: ${ext.name}/kinds/${name}`);
      aliases.push(alias);
    }
  }
  return aliases;
}

describe("Kind registry parity (TS side)", () => {
  test("TS builtins register exactly ts_aliases ∪ derived descriptor aliases", () => {
    const k = createKernelWithBuiltins() as unknown as {
      _kinds: Map<string, { alias: string }>;
    };
    const got = [...k._kinds.values()]
      .map((kp) => kp.alias)
      .filter(Boolean)
      .sort();
    const expected = [...new Set([...parity.ts_aliases, ...descriptorAliases()])].sort();
    expect(got).toEqual(expected);
  });

  test("descriptor aliases never need manual registry entries (i-132 pin)", () => {
    const derived = new Set(descriptorAliases());
    expect(derived.size).toBeGreaterThan(0);
    const handListed = parity.ts_aliases.filter((a) => derived.has(a));
    expect(handListed).toEqual([]);
    const allowlisted = parity.py_only_allowlist.filter((a) => derived.has(a));
    expect(allowlisted).toEqual([]);
  });
});
