/**
 * TestkitExtension — first-class TEST artifacts for the SDLC (TS twin).
 *
 * 1:1 parity with python/dna/extensions/testkit. Registers TWO artifact
 * KindPorts (a test script is a document, like a Spec/HtmlArtifact — produced BY
 * a work item and verifying it, not a work-item itself):
 *
 *   - TestGuide (testkit-test-guide) — a declarative test SCRIPT: ordered `steps`
 *     (action → expected) that validate work items, linked via `verifies`.
 *   - TestRun (testkit-test-run) — an EXECUTION record: `outcome`, who ran it,
 *     per-step results + evidence. A passing run whose `verifies` points at a
 *     Story drives the derived journey's `verify` phase.
 *
 * Both GLOBAL, stored under `<scope>/.dna/<scope>/test-guides|test-runs/`.
 * Auto-exposed in Studio via `ui` metadata (generic docs surface; schema forms).
 */
import type { ExtensionHost, Extension, KindPort } from "../kernel/protocols.js";
import { KindBase } from "../kernel/kind_base.js";
import { SD, TenantScope } from "../kernel/protocols.js";
import type { Document } from "../kernel/document.js";
// NOTE: the `ui = docs_ui(...)` Studio-sidebar metadata is Python-only (served
// by kinds-api); there is no TS `studio_ui` twin and the parity test does not
// cover `ui` (the HookType TS twin omits it too). Kept off the TS Kinds.

const API_VERSION = "github.com/ruinosus/dna/testkit/v1";
const ORIGIN = "github.com/ruinosus/dna/testkit";

// Excludes "unit" — unit tests live in the CI suites, not human/orchestrated guides.
const TEST_KINDS = ["manual", "smoke", "e2e", "regression", "integration"];
const GUIDE_STATUS = ["draft", "active", "deprecated"];
const RUN_OUTCOME = ["pass", "fail", "partial", "blocked"];
const STEP_RESULT = ["pass", "fail", "skip"];

class TestGuideKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly kind = "TestGuide";
  readonly alias = "testkit-test-guide";
  readonly origin = ORIGIN;
  readonly scope = TenantScope.GLOBAL;
  readonly storage = SD.yaml("test-guides");
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly isSchemaAffecting = false;
  // Inheritable by default (like HtmlArtifact/Research — an artifact, not a work-item).
  readonly graphStyle = { fill: "#2DD4BF", stroke: "#0D9488", textColor: "#fff" };
  readonly asciiIcon = "🧪";
  readonly displayLabel = "Test Guides";
  readonly docs =
    "A TestGuide is a declarative test SCRIPT: an ordered list of steps " +
    "(action → expected) that validates one or more work items. A versioned, " +
    "schema-validated, re-runnable doc. Links to its Story via `verifies`.";

  depFilters() { return null; }
  getDefaultAgentName() { return null; }
  getLayerPolicies() { return null; }
  parse(raw: Record<string, unknown>) { return raw; }
  promptTemplate() { return null; }

  schema(): Record<string, unknown> {
    return {
      type: "object",
      required: ["description", "kind_of_test", "steps"],
      additionalProperties: false,
      properties: {
        description: {
          type: "string",
          description: "What this guide validates (one line or short paragraph).",
        },
        kind_of_test: { type: "string", enum: TEST_KINDS },
        status: { type: "string", enum: GUIDE_STATUS, default: "active" },
        steps: {
          type: "array",
          minItems: 1,
          items: {
            type: "object",
            required: ["action", "expected"],
            additionalProperties: false,
            properties: {
              action: { type: "string", description: "What the tester does." },
              expected: { type: "string", description: "Observable expected result." },
              where: {
                type: "string",
                description:
                  "Where in the product to do it (route/screen) so a non-dev can follow, e.g. '/scopes/:scope/sdlc/v2?t=focus'.",
              },
            },
          },
        },
        verifies: {
          type: "array",
          items: { type: "string" },
          default: [],
          description: "Work items this guide verifies, as 'Kind/name' refs (e.g. 'Story/s-x').",
        },
        prerequisites: {
          type: "array",
          items: { type: "string" },
          default: [],
          description: "Setup needed before running, e.g. ['make up', 'tenant acme selected'].",
        },
        scope_hint: { type: "string", description: "Target area/scope for the run." },
        owner: { type: "string", description: "Actor who owns this guide." },
        labels: { type: "array", items: { type: "string" }, default: [] },
        created_at: { type: "string", format: "date-time" },
        updated_at: { type: "string", format: "date-time" },
      },
    };
  }

  describe(doc: Document): string | null {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const steps = (spec.steps as unknown[]) ?? [];
    return `${spec.kind_of_test ?? "?"} · ${steps.length} steps [${spec.status ?? "active"}]`;
  }

  summary(doc: Document): Record<string, unknown> {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const steps = (spec.steps as unknown[]) ?? [];
    return {
      kind_of_test: spec.kind_of_test ?? "",
      status: spec.status ?? "active",
      steps_count: steps.length,
      verifies: spec.verifies ?? [],
      owner: spec.owner ?? "",
    };
  }
}

class TestRunKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly kind = "TestRun";
  readonly alias = "testkit-test-run";
  readonly origin = ORIGIN;
  readonly scope = TenantScope.GLOBAL;
  readonly storage = SD.yaml("test-runs");
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly isSchemaAffecting = false;
  // Inheritable by default (artifact, not a work-item).
  readonly graphStyle = { fill: "#34D399", stroke: "#059669", textColor: "#fff" };
  readonly asciiIcon = "🧾";
  readonly displayLabel = "Test Runs";
  readonly docs =
    "A TestRun is an EXECUTION record of a TestGuide: the outcome " +
    "(pass/fail/partial/blocked), who ran it, per-step results and evidence. " +
    "A passing run whose `verifies` points at a Story drives the derived " +
    "journey's `verify` phase.";

  depFilters() { return null; }
  getDefaultAgentName() { return null; }
  getLayerPolicies() { return null; }
  parse(raw: Record<string, unknown>) { return raw; }
  promptTemplate() { return null; }

  schema(): Record<string, unknown> {
    return {
      type: "object",
      required: ["guide_ref", "outcome"],
      additionalProperties: false,
      properties: {
        guide_ref: { type: "string", description: "Name of the TestGuide that was executed." },
        outcome: { type: "string", enum: RUN_OUTCOME },
        verifies: {
          type: "array",
          items: { type: "string" },
          default: [],
          description: "Work items this run verifies (inherited from the guide); drives journey 'verify'.",
        },
        executed_by: { type: "string", description: "Actor who ran it." },
        executed_at: { type: "string", format: "date-time" },
        step_results: {
          type: "array",
          default: [],
          items: {
            type: "object",
            required: ["step_index", "result"],
            additionalProperties: false,
            properties: {
              step_index: { type: "integer", minimum: 0 },
              result: { type: "string", enum: STEP_RESULT },
              notes: { type: "string" },
              screenshot: {
                type: "string",
                description: "Screenshot evidence for this step (data URL or asset ref).",
              },
            },
          },
        },
        evidence: {
          type: "array",
          items: { type: "string" },
          default: [],
          description: "Refs/links backing the outcome, e.g. ['HtmlArtifact/ha-x', urls].",
        },
        screenshots: {
          type: "array",
          default: [],
          items: {
            type: "object",
            properties: {
              asset: { type: "string" },
              mime: { type: "string" },
              blob: { type: "string" },
            },
            required: ["asset"],
          },
          description:
            "Run-level evidence prints, Asset-backed (asset name + blob path), NOT inline base64.",
        },
        notes: { type: "string" },
        labels: { type: "array", items: { type: "string" }, default: [] },
      },
    };
  }

  describe(doc: Document): string | null {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return `${spec.guide_ref ?? "?"} → ${spec.outcome ?? "?"}`;
  }

  summary(doc: Document): Record<string, unknown> {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      guide_ref: spec.guide_ref ?? "",
      outcome: spec.outcome ?? "",
      executed_by: spec.executed_by ?? "",
      executed_at: spec.executed_at ?? null,
      verifies: spec.verifies ?? [],
    };
  }
}

export class TestkitExtension implements Extension {
  readonly name = "testkit";
  readonly version = "1.0.0";

  register(kernel: ExtensionHost): void {
    kernel.kind(new TestGuideKind());
    kernel.kind(new TestRunKind());
  }

  /** Parity with Python's `TestkitExtension.kinds()`. */
  kinds(): KindPort[] {
    return [new TestGuideKind(), new TestRunKind()];
  }
}
