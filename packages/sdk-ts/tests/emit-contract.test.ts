/**
 * `emit` — the EmitterPort CONTRACT, run over EVERY registered target (TS twin of
 * `test_emit_contract.py`, s-emit-port-contract).
 *
 * Pins the contract invariants EVERY emitter must honor, asserted generically over
 * `availableTargets()` so a NEW emitter inherits the checks the moment it registers:
 *   1. the byte-equal invariant — the composed instruction in the artifact equals
 *      `mi.buildPrompt({agent})`, via the contract's own `extractInstructions` hook
 *      (holds for config-declarative AND scaffold targets uniformly).
 *   2. the port shape — target/fileExtension consistent with EmitResult; losses list.
 *   3. the registry is pluggable and honest — both flavors present; UnknownTarget
 *      names the available set.
 */
import { describe, it, expect } from "bun:test";
import { join } from "node:path";

import { quickInstance } from "../src/bootstrap.js";
import {
  emitAgent,
  buildEmitContext,
  availableTargets,
  getEmitter,
  UnknownTarget,
} from "../src/index.js";

const ROOT = join(import.meta.dir, "..", "..", "..");
const BASE = join(ROOT, "examples", "emitting-to-a-runtime", ".dna");
const SCOPE = "concierge";
const AGENT = "concierge";

describe("EmitterPort contract — over every registered target", () => {
  it("byte-equal invariant holds for every target", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const prompt = await mi.buildPrompt({ agent: AGENT });
    for (const target of await availableTargets()) {
      const result = await emitAgent(mi, AGENT, target);
      const emitter = await getEmitter(target);
      const recovered = emitter.extractInstructions(result.artifact);
      expect(recovered, `${target} carries no recoverable instruction`).not.toBeNull();
      expect(recovered).toBe(prompt);
    }
  });

  it("port shape is consistent for every target", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    for (const target of await availableTargets()) {
      const emitter = await getEmitter(target);
      expect(emitter.target).toBe(target);
      expect(emitter.fileExtension.length).toBeGreaterThan(0);
      const result = await emitAgent(mi, AGENT, target);
      expect(result.target).toBe(target);
      expect(result.filename.endsWith(emitter.fileExtension)).toBe(true);
      expect(Array.isArray(result.losses)).toBe(true);
      const joined = result.losses.join(" ");
      expect(joined).toContain("composition structure");
      expect(joined).toContain("tenant overlay");
      expect(joined).toContain("eval-as-contract");
    }
  });

  it("registry is non-empty and contains both flavors", async () => {
    const targets = await availableTargets();
    expect(targets.length).toBeGreaterThan(0);
    expect(targets).toContain("agent-framework"); // config-declarative
    expect(targets).toContain("openai-agents"); // scaffold / code-first
  });

  it("UnknownTarget names the available set", async () => {
    let err: unknown;
    try {
      await getEmitter("no-such-runtime");
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(UnknownTarget);
    expect(new Set((err as UnknownTarget).available)).toEqual(new Set(await availableTargets()));
  });

  it("buildEmitContext is the shared front door", async () => {
    const mi = await quickInstance(SCOPE, BASE);
    const ctx = await buildEmitContext(mi, AGENT);
    expect(ctx.instructions).toBe(await mi.buildPrompt({ agent: AGENT }));
    expect(ctx.name).toBe(AGENT);
  });
});
