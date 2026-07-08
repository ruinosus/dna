/**
 * s-alias-generated-not-typed — aliases GERADOS de (owner, kind), não digitados.
 *
 * Twin de packages/sdk-py/tests/test_alias_generation.py. Contrato:
 *
 * 1. Kind SEM `alias` declarado ganha um gerado: `<owner>-<kebab(kind)>`.
 *    Owner vem de `aliasOwner` no port, senão do contexto da Extension em
 *    `kernel.load()` (`ext.aliasOwner` / `ext.name`), senão do 1º token do
 *    apiVersion. Ports gerados são estampados `__alias_generated__`.
 * 2. Aliases legados ficam INTOCADOS (wire format vivo). O ratchet
 *    EXPLICIT_ALIAS_ALLOWLIST é shrink-only: Kind novo NÃO declara alias.
 * 3. `kernel.validateDepFilters()` roda no fim de `loadBuiltins()`:
 *    dep_filter de extension apontando pra alias desconhecido → ERRO de
 *    boot. Ports per-scope (declarative) continuam warning.
 * 4. O formato legado `kind=<Nome>` resolve via shim com warn de
 *    deprecação no resolver canônico.
 */
import { describe, expect, spyOn, test } from "bun:test";
import {
  EXPLICIT_ALIAS_ALLOWLIST,
  Kernel,
  generateAlias,
  kebabKindName,
} from "../src/kernel/index.js";
import { KindRegistrationError } from "../src/kernel/errors.js";
// ATENÇÃO: StorageDescriptor é interface type-only; o VALOR runtime é `SD`
// (protocols.ts) — mesmo import que kind-plane.test.ts usa.
import { SD } from "../src/kernel/protocols.js";
import type { KindPort } from "../src/kernel/protocols.js";
import { createKernelWithBuiltins } from "../src/bootstrap.js";

function stubKind(
  kindName: string,
  extra: Partial<KindPort> & Record<string, unknown> = {},
): KindPort {
  return {
    apiVersion: "test.io/v1",
    kind: kindName,
    alias: `test-${kindName.toLowerCase()}`,
    isRoot: false,
    isPromptTarget: false,
    promptTargetPriority: 0,
    flattenInContext: false,
    storage: SD.yaml("items"),
    depFilters: () => null,
    getDefaultAgentName: () => null,
    getLayerPolicies: () => null,
    parse: (raw: unknown) => raw,
    describe: () => null,
    summary: () => null,
    promptTemplate: () => null,
    ...extra,
  } as KindPort;
}

// ---------- 1. kebab + generation helpers ----------

describe("kebabKindName", () => {
  const cases: Array<[string, string]> = [
    ["EvalCase", "eval-case"],
    ["Agent", "agent"],
    ["ADR", "adr"],
    ["HTMLThing", "html-thing"],
    ["JobType", "job-type"],
    ["Story", "story"],
    ["PreMortem", "pre-mortem"],
  ];
  for (const [kind, expected] of cases) {
    test(`${kind} → ${expected}`, () => {
      expect(kebabKindName(kind)).toBe(expected);
    });
  }
});

test("generateAlias", () => {
  expect(generateAlias("sdlc", "JobType")).toBe("sdlc-job-type");
  expect(generateAlias("eval", "EvalCase")).toBe("eval-eval-case");
});

// ---------- 2. kind() generates when alias missing ----------

test("kind without alias gets generated", () => {
  const k = new Kernel();
  const port = stubKind("WidgetThing", {
    apiVersion: "myext.test/v1",
    alias: null as unknown as string, // ← não digitado: gerado no registro
    aliasOwner: "myext",
    storage: SD.yaml("widget-things"),
  });
  k.kind(port);
  expect(port.alias).toBe("myext-widget-thing");
  expect((port as unknown as { __alias_generated__?: boolean }).__alias_generated__).toBe(true);
});

test("generated alias falls back to apiVersion owner", () => {
  const k = new Kernel();
  const port = stubKind("GadgetThing", {
    apiVersion: "fallback.test/v1",
    alias: null as unknown as string,
    storage: SD.yaml("gadget-things"),
  });
  k.kind(port);
  expect(port.alias).toBe("fallback-gadget-thing");
});

test("generated alias still subject to uniqueness", () => {
  const k = new Kernel();
  k.kind(stubKind("SameThing", {
    apiVersion: "uniq.test/v1",
    alias: null as unknown as string,
    storage: SD.yaml("same-a"),
  }));
  // mesma geração → colide no H1 alias-uniqueness (e no name-collision i-195)
  expect(() =>
    k.kind(stubKind("SameThing", {
      apiVersion: "uniq.test/v2",
      alias: null as unknown as string,
      storage: SD.yaml("same-b"),
    })),
  ).toThrow(KindRegistrationError);
});

// ---------- 3. load() provides extension owner context ----------

test("load provides owner context", () => {
  const port = stubKind("ContextThing", {
    apiVersion: "weird.namespace.io/v1",
    alias: null as unknown as string,
    storage: SD.yaml("context-things"),
  });
  const ext = {
    name: "ctxext",
    version: "0.0.1",
    register(kernel: Kernel): void {
      kernel.kind(port);
    },
  };
  const k = new Kernel();
  k.load(ext);
  const registered = k.kindPortFor("ContextThing");
  // owner veio da Extension (ctxext), não do apiVersion (weird)
  expect(registered?.alias).toBe("ctxext-context-thing");
});

// ---------- 4. ratchet: Kind novo não digita alias ----------

test("explicit alias ratchet is shrink-only (exact equality, both directions)", () => {
  // Todo port builtin com alias digitado à mão está no allowlist. Kind
  // NOVO deve OMITIR alias (geração) — adicionar nome aqui é proibido;
  // a lista só encolhe conforme classes migram pra geração/descriptors.
  const k = createKernelWithBuiltins();
  const explicit = new Set(
    k.kindPorts()
      .filter((kp) => {
        const p = kp as unknown as {
          alias?: string; __alias_generated__?: boolean; __declarative__?: boolean;
        };
        // descriptors têm alias no YAML (parity-critical) — fora do ratchet
        return Boolean(p.alias) && !p.__alias_generated__ && !p.__declarative__;
      })
      .map((kp) => kp.alias),
  );
  const stray = [...explicit].filter((a) => !EXPLICIT_ALIAS_ALLOWLIST.has(a)).sort();
  expect(
    stray,
    `Kind(s) novo(s) com alias digitado à mão: ${JSON.stringify(stray)}. ` +
    `Omita o alias (será gerado <owner>-<kebab(kind)>) em vez de digitá-lo ` +
    `— s-alias-generated-not-typed.`,
  ).toEqual([]);
  // Igualdade nos DOIS sentidos: entrada sem port vivo = classe migrou
  // pra geração/descriptor — REMOVA do allowlist (é assim que ele
  // provadamente encolhe).
  const dead = [...EXPLICIT_ALIAS_ALLOWLIST].filter((a) => !explicit.has(a)).sort();
  expect(
    dead,
    `Entrada(s) morta(s) no EXPLICIT_ALIAS_ALLOWLIST: ${JSON.stringify(dead)} — ` +
    `a classe migrou; remova do allowlist (shrink-only).`,
  ).toEqual([]);
});

// ---------- 5. validateDepFilters: unknown alias = ERRO de boot ----------

test("validateDepFilters: unknown alias raises", () => {
  const k = new Kernel();
  k.kind(stubKind("BrokenDeps", {
    apiVersion: "broken.test/v1",
    alias: "broken-broken-deps",
    storage: SD.yaml("broken-deps"),
    depFilters: () => ({ things: "no-such-alias" }),
  }));
  expect(() => k.validateDepFilters()).toThrow(/no-such-alias/);
});

test("validateDepFilters: legacy kind= format rejected for builtin", () => {
  // Builtins são alias-puros pós-story — kind=X em extension é erro.
  const k = new Kernel();
  k.kind(stubKind("LegacyFmt", {
    apiVersion: "legacyfmt.test/v1",
    alias: "legacyfmt-legacy-fmt",
    storage: SD.yaml("legacy-fmts"),
    depFilters: () => ({ stories: "kind=Story" }),
  }));
  expect(() => k.validateDepFilters()).toThrow(/kind=/);
});

test("validateDepFilters: declarative port only warns", () => {
  const k = new Kernel();
  const scoped = stubKind("ScopedThing", {
    apiVersion: "scoped.test/v1",
    alias: "scoped-scoped-thing",
    storage: SD.yaml("scoped-things"),
    __declarative__: true,
    depFilters: () => ({ refs: "missing-alias" }),
  });
  // funil per-scope — injetado direto, como o twin Python
  (k as unknown as { _kinds: Map<string, KindPort> })._kinds.set(
    "scoped.test/v1\0ScopedThing",
    scoped,
  );
  const warn = spyOn(console, "warn").mockImplementation(() => {});
  try {
    k.validateDepFilters(); // NÃO levanta
    const warned = warn.mock.calls.some((call) =>
      call.some((arg) => String(arg).includes("missing-alias")),
    );
    expect(warned).toBe(true);
  } finally {
    warn.mockRestore();
  }
});

test("validateDepFilters: pipe-union with unknown term raises", () => {
  const k = new Kernel();
  k.kind(stubKind("UnionThing", {
    apiVersion: "union.test/v1",
    alias: "union-union-thing",
    storage: SD.yaml("union-things"),
    depFilters: () => ({ ref: "union-union-thing|no-such-union-term" }),
  }));
  expect(() => k.validateDepFilters()).toThrow(/no-such-union-term/);
});

test("loadBuiltins passes validation", () => {
  // Todos os dep_filters builtin resolvem — loadBuiltins valida no fim
  // (levantaria se algum builtin apontasse pra alias morto).
  const k = createKernelWithBuiltins();
  k.validateDepFilters();
});

// ---------- 6. resolver canônico com shim kind= deprecado ----------

test("resolveDepFilterTarget: alias + legacy kind= shim + unknown", () => {
  const k = new Kernel();
  k.kind(stubKind("TargetThing", {
    apiVersion: "tgt.test/v1",
    alias: "tgt-target-thing",
    storage: SD.yaml("target-things"),
  }));
  expect(k.resolveDepFilterTarget("tgt-target-thing")?.kind).toBe("TargetThing");
  const warn = spyOn(console, "warn").mockImplementation(() => {});
  try {
    const port = k.resolveDepFilterTarget("kind=TargetThing");
    expect(port?.kind).toBe("TargetThing");
    expect(warn).toHaveBeenCalled();
  } finally {
    warn.mockRestore();
  }
  expect(k.resolveDepFilterTarget("nope-nothing")).toBeNull();
});
