/**
 * Máxima — herdável ⇒ nunca TENANTED (s-inheritable-kinds-tenancy-invariant).
 *
 * 1:1 parity com packages/sdk-py/tests/test_inheritable_kinds_tenancy.py
 *
 * Um Kind que é um *default de `_lib` consumido por scopes/tenants* — o
 * conjunto curado DEFAULT_INHERITABLE_KINDS_V1 (Agent, LottieAsset,
 * Skill, Theme, HtmlTemplate, ImagePrompt, PromptTemplate, JobType) — PRECISA
 * ser gravável na camada base (`_lib`). A leitura (resolver: inheritance +
 * mergeOverrideFull) promete um default base que scopes/tenants herdam e podem
 * sobrescrever; a escrita TenantScope.TENANTED PROÍBE gravar essa base — os dois
 * contratos brigam. Logo a tenancy de um herdável é permissiva (scope ausente)
 * ou GLOBAL — nunca TENANTED (que fica só p/ dados per-tenant sem default de
 * plataforma: audit-log, voice-episode, Canvas, UserProfile).
 */
import { describe, expect, test } from "bun:test";
import { createKernelWithBuiltins } from "../src/bootstrap.js";
import { DEFAULT_INHERITABLE_KINDS_V1 } from "../src/kernel/resolver.js";
import { TenantScope } from "../src/kernel/protocols.js";

describe("inheritable kinds tenancy invariant", () => {
  test("no inheritable kind is declared TENANTED", () => {
    const k = createKernelWithBuiltins();
    const offenders: string[] = [];
    for (const kindName of [...DEFAULT_INHERITABLE_KINDS_V1].sort()) {
      const kp = k.kindPortFor(kindName);
      if (kp === null) continue; // não registrado neste build — sem violação
      if ((kp as { scope?: TenantScope }).scope === TenantScope.TENANTED) {
        offenders.push(kindName);
      }
    }
    expect(offenders).toEqual([]);
  });
});
