// s-platform-inherit-by-default — scope inheritance is DENYLIST by default.
// `_lib` is the declarative stdlib; every Kind inherits EXCEPT the
// per-scope ledger + structural Kinds. 1:1 parity with Python
// Kernel._NON_INHERITABLE_KINDS / _INHERITABLE_KINDS.
import { describe, expect, test } from "bun:test";
import { createKernelWithBuiltins } from "../src/bootstrap";

// _NON_INHERITABLE_KINDS / INHERITABLE_KINDS are now derived INSTANCE getters
// (s-kernel-kindport-classification-attrs) — read them off a kernel that has the
// built-in Kinds registered.
const LEDGER_AND_STRUCTURAL = [
  "Story", "Issue", "Feature", "Milestone", "Roadmap",
  "Narrative", "VibeSession", "LessonLearned", "Plan",
  "Genome", "KindDefinition", "LayerPolicy",
];

describe("inherit-by-default (denylist)", () => {
  test("ledger + structural Kinds do NOT inherit", () => {
    const k = createKernelWithBuiltins();
    for (const kind of LEDGER_AND_STRUCTURAL) {
      expect(k.NON_INHERITABLE_KINDS.has(kind)).toBe(true);
      expect(k.INHERITABLE_KINDS.has(kind)).toBe(false);
    }
  });

  test("template-y + arbitrary Kinds inherit by default", () => {
    const k = createKernelWithBuiltins();
    for (const kind of [
      "Agent", "PromptTemplate", "Skill", "Theme", "LottieAsset",
      "Automation", "ImagePrompt", "HtmlTemplate", "Reference", "SomeFutureKind",
    ]) {
      expect(k.INHERITABLE_KINDS.has(kind)).toBe(true);
    }
  });
});
