/**
 * Generic write-path spec↔schema validation (s-write-path-validation, i-008)
 * — TS side. Py twin: packages/sdk-py/tests/test_write_path_validation.py.
 *
 * The kernel used to validate Kind schemas only at SCAN/read (the fail-soft
 * `parse_error` channel) — `writeDocument` would persist a shape-broken
 * spec that exploded later, far from the author. Now `WritePipeline.write`
 * validates the spec against the Kind's declared `schema()` AFTER the
 * `pre_save` veto hooks (Kind-owned cures land first) and BEFORE
 * persistence. Kinds without a schema stay permissive; the error is
 * didactic (field, violation, `dna kind show <Kind>` — the install #26
 * pattern); `DNA_WRITE_VALIDATION=warn|off` are the escape hatches.
 */
import { describe, it, expect, afterEach } from "bun:test";
import { createKernelWithBuiltins } from "../src/bootstrap.js";
import { SpecValidationError } from "../src/kernel/protocols.js";

const SDLC_API = "github.com/ruinosus/dna/sdlc/v1";
const EVAL_API = "github.com/ruinosus/dna/eval/v1";
const AUTOMATION_API = "github.com/ruinosus/dna/automation/v1";

function freshKernel() {
  const k = createKernelWithBuiltins();
  const src = {
    saveCalls: [] as unknown[],
    async saveDocument(scope: string, kind: string, name: string) {
      this.saveCalls.push([scope, kind, name]);
      return "v1";
    },
    async deleteDocument() {},
    async loadBootstrapDocs() { return []; },
    async loadDocument() { return null; },
    async loadAll() { return []; },
    async loadLayer() { return []; },
    async listVersions() { return []; },
    async listScopes() { return []; },
  };
  k.source(src as never);
  k.writableSource(src as never);
  k.cache({
    has: async () => false,
    store: async () => {},
    loadKey: async () => [],
    loadAll: async () => [],
  } as never);
  return { k, src };
}

function raw(
  api: string,
  kind: string,
  name: string,
  spec: Record<string, unknown>,
): Record<string, unknown> {
  return { apiVersion: api, kind, metadata: { name }, spec };
}

function validLesson(name: string): Record<string, unknown> {
  return raw(SDLC_API, "LessonLearned", name, {
    area: "Feature/write-path",
    surface_when: ["feature_touched"],
    source_refs: ["s-write-path-validation"],
    affect: "triumph",
    affect_reason: "write-path validation shipped with 2/2925 evidence",
    summary: "validate at write, not only at scan",
  });
}

afterEach(() => {
  delete process.env.DNA_WRITE_VALIDATION;
});

describe("write-path spec↔schema validation (i-008)", () => {
  it("vetoes an invalid spec and persists nothing", async () => {
    const { k, src } = freshKernel();
    const bad = validLesson("rem-bad");
    (bad.spec as Record<string, unknown>).confidence_score = "faint"; // schema: number
    await expect(
      k.writeDocument("s", "LessonLearned", "rem-bad", bad),
    ).rejects.toThrow(SpecValidationError);
    expect(src.saveCalls).toEqual([]);
  });

  it("vetoes a missing required field", async () => {
    const { k, src } = freshKernel();
    await expect(
      k.writeDocument(
        "s", "LessonLearned", "rem-skel",
        raw(SDLC_API, "LessonLearned", "rem-skel", { summary: "no area" }),
      ),
    ).rejects.toThrow(/required property 'area'|must have required property/);
    expect(src.saveCalls).toEqual([]);
  });

  it("persists a valid spec", async () => {
    const { k, src } = freshKernel();
    await k.writeDocument("s", "LessonLearned", "rem-ok", validLesson("rem-ok"));
    expect(src.saveCalls.length).toBe(1);
  });

  it("raises a didactic error (field + violation + kind show hint)", async () => {
    const { k } = freshKernel();
    const bad = validLesson("rem-bad");
    (bad.spec as Record<string, unknown>).confidence_score = "faint";
    let msg = "";
    try {
      await k.writeDocument("s", "LessonLearned", "rem-bad", bad);
    } catch (e) {
      msg = (e as Error).message;
    }
    expect(msg).toContain("spec.confidence_score");
    expect(msg).toContain("dna kind show LessonLearned");
    expect(msg).toContain("s/LessonLearned/rem-bad");
  });

  it("a Kind without a schema stays permissive", async () => {
    const { k, src } = freshKernel();
    await k.writeDocument(
      "s", "TotallyUnregisteredKind", "n",
      raw("example.com/x/v1", "TotallyUnregisteredKind", "n", {
        anything: ["goes", 1, null],
      }),
    );
    expect(src.saveCalls.length).toBe(1);
  });

  it("spec_defaults (descriptor D5) fill before validation", async () => {
    const { k, src } = freshKernel();
    k.kindFromDescriptor({
      apiVersion: "github.com/ruinosus/dna/core/v1",
      kind: "KindDefinition",
      metadata: { name: "wpv-defaulted" },
      spec: {
        target_api_version: "example.com/wpv/v1",
        target_kind: "WpvDefaulted",
        alias: "example-wpv-defaulted",
        origin: "example.com/wpv",
        plane: "record",
        storage: { type: "yaml", container: "wpv-defaulted" },
        spec_defaults: { mode: "auto" },
        schema: {
          type: "object",
          required: ["mode"],
          properties: { mode: { type: "string" } },
        },
      },
    });
    await k.writeDocument(
      "s", "WpvDefaulted", "d",
      raw("example.com/wpv/v1", "WpvDefaulted", "d", {}), // mode from defaults
    );
    expect(src.saveCalls.length).toBe(1);
  });

  it("DNA_WRITE_VALIDATION=warn persists anyway", async () => {
    const { k, src } = freshKernel();
    process.env.DNA_WRITE_VALIDATION = "warn";
    await k.writeDocument(
      "s", "LessonLearned", "rem-warn",
      raw(SDLC_API, "LessonLearned", "rem-warn", { summary: "no area" }),
    );
    expect(src.saveCalls.length).toBe(1);
  });

  it("DNA_WRITE_VALIDATION=off skips the step", async () => {
    const { k, src } = freshKernel();
    process.env.DNA_WRITE_VALIDATION = "off";
    await k.writeDocument(
      "s", "LessonLearned", "rem-off",
      raw(SDLC_API, "LessonLearned", "rem-off", { summary: "no area" }),
    );
    expect(src.saveCalls.length).toBe(1);
  });

  it("an unknown mode falls back to enforce", async () => {
    const { k } = freshKernel();
    process.env.DNA_WRITE_VALIDATION = "bananas";
    await expect(
      k.writeDocument(
        "s", "LessonLearned", "rem-x",
        raw(SDLC_API, "LessonLearned", "rem-x", { summary: "no area" }),
      ),
    ).rejects.toThrow(SpecValidationError);
  });

  // --- red→green: the real i-008 shapes ------------------------------------

  it("i-008: a shape-broken Automation is vetoed by the GENERIC step", async () => {
    const { k, src } = freshKernel();
    await expect(
      k.writeDocument(
        "s", "Automation", "no-cron",
        raw(AUTOMATION_API, "Automation", "no-cron", {
          on: { type: "cron" },
          runner: { kind: "agent", ref: "x" },
        }),
      ),
    ).rejects.toThrow(SpecValidationError);
    expect(src.saveCalls).toEqual([]);
  });

  it("EvalCase with a wrong checks shape is vetoed; a valid one persists", async () => {
    const { k, src } = freshKernel();
    await expect(
      k.writeDocument(
        "s", "EvalCase", "bad-checks",
        raw(EVAL_API, "EvalCase", "bad-checks", {
          checks: { type: "contains", value: "x" },
        }),
      ),
    ).rejects.toThrow(/spec\.checks/);
    expect(src.saveCalls).toEqual([]);
    await k.writeDocument(
      "s", "EvalCase", "ok",
      raw(EVAL_API, "EvalCase", "ok", {
        checks: [{ type: "contains", value: "hello" }],
      }),
    );
    expect(src.saveCalls.length).toBe(1);
  });
});
