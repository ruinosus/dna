#!/usr/bin/env bun
/**
 * Read the `generate-artifact` Tool surface via the DNA **TypeScript** SDK.
 *
 *     bun run examples/tools_as_data/read_ts.ts
 *
 * Prints the agent-facing surface ({description, parameters}) as canonical
 * JSON. Run alongside `read_py.py` (the Python twin) and diff the output:
 * both read the SAME Tool document (tools-demo/tools/generate-artifact.yaml)
 * through the byte-identical `Tool` Kind descriptor and produce byte-identical
 * surfaces — the first time the Py↔TS parity pays off in a real consumer.
 */
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { loadTools } from "../../packages/sdk-ts/src/index.js";

const BASE_DIR = join(dirname(fileURLToPath(import.meta.url)), ".dna");

const tools = await loadTools("tools-demo", BASE_DIR);
const surface = tools.get("generate-artifact");
const out = { description: surface.description, parameters: surface.parameters };
// Sorted keys + 2-space indent to match the Python `json.dumps(..., sort_keys)`.
console.log(JSON.stringify(sortDeep(out), null, 2));

// Deterministic key order so the two runtimes emit byte-identical JSON.
function sortDeep(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortDeep);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value as Record<string, unknown>)
        .sort()
        .map((k) => [k, sortDeep((value as Record<string, unknown>)[k])]),
    );
  }
  return value;
}
