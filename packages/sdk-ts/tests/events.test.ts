// typescript/tests/events.test.ts
import { describe, test, expect } from "bun:test";
import { deriveEventType, DELETE_EVENT_TYPE } from "../src/kernel/events";

describe("deriveEventType", () => {
  test("EvalRun → eval_run_completed regardless of is_update", async () => {
    expect(deriveEventType("EvalRun", false)).toBe("eval_run_completed");
    expect(deriveEventType("EvalRun", true)).toBe("eval_run_completed");
  });

  test("EvalBaseline → baseline_pinned", async () => {
    expect(deriveEventType("EvalBaseline", false)).toBe("baseline_pinned");
    expect(deriveEventType("EvalBaseline", true)).toBe("baseline_pinned");
  });

  test("Finding new → finding_created", async () => {
    expect(deriveEventType("Finding", false)).toBe("finding_created");
  });

  test("Finding update → finding_status_changed", async () => {
    expect(deriveEventType("Finding", true)).toBe("finding_status_changed");
  });

  test("generic kind new → document_created", async () => {
    expect(deriveEventType("Agent", false)).toBe("document_created");
  });

  test("generic kind update → document_modified", async () => {
    expect(deriveEventType("Agent", true)).toBe("document_modified");
  });

  test("DELETE_EVENT_TYPE constant", async () => {
    expect(DELETE_EVENT_TYPE).toBe("document_deleted");
  });
});
