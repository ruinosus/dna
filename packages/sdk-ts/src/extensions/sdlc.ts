/**
 * SdlcExtension — software-development lifecycle Kinds.
 *
 * Seven Kinds for declarative product/engineering management as YAML/markdown:
 *
 *   - Roadmap (sdlc-roadmap) — top-level, lists epics across horizons
 *   - Epic (sdlc-epic) — Jira/ADO-aligned aggregation umbrella; optional target date
 *   - Feature (sdlc-feature) — shippable unit; implements UseCases
 *   - Story (sdlc-story) — granular task with owner + estimate
 *   - Issue (sdlc-issue) — bug/enhancement/question/task; can link to a Finding
 *   - Spec (sdlc-spec) — top-level design artifact (ADR-style)
 *   - Plan (sdlc-plan) — implementation plan, child of a Spec
 *
 * 1:1 parity with Python ``dna.extensions.sdlc`` for the KIND
 * surface (registration, descriptors, schemas, write-guards).
 *
 * Known Py-only helpers (verified 2026-07-08, s-dna-sdlc-cli-extraction —
 * documented here on purpose, not silently): ``journey_derive.py`` (the
 * derived per-work-item journey computation consumed by the server journey/
 * focus routes and the CLI) and ``work_item_outputs.py`` (produces[]
 * resolution) have NO TS twin. They are pure read-side helpers OVER Kind
 * data, not Kind behavior — port them when a TS consumer needs the derived
 * journey, and add their members to the parity fixtures at that point.
 *
 * v1.3 BREAKING: Milestone Kind renamed to Epic.
 */

import type { ExtensionHost, Extension } from "../kernel/protocols.js";
import { KindBase } from "../kernel/kind_base.js";
import { SD, TenantScope } from "../kernel/protocols.js";
import { loadDescriptors } from "../kernel/descriptor-loader.js";
import type { Document } from "../kernel/document.js";

const API_VERSION = "github.com/ruinosus/dna/sdlc/v1";

// v1.3: MILESTONE_STATUSES → EPIC_STATUSES (Jira/ADO alignment).
const EPIC_STATUSES = ["planning", "in-progress", "done", "cancelled", "deprecated"] as const;
const FEATURE_STATUSES = ["discovery", "in-development", "done", "cancelled", "blocked"] as const;
// 2026-05-26 — rec-triage-as-status (Py twin): needs-triage prepended,
// deferred antes de cancelled. Stories existentes em `todo` permanecem.
const STORY_STATUSES = [
  "needs-triage",
  "todo",
  "in-progress",
  "review",
  "done",
  "blocked",
  "deferred",
  "cancelled",
] as const;
const ISSUE_STATUSES = ["open", "triaged", "in-progress", "resolved", "wont-fix", "duplicate"] as const;
const ISSUE_TYPES = ["bug", "enhancement", "question", "task"] as const;
const ISSUE_SEVERITIES = ["low", "medium", "high", "critical"] as const;
// v1.13: the Kaizen observation arc (observed → routed → resolved) lives
// ONLY in the descriptor sdlc/kinds/kaizen.kind.yaml since F3 P2 — the
// enum is the schema's `status.enum`; CLI call sites use literals.
// v1.5: shared priority enum across Story/Feature/Epic/Issue (Jira-aligned).
const PRIORITIES = ["highest", "high", "medium", "low", "lowest"] as const;

// Universal journey phases — additive layer over Story/Feature/Epic
// status, Spec phase, etc. Maps to Superpowers / BMAD / Spec Kit / Kiro.
const JOURNEY_PHASES = ["discover", "specify", "plan", "build", "verify", "reflect"] as const;

// v1.6: Activity Timeline event types (open enum — additionalProperties
// True per entry lets new types add fields without migration).
const TIMELINE_TYPES = [
  "status_change", "groom", "comment", "decision", "artifact_produced",
] as const;
const TIMELINE_SOURCES = [
  "cli", "studio", "agent-session-extracted", "system",
] as const;

// produces[] — a work item is a HUB of the artifacts it produced, of ANY
// Kind (mirror of AgentSession.produced_artifacts + the Python
// _produces_field_schema). Read by the derived journey + FOCUS panel +
// `dna sdlc produces list` via resolveWorkItemOutputs (produces ∪ legacy).
// Parity: keep byte-aligned with packages/sdk-py .../sdlc/__init__.py.
function producesFieldSchema() {
  return {
    type: "array",
    description: "Artifacts this work item produced — any Kind (hub).",
    items: {
      type: "object",
      required: ["kind", "name"],
      additionalProperties: true,
      properties: {
        kind: { type: "string", description: "Artifact Kind (any)." },
        name: { type: "string", description: "Artifact doc name." },
        role: { type: "string", description: "Optional role hint (e.g. visual-spec, plan, investigation)." },
        at: { type: "string", format: "date-time" },
      },
    },
  };
}

function timelineFieldSchema() {
  return {
    type: "array",
    description:
      "Append-only activity log. Auto-stamped by the CLI on every " +
      "status flip / groom / artifact write; populated by AgentSession " +
      "capture for decision + artifact_produced events.",
    items: {
      type: "object",
      required: ["at", "actor", "type"],
      additionalProperties: true,
      properties: {
        at: { type: "string", format: "date-time" },
        actor: { type: "string" },
        type: { type: "string", enum: [...TIMELINE_TYPES] },
        source: { type: "string", enum: [...TIMELINE_SOURCES] },
        from: { type: "string" },
        to: { type: "string" },
        fields: { type: "object" },
        summary: { type: "string" },
        excerpt: { type: "string" },
        paths: { type: "array", items: { type: "string" } },
        commit_ref: { type: "string" },
        session_ref: { type: "string" },
      },
    },
  };
}

// ---------------------------------------------------------------------------
// Roadmap
// ---------------------------------------------------------------------------

class RoadmapKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly scope = TenantScope.GLOBAL; // SDLC primitives are project-level
  readonly kind = "Roadmap";
  readonly alias = "sdlc-roadmap";
  readonly scopeInheritable = false;
  readonly origin = "github.com/ruinosus/dna/sdlc";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly plane = "record" as const;
  readonly storage = SD.yaml("roadmaps");
  readonly graphStyle = { fill: "#0EA5E9", stroke: "#0284C7", textColor: "#fff" };
  readonly asciiIcon = "🗺️";
  readonly displayLabel = "Roadmaps";
  readonly docs =
    "A Roadmap groups Epics across time horizons (e.g. Q1 2026, " +
    "Q2 2026). Pure organizational doc — no status of its own; the " +
    "rolled-up status comes from the Epics it lists.";

  depFilters() { return { epics: "sdlc-epic" }; }
  schema() {
    return {
      type: "object",
      required: ["description", "horizons"],
      additionalProperties: true,
      properties: {
        description: { type: "string" },
        owner_team: { type: "string" },
        horizons: {
          type: "array",
          items: {
            type: "object",
            required: ["label", "epics"],
            properties: {
              label: { type: "string", description: "e.g. 'Q1 2026'" },
              start_date: { type: "string", format: "date" },
              end_date: { type: "string", format: "date" },
              epics: {
                type: "array",
                items: { type: "string" },
                description: "Names of Epic docs in this horizon",
              },
            },
          },
        },
        links: {
          type: "array",
          items: { type: "string" },
          description: "External URLs (Confluence, Notion, etc.)",
        },
      },
    };
  }
  summary(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const horizons = (spec.horizons as Array<Record<string, unknown>>) ?? [];
    const total = horizons.reduce(
      (sum, h) => sum + ((h.epics as unknown[])?.length ?? 0),
      0,
    );
    const desc = (spec.description as string) ?? "";
    return {
      description: desc.slice(0, 80),
      horizons: horizons.length,
      epics: total,
    };
  }
}

// ---------------------------------------------------------------------------
// Epic — Jira/ADO-aligned aggregation umbrella (was Milestone in v1.2)
// ---------------------------------------------------------------------------

class EpicKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly scope = TenantScope.GLOBAL; // SDLC primitives are project-level
  readonly kind = "Epic";
  readonly alias = "sdlc-epic";
  readonly origin = "github.com/ruinosus/dna/sdlc";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly plane = "record" as const;
  readonly storage = SD.yaml("epics");
  readonly graphStyle = { fill: "#8B5CF6", stroke: "#7C3AED", textColor: "#fff" };
  readonly asciiIcon = "🎯";
  readonly displayLabel = "Epics";
  readonly docs =
    "An Epic groups Features under a single business goal " +
    "(Jira/ADO terminology). May optionally carry a target_date when " +
    "the Epic doubles as a dated release; otherwise it's a pure " +
    "aggregation umbrella. status: planning → in-progress → done.";

  depFilters() { return { features: "sdlc-feature" }; }
  schema() {
    return {
      type: "object",
      required: ["status"], // v1.3: target_date no longer required
      additionalProperties: true,
      properties: {
        title: {
          type: "string",
          description: "Human-readable display name (Jira 'summary').",
        },
        description: { type: "string" },
        target_date: { type: "string", format: "date" },
        status: { type: "string", enum: [...EPIC_STATUSES] },
        target_package: {
          type: "string",
          description: "owner/name reference to a Genome",
        },
        target_version: {
          type: "string",
          description: "Semver to match Genome.spec.version when done",
        },
        features: { type: "array", items: { type: "string" } },
        closed_at: { type: "string", format: "date-time" },
        cancelled_reason: { type: "string" },
        // v1.5 — board-grade common fields. Epics drop sprint_ref +
        // time_tracking + mockups + release_target.
        priority: { type: "string", enum: [...PRIORITIES] },
        labels: { type: "array", items: { type: "string" } },
        reporter: { type: "string" },
        watchers: { type: "array", items: { type: "string" } },
        journey_phase: { type: "string", enum: [...JOURNEY_PHASES] },
        created_at: { type: "string", format: "date-time" },
        updated_at: { type: "string", format: "date-time" },
        definition_of_done: { type: "array", items: { type: "string" } },
        business_value: { type: "number", minimum: 0, maximum: 1000 },
        produces: producesFieldSchema(),
        timeline: timelineFieldSchema(),
      },
    };
  }
  summary(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      status: spec.status ?? "planning",
      target_date: spec.target_date ?? "",
      target_package: spec.target_package ?? "",
      target_version: spec.target_version ?? "",
      features: ((spec.features as unknown[]) ?? []).length,
      priority: spec.priority ?? "medium",
      labels: (spec.labels as unknown[]) ?? [],
      business_value: spec.business_value,
    };
  }
}

// ---------------------------------------------------------------------------
// Feature
// ---------------------------------------------------------------------------

class FeatureKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly scope = TenantScope.GLOBAL; // SDLC primitives are project-level
  readonly kind = "Feature";
  readonly alias = "sdlc-feature";
  readonly scopeInheritable = false;
  readonly origin = "github.com/ruinosus/dna/sdlc";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly plane = "record" as const;
  readonly storage = SD.yaml("features");
  readonly graphStyle = { fill: "#10B981", stroke: "#059669", textColor: "#fff" };
  readonly asciiIcon = "🚀";
  readonly displayLabel = "Features";
  readonly docs =
    "A Feature is a shippable unit. It implements one or more " +
    "UseCases, decomposes into Stories, and is owned by an Actor. " +
    "Its status reflects the development pipeline: discovery → " +
    "in-development → done.";

  depFilters() {
    return {
      stories: "sdlc-story",
      use_cases: "helix-usecase",
      owner: "helix-actor",
      epic: "sdlc-epic",
    };
  }
  schema() {
    return {
      type: "object",
      required: ["description", "status"],
      additionalProperties: true,
      properties: {
        title: { type: "string", description: "Human-readable display name." },
        description: { type: "string" },
        // User-story slots (2026-05-11 UX audit) — Py parity.
        as_a: { type: "string", description: "Role: 'As a <role>'." },
        i_want: { type: "string", description: "Goal: 'I want <goal>'." },
        so_that: { type: "string", description: "Benefit: 'so that <benefit>'." },
        acceptance_criteria: { type: "array", items: { type: "string" } },
        definition_of_done: { type: "array", items: { type: "string" } },
        narrative_line: {
          type: "string",
          description:
            "One-sentence agent-curated prose summary of what this " +
            "Feature has been DOING (past-tense, semantic) — shown next " +
            "to the Feature in Studio's narrative swimlane. Distinct " +
            "from `description` (intent / problem statement).",
        },
        status: { type: "string", enum: [...FEATURE_STATUSES] },
        epic: { type: "string", description: "Parent Epic name" },
        stories: { type: "array", items: { type: "string" } },
        use_cases: { type: "array", items: { type: "string" } },
        owner: { type: "string", description: "Actor name" },
        estimate: {
          type: "string",
          description: "T-shirt size or story points (free-form)",
        },
        closed_at: { type: "string", format: "date-time" },
        blocked_reason: { type: "string" },
        // v1.5 — board-grade fields.
        priority: { type: "string", enum: [...PRIORITIES] },
        labels: { type: "array", items: { type: "string" } },
        reporter: { type: "string" },
        watchers: { type: "array", items: { type: "string" } },
        journey_phase: { type: "string", enum: [...JOURNEY_PHASES] },
        created_at: { type: "string", format: "date-time" },
        updated_at: { type: "string", format: "date-time" },
        sprint_ref: { type: "string" },
        time_tracking: {
          type: "object",
          additionalProperties: false,
          properties: {
            logged_h: { type: "number", minimum: 0 },
            remaining_h: { type: "number", minimum: 0 },
            original_estimate_h: { type: "number", minimum: 0 },
          },
        },
        // NB: `definition_of_done` already declared above on line 285;
        // dedupe pra TS1117. business_value/mockups/release_target/
        // timeline ficam aqui na board-grade section.
        business_value: { type: "number", minimum: 0, maximum: 1000 },
        mockups: { type: "array", items: { type: "string" } },
        release_target: { type: "string" },
        produces: producesFieldSchema(),
        timeline: timelineFieldSchema(),
      },
    };
  }
  summary(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      status: spec.status ?? "discovery",
      epic: spec.epic ?? "",
      owner: spec.owner ?? "",
      stories: ((spec.stories as unknown[]) ?? []).length,
      use_cases: ((spec.use_cases as unknown[]) ?? []).length,
      priority: spec.priority ?? "medium",
      labels: (spec.labels as unknown[]) ?? [],
      sprint_ref: spec.sprint_ref ?? "",
      business_value: spec.business_value,
    };
  }
}

// ---------------------------------------------------------------------------
// Story
// ---------------------------------------------------------------------------

class StoryKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly scope = TenantScope.GLOBAL; // SDLC primitives are project-level
  readonly kind = "Story";
  readonly alias = "sdlc-story";
  readonly scopeInheritable = false;
  readonly origin = "github.com/ruinosus/dna/sdlc";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly plane = "record" as const;
  readonly storage = SD.yaml("stories");
  readonly graphStyle = { fill: "#F59E0B", stroke: "#D97706", textColor: "#fff" };
  readonly asciiIcon = "📖";
  readonly displayLabel = "Stories";
  readonly docs =
    "A Story is a granular task: one developer, one PR, one estimate. " +
    "Lists acceptance criteria, dependencies (other Stories that must " +
    "land first), and rolls up to a Feature.";

  depFilters() {
    return {
      feature: "sdlc-feature",
      owner: "helix-actor",
      dependencies: "sdlc-story",
      spec_refs: "sdlc-spec",
    };
  }
  schema() {
    return {
      type: "object",
      required: ["description", "status"],
      additionalProperties: true,
      properties: {
        title: { type: "string", description: "Human-readable display name." },
        description: { type: "string" },
        // User-story slots (2026-05-11 UX audit) — Py parity.
        as_a: { type: "string", description: "Role: 'As a <role>'." },
        i_want: { type: "string", description: "Goal: 'I want <goal>'." },
        so_that: { type: "string", description: "Benefit: 'so that <benefit>'." },
        status: { type: "string", enum: [...STORY_STATUSES] },
        feature: { type: "string", description: "Parent Feature name" },
        owner: { type: "string", description: "Actor name" },
        estimate: {
          type: "number",
          description: "Fibonacci story points (1, 2, 3, 5, 8, 13, 21)",
        },
        acceptance_criteria: {
          type: "array",
          items: {
            oneOf: [
              { type: "string" },
              {
                type: "object",
                required: ["text"],
                properties: {
                  text: { type: "string" },
                  done: { type: "boolean" },
                  done_at: { type: "string", format: "date-time" },
                  done_by: { type: "string" },
                },
              },
            ],
          },
          description:
            "Acceptance criteria. Legacy: string[]. New " +
            "(s-ac-dod-checklist-state): list of {text, done?, done_at?, " +
            "done_by?} for per-item state tracking.",
        },
        dependencies: {
          type: "array",
          items: { type: "string" },
          description: "Other Story names that must land first",
        },
        spec_refs: {
          type: "array",
          items: { type: "string" },
          description:
            "Spec docs (kind=Spec) this Story implements. M:N linkage " +
            "between the planning axis (Story) and the design axis (Spec).",
        },
        closed_at: { type: "string", format: "date-time" },
        blocked_reason: { type: "string" },
        // v1.5 — board-grade fields (all opt; back-compat preserved).
        priority: { type: "string", enum: [...PRIORITIES] },
        labels: { type: "array", items: { type: "string" } },
        reporter: { type: "string" },
        watchers: { type: "array", items: { type: "string" } },
        journey_phase: { type: "string", enum: [...JOURNEY_PHASES] },
        created_at: { type: "string", format: "date-time" },
        updated_at: { type: "string", format: "date-time" },
        sprint_ref: { type: "string" },
        time_tracking: {
          type: "object",
          additionalProperties: false,
          properties: {
            logged_h: { type: "number", minimum: 0 },
            remaining_h: { type: "number", minimum: 0 },
            original_estimate_h: { type: "number", minimum: 0 },
          },
        },
        definition_of_done: {
          type: "array",
          items: {
            oneOf: [
              { type: "string" },
              {
                type: "object",
                required: ["text"],
                properties: {
                  text: { type: "string" },
                  done: { type: "boolean" },
                  done_at: { type: "string", format: "date-time" },
                  done_by: { type: "string" },
                },
              },
            ],
          },
          description:
            "Per-Story DoD. Same union shape as acceptance_criteria — " +
            "legacy string[] OR list of {text, done?, done_at?, done_by?}.",
        },
        business_value: { type: "number", minimum: 0, maximum: 1000 },
        mockups: { type: "array", items: { type: "string" } },
        release_target: { type: "string" },
        produces: producesFieldSchema(),
        timeline: timelineFieldSchema(),
      },
    };
  }
  summary(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      status: spec.status ?? "todo",
      feature: spec.feature ?? "",
      owner: spec.owner ?? "",
      estimate: spec.estimate,
      spec_refs: ((spec.spec_refs as unknown[]) ?? []).length,
      priority: spec.priority ?? "medium",
      labels: (spec.labels as unknown[]) ?? [],
      sprint_ref: spec.sprint_ref ?? "",
      business_value: spec.business_value,
    };
  }
}

// ---------------------------------------------------------------------------
// Issue
// ---------------------------------------------------------------------------

class IssueKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly scope = TenantScope.GLOBAL; // SDLC primitives are project-level
  readonly kind = "Issue";
  readonly alias = "sdlc-issue";
  readonly scopeInheritable = false;
  readonly origin = "github.com/ruinosus/dna/sdlc";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly plane = "record" as const;
  readonly storage = SD.yaml("issues");
  readonly graphStyle = { fill: "#EF4444", stroke: "#DC2626", textColor: "#fff" };
  readonly asciiIcon = "🐞";
  readonly displayLabel = "Issues";
  readonly docs =
    "An Issue is a human-authored ticket — bug, enhancement, question, " +
    "or task. Tracked across open → triaged → in-progress → resolved. " +
    "Optional links to a parent Feature (work it belongs to) and a " +
    "related Finding (eval-detected origin).";

  depFilters() {
    return {
      related_feature: "sdlc-feature",
      owner: "helix-actor",
    };
  }
  schema() {
    return {
      type: "object",
      required: ["description", "type", "severity", "status"],
      additionalProperties: true,
      properties: {
        title: { type: "string", description: "Human-readable display name." },
        description: { type: "string" },
        type: { type: "string", enum: [...ISSUE_TYPES] },
        severity: { type: "string", enum: [...ISSUE_SEVERITIES] },
        status: { type: "string", enum: [...ISSUE_STATUSES] },
        owner: { type: "string", description: "Actor name" },
        related_feature: { type: "string", description: "Feature name" },
        related_finding: { type: "string", description: "Finding name" },
        reproduction_steps: { type: "array", items: { type: "string" } },
        expected_behavior: { type: "string" },
        actual_behavior: { type: "string" },
        closed_at: { type: "string", format: "date-time" },
        resolution: { type: "string" },
        // v1.5 — board-grade common fields. Issues use `severity`
        // natively; `priority` is orthogonal (severity = how bad,
        // priority = how soon).
        priority: { type: "string", enum: [...PRIORITIES] },
        labels: { type: "array", items: { type: "string" } },
        reporter: { type: "string" },
        watchers: { type: "array", items: { type: "string" } },
        journey_phase: { type: "string", enum: [...JOURNEY_PHASES] },
        created_at: { type: "string", format: "date-time" },
        updated_at: { type: "string", format: "date-time" },
        produces: producesFieldSchema(),
        timeline: timelineFieldSchema(),
      },
    };
  }
  summary(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      type: spec.type ?? "bug",
      severity: spec.severity ?? "medium",
      status: spec.status ?? "open",
      owner: spec.owner ?? "",
      related_feature: spec.related_feature ?? "",
      priority: spec.priority ?? "medium",
      labels: (spec.labels as unknown[]) ?? [],
    };
  }
}

// ---------------------------------------------------------------------------
// Spec — pattern-agnostic pointer to design doc
// ---------------------------------------------------------------------------

// ADR-style status (Nygard). Plan reuses the same enum.
const ARTIFACT_STATUSES = ["draft", "proposed", "accepted", "deprecated", "superseded"] as const;

// Spec.phase — Superpowers/Spec-Kit phase progression. Orthogonal to status.
const SPEC_PHASES = ["brainstorm", "spec", "plan_ready", "implementing", "done"] as const;

class SpecKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly scope = TenantScope.GLOBAL; // SDLC primitives are project-level
  readonly kind = "Spec";
  readonly alias = "sdlc-spec";
  readonly origin = "github.com/ruinosus/dna/sdlc";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly plane = "record" as const;
  readonly storage = SD.bundle("specs", "SPEC.md", "text", "body");
  // Embeddable (s-spec-embeddable): the markdown body is the design's
  // substance — Plan/Issue/Epic/Doc/Research already embed; Spec was the
  // lone SDLC-artifact gap so `dna cognitive search` missed design docs.
  readonly embedFields = ["title", "summary", "body"];
  readonly graphStyle = { fill: "#6366F1", stroke: "#4F46E5", textColor: "#fff" };
  readonly asciiIcon = "📐";
  readonly displayLabel = "Specs";
  readonly docs =
    "A Spec is a top-level design artifact. Cross-cutting by default — " +
    "linkage to work items happens via Story.spec_refs[] (M:N). " +
    "Pattern-agnostic: superpowers, BMAD, droid, RFC, ADR, Spec Kit. " +
    "ADR-style status; phase tracks the orthogonal SDLC view.";

  depFilters() {
    return { epic: "sdlc-epic", supersedes: "sdlc-spec" };
  }
  schema() {
    return {
      type: "object",
      required: ["title", "date", "status"],
      additionalProperties: true,
      properties: {
        title: { type: "string" },
        date: { type: "string", format: "date" },
        status: { type: "string", enum: [...ARTIFACT_STATUSES] },
        phase: {
          type: "string",
          enum: [...SPEC_PHASES],
          description: "Where in the SDLC this spec's work sits. Orthogonal to status.",
        },
        pattern: { type: "string" },
        body: { type: "string" }, origin: { type: "string" },
        epic: { type: "string" },
        authors: { type: "array", items: { type: "string" } },
        tags: { type: "array", items: { type: "string" } },
        supersedes: { type: "string" },
        summary: { type: "string" },
      },
    };
  }
  summary(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      title: ((spec.title as string) ?? "").slice(0, 80),
      date: spec.date ?? "",
      status: spec.status ?? "draft",
      phase: spec.phase ?? "",
      pattern: spec.pattern ?? "",
      epic: spec.epic ?? "",
    };
  }
}

class PlanKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly scope = TenantScope.GLOBAL; // SDLC primitives are project-level
  readonly kind = "Plan";
  readonly alias = "sdlc-plan";
  readonly scopeInheritable = false;
  readonly origin = "github.com/ruinosus/dna/sdlc";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly plane = "record" as const;
  readonly storage = SD.bundle("plans", "PLAN.md", "text", "body");
  readonly graphStyle = { fill: "#06B6D4", stroke: "#0891B2", textColor: "#fff" };
  readonly asciiIcon = "📋";
  readonly displayLabel = "Plans";
  readonly docs =
    "A Plan is a pointer to an implementation plan. Usually descends " +
    "from a Spec via spec_ref. Pattern-agnostic.";

  depFilters() {
    return {
      spec_ref: "sdlc-spec",
      epic: "sdlc-epic",
    };
  }
  schema() {
    return {
      type: "object",
      required: ["title", "date", "status"],
      additionalProperties: true,
      properties: {
        title: { type: "string" },
        date: { type: "string", format: "date" },
        status: { type: "string", enum: [...ARTIFACT_STATUSES] },
        pattern: { type: "string" },
        body: { type: "string" }, origin: { type: "string" },
        spec_ref: { type: "string" },
        epic: { type: "string" },
        authors: { type: "array", items: { type: "string" } },
        tags: { type: "array", items: { type: "string" } },
        summary: { type: "string" },
        // Parity with the Py twin (PlanKind.schema): journey_phase lights the
        // derived `plan` phase; methodology records which planning method
        // produced the plan (superpowers/bmad/...) — opt-in, agnostic.
        journey_phase: { type: "string", enum: [...JOURNEY_PHASES] },
        methodology: { type: "string", enum: [...JOURNEY_METHODOLOGIES] },
      },
    };
  }
  summary(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      title: ((spec.title as string) ?? "").slice(0, 80),
      date: spec.date ?? "",
      status: spec.status ?? "draft",
      pattern: spec.pattern ?? "",
      spec_ref: spec.spec_ref ?? "",
    };
  }
}

// ---------------------------------------------------------------------------
// AgentSession — chat dev↔AI as versioned project artifact (Karpathy 2025)
// ---------------------------------------------------------------------------

class AgentSessionKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly scope = TenantScope.GLOBAL; // SDLC primitives are project-level
  readonly kind = "AgentSession";
  readonly alias = "sdlc-agent-session";
  readonly origin = "github.com/ruinosus/dna/sdlc";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly plane = "record" as const;
  readonly storage = SD.bundle("agent-sessions", "SESSION.md", "text", "body");
  readonly graphStyle = { fill: "#EC4899", stroke: "#DB2777", textColor: "#fff" };
  readonly asciiIcon = "📜";
  readonly displayLabel = "Vibe Sessions";
  readonly docs =
    "A AgentSession captures a developer↔AI coding conversation as a " +
    "versioned project artifact. Tool-agnostic (Claude Code, Cursor, " +
    "Cline, Codex, Aider) via per-tool adapters.";

  depFilters() {
    return { participants: "helix-actor" };
  }
  schema() {
    return {
      type: "object",
      required: ["title", "tool", "session_id", "started_at"],
      additionalProperties: true,
      properties: {
        title: { type: "string" },
        tool: {
          type: "string",
          description: "claude-code | cursor | cline | codex | aider | specstory | other",
        },
        tool_version: { type: "string" },
        session_id: { type: "string" },
        model: { type: "string" },
        workspace_path: { type: "string" },
        started_at: { type: "string", format: "date-time" },
        ended_at: { type: "string", format: "date-time" },
        participants: { type: "array", items: { type: "string" } },
        produced_artifacts: {
          type: "array",
          items: {
            type: "object",
            required: ["kind", "name"],
            properties: {
              kind: { type: "string" },
              name: { type: "string" },
            },
          },
        },
        applied_commits: { type: "array", items: { type: "string" } },
        file_changes: { type: "array", items: { type: "string" } },
        token_usage: { type: "object" },
        cost_usd: { type: "number" },
        summary: { type: "string" },
        body: { type: "string" },
        raw_source: { type: "string" },
        tool_specific: { type: "object" },
      },
    };
  }
  summary(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      title: ((spec.title as string) ?? "").slice(0, 80),
      tool: spec.tool ?? "",
      model: spec.model ?? "",
      started_at: spec.started_at ?? "",
      produced_artifacts: ((spec.produced_artifacts as unknown[]) ?? []).length,
    };
  }
}

// ---------------------------------------------------------------------------
// Narrative — agent-curated project storytelling (1:1 twin of Py)
// ---------------------------------------------------------------------------

// Narrative — F3 lote-2 (spec 2026-06-10-kinds-descriptor-f3): the twin NarrativeKind classes (Py+TS) were
// DELETED — synthesized from kinds/narrative.kind.yaml (parity-critical
// package data, byte-identical Py↔TS) via the loadDescriptors loop in
// register(). Equivalence with the extinct class frozen in
// tests/test_lote2_descriptor_equivalence.py (golden:
// tests/goldens/lote2/Narrative.golden.json).

// ---------------------------------------------------------------------------
// Bug / Task / Spike — granular work items (split from Issue umbrella)
// ---------------------------------------------------------------------------

const BUG_SEVERITY = ["low", "medium", "high", "critical"] as const;
const BUG_STATUSES = ["open", "triaged", "in-progress", "resolved", "wont-fix", "duplicate", "regression"] as const;
const TASK_STATUSES = ["todo", "in-progress", "done", "blocked", "cancelled"] as const;
const SPIKE_STATUSES = ["proposed", "in-progress", "answered", "abandoned"] as const;

class BugKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly scope = TenantScope.GLOBAL;
  readonly kind = "Bug";
  readonly alias = "sdlc-bug";
  readonly origin = "github.com/ruinosus/dna/sdlc";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly plane = "record" as const;
  readonly storage = SD.bundle("bugs", "BUG.md", "text", "body");
  readonly graphStyle = { fill: "#DC2626", stroke: "#991B1B", textColor: "#fff" };
  readonly asciiIcon = "🐛";
  readonly displayLabel = "Bugs";
  readonly docs =
    "Defeito factual com repro + severity. Schema dedicado " +
    "(repro_steps, environment, root_cause, fix_summary).";

  depFilters() {
    return {
      related_story: "sdlc-story",
      related_feature: "sdlc-feature",
      fix_adr: "sdlc-adr",
    };
  }
  schema() {
    return {
      type: "object",
      required: ["title", "severity", "status"],
      additionalProperties: true,
      properties: {
        title: { type: "string" },
        description: { type: "string" },
        severity: { type: "string", enum: [...BUG_SEVERITY] },
        status: { type: "string", enum: [...BUG_STATUSES] },
        repro_steps: { type: "array", items: { type: "string" } },
        expected: { type: "string" },
        actual: { type: "string" },
        environment: { type: "string" },
        root_cause: { type: "string" },
        fix_summary: { type: "string" },
        fix_adr: { type: "string" },
        related_story: { type: "string" },
        related_feature: { type: "string" },
        related_finding: { type: "string" },
        reporter: { type: "string" },
        owner: { type: "string" },
        found_at: { type: "string", format: "date-time" },
        resolved_at: { type: "string", format: "date-time" },
        labels: { type: "array", items: { type: "string" } },
        priority: { type: "string", enum: [...PRIORITIES] },
        body: { type: "string" },
        produces: producesFieldSchema(),
        timeline: timelineFieldSchema(),
        created_at: { type: "string", format: "date-time" },
        updated_at: { type: "string", format: "date-time" },
      },
    };
  }
  summary(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      title: (spec.title as string) ?? "",
      severity: (spec.severity as string) ?? "",
      status: (spec.status as string) ?? "",
    };
  }
}

class TaskKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly scope = TenantScope.GLOBAL;
  readonly kind = "Task";
  readonly alias = "sdlc-task";
  readonly origin = "github.com/ruinosus/dna/sdlc";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly plane = "record" as const;
  readonly storage = SD.bundle("tasks", "TASK.md", "text", "body");
  readonly graphStyle = { fill: "#3B82F6", stroke: "#1D4ED8", textColor: "#fff" };
  readonly asciiIcon = "✅";
  readonly displayLabel = "Tasks";
  readonly docs =
    "Work item granular (horas-dias). Sub-item de Story (Atlassian " +
    "Jira Align hierarchy: Story → Task → Sub-task).";

  depFilters() { return { story_ref: "sdlc-story", owner: "helix-actor" }; }
  schema() {
    return {
      type: "object",
      required: ["title", "status"],
      additionalProperties: true,
      properties: {
        title: { type: "string" },
        description: { type: "string" },
        status: { type: "string", enum: [...TASK_STATUSES] },
        story_ref: { type: "string" },
        owner: { type: "string" },
        estimate_hours: { type: "number", minimum: 0 },
        logged_hours: { type: "number", minimum: 0 },
        due: { type: "string", format: "date" },
        priority: { type: "string", enum: [...PRIORITIES] },
        labels: { type: "array", items: { type: "string" } },
        blocked_reason: { type: "string" },
        closed_at: { type: "string", format: "date-time" },
        body: { type: "string" },
        produces: producesFieldSchema(),
        timeline: timelineFieldSchema(),
        created_at: { type: "string", format: "date-time" },
        updated_at: { type: "string", format: "date-time" },
      },
    };
  }
  summary(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      title: (spec.title as string) ?? "",
      status: (spec.status as string) ?? "",
      owner: (spec.owner as string) ?? "",
    };
  }
}

class SpikeKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly scope = TenantScope.GLOBAL;
  readonly kind = "Spike";
  readonly alias = "sdlc-spike";
  readonly origin = "github.com/ruinosus/dna/sdlc";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly plane = "record" as const;
  readonly storage = SD.bundle("spikes", "SPIKE.md", "text", "body");
  readonly graphStyle = { fill: "#A855F7", stroke: "#7E22CE", textColor: "#fff" };
  readonly asciiIcon = "🔬";
  readonly displayLabel = "Spikes";
  readonly docs =
    "Time-boxed technical investigation. ONE question + finite " +
    "time + outcome handoff (findings → Story or ADR).";

  depFilters() {
    return {
      follow_up_story: "sdlc-story",
      follow_up_adr: "sdlc-adr",
      follow_up_spec: "sdlc-spec",
      feature: "sdlc-feature",
      // Multi-ref attachments (2026-05-26 — design-spike workflow).
      references: "sdlc-reference",
      related_spikes: "sdlc-spike",
    };
  }
  schema() {
    return {
      type: "object",
      required: ["title", "question_to_answer", "status"],
      additionalProperties: true,
      properties: {
        title: { type: "string" },
        question_to_answer: { type: "string" },
        status: { type: "string", enum: [...SPIKE_STATUSES] },
        time_box_hours: { type: "number", minimum: 0, default: 8 },
        logged_hours: { type: "number", minimum: 0 },
        findings: { type: "string" },
        recommendation: { type: "string" },
        follow_up_story: { type: "string" },
        follow_up_adr: { type: "string" },
        follow_up_spec: { type: "string" },
        feature: { type: "string" },
        owner: { type: "string" },
        html_artifacts: { type: "array", items: { type: "string" } },
        research_refs: { type: "array", items: { type: "string" } },
        references: { type: "array", items: { type: "string" } },
        related_spikes: { type: "array", items: { type: "string" } },
        started_at: { type: "string", format: "date-time" },
        completed_at: { type: "string", format: "date-time" },
        labels: { type: "array", items: { type: "string" } },
        body: { type: "string" },
        produces: producesFieldSchema(),
        timeline: timelineFieldSchema(),
        created_at: { type: "string", format: "date-time" },
        updated_at: { type: "string", format: "date-time" },
      },
    };
  }
  summary(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      title: (spec.title as string) ?? "",
      status: (spec.status as string) ?? "",
      time_box_hours: (spec.time_box_hours as number) ?? null,
    };
  }
}

// ---------------------------------------------------------------------------
// Initiative — investment unit (Atlassian Jira Align hierarchy)
// ---------------------------------------------------------------------------

const INITIATIVE_STATUSES = ["proposed", "in-flight", "done", "cancelled", "deferred"] as const;

class InitiativeKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly scope = TenantScope.GLOBAL;
  readonly kind = "Initiative";
  readonly alias = "sdlc-initiative";
  readonly origin = "github.com/ruinosus/dna/sdlc";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly plane = "record" as const;
  readonly storage = SD.bundle("initiatives", "INITIATIVE.md", "text", "body");
  readonly graphStyle = { fill: "#0EA5E9", stroke: "#0284C7", textColor: "#fff" };
  readonly asciiIcon = "🎲";
  readonly displayLabel = "Initiatives";
  readonly docs =
    "Investment-level umbrella (1-2 quarters) between Theme/OKR and " +
    "Epic. Atlassian Jira Align hierarchy.";

  depFilters() {
    return { epics: "sdlc-epic", owner: "helix-actor" };
  }
  schema() {
    return {
      type: "object",
      required: ["title", "status"],
      additionalProperties: true,
      properties: {
        title: { type: "string" },
        description: { type: "string" },
        status: { type: "string", enum: [...INITIATIVE_STATUSES] },
        owner: { type: "string" },
        horizon_start: { type: "string", format: "date" },
        horizon_end: { type: "string", format: "date" },
        outcome_metric: { type: "string" },
        target_value: { type: "string" },
        epics: { type: "array", items: { type: "string" } },
        theme_ref: { type: "string" },
        business_value: { type: "number" },
        priority: { type: "string", enum: [...PRIORITIES] },
        labels: { type: "array", items: { type: "string" } },
        body: { type: "string" },
        created_at: { type: "string", format: "date-time" },
        updated_at: { type: "string", format: "date-time" },
      },
    };
  }
  summary(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      title: (spec.title as string) ?? "",
      status: (spec.status as string) ?? "",
      epics_count: ((spec.epics as unknown[]) ?? []).length,
    };
  }
}

// ---------------------------------------------------------------------------
// Reference — external citation artifact
// ---------------------------------------------------------------------------

const REFERENCE_KIND_OFS = ["web", "paper", "book", "file", "internal-doc", "other"] as const;

/**
 * Reference — external citation artifact (web/paper/book/file/internal-doc).
 *
 * Wraps external sources with metadata so SDLC docs can cite evidence
 * durably. Any other Kind (Story, Feature, Spec, Plan, Engram, etc.)
 * gains an optional `spec.references: list[str]` field naming Reference
 * doc slugs. CLI `dna sdlc cite` maintains the bidirectional graph
 * (Reference.spec.cited_by += caller_ref).
 *
 * Ported from Python for s-alias-generated-not-typed: Spike.depFilters
 * points at `sdlc-reference`, and validateDepFilters requires every
 * builtin dep_filter alias to resolve — the Kind can no longer be
 * py-only. 1:1 twin of dna.extensions.sdlc.ReferenceKind.
 *
 * Spec: docs/superpowers/specs/2026-05-12-f-reference-citation-kind.md
 */
class ReferenceKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly scope = TenantScope.GLOBAL;
  readonly kind = "Reference";
  readonly alias = "sdlc-reference";
  readonly origin = "github.com/ruinosus/dna/sdlc";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly plane = "record" as const;
  readonly storage = SD.yaml("references");
  readonly graphStyle = { fill: "#6366F1", stroke: "#4F46E5", textColor: "#fff" };
  readonly asciiIcon = "📚";
  readonly displayLabel = "References";

  depFilters() {
    return {};
  }
  schema() {
    return {
      type: "object",
      required: ["title", "kind_of", "summary"],
      additionalProperties: true,
      properties: {
        title: { type: "string" },
        kind_of: { type: "string", enum: [...REFERENCE_KIND_OFS] },
        url: { type: "string" },
        fetched_at: { type: "string", format: "date-time" },
        summary: { type: "string", description: "1-2 sentence what this source says." },
        key_quotes: { type: "array", items: { type: "string" }, default: [] },
        relevance: { type: "string", description: "Why this matters for THIS project." },
        tags: { type: "array", items: { type: "string" }, default: [] },
        cited_by: {
          type: "array",
          items: { type: "string" },
          default: [],
          description: "Auto-maintained by `dna sdlc cite`. Don't author by hand.",
        },
        content_path: {
          type: "string",
          description:
            "Optional path to rich-content sidecar (e.g. docs/superpowers/research/<slug>.md)",
        },
        owner: { type: "string", default: "claude-code" },
        created_at: { type: "string", format: "date-time" },
        updated_at: { type: "string", format: "date-time" },
      },
    };
  }
  summary(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    return {
      title: (spec.title as string) ?? "",
      kind_of: (spec.kind_of as string) ?? "other",
      url: (spec.url as string) ?? "",
      cited_by_count: ((spec.cited_by as unknown[]) ?? []).length,
    };
  }
}

// ---------------------------------------------------------------------------
// Changelog — Keep a Changelog 1.1.0 + SemVer 2.0
// ---------------------------------------------------------------------------

// Changelog — F3 lote-2 (spec 2026-06-10-kinds-descriptor-f3): the twin ChangelogKind classes (Py+TS) were
// DELETED — synthesized from kinds/changelog.kind.yaml (parity-critical
// package data, byte-identical Py↔TS) via the loadDescriptors loop in
// register(). Equivalence with the extinct class frozen in
// tests/test_lote2_descriptor_equivalence.py (golden:
// tests/goldens/lote2/Changelog.golden.json).

// ---------------------------------------------------------------------------
// Postmortem — Google SRE blameless incident analysis
// ---------------------------------------------------------------------------

// Postmortem — F3 lote-2 (spec 2026-06-10-kinds-descriptor-f3): the twin PostmortemKind classes (Py+TS) were
// DELETED — synthesized from kinds/postmortem.kind.yaml (parity-critical
// package data, byte-identical Py↔TS) via the loadDescriptors loop in
// register(). Equivalence with the extinct class frozen in
// tests/test_lote2_descriptor_equivalence.py (golden:
// tests/goldens/lote2/Postmortem.golden.json).

// ---------------------------------------------------------------------------
// RiskRegister — PMBOK 7 + ISO 31000:2018
// ---------------------------------------------------------------------------

// RiskRegister — F3 lote-2 (spec 2026-06-10-kinds-descriptor-f3): the twin RiskRegisterKind classes (Py+TS) were
// DELETED — synthesized from kinds/risk-register.kind.yaml (parity-critical
// package data, byte-identical Py↔TS) via the loadDescriptors loop in
// register(). Equivalence with the extinct class frozen in
// tests/test_lote2_descriptor_equivalence.py (golden:
// tests/goldens/lote2/RiskRegister.golden.json).

// ---------------------------------------------------------------------------
// ADR — Architecture Decision Record (Nygard 2011 / MADR)
// ---------------------------------------------------------------------------

// ADR — F3 lote-2 (spec 2026-06-10-kinds-descriptor-f3): the twin ADRKind classes (Py+TS) were
// DELETED — synthesized from kinds/adr.kind.yaml (parity-critical
// package data, byte-identical Py↔TS) via the loadDescriptors loop in
// register(). Equivalence with the extinct class frozen in
// tests/test_lote2_descriptor_equivalence.py (golden:
// tests/goldens/lote2/ADR.golden.json).

// ---------------------------------------------------------------------------
// Retrospective — sprint/release/incident retro (Atlassian 4 Ls)
// ---------------------------------------------------------------------------

// Retrospective — F3 lote-1 (spec 2026-06-10-kinds-descriptor-f3): the twin
// RetrospectiveKind classes (Py+TS) were DELETED — synthesized from
// kinds/retrospective.kind.yaml (parity-critical package data) via the
// loadDescriptors loop in register(). The old TS-only summary()/slim schema
// drifted from Py; the descriptor unifies on the canonical (Py) surface.

// ---------------------------------------------------------------------------
// Extension
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// WorkflowEvent — append-only ledger of phase transitions (1:1 twin of Py)
// ---------------------------------------------------------------------------

const JOURNEY_METHODOLOGIES = [
  "superpowers", "bmad", "spec-kit", "kiro",
  "rfc", "adr", "ad-hoc", "custom",
] as const;

// ---------------------------------------------------------------------------
// SavedView — named filter+groupBy+sort+layout entity (Linear/Notion pattern)
// ---------------------------------------------------------------------------

// SavedView — F3 lote-2 (spec 2026-06-10-kinds-descriptor-f3): the twin SavedViewKind classes (Py+TS) were
// DELETED — synthesized from kinds/saved-view.kind.yaml (parity-critical
// package data, byte-identical Py↔TS) via the loadDescriptors loop in
// register(). Equivalence with the extinct class frozen in
// tests/test_lote2_descriptor_equivalence.py (golden:
// tests/goldens/lote2/SavedView.golden.json).

// WorkflowEvent — F3 lote-1: twin classes deleted — synthesized from
// kinds/workflow-event.kind.yaml. Old TS summary defaults ("") drifted from
// Py (null); the descriptor unifies on the canonical (Py) surface.

// Insight — F3 lote-2 (spec 2026-06-10-kinds-descriptor-f3): the twin InsightKind classes (Py+TS) were
// DELETED — synthesized from kinds/insight.kind.yaml (parity-critical
// package data, byte-identical Py↔TS) via the loadDescriptors loop in
// register(). Equivalence with the extinct class frozen in
// tests/test_lote2_descriptor_equivalence.py (golden:
// tests/goldens/lote2/Insight.golden.json).

// StatusReport — F3 lote-2 (spec 2026-06-10-kinds-descriptor-f3): the twin StatusReportKind classes (Py+TS) were
// DELETED — synthesized from kinds/status-report.kind.yaml (parity-critical
// package data, byte-identical Py↔TS) via the loadDescriptors loop in
// register(). Equivalence with the extinct class frozen in
// tests/test_lote2_descriptor_equivalence.py (golden:
// tests/goldens/lote2/StatusReport.golden.json).

// ---------------------------------------------------------------------------
// Cognitive Memory Triad (v1.9.0) — LessonLearned + SynthesisRun + ArchiveProposal
//
// Spec: docs/superpowers/specs/2026-05-11-cognitive-memory-triad.md
// Surface labels (pt-BR) in Studio: "Lições Aprendidas" / "Sínteses" / "Arquivamento".
// Kind names stay English per repo convention (same pattern as Insight).
// ---------------------------------------------------------------------------

// REMEMBRANCE_AFFECTS / REMEMBRANCE_SURFACE_TRIGGERS now live ONLY in
// kinds/lesson-learned.kind.yaml (F3 lote-1) — the descriptor is the
// single source for the LessonLearned enums.
// F3 lote-2: the per-Kind enum consts that used to live here
// (DREAM_*/FORGETTING_*/ADR_STATUSES/RISK_*/SAVED_VIEW_*/POSTMORTEM_SEVERITY/
// INSIGHT_CONFIDENCE_LEVELS) died with the classes — the descriptors under
// sdlc/kinds/*.kind.yaml are the single source for the enums; tests read
// them from the synthesized port's schema.


// LessonLearned — F3 lote-1: twin classes deleted — synthesized from
// kinds/lesson-learned.kind.yaml. The old TS class was strict + missing
// affect_reason/affect_evidence_refs (real drift); the descriptor unifies
// on the canonical (Py) surface.

// SynthesisRun — F3 lote-2 (spec 2026-06-10-kinds-descriptor-f3): the twin SynthesisRunKind classes (Py+TS) were
// DELETED — synthesized from kinds/synthesis-run.kind.yaml (parity-critical
// package data, byte-identical Py↔TS) via the loadDescriptors loop in
// register(). Equivalence with the extinct class frozen in
// tests/test_lote2_descriptor_equivalence.py (golden:
// tests/goldens/lote2/SynthesisRun.golden.json).


// ArchiveProposal — F3 lote-2 (spec 2026-06-10-kinds-descriptor-f3): the twin ArchiveProposalKind classes (Py+TS) were
// DELETED — synthesized from kinds/archive-proposal.kind.yaml (parity-critical
// package data, byte-identical Py↔TS) via the loadDescriptors loop in
// register(). Equivalence with the extinct class frozen in
// tests/test_lote2_descriptor_equivalence.py (golden:
// tests/goldens/lote2/ArchiveProposal.golden.json).


// ---------------------------------------------------------------------------
// PromptTemplate — expr batch B (plan 2026-06-11-descriptor-expressiveness,
// Chunk 4): the twin classes were DELETED; synthesized from
// sdlc/kinds/prompt-template.kind.yaml via the loadDescriptors loop in
// register().
//
// s-consolidate-cognitive-policies (f-kind-catalog-governance, 2026-07-07):
// the 9 cognitive policy Kinds (RecallPolicy, DecayPolicy, MemoryPolicy, the
// old CognitivePolicy, AllocationPolicy, PaginationPolicy,
// EngramStrengthPolicy, EmbeddingProfile, AffectPalette) were consolidated
// into ONE expanded CognitivePolicy descriptor
// (sdlc/kinds/cognitive-policy.kind.yaml) with one top-level spec section per
// former Kind. The 8 retired names are pinned in the Py kernel's
// _REMOVED_KINDS (+ _REMOVED_KIND_NOTES; the write path is Py-only).
// ---------------------------------------------------------------------------


// ---------------------------------------------------------------------------
// Kaizen — first-class improvement observation (record plane)
//
// F3 P2 (spec 2026-06-10-kinds-descriptor-f3): the twin KaizenKind classes
// (Py + TS) were DELETED — the Kind is now synthesized from the descriptor
// sdlc/kinds/kaizen.kind.yaml (parity-critical package data, byte-identical
// Py↔TS) via kernel.kindFromDescriptor in register() below. Equivalence with
// the old class is frozen in sdk-py tests/test_kaizen_descriptor_equivalence.py
// + tests/sdlc.test.ts.
// ---------------------------------------------------------------------------


export class SdlcExtension implements Extension {
  readonly name = "sdlc";
  // v1.14.0 — s-consolidate-cognitive-policies: the 9 cognitive policy
  // Kinds consolidated into one expanded CognitivePolicy (TS parity with
  // Python SdlcExtension v1.14.0).
  readonly version = "1.14.0";

  register(kernel: ExtensionHost): void {
    kernel.kind(new RoadmapKind());
    kernel.kind(new EpicKind());
    kernel.kind(new FeatureKind());
    kernel.kind(new StoryKind());
    kernel.kind(new IssueKind());
    kernel.kind(new SpecKind());
    kernel.kind(new PlanKind());
    kernel.kind(new AgentSessionKind());
    kernel.kind(new BugKind());
    kernel.kind(new TaskKind());
    kernel.kind(new SpikeKind());
    kernel.kind(new InitiativeKind());
    // v1.10.0 — f-reference-citation-kind (ported from Python for
    // s-alias-generated-not-typed: Spike.depFilters → "sdlc-reference").
    kernel.kind(new ReferenceKind());
    // expr batch B: PromptTemplate is a descriptor now — registered via the
    // loadDescriptors loop below. s-consolidate-cognitive-policies: the
    // cognitive policy family is ONE descriptor (cognitive-policy.kind.yaml).
    // F3 P2 (spec 2026-06-10-kinds-descriptor-f3): builtin record Kinds
    // expressed as descriptors — kinds/*.kind.yaml package data registered
    // through the SAME funnel as per-scope KindDefinitions (plane lint +
    // digest idempotency + builtin conflict marker). Structured as a loop
    // so migration batches just drop files into sdlc/kinds/ — no per-Kind
    // code. Pilot: Kaizen (v1.13.0 s-kaizen-kind, class twins deleted).
    for (const raw of loadDescriptors(import.meta.url, "sdlc/kinds")) {
      kernel.kindFromDescriptor(raw);
    }
  }
}
