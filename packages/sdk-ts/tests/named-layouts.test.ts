/**
 * s-dx-named-layouts — author picks composition ORDER by name.
 *
 * Twin of packages/sdk-py/tests/test_named_layouts.py.
 *
 * Before this story, ordering the Soul (persona) before the task instruction
 * meant hand-writing a raw `promptTemplate` full of internal section names.
 * A named `layout:` field resolves to an embedded preset via the Kind — the
 * common case never authors Mustache.
 */
import { afterEach, describe, expect, test } from "bun:test";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { quickInstance } from "../src/bootstrap.js";
import { UnknownLayout } from "../src/kernel/errors.js";

const AGENT_BODY = "# Task\n\nDo the task.";
const SOUL_BODY = "## Persona\n\nCalm, precise, direct.";

const tmpDirs: string[] = [];

function mkScope(opts: { layout?: string; promptTemplate?: string }): string {
  const base = mkdtempSync(path.join(tmpdir(), "dna-layout-"));
  tmpDirs.push(base);
  const scope = "layout-scope";
  const root = path.join(base, scope);
  mkdirSync(path.join(root, "agents", "a1"), { recursive: true });
  mkdirSync(path.join(root, "souls", "s1"), { recursive: true });
  writeFileSync(
    path.join(root, "Genome.yaml"),
    "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\nmetadata:\n  name: " +
      scope +
      "\nspec:\n  default_agent: a1\n",
  );
  const fm = ["name: a1", "description: demo", "soul: s1"];
  if (opts.layout != null) fm.push(`layout: ${opts.layout}`);
  if (opts.promptTemplate != null) fm.push(`promptTemplate: ${JSON.stringify(opts.promptTemplate)}`);
  writeFileSync(
    path.join(root, "agents", "a1", "AGENT.md"),
    "---\n" + fm.join("\n") + "\n---\n" + AGENT_BODY,
  );
  writeFileSync(
    path.join(root, "souls", "s1", "SOUL.md"),
    "---\nname: s1\n---\n" + SOUL_BODY,
  );
  return base;
}

async function build(opts: { layout?: string; promptTemplate?: string }): Promise<string> {
  const base = mkScope(opts);
  const mi = await quickInstance("layout-scope", base);
  return await mi.buildPrompt({ agent: "a1" });
}

afterEach(() => {
  while (tmpDirs.length) rmSync(tmpDirs.pop()!, { recursive: true, force: true });
});

describe("s-dx-named-layouts", () => {
  test("absent layout is instruction-first (instruction before persona)", async () => {
    const prompt = await build({});
    expect(prompt.indexOf("Do the task.")).toBeLessThan(prompt.indexOf("Calm, precise, direct."));
  });

  test("instruction-first === default", async () => {
    const dflt = await build({});
    const explicit = await build({ layout: "instruction-first" });
    const alias = await build({ layout: "default" });
    expect(explicit).toBe(dflt);
    expect(alias).toBe(dflt);
  });

  test("persona-first puts the Soul before the instruction", async () => {
    const prompt = await build({ layout: "persona-first" });
    expect(prompt).toContain("Calm, precise, direct.");
    expect(prompt).toContain("Do the task.");
    expect(prompt.indexOf("Calm, precise, direct.")).toBeLessThan(prompt.indexOf("Do the task."));
  });

  test("raw promptTemplate wins over layout", async () => {
    const prompt = await build({ layout: "persona-first", promptTemplate: "RAW-ONLY {{agent.name}}" });
    expect(prompt.trim()).toBe("RAW-ONLY a1");
  });

  test("unknown layout fails loud with UnknownLayout", async () => {
    let err: unknown;
    try {
      await build({ layout: "persona_first" }); // typo: underscore
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(UnknownLayout);
    expect((err as UnknownLayout).layout).toBe("persona_first");
    expect((err as UnknownLayout).agent).toBe("a1");
    expect((err as UnknownLayout).available).toContain("persona-first");
  });
});
