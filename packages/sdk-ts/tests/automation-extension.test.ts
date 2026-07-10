/**
 * Automation Kind (s-tier-a-automation) — TS side.
 *
 * Py twin: packages/sdk-py/tests/test_automation_extension.py. The
 * descriptor FILE is byte-identical package data
 * (descriptor-hash-parity.test.ts); this pins the TS registration
 * surface, the two validation layers (JSON Schema shape at parse; the
 * `pre_save` veto guard for cron grammar + hook-name vocabulary) and the
 * host query helpers.
 */
import { describe, it, expect } from "bun:test";
import { createKernelWithBuiltins } from "../src/bootstrap.js";
import { KNOWN_HOOK_NAMES } from "../src/kernel/hooks.js";
import {
  automationsFor,
  triggerKey,
  TRIGGER_TYPES,
} from "../src/extensions/automation/query.js";
import { validateCronExpression } from "../src/extensions/automation/write-guards.js";
import type { Document } from "../src/kernel/document.js";

const API = "github.com/ruinosus/dna/automation/v1";

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
  // The evidence-capture post_save listener resolves an instance, which
  // requires a cache port.
  k.cache({
    has: async () => false,
    store: async () => {},
    loadKey: async () => [],
    loadAll: async () => [],
  } as never);
  return k;
}

const kernel = createKernelWithBuiltins();
const port = kernel.kindPortFor("Automation") as unknown as Record<string, unknown>;
const parse = (port.parse as (raw: Record<string, unknown>) => Record<string, unknown>).bind(port);

function raw(spec: Record<string, unknown>, name = "t"): Record<string, unknown> {
  return { apiVersion: API, kind: "Automation", metadata: { name }, spec };
}

describe("AutomationExtension (builtin descriptor)", () => {
  it("registers Automation from the descriptor with the dna-automation alias", () => {
    expect(port).toBeTruthy();
    expect(port.alias).toBe("dna-automation");
    expect(port.plane).toBe("record");
    expect(port.__declarative__).toBe(true);
    expect(port.__builtin_descriptor__).toBe(true);
    const sd = port.storage as { container: string };
    expect(sd.container).toBe("automations");
  });

  it("tenancy is permissive (inheritable ⇒ never TENANTED)", () => {
    expect((port as { scope?: unknown }).scope ?? null).toBeNull();
  });

  it("ships a strict schema whose trigger enum mirrors TRIGGER_TYPES", () => {
    const schema = (port.schema as () => Record<string, unknown>).call(port) as {
      additionalProperties: boolean;
      properties: { on: { properties: { type: { enum: string[] } } } };
    };
    expect(schema.additionalProperties).toBe(false);
    expect(schema.properties.on.properties.type.enum).toEqual([...TRIGGER_TYPES]);
  });

  it("parse accepts a valid doc per trigger type and fills enabled", () => {
    const parsed = parse(raw({
      on: { type: "cron", cron: "0 10 * * 1,3,5" },
      runner: { kind: "agent", ref: "reporter" },
    })) as { spec: Record<string, unknown> };
    expect(parsed.spec.enabled).toBe(true);
    parse(raw({
      on: { type: "hook", hook: "post_save" },
      runner: { kind: "agent", ref: "auditor" },
    }));
    parse(raw({
      on: {
        type: "tool",
        tool_name: "deep_research_async",
        input_schema: [{ name: "topic" }],
        primary_input: "topic",
      },
      runner: { kind: "agent", ref: "researcher" },
      agent_directive: "Research {topic} and synthesize.",
    }));
  });

  it("parse rejects a trigger without its per-type field (allOf conditionals)", () => {
    expect(() => parse(raw({
      on: { type: "cron" }, runner: { kind: "agent", ref: "x" },
    }))).toThrow(/cron/);
    expect(() => parse(raw({
      on: { type: "hook" }, runner: { kind: "agent", ref: "x" },
    }))).toThrow(/hook/);
    expect(() => parse(raw({
      on: { type: "tool" }, runner: { kind: "agent", ref: "x" },
    }))).toThrow(/tool_name/);
  });

  it("parse rejects the upstream-only `engine` runner and a ref-less runner", () => {
    expect(() => parse(raw({
      on: { type: "cron", cron: "0 3 * * *" },
      runner: { kind: "engine", ref: "dreamer" },
    }))).toThrow();
    expect(() => parse(raw({
      on: { type: "cron", cron: "0 3 * * *" },
      runner: { kind: "agent" },
    }))).toThrow(/ref/);
  });
});

describe("validateCronExpression (zero-dep 5-field grammar)", () => {
  const good = [
    "0 10 * * 1,3,5",
    "*/15 * * * *",
    "0-30/5 2 1-15 * *",
    "59 23 31 12 7",
    "0 0 1 1 0",
  ];
  for (const expr of good) {
    it(`accepts ${JSON.stringify(expr)}`, () => {
      validateCronExpression(expr);
    });
  }

  const bad: Array<[string, RegExp]> = [
    ["* * * *", /expected 5 fields/],
    ["* * * * * *", /expected 5 fields/],
    ["60 * * * *", /out of range/],
    ["* 24 * * *", /out of range/],
    ["* * 0 * *", /out of range/],
    ["* * * 13 *", /out of range/],
    ["* * * * 8", /out of range/],
    ["a * * * *", /not a number/],
    ["*/0 * * * *", /positive integer/],
    ["/5 * * * *", /step without a base/],
    ["5-1 * * * *", /inverted range/],
    ["1,,2 * * * *", /empty list item/],
    ["@daily", /expected 5 fields/],
    ["0 10 * * MON", /not a number/], // name aliases: documented non-goal
  ];
  for (const [expr, detail] of bad) {
    it(`rejects ${JSON.stringify(expr)}`, () => {
      expect(() => validateCronExpression(expr)).toThrow(detail);
    });
  }
});

describe("pre_save veto guard (semantics the schema cannot express)", () => {
  it("vetoes a shape-broken doc at WRITE time (scan-only validation is too late)", async () => {
    const k = freshKernel();
    await expect(k.writeDocument(
      "s", "Automation", "no-cron",
      raw({ on: { type: "cron" },
            runner: { kind: "agent", ref: "x" } }, "no-cron"),
    )).rejects.toThrow(/cron/);
  });

  it("vetoes a schema-valid but grammatically bad cron", async () => {
    const k = freshKernel();
    await expect(k.writeDocument(
      "s", "Automation", "bad-cron",
      raw({ on: { type: "cron", cron: "61 * * * *" },
            runner: { kind: "agent", ref: "x" } }, "bad-cron"),
    )).rejects.toThrow(/invalid cron expression/);
  });

  it("vetoes an unknown hook name, listing the typed vocabulary", async () => {
    const k = freshKernel();
    await expect(k.writeDocument(
      "s", "Automation", "bad-hook",
      raw({ on: { type: "hook", hook: "pre_saev" },
            runner: { kind: "agent", ref: "x" } }, "bad-hook"),
    )).rejects.toThrow(/not a kernel lifecycle hook/);
  });

  it("accepts every KNOWN_HOOK_NAMES entry and a valid cron", async () => {
    const k = freshKernel();
    for (const hook of KNOWN_HOOK_NAMES) {
      await k.writeDocument(
        "s", "Automation", `on-${hook.replaceAll("_", "-")}`,
        raw({ on: { type: "hook", hook },
              runner: { kind: "agent", ref: "x" } }),
      );
    }
    await k.writeDocument(
      "s", "Automation", "ok",
      raw({ on: { type: "cron", cron: "*/15 0-6 * * 1-5" },
            runner: { kind: "tool", ref: "sync-upstream" } }, "ok"),
    );
  });

  it("ignores other Kinds", async () => {
    const k = freshKernel();
    await k.writeDocument(
      "s", "Genome", "g",
      { apiVersion: "github.com/ruinosus/dna/v1", kind: "Genome",
        metadata: { name: "g" },
        spec: { on: { type: "cron", cron: "61 * * * *" } } },
    );
  });
});

describe("query helpers (the host executor's read surface)", () => {
  function doc(name: string, spec: Record<string, unknown>): Document {
    return { name, spec } as unknown as Document;
  }
  const instance = {
    all: () => [
      doc("nightly", { on: { type: "cron", cron: "0 3 * * *" },
                       runner: { kind: "agent", ref: "reporter" } }),
      doc("paused", { on: { type: "cron", cron: "0 4 * * *" },
                      runner: { kind: "agent", ref: "reporter" },
                      enabled: false }),
      doc("on-save", { on: { type: "hook", hook: "post_save" },
                       runner: { kind: "tool", ref: "indexer" } }),
      doc("research", { on: { type: "tool", tool_name: "deep_research_async" },
                        runner: { kind: "agent", ref: "researcher" } }),
    ],
  };
  const names = (docs: Document[]) =>
    docs.map((d) => (d as unknown as { name: string }).name);

  it("filters by trigger type", () => {
    expect(names(automationsFor(instance, "cron"))).toEqual(["nightly"]);
    expect(names(automationsFor(instance, "hook"))).toEqual(["on-save"]);
    expect(names(automationsFor(instance, "tool"))).toEqual(["research"]);
  });

  it("drops disabled automations by default", () => {
    expect(names(automationsFor(instance))).toEqual([
      "nightly", "on-save", "research",
    ]);
    expect(names(automationsFor(instance, "cron", { enabledOnly: false })))
      .toEqual(["nightly", "paused"]);
  });

  it("rejects an unknown trigger type", () => {
    expect(() => automationsFor(instance, "event" as never))
      .toThrow(/unknown triggerType/);
  });

  it("triggerKey resolves per trigger type", () => {
    const docs = Object.fromEntries(
      instance.all().map((d) => [(d as unknown as { name: string }).name, d]),
    );
    expect(triggerKey(docs["nightly"]!)).toBe("0 3 * * *");
    expect(triggerKey(docs["on-save"]!)).toBe("post_save");
    expect(triggerKey(docs["research"]!)).toBe("deep_research_async");
    expect(triggerKey(doc("empty", {}))).toBeNull();
  });
});

describe("projections (D2/D3)", () => {
  it("summary projects trigger + runner + enabled", () => {
    const summary = (port.summary as (d: unknown) => Record<string, unknown>)
      .call(port, {
        spec: {
          on: { type: "cron", cron: "0 3 * * *" },
          runner: { kind: "agent", ref: "reporter" },
          enabled: true,
        },
      });
    expect(summary).toEqual({
      on_type: "cron",
      trigger: { cron: "0 3 * * *" },
      runner_kind: "agent",
      runner_ref: "reporter",
      enabled: true,
    });
  });

  it("describe projects description", () => {
    const described = (port.describe as (d: unknown) => string | null)
      .call(port, { spec: { description: "nightly status report" } });
    expect(described).toBe("nightly status report");
  });
});
