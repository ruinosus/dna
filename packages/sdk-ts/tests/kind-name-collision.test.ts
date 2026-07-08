/**
 * i-195 — kind-name collision guard + deterministic disambiguation.
 * Py twin: packages/sdk-py/tests/test_kind_name_collision.py
 *
 * Two apiVersions sharing a kind name make every bare-name lookup
 * ambiguous (the live Py case: the Reference pair). The TS kernel gets
 * the same registration guard + exact (apiVersion, kind) lookups so the
 * SDKs stay behaviorally aligned even though TS ships only ONE
 * Reference today.
 */
import { describe, expect, test } from "bun:test";

import { Kernel, KIND_NAME_COLLISION_ALLOWLIST } from "../src/kernel";
import { KindRegistrationError } from "../src/kernel/errors";
// StorageDescriptor é interface type-only; o VALOR runtime é `SD`
// (mesmo padrão de kind-plane.test.ts).
import { SD } from "../src/kernel/protocols";
import type { KindPort } from "../src/kernel/protocols";

function stubKind(
  kindName: string,
  apiVersion: string,
  alias: string,
  extra: Partial<KindPort> = {},
): KindPort {
  return {
    apiVersion,
    kind: kindName,
    alias,
    isRoot: false,
    isPromptTarget: false,
    promptTargetPriority: 0,
    flattenInContext: false,
    storage: SD.yaml(`${alias}-items`),
    depFilters: () => null,
    getDefaultAgentName: () => null,
    getLayerPolicies: () => null,
    parse: (raw) => raw,
    describe: () => null,
    summary: () => null,
    promptTemplate: () => null,
    ...extra,
  } as KindPort;
}

describe("i-195 kind-name collision guard", () => {
  test("new kind name collision across apiVersions raises", () => {
    const k = new Kernel();
    k.kind(stubKind("FooCollide", "a.test/v1", "a-foo-collide"));
    expect(() =>
      k.kind(stubKind("FooCollide", "b.test/v1", "b-foo-collide")),
    ).toThrow(KindRegistrationError);
    expect(() =>
      k.kind(stubKind("FooCollide", "b.test/v1", "b-foo-collide")),
    ).toThrow(/i-195/);
  });

  test("Reference collision is allowlisted", () => {
    const k = new Kernel();
    k.kind(stubKind("Reference", "researchlike.test/v1", "researchlike-reference"));
    // must NOT throw — "Reference" is the shrink-only allowlisted pair
    k.kind(stubKind("Reference", "sdlclike.test/v1", "sdlclike-reference"));
    expect(k.kindPorts().filter((p) => p.kind === "Reference").length).toBe(2);
  });

  test("allowlist is a shrink-only ratchet", () => {
    // Emptied by the Reference-family merge; NEVER grows. New
    // collisions must rename instead (i-195).
    expect([...KIND_NAME_COLLISION_ALLOWLIST].sort()).toEqual(["Reference"]);
  });

  test("kindPortFor with apiVersion is exact", () => {
    const k = new Kernel();
    k.kind(stubKind("Reference", "researchlike.test/v1", "researchlike-reference"));
    k.kind(stubKind("Reference", "sdlclike.test/v1", "sdlclike-reference"));
    expect(k.kindPortFor("Reference", "researchlike.test/v1")?.alias).toBe(
      "researchlike-reference",
    );
    expect(k.kindPortFor("Reference", "sdlclike.test/v1")?.alias).toBe(
      "sdlclike-reference",
    );
    expect(k.kindPortFor("Reference", "nope/v1")).toBeNull();
  });

  test("bare lookup prefers extension over per-scope declarative", () => {
    const k = new Kernel();
    const declarative = stubKind(
      "FooCollide", "a.test/v1", "a-foo-collide",
    ) as unknown as Record<string, unknown>;
    declarative.__declarative__ = true; // per-scope KindDefinition marker
    // per-scope funnel writes straight into the map (bypasses kind())
    (k as unknown as { _kinds: Map<string, unknown> })._kinds.set(
      "a.test/v1\0FooCollide",
      declarative,
    );
    k.kind(stubKind("FooCollide", "b.test/v1", "b-foo-collide"));
    expect(k.kindPortFor("FooCollide")?.alias).toBe("b-foo-collide");
  });
});
