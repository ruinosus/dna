/**
 * s-dna-rw-roundtrip-suite — reader/writer round-trip conformance, TS mirror
 * of `dna/testing/rw_conformance.py`.
 *
 * For EVERY reader/writer pair registered by the builtin bootstrap
 * (`createKernelWithBuiltins()` + the auto-generated generic pairs), enforce
 * the round-trip invariant that is the thesis of the notation (spec §2.1):
 *
 *   1. serialize() returns well-shaped, non-empty entries;
 *   2. write() and serialize() emit the same file tree (no drift);
 *   3. a registered reader detects the writer's output (container-aware,
 *      same routing as the scanner) and reads back the same kind + name;
 *   4. after ONE permitted normalization pass, emit→read→emit is a byte
 *      fixpoint.
 *
 * Plus the same fixpoint over the REAL market bundles in
 * `scopes/market-integration` (marketplace Skills, brad soul, AGENTS.md).
 */
import { describe, expect, test } from "bun:test";
import { mkdtempSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve } from "node:path";

import { createKernelWithBuiltins } from "../src/bootstrap.js";
import { FilesystemBundleHandle } from "../src/kernel/bundle-handle.js";
import type { KindPort, ReaderPort, SerializedFile, WriterPort } from "../src/kernel/protocols.js";

const REPO_ROOT = resolve(import.meta.dir, "../../..");
const MARKET_SCOPE = join(REPO_ROOT, "scopes", "market-integration", ".dna", "market-demo");

// ---------------------------------------------------------------------------
// kernel + pair enumeration
// ---------------------------------------------------------------------------

const kernel = createKernelWithBuiltins() as unknown as {
  _kinds: Map<string, KindPort>;
  _ensureGenericReadersWriters(): void;
  activeReaders: readonly ReaderPort[];
  activeWriters: readonly WriterPort[];
};
kernel._ensureGenericReadersWriters();
const READERS = kernel.activeReaders;
const WRITERS = kernel.activeWriters;

// Spec seeds for Kinds whose hand-rolled writers key off specific fields
// (mirror of DEFAULT_SPEC_SEEDS in the Python kit).
const SPEC_SEEDS: Record<string, Record<string, unknown>> = {
  Skill: { instruction: "Round-trip conformance kit instruction.\n" },
  Soul: { soul_content: "## Personality\n\nRound-trip kit soul.\n" },
  Agent: { instruction: "Round-trip conformance kit instruction.\n" },
  AgentProgram: { instruction: "Round-trip conformance kit program.\n" },
  Research: { synthesis: "Round-trip conformance kit synthesis.\n" },
  // GuardrailWriter serializes spec.rules as a list of "- " lines.
  Guardrail: { rules: ["Round-trip conformance kit rule."] },
  // GraphifyArtifact bundles are only valid WITH their graph.json payload
  // (see the Python kit for the full rationale).
  GraphifyArtifact: { graph_data: { nodes: [], links: [] } },
};

function fixtureFor(kp: KindPort): Record<string, unknown> {
  const bodyField = kp.storage?.bodyField ?? "content";
  const name = `rw-kit-${kp.kind.toLowerCase()}`;
  return {
    apiVersion: kp.apiVersion,
    kind: kp.kind,
    metadata: { name, description: "Round-trip conformance kit fixture." },
    spec: {
      [bodyField]: "Round-trip conformance kit body.\n",
      ...(SPEC_SEEDS[kp.kind] ?? {}),
    },
  };
}

// ---------------------------------------------------------------------------
// helpers (mirror of the Python kit)
// ---------------------------------------------------------------------------

function materialize(entries: SerializedFile[], bundleDir: string): void {
  for (const f of entries) {
    const target = join(bundleDir, f.relativePath);
    mkdirSync(dirname(target), { recursive: true });
    if (f.contentBytes !== undefined) writeFileSync(target, f.contentBytes);
    else writeFileSync(target, f.content ?? "", "utf-8");
  }
}

function treeBytes(root: string): Record<string, string> {
  const out: Record<string, string> = {};
  const walk = (dir: string, prefix: string): void => {
    for (const entry of readdirSync(dir).sort()) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full, `${prefix}${entry}/`);
      else out[`${prefix}${entry}`] = readFileSync(full).toString("base64");
    }
  };
  walk(root, "");
  return out;
}

function entriesBytes(entries: SerializedFile[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of entries) {
    out[f.relativePath] = f.contentBytes !== undefined
      ? Buffer.from(f.contentBytes).toString("base64")
      : Buffer.from(f.content ?? "", "utf-8").toString("base64");
  }
  return out;
}

/** Scanner-equivalent routing: container-owned first, unscoped fallback. */
function orderedReaders(container: string): ReaderPort[] {
  const owned = READERS.filter((r) => r._ownerContainer === container);
  const unscoped = READERS.filter((r) => r._ownerContainer == null);
  return [...owned, ...unscoped];
}

async function detectingReader(bundleDir: string): Promise<ReaderPort | null> {
  const handle = new FilesystemBundleHandle(bundleDir);
  const container = dirname(bundleDir).split("/").filter(Boolean).pop() ?? "";
  for (const r of orderedReaders(container)) {
    try {
      if (await r.detect(handle)) return r;
    } catch {
      continue; // detect() is a probe (scanner parity)
    }
  }
  return null;
}

function assertEntryShape(entries: SerializedFile[], who: string): void {
  expect(Array.isArray(entries) && entries.length > 0).toBe(true);
  for (const f of entries) {
    expect(typeof f.relativePath).toBe("string");
    const hasText = typeof f.content === "string";
    const hasBytes = f.contentBytes !== undefined;
    if (hasText === hasBytes) {
      throw new Error(
        `${who}.serialize() entry ${f.relativePath} must carry exactly one ` +
        `of content (string) / contentBytes (Uint8Array).`,
      );
    }
  }
}

function tmpRoot(): string {
  return mkdtempSync(join(tmpdir(), "rw-kit-"));
}

// ---------------------------------------------------------------------------
// synthetic pairs — one describe per Kind with a claiming writer
// ---------------------------------------------------------------------------

const PAIRS: Array<{ kind: string; container: string; raw: Record<string, unknown>; writer: WriterPort }> = [];
for (const kp of kernel._kinds.values()) {
  const raw = fixtureFor(kp);
  const writer = WRITERS.find((w) => w.canWrite(raw));
  if (!writer) continue; // YAML-record kinds — covered by the source kit
  PAIRS.push({
    kind: kp.kind,
    container: kp.storage?.container ?? "bundles",
    raw,
    writer,
  });
}

describe("reader/writer round-trip conformance (synthetic fixtures)", () => {
  test("bootstrap registers at least one pair", () => {
    expect(PAIRS.length).toBeGreaterThan(0);
  });

  for (const pair of PAIRS) {
    const name = (pair.raw.metadata as Record<string, unknown>).name as string;

    test(`${pair.kind}: serialize shape`, () => {
      assertEntryShape(pair.writer.serialize(pair.raw), pair.writer.constructor.name);
    });

    test(`${pair.kind}: write/serialize coherent`, async () => {
      const tmp = tmpRoot();
      try {
        const serDir = join(tmp, "ser", pair.container, name);
        const wriDir = join(tmp, "wri", pair.container, name);
        mkdirSync(serDir, { recursive: true });
        mkdirSync(wriDir, { recursive: true });
        materialize(pair.writer.serialize(pair.raw), serDir);
        await pair.writer.write(new FilesystemBundleHandle(wriDir), pair.raw);
        expect(treeBytes(wriDir)).toEqual(treeBytes(serDir));
      } finally {
        rmSync(tmp, { recursive: true, force: true });
      }
    });

    test(`${pair.kind}: writer output readable + fixpoint`, async () => {
      const tmp = tmpRoot();
      try {
        const cycle = async (
          raw: Record<string, unknown>, step: string,
        ): Promise<{ entries: SerializedFile[]; raw2: Record<string, unknown> }> => {
          const entries = pair.writer.serialize(raw);
          const bundleDir = join(tmp, step, pair.container, name);
          mkdirSync(bundleDir, { recursive: true });
          materialize(entries, bundleDir);
          const reader = await detectingReader(bundleDir);
          if (reader == null) {
            throw new Error(
              `NO registered reader detects the bundle ` +
              `${pair.writer.constructor.name} emits for kind ${pair.kind} — ` +
              `the writer's output is invisible to every scan.`,
            );
          }
          const raw2 = await reader.read(new FilesystemBundleHandle(bundleDir));
          expect(raw2.kind).toBe(pair.kind);
          return { entries, raw2 };
        };

        // identity survives the first cycle
        const first = await cycle(pair.raw, "normalize");
        expect((first.raw2.metadata as Record<string, unknown>).name).toBe(name);

        // §2.1 idempotence: after ONE permitted normalization pass,
        // emit→read→emit is a byte fixpoint.
        const second = await cycle(first.raw2, "second");
        const third = await cycle(second.raw2, "third");
        expect(entriesBytes(third.entries)).toEqual(entriesBytes(second.entries));
      } finally {
        rmSync(tmp, { recursive: true, force: true });
      }
    });
  }
});

// ---------------------------------------------------------------------------
// real market bundles — fixpoint on artifacts we did not author
// ---------------------------------------------------------------------------

function realBundleDirs(root: string): string[] {
  const candidates: string[] = [root];
  for (const child of readdirSync(root).sort()) {
    const full = join(root, child);
    if (!statSync(full).isDirectory() || child.startsWith(".") || child.startsWith("_")) continue;
    candidates.push(full);
    for (const grand of readdirSync(full).sort()) {
      const g = join(full, grand);
      if (statSync(g).isDirectory() && !grand.startsWith(".") && !grand.startsWith("_")) {
        candidates.push(g);
      }
    }
  }
  return candidates;
}

describe("reader/writer round-trip conformance (real market bundles)", () => {
  let dirs: string[] = [];
  try {
    if (statSync(MARKET_SCOPE).isDirectory()) dirs = realBundleDirs(MARKET_SCOPE);
  } catch {
    dirs = [];
  }

  test("market scope fixtures exist", () => {
    expect(dirs.length).toBeGreaterThan(3);
  });

  for (const bundleDir of dirs) {
    const rel = bundleDir.slice(dirname(MARKET_SCOPE).length + 1) || "market-demo";
    test(`real_roundtrip:${rel}`, async () => {
      const reader = await detectingReader(bundleDir);
      if (reader == null) return; // not a bundle any reader claims
      const raw1 = await reader.read(new FilesystemBundleHandle(bundleDir));
      const writer = WRITERS.find((w) => w.canWrite(raw1));
      if (writer == null) return; // read as a kind no writer claims
      const first = writer.serialize(raw1);
      assertEntryShape(first, writer.constructor.name);
      const tmp = tmpRoot();
      try {
        const reDir = join(tmp, dirname(bundleDir).split("/").pop() ?? "c", bundleDir.split("/").pop() ?? "b");
        mkdirSync(reDir, { recursive: true });
        materialize(first, reDir);
        const reReader = await detectingReader(reDir);
        expect(reReader).not.toBeNull();
        const raw2 = await reReader!.read(new FilesystemBundleHandle(reDir));
        expect(raw2.kind).toBe(raw1.kind);
        const second = writer.serialize(raw2);
        expect(entriesBytes(second)).toEqual(entriesBytes(first));
      } finally {
        rmSync(tmp, { recursive: true, force: true });
      }
    });
  }
});
