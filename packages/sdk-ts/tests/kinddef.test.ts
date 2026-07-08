/**
 * Phase C tests — KindDefinition meta-kind, DeclarativeKindPort,
 * 2-phase loading, conflict resolution, round-trip via the generic writer.
 *
 * Mirrors python/tests/test_kinddef.py.
 */
import { describe, test, expect } from "bun:test";
import { mkdtempSync, writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import yaml from "js-yaml";

import { Kernel } from "../src/kernel/index.js";
import { HelixExtension } from "../src/extensions/helix.js";
import { AgentSkillsExtension } from "../src/extensions/agentskills.js";
import { SoulSpecExtension } from "../src/extensions/soulspec.js";
import { AgentsMdExtension } from "../src/extensions/agentsmd.js";
import { GuardrailExtension } from "../src/extensions/guardrails.js";
import { KindDefinitionExtension } from "../src/extensions/kinddef.js";
import { FilesystemSource } from "../src/adapters/filesystem/source.js";
import { FilesystemCache } from "../src/adapters/filesystem/cache.js";
import {
  KindDefinitionSchema,
  KIND_DEFINITION_API_VERSION,
  KIND_DEFINITION_KIND,
} from "../src/kernel/models.js";
import { DeclarativeKindPort, storageDictToDescriptor } from "../src/kernel/meta.js";

function _fullKindDefSpec(): Record<string, unknown> {
  return {
    target_api_version: "example.com/v1",
    target_kind: "Recipe",
    alias: "example-recipe",
    origin: "example.com",
    is_root: false,
    prompt_target: false,
    flatten_in_context: false,
    docs: "A cooking recipe with ingredients and steps.",
    schema: {
      type: "object",
      required: ["title", "ingredients"],
      properties: {
        title: { type: "string" },
        ingredients: { type: "array", items: { type: "string" } },
        minutes: { type: "integer", minimum: 0 },
      },
      additionalProperties: true,
    },
    storage: {
      type: "bundle",
      container: "recipes",
      marker: "RECIPE.md",
      body_as: "text",
      body_field: "description",
    },
    dep_filters: { "example-recipe": "include" },
  };
}

function _fullKindDefRaw(): Record<string, unknown> {
  return {
    apiVersion: KIND_DEFINITION_API_VERSION,
    kind: KIND_DEFINITION_KIND,
    metadata: { name: "recipe" },
    spec: _fullKindDefSpec(),
  };
}

function _makeModule(scopeDir: string): void {
  mkdirSync(scopeDir, { recursive: true });
  writeFileSync(
    join(scopeDir, "manifest.yaml"),
    yaml.dump({
      apiVersion: "github.com/ruinosus/dna/v1",
      kind: "Genome",
      metadata: { name: scopeDir.split("/").pop(), description: "test" },
      spec: {},
    }),
  );
}

function _kernelWithAll(): Kernel {
  const k = new Kernel();
  k.load(new HelixExtension());
  k.load(new AgentSkillsExtension());
  k.load(new SoulSpecExtension());
  k.load(new AgentsMdExtension());
  k.load(new GuardrailExtension());
  k.load(new KindDefinitionExtension());
  return k;
}

// ---------------------------------------------------------------------------
// 3.1 Schema parse
// ---------------------------------------------------------------------------

describe("3.1 KindDefinitionSchema", () => {
  test("parses a full spec", async () => {
    const typed = KindDefinitionSchema.parse(_fullKindDefRaw());
    expect(typed.metadata.name).toBe("recipe");
    expect(typed.spec.target_kind).toBe("Recipe");
    expect(typed.spec.alias).toBe("example-recipe");
    expect((typed.spec.schema as Record<string, unknown>).required).toEqual([
      "title",
      "ingredients",
    ]);
  });

  test("rejects missing required fields", async () => {
    const bad = {
      apiVersion: KIND_DEFINITION_API_VERSION,
      kind: KIND_DEFINITION_KIND,
      metadata: { name: "broken" },
      spec: { target_kind: "X" },
    };
    expect(() => KindDefinitionSchema.parse(bad)).toThrow();
  });
});

// ---------------------------------------------------------------------------
// 3.2 DeclarativeKindPort + storage conversion
// ---------------------------------------------------------------------------

describe("3.2 DeclarativeKindPort", () => {
  test("parse happy path validates against JSON schema", async () => {
    const typed = KindDefinitionSchema.parse(_fullKindDefRaw());
    const port = DeclarativeKindPort.fromTyped(typed);
    expect(port.kind).toBe("Recipe");
    expect(port.apiVersion).toBe("example.com/v1");
    expect(port.alias).toBe("example-recipe");
    expect(port.depFilters()).toEqual({ "example-recipe": "include" });

    const raw = {
      apiVersion: "example.com/v1",
      kind: "Recipe",
      metadata: { name: "pasta" },
      spec: { title: "Pasta", ingredients: ["flour", "water"] },
    };
    const out = port.parse(raw) as { spec: { title: string } };
    expect(out.spec.title).toBe("Pasta");
  });

  test("parse rejects missing required fields", async () => {
    const typed = KindDefinitionSchema.parse(_fullKindDefRaw());
    const port = DeclarativeKindPort.fromTyped(typed);
    const raw = {
      apiVersion: "example.com/v1",
      kind: "Recipe",
      metadata: { name: "broken" },
      spec: { title: "Only title" },
    };
    expect(() => port.parse(raw)).toThrow(/validation failed/);
  });

  test("storage_dict_to_descriptor — bundle", async () => {
    const sd = storageDictToDescriptor({ type: "bundle", container: "recipes", marker: "RECIPE.md" });
    expect(sd.pattern).toBe("bundle");
    expect(sd.container).toBe("recipes");
    expect(sd.marker).toBe("RECIPE.md");
  });

  test("storage_dict_to_descriptor — yaml", async () => {
    const sd = storageDictToDescriptor({ type: "yaml", container: "recipes" });
    expect(sd.pattern).toBe("yaml");
    expect(sd.container).toBe("recipes");
  });

  test("storage_dict_to_descriptor — standalone", async () => {
    const sd = storageDictToDescriptor({ type: "standalone", path: "FOO.md" });
    expect(sd.pattern).toBe("standalone");
    expect(sd.marker).toBe("FOO.md");
  });

  test("storage_dict_to_descriptor — unknown type is loud", async () => {
    expect(() => storageDictToDescriptor({ type: "weird", container: "x" })).toThrow(/unknown storage type/);
  });

  test("storage_dict_to_descriptor — missing type is loud", async () => {
    expect(() => storageDictToDescriptor({ container: "x" })).toThrow(/type/);
  });
});

// ---------------------------------------------------------------------------
// 3.3 KindDefinitionExtension loads from filesystem
// ---------------------------------------------------------------------------

describe("3.3 KindDefinitionExtension", () => {
  test("extension registers KindDefinition kind", async () => {
    const k = _kernelWithAll();
    const key = `${KIND_DEFINITION_API_VERSION}\0${KIND_DEFINITION_KIND}`;
    expect(k._kinds.has(key)).toBe(true);
    expect(k._kinds.get(key)!.alias).toBe("kinddef-kinddefinition");
  });

  test("loads KindDefinition from disk", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "kinddef-"));
    const scopeDir = join(tmp, ".dna", "demo");
    _makeModule(scopeDir);
    const bundle = join(scopeDir, "kinds", "recipe");
    mkdirSync(bundle, { recursive: true });
    writeFileSync(join(bundle, "KIND.yaml"), yaml.dump(_fullKindDefRaw()));

    const k = _kernelWithAll();
    k.source(new FilesystemSource(join(tmp, ".dna")));
    k.cache(new FilesystemCache(join(tmp, ".dna")));

    const mi = await k.instance("demo");
    const kinddefs = mi.all("KindDefinition");
    expect(kinddefs.length).toBe(1);
    expect(kinddefs[0].name).toBe("recipe");
  });
});

// ---------------------------------------------------------------------------
// 3.4 End-to-end 2-phase loading
// ---------------------------------------------------------------------------

describe("3.4 Two-phase loading", () => {
  test("KindDefinition + instance doc of the new kind", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "kinddef-2phase-"));
    const scopeDir = join(tmp, ".dna", "demo");
    _makeModule(scopeDir);

    const bundle = join(scopeDir, "kinds", "recipe");
    mkdirSync(bundle, { recursive: true });
    writeFileSync(join(bundle, "KIND.yaml"), yaml.dump(_fullKindDefRaw()));

    const recipeDir = join(scopeDir, "recipes", "pasta");
    mkdirSync(recipeDir, { recursive: true });
    writeFileSync(
      join(recipeDir, "RECIPE.md"),
      "---\nname: pasta\ntitle: Simple Pasta\ningredients:\n  - flour\n  - water\n---\n\nBoil water, cook pasta.",
    );

    const k = _kernelWithAll();
    k.source(new FilesystemSource(join(tmp, ".dna")));
    k.cache(new FilesystemCache(join(tmp, ".dna")));

    const mi = await k.instance("demo");

    // Declarative port registered
    const key = `example.com/v1\0Recipe`;
    expect(k._kinds.has(key)).toBe(true);
    expect((k._kinds.get(key) as unknown as { __declarative__?: boolean }).__declarative__).toBe(true);

    const recipes = mi.all("Recipe");
    expect(recipes.length).toBe(1);
    const doc = recipes[0];
    expect(doc.name).toBe("pasta");
    expect(doc.spec.title).toBe("Simple Pasta");
    expect(doc.spec.ingredients).toEqual(["flour", "water"]);
  });
});

// ---------------------------------------------------------------------------
// 3.5 Conflict resolution — extension wins
// ---------------------------------------------------------------------------

describe("3.5 Conflict resolution", () => {
  test("extension-backed SoulKind wins over a colliding KindDefinition", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "kinddef-conflict-"));
    const scopeDir = join(tmp, ".dna", "demo");
    _makeModule(scopeDir);

    const colliding = {
      apiVersion: KIND_DEFINITION_API_VERSION,
      kind: KIND_DEFINITION_KIND,
      metadata: { name: "soul-override" },
      spec: {
        target_api_version: "soulspec.org/v1",
        target_kind: "Soul",
        alias: "fake-soul",
        origin: "evil.example.com",
        schema: { type: "object" },
        storage: { type: "bundle", container: "fake-souls", marker: "FAKE.md" },
      },
    };
    const bundle = join(scopeDir, "kinds", "soul-override");
    mkdirSync(bundle, { recursive: true });
    writeFileSync(join(bundle, "KIND.yaml"), yaml.dump(colliding));

    const events: Array<Record<string, unknown>> = [];
    const k = _kernelWithAll();
    k.on("kinddef_conflict", (ctx) => { events.push(ctx as unknown as Record<string, unknown>); });
    k.source(new FilesystemSource(join(tmp, ".dna")));
    k.cache(new FilesystemCache(join(tmp, ".dna")));

    const mi = await k.instance("demo");

    const soulPort = k._kinds.get("soulspec.org/v1\0Soul")!;
    expect((soulPort as unknown as { __declarative__?: boolean }).__declarative__).not.toBe(true);
    expect(soulPort.alias).toBe("soulspec-soul");

    expect(events.some((e) => e.kind === "Soul")).toBe(true);
    expect(mi.all("KindDefinition").length).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// 3.6 Round-trip via the kernel's serializeDocument path
// ---------------------------------------------------------------------------

describe("3.6 Round-trip", () => {
  test("write a declarative-kind doc via GenericBundleWriter and reload", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "kinddef-rt-"));
    const scopeDir = join(tmp, ".dna", "demo");
    _makeModule(scopeDir);

    const bundle = join(scopeDir, "kinds", "recipe");
    mkdirSync(bundle, { recursive: true });
    writeFileSync(join(bundle, "KIND.yaml"), yaml.dump(_fullKindDefRaw()));

    const k = _kernelWithAll();
    k.source(new FilesystemSource(join(tmp, ".dna")));
    k.cache(new FilesystemCache(join(tmp, ".dna")));
    await k.instance("demo");

    const raw = {
      apiVersion: "example.com/v1",
      kind: "Recipe",
      metadata: { name: "bread" },
      spec: {
        title: "Sourdough",
        ingredients: ["flour", "water", "salt"],
        description: "A crusty loaf.",
      },
    };

    const result = k.serializeDocument("demo", "Recipe", "bread", raw);
    expect(result.files.some((f) => f.relativePath.endsWith("RECIPE.md"))).toBe(true);

    for (const f of result.files) {
      const target = join(scopeDir, f.relativePath);
      mkdirSync(join(target, ".."), { recursive: true });
      writeFileSync(target, f.content);
    }

    const k2 = _kernelWithAll();
    k2.source(new FilesystemSource(join(tmp, ".dna")));
    k2.cache(new FilesystemCache(join(tmp, ".dna")));
    const mi2 = await k2.instance("demo");

    const recipes = mi2.all("Recipe");
    expect(recipes.length).toBe(1);
    const reloaded = recipes[0];
    expect(reloaded.name).toBe("bread");
    expect(reloaded.spec.title).toBe("Sourdough");
    expect(reloaded.spec.ingredients).toEqual(["flour", "water", "salt"]);
  });
});
