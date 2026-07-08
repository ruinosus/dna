import { describe, expect, test } from "bun:test";
import { createKernelWithBuiltins } from "../src/bootstrap";
import { KindBase } from "../src/kernel/kind_base";
import { SD } from "../src/kernel/protocols";

/**
 * s-kernel-kindport-classification-attrs — the kernel's Kind-classification
 * sets are DERIVED from per-KindPort attributes (isOverlayable / scopeInheritable)
 * instead of hardcoded name sets. 1:1 parity with the Python twin.
 *
 * Gate: the derived sets must EQUAL the original hardcoded sets, exactly.
 */

const ORIG_NON_OVERLAYABLE = new Set(["Genome", "KindDefinition", "LayerPolicy"]);
const ORIG_NON_INHERITABLE = new Set([
  "Story", "Issue", "Feature", "Milestone", "Roadmap",
  "Narrative", "VibeSession", "LessonLearned", "Plan",
  "Genome", "KindDefinition", "LayerPolicy",
]);

function sorted(s: ReadonlySet<string>): string[] {
  return Array.from(s).sort();
}

describe("kind classification — derived equals original", () => {
  test("NON_OVERLAYABLE_KINDS", () => {
    const k = createKernelWithBuiltins();
    expect(sorted(k.NON_OVERLAYABLE_KINDS)).toEqual(sorted(ORIG_NON_OVERLAYABLE));
  });

  test("NON_INHERITABLE_KINDS (incl. legacy Milestone/VibeSession)", () => {
    const k = createKernelWithBuiltins();
    expect(sorted(k.NON_INHERITABLE_KINDS)).toEqual(sorted(ORIG_NON_INHERITABLE));
  });

  test("INHERITABLE_KINDS denylist membership", () => {
    const k = createKernelWithBuiltins();
    expect(k.INHERITABLE_KINDS.has("Agent")).toBe(true);
    expect(k.INHERITABLE_KINDS.has("Skill")).toBe(true);
    expect(k.INHERITABLE_KINDS.has("Story")).toBe(false);
    expect(k.INHERITABLE_KINDS.has("Genome")).toBe(false);
    expect(k.INHERITABLE_KINDS.has("Milestone")).toBe(false); // legacy denylist name
  });
});

describe("kind classification — attribute defaults + representatives", () => {
  test("KindBase defaults", () => {
    class Bare extends KindBase {
      readonly apiVersion = "x/v1";
      readonly kind = "Bare";
      readonly alias = "x-bare";
      readonly storage = SD.yaml("bares");
    }
    const b = new Bare();
    expect(b.isSchemaAffecting).toBe(false);
    expect(b.isOverlayable).toBe(true);
    expect(b.scopeInheritable).toBe(true);
  });

  test("representative Kinds carry the right classification", () => {
    const k = createKernelWithBuiltins() as unknown as {
      _kinds: Map<string, {
        kind: string;
        isSchemaAffecting?: boolean;
        isOverlayable?: boolean;
        scopeInheritable?: boolean;
      }>;
    };
    const by = new Map([...k._kinds.values()].map((kp) => [kp.kind, kp]));
    const pkg = by.get("Genome")!;
    expect(pkg.isSchemaAffecting).toBe(true);
    expect(pkg.isOverlayable).toBe(false);
    expect(pkg.scopeInheritable).toBe(false);
    const ua = by.get("Agent")!;
    expect(ua.isSchemaAffecting).toBe(true);
    expect(ua.isOverlayable ?? true).toBe(true);
    expect(ua.scopeInheritable ?? true).toBe(true);
    const story = by.get("Story")!;
    expect(story.isSchemaAffecting ?? false).toBe(false);
    expect(story.scopeInheritable).toBe(false);
  });
});
