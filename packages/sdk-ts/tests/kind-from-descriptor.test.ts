/**
 * F3 D3: funil builtin + conflito unificado + idempotência forte + lint.
 *
 * Py twin: packages/sdk-py/tests/test_kind_from_descriptor.py.
 * Spec: docs/superpowers/specs/2026-06-10-kinds-descriptor-f3-design.md (D3).
 */
import { describe, it, expect } from "bun:test";
import { KindRegistrationError } from "../src/kernel/errors.js";
import { Kernel } from "../src/kernel/index.js";
import { documentHash } from "../src/kernel/lock.js";
import { RAW_FULL } from "./fixtures/kinddef-f3-raw.js";

type Marked = { __builtin_descriptor__?: boolean; __declarative__?: boolean; __descriptor_digest__?: string };

describe("kernel.kindFromDescriptor (F3 D3)", () => {
  it("registers with the builtin marker", () => {
    const k = new Kernel();
    const port = k.kindFromDescriptor(RAW_FULL);
    expect((port as Marked).__builtin_descriptor__).toBe(true);
    expect((port as Marked).__declarative__).toBe(true);
    expect(k.kindPortFor("KaizenLike")).toBe(port);
  });

  it("stamps the descriptor digest with the documentHash recipe", () => {
    // MESMA receita do Py (sync/hash.py:document_hash): sha256 do JSON
    // canônico (sort_keys=True, ensure_ascii=False) do spec.
    const k = new Kernel();
    const port = k.kindFromDescriptor(RAW_FULL);
    expect((port as Marked).__descriptor_digest__).toBe(
      documentHash(RAW_FULL.spec as Record<string, unknown>),
    );
  });

  it("per-scope KindDefinition LOSES to a builtin descriptor (skip + warn + event) — parity fix: no overwrite", () => {
    const k = new Kernel();
    const builtin = k.kindFromDescriptor(RAW_FULL);
    const events: unknown[] = [];
    k.on("kinddef_conflict", (ctx) => events.push(ctx));
    // per-scope chega via _registerKindDefinitions (fase 1 do load)
    const perscopeRaw = { ...RAW_FULL, metadata: { name: "kz-override" } };
    (k as unknown as { _registerKindDefinitions(d: Record<string, unknown>[]): boolean })
      ._registerKindDefinitions([perscopeRaw]);
    // builtin venceu (antes da F3 o TS SOBRESCREVIA o builtin aqui)
    expect(k.kindPortFor("KaizenLike")).toBe(builtin);
    expect((k.kindPortFor("KaizenLike") as Marked).__builtin_descriptor__).toBe(true);
    // evento emitido (mesmo contrato do conflito com extension-class)
    expect(events.length).toBe(1);
  });

  it("idempotent: same descriptor re-register is a no-op", () => {
    const k = new Kernel();
    const first = k.kindFromDescriptor(RAW_FULL);
    const again = k.kindFromDescriptor(RAW_FULL); // mesmo digest → no-op
    expect(again).toBe(first);
  });

  it("a DIFFERENT descriptor on the same key throws", () => {
    const k = new Kernel();
    k.kindFromDescriptor(RAW_FULL);
    const other = {
      ...RAW_FULL,
      spec: { ...(RAW_FULL.spec as Record<string, unknown>), alias: "test-other-alias" },
    };
    expect(() => k.kindFromDescriptor(other)).toThrow(KindRegistrationError);
  });

  it("the plane lint applies to BOTH descriptor funnels", () => {
    const bad = {
      ...RAW_FULL,
      spec: {
        ...(RAW_FULL.spec as Record<string, unknown>),
        plane: "record",
        prompt_target: true,
      },
    };
    const k = new Kernel();
    expect(() => k.kindFromDescriptor(bad)).toThrow(/plane/);
    // e no funil per-scope: NÃO registra + warning (per-scope nunca derruba o boot)
    const k2 = new Kernel();
    (k2 as unknown as { _registerKindDefinitions(d: Record<string, unknown>[]): boolean })
      ._registerKindDefinitions([bad]);
    expect(k2.kindPortFor("KaizenLike")).toBeNull();
  });
});

// --- F3 D4: embeddability derivation ---------------------------------------

describe("kernel.embeddableKinds (F3 D4)", () => {
  it("derives from descriptor embed: declarations", () => {
    const k = new Kernel();
    k.kindFromDescriptor(RAW_FULL); // declares embed: [body, labels]
    expect(k.embeddableKinds()).toEqual(new Set(["KaizenLike"]));
  });

  it("is empty without declarations", () => {
    expect(new Kernel().embeddableKinds()).toEqual(new Set());
  });
});
