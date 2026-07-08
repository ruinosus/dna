/**
 * Descriptor expressiveness — the 6 new KindDefinitionSpec fields (D1/D3-D7).
 * Twin of packages/sdk-py/tests/test_descriptor_expressiveness_fields.py.
 *
 * ui, describe, ui_schema, spec_defaults, default_agent_field,
 * description_fallback_field — all optional, back-compat defaults. ui keys are
 * validated ⊆ StudioUIMetadata fields (strict); ui_schema is permissive.
 */
import { describe as suite, expect, test } from "bun:test";
import { KindDefinitionSchema } from "../src/kernel/models.js";
import { DeclarativeKindPort } from "../src/kernel/meta.js";
import { StudioUIMetadata, UI_METADATA_FIELDS } from "../src/kernel/studio_ui.js";
import type { Document } from "../src/kernel/document.js";

function baseRaw(spec: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    apiVersion: "github.com/ruinosus/dna/core/v1",
    kind: "KindDefinition",
    metadata: { name: "expr-thing" },
    spec: {
      target_api_version: "github.com/ruinosus/dna/expr/v1",
      target_kind: "ExprThing",
      alias: "expr-thing",
      origin: "github.com/ruinosus/dna/expr",
      storage: { type: "yaml", container: "expr-things" },
      schema: {
        type: "object",
        properties: {
          agent_ref: { type: "string" },
          description: { type: "string" },
          name: { type: "string" },
          status: { type: "string" },
        },
      },
      ...spec,
    },
  };
}

function parse(raw: Record<string, unknown>) {
  return KindDefinitionSchema.parse(raw).spec;
}

suite("KindDefinitionSpec — descriptor expressiveness fields", () => {
  test("all six fields parse with correct types", () => {
    const s = parse(
      baseRaw({
        ui: {
          mode: "quality",
          in_sidebar: true,
          display_order: 20,
          label: { en: "Things", "pt-BR": "Coisas" },
          icon: "🔬",
          routes: { list: "expr/things", detail: "expr/things/:id" },
          permissions: { list: "any" },
        },
        describe: "{name} ({status})",
        ui_schema: { name: { widget: "input", anything: "goes" } },
        spec_defaults: { status: "pending" },
        default_agent_field: "agent_ref",
        description_fallback_field: "description",
      }),
    );
    expect((s.ui as Record<string, unknown>).mode).toBe("quality");
    expect(s.describe).toBe("{name} ({status})");
    expect(s.ui_schema).toEqual({ name: { widget: "input", anything: "goes" } });
    expect(s.spec_defaults).toEqual({ status: "pending" });
    expect(s.default_agent_field).toBe("agent_ref");
    expect(s.description_fallback_field).toBe("description");
  });

  test("absent fields default to null/undefined (back-compat)", () => {
    const s = parse(baseRaw());
    expect(s.ui ?? null).toBeNull();
    expect(s.describe ?? null).toBeNull();
    expect(s.ui_schema ?? null).toBeNull();
    expect(s.spec_defaults ?? null).toBeNull();
    expect(s.default_agent_field ?? null).toBeNull();
    expect(s.description_fallback_field ?? null).toBeNull();
  });

  test("ui unknown key raises", () => {
    expect(() => parse(baseRaw({ ui: { mode: "quality", bogus: 1 } }))).toThrow();
  });

  test("every StudioUIMetadata field is an accepted ui key", () => {
    const ui: Record<string, unknown> = {};
    for (const f of UI_METADATA_FIELDS) ui[f] = null;
    ui.mode = "build";
    const s = parse(baseRaw({ ui }));
    for (const k of Object.keys(s.ui as Record<string, unknown>)) {
      expect(UI_METADATA_FIELDS as readonly string[]).toContain(k);
    }
  });

  test("ui must be a mapping (array rejected)", () => {
    expect(() => parse(baseRaw({ ui: ["mode"] }))).toThrow();
  });

  test("ui_schema unknown keys ok (permissive)", () => {
    const s = parse(baseRaw({ ui_schema: { any_field: { widget: "made-up", order: 9 } } }));
    expect(s.ui_schema).toEqual({ any_field: { widget: "made-up", order: 9 } });
  });

  test("describe string form", () => {
    expect(parse(baseRaw({ describe: "{name}" })).describe).toBe("{name}");
  });

  test("describe path form", () => {
    expect(parse(baseRaw({ describe: { path: "description" } })).describe).toEqual({
      path: "description",
    });
  });

  test("describe bad type raises", () => {
    expect(() => parse(baseRaw({ describe: 123 }))).toThrow();
  });
});

// ─────────────────────────────────────────────────────────────────────────
// Task 3 (port): DeclarativeKindPort consumes the fields
// ─────────────────────────────────────────────────────────────────────────

function port(spec: Record<string, unknown> = {}): DeclarativeKindPort {
  const typed = KindDefinitionSchema.parse(baseRaw(spec));
  return DeclarativeKindPort.fromTyped(typed);
}

function autolabRaw(spec: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    apiVersion: "github.com/ruinosus/dna/core/v1",
    kind: "KindDefinition",
    metadata: { name: "autolab-run-like" },
    spec: {
      target_api_version: "github.com/ruinosus/dna/autolab/v1",
      target_kind: "AutolabRunLike",
      alias: "autolab-run-like",
      origin: "local",
      storage: { type: "yaml", container: "autolab-runs" },
      schema: {
        type: "object",
        required: ["program", "max_iterations"],
        additionalProperties: true,
        properties: {
          program: { type: "string" },
          max_iterations: { type: "integer", minimum: 1 },
          max_wall_clock_sec: { type: "integer", minimum: 60 },
          plateau_patience: { type: "integer", minimum: 1 },
          mode: { type: "string", enum: ["autonomous", "preview"] },
          tasks_dir: { type: "string" },
          meta_agent: { type: "string" },
        },
      },
      ...spec,
    },
  };
}

const AUTOLAB_DEFAULTS = {
  max_wall_clock_sec: 3600,
  plateau_patience: 3,
  mode: "autonomous",
  tasks_dir: "tasks/",
  meta_agent: "meta-harness-engineer",
};

function autolabPort(spec: Record<string, unknown> = {}): DeclarativeKindPort {
  return DeclarativeKindPort.fromTyped(KindDefinitionSchema.parse(autolabRaw(spec)));
}

function doc(spec: Record<string, unknown>): Document {
  return { spec } as unknown as Document;
}

suite("DeclarativeKindPort — descriptor expressiveness", () => {
  // ── port.ui reconstructed StudioUIMetadata ──────────────────────────────
  test("port.ui = reconstructed StudioUIMetadata", () => {
    const p = port({
      ui: {
        mode: "quality",
        in_sidebar: true,
        display_order: 20,
        label: { en: "Things", "pt-BR": "Coisas" },
        icon: "🔬",
      },
    });
    expect(p.ui).toBeInstanceOf(StudioUIMetadata);
    expect(p.ui?.mode).toBe("quality");
    expect(p.ui?.toDict()).toEqual({
      mode: "quality",
      in_sidebar: true,
      display_order: 20,
      label: { en: "Things", "pt-BR": "Coisas" },
      icon: "🔬",
    });
    expect(p.ui?.resolveLabel("pt-BR")).toBe("Coisas");
  });

  test("port.ui = undefined when absent", () => {
    expect(port().ui).toBeUndefined();
  });

  // ── pass-through attrs ──────────────────────────────────────────────────
  test("port.descriptionFallbackField pass-through", () => {
    expect(port({ description_fallback_field: "description" }).descriptionFallbackField).toBe(
      "description",
    );
    expect(port().descriptionFallbackField).toBeUndefined();
  });

  // ── describe(doc) ───────────────────────────────────────────────────────
  test("describe template substitutes fields", () => {
    expect(port({ describe: "{name} ({status})" }).describe(doc({ name: "Foo", status: "open" }))).toBe(
      "Foo (open)",
    );
  });

  test("describe template missing field → empty", () => {
    expect(port({ describe: "{name} ({status})" }).describe(doc({ name: "Foo" }))).toBe("Foo ()");
  });

  test("describe path form verbatim", () => {
    expect(port({ describe: { path: "description" } }).describe(doc({ description: "hi" }))).toBe("hi");
  });

  test("describe path form missing → null", () => {
    expect(port({ describe: { path: "description" } }).describe(doc({ name: "Foo" }))).toBeNull();
  });

  test("describe none when absent", () => {
    expect(port().describe(doc({ name: "Foo" }))).toBeNull();
  });

  // ── parse(raw) spec_defaults merge + lint ───────────────────────────────
  test("parse merges spec_defaults before validation", () => {
    const p = autolabPort({ spec_defaults: AUTOLAB_DEFAULTS });
    const out = p.parse({ spec: { program: "p", max_iterations: 3 } }) as {
      spec: Record<string, unknown>;
    };
    expect(out.spec.mode).toBe("autonomous");
    expect(out.spec.max_wall_clock_sec).toBe(3600);
    expect(out.spec.program).toBe("p");
    expect(out.spec.max_iterations).toBe(3);
  });

  test("parse spec overrides defaults", () => {
    const p = autolabPort({ spec_defaults: AUTOLAB_DEFAULTS });
    const out = p.parse({ spec: { program: "p", max_iterations: 3, mode: "preview" } }) as {
      spec: Record<string, unknown>;
    };
    expect(out.spec.mode).toBe("preview");
  });

  test("load-time lint accepts autolab partial defaults (ignores required)", () => {
    expect(() => autolabPort({ spec_defaults: AUTOLAB_DEFAULTS })).not.toThrow();
  });

  test("load-time lint rejects default key absent from schema", () => {
    expect(() => autolabPort({ spec_defaults: { not_a_field: 1 } })).toThrow(/spec_defaults/);
  });

  test("load-time lint rejects default value violating subschema", () => {
    expect(() => autolabPort({ spec_defaults: { mode: "bogus" } })).toThrow(/spec_defaults/);
  });

  test("parse without spec_defaults is pass-through", () => {
    const out = port().parse({ spec: { name: "x" } }) as { spec: Record<string, unknown> };
    expect(out.spec).toEqual({ name: "x" });
  });

  // ── getDefaultAgentName VERBATIM ────────────────────────────────────────
  test("getDefaultAgentName verbatim", () => {
    expect(port({ default_agent_field: "agent_ref" }).getDefaultAgentName(doc({ agent_ref: "a" }))).toBe(
      "a",
    );
  });

  test("getDefaultAgentName empty string verbatim (not null)", () => {
    expect(port({ default_agent_field: "agent_ref" }).getDefaultAgentName(doc({ agent_ref: "" }))).toBe(
      "",
    );
  });

  test("getDefaultAgentName missing field → null", () => {
    expect(port({ default_agent_field: "agent_ref" }).getDefaultAgentName(doc({ name: "x" }))).toBeNull();
  });

  test("getDefaultAgentName falls back to static default_agent when no field", () => {
    expect(port({ default_agent: "static-agent" }).getDefaultAgentName(doc({}))).toBe("static-agent");
  });
});
