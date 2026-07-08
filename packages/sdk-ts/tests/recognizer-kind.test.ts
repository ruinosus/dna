import { describe, expect, test } from "bun:test";
import { createKernelWithBuiltins } from "../src/bootstrap.js";

describe("Recognizer Kind", () => {
  test("registered with correct metadata", async () => {
    const k = createKernelWithBuiltins();
    for (const kp of k._kinds.values()) {
      if (kp.kind === "Recognizer") {
        expect(kp.alias).toBe("presidio-recognizer");
        expect(kp.apiVersion).toBe("presidio/v1");
        expect(kp.origin).toBe("microsoft.github.io/presidio");
        return;
      }
    }
    throw new Error("Recognizer kind not found");
  });

  test("SafetyPolicy has dep_filters referencing recognizers", async () => {
    const k = createKernelWithBuiltins();
    for (const kp of k._kinds.values()) {
      if (kp.kind === "SafetyPolicy") {
        const deps = kp.depFilters();
        expect(deps).toBeTruthy();
        expect(deps!.recognizers).toBe("presidio-recognizer");
        return;
      }
    }
  });
});
