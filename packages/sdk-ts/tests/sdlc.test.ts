import { describe, it, expect } from "bun:test";
import { Kernel } from "../src/kernel/index.js";
import { SdlcExtension } from "../src/extensions/sdlc.js";

describe("SdlcExtension — TS parity with Python", () => {
  it("registers 31 Kinds under github.com/ruinosus/dna/sdlc/v1 (the 9 cognitive policy Kinds are ONE unified CognitivePolicy since s-consolidate-cognitive-policies, 39→31 — full 1:1 with Py)", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const registered = Array.from((k as any)._kinds.keys() as IterableIterator<string>)
      .filter((key: string) => key.startsWith("github.com/ruinosus/dna/sdlc/v1\0"))
      .map((key: string) => key.split("\0")[1])
      .sort();
    expect(registered).toEqual([
      "ADR", "AgentSession",
      "ArchiveProposal", "Bug", "Changelog", "CognitivePolicy",
      "Epic",
      "Feature", "Forecast", "Initiative", "Insight", "Issue", "Kaizen",
      "LessonLearned", "Narrative",
      "Plan", "Postmortem", "PromptTemplate", "Reference",
      "Retrospective", "RiskRegister", "Roadmap", "SavedView", "Spec",
      "Spike", "StatusReport", "Story", "SynthesisRun",
      "SynthesizerState", "Task", "WorkflowEvent",
    ]);
  });

  it("AgentSession Kind is bundle-storage with required tool-agnostic fields", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const vs = ((k as any)._kinds as Map<string, { schema: () => Record<string, unknown>; alias: string; storage: { pattern: { value?: string }; container?: string; marker?: string } }>)
      .get("github.com/ruinosus/dna/sdlc/v1\0AgentSession")!;
    expect(vs.alias).toBe("sdlc-agent-session");
    expect(vs.storage.pattern.value ?? vs.storage.pattern).toBe("bundle");
    expect(vs.storage.container).toBe("agent-sessions");
    expect(vs.storage.marker).toBe("SESSION.md");
    const schema = vs.schema();
    expect(new Set(schema.required as string[])).toEqual(
      new Set(["title", "tool", "session_id", "started_at"]),
    );
  });

  it("exposes 1:1 aliases with Python", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const aliases = Array.from(((k as any)._kinds as Map<string, { alias: string }>).values())
      .map((kp) => kp.alias)
      .filter((a) => a.startsWith("sdlc-"))
      .sort();
    expect(aliases).toEqual([
      "sdlc-adr",
      "sdlc-agent-session",
      "sdlc-archive-proposal",
      "sdlc-bug",
      "sdlc-changelog",
      "sdlc-cognitive-policy",
      "sdlc-epic",
      "sdlc-feature",
      "sdlc-forecast",
      "sdlc-initiative",
      "sdlc-insight",
      "sdlc-issue",
      "sdlc-kaizen",
      "sdlc-lesson-learned",
      "sdlc-narrative",
      "sdlc-plan",
      "sdlc-postmortem",
      "sdlc-prompt-template",
      "sdlc-reference",
      "sdlc-retrospective",
      "sdlc-risk-register",
      "sdlc-roadmap",
      "sdlc-saved-view",
      "sdlc-spec",
      "sdlc-spike",
      "sdlc-status-report",
      "sdlc-story",
      "sdlc-synthesis-run",
      "sdlc-synthesizer-state",
      "sdlc-task",
      "sdlc-workflow-event",
    ]);
  });

  it("Spec is pattern-agnostic (no enum on pattern field)", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const sp = ((k as any)._kinds as Map<string, { schema: () => Record<string, unknown> }>)
      .get("github.com/ruinosus/dna/sdlc/v1\0Spec")!;
    const schema = sp.schema();
    const props = schema.properties as Record<string, Record<string, unknown>>;
    expect(props.pattern.enum).toBeUndefined();
    expect(schema.required).toContain("title");
    expect(schema.required).toContain("date");
    expect(schema.required).toContain("status");
    expect(schema.required).not.toContain("file_path"); // bundle pattern — body in marker
    // ADR-style status (Nygard); legacy "shipped"/"rejected" gone in v1.2.
    const statuses = props.status.enum as string[];
    expect(statuses).toEqual(["draft", "proposed", "accepted", "deprecated", "superseded"]);
    // Spec.phase — Superpowers/Spec-Kit phase progression.
    const phases = props.phase.enum as string[];
    expect(phases).toEqual(["brainstorm", "spec", "plan_ready", "implementing", "done"]);
    // Axis flip: Spec.feature was removed.
    expect(props.feature).toBeUndefined();
  });

  it("Story has spec_refs[] for M:N linkage to Specs (axis flip)", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const st = ((k as any)._kinds as Map<string, { schema: () => Record<string, unknown>; depFilters: () => Record<string, string> }>)
      .get("github.com/ruinosus/dna/sdlc/v1\0Story")!;
    const props = st.schema().properties as Record<string, Record<string, unknown>>;
    expect(props.spec_refs.type).toBe("array");
    expect((props.spec_refs.items as { type: string }).type).toBe("string");
    expect(st.depFilters().spec_refs).toBe("sdlc-spec");
  });

  it("Plan links to Spec via spec_ref dep filter; feature axis removed", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const pl = ((k as any)._kinds as Map<string, { depFilters: () => Record<string, string>; schema: () => Record<string, unknown> }>)
      .get("github.com/ruinosus/dna/sdlc/v1\0Plan")!;
    const deps = pl.depFilters();
    expect(deps.spec_ref).toBe("sdlc-spec");
    expect(deps.feature).toBeUndefined();
    const props = pl.schema().properties as Record<string, unknown>;
    expect(props.feature).toBeUndefined();
  });

  it("Epic schema requires status (target_date optional) and lists done/deprecated (Jira-aligned)", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const ms = ((k as any)._kinds as Map<string, { schema: () => Record<string, unknown> }>)
      .get("github.com/ruinosus/dna/sdlc/v1\0Epic")!;
    const schema = ms.schema();
    expect(schema.required).toContain("status");
    // v1.3 BREAKING: target_date is OPTIONAL on Epic (was required on Milestone).
    expect(schema.required).not.toContain("target_date");
    const props = schema.properties as Record<string, { enum?: string[] }>;
    expect(props.status.enum).toContain("done");
    expect(props.status.enum).toContain("deprecated");
    expect(props.status.enum).not.toContain("shipped"); // renamed v1.2
    // closed_at field uniformizado com Story/Issue
    expect((schema.properties as Record<string, unknown>).closed_at).toBeDefined();
  });

  it("Feature dep_filters link UseCase + Actor + Story (cross-extension composition)", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const ft = ((k as any)._kinds as Map<string, { depFilters: () => Record<string, string> }>)
      .get("github.com/ruinosus/dna/sdlc/v1\0Feature")!;
    const deps = ft.depFilters();
    expect(deps.use_cases).toBe("helix-usecase");
    expect(deps.owner).toBe("helix-actor");
    expect(deps.stories).toBe("sdlc-story");
  });

  it("Issue links to Finding + Feature for eval-derived → manual bridge", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const issue = ((k as any)._kinds as Map<string, { schema: () => Record<string, unknown>; depFilters: () => Record<string, string> }>)
      .get("github.com/ruinosus/dna/sdlc/v1\0Issue")!;
    const schema = issue.schema();
    const props = schema.properties as Record<string, { enum?: string[] }>;
    expect(props.type.enum).toEqual(["bug", "enhancement", "question", "task"]);
    expect(props.severity.enum).toEqual(["low", "medium", "high", "critical"]);
    const deps = issue.depFilters();
    expect(deps.related_feature).toBe("sdlc-feature");
  });

  // ─── v1.5 board-grade fields ────────────────────────────────────────

  it("Story v1.5: priority + labels + sprint_ref + time_tracking + business_value", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const st = ((k as any)._kinds as Map<string, { schema: () => Record<string, unknown> }>)
      .get("github.com/ruinosus/dna/sdlc/v1\0Story")!;
    const props = st.schema().properties as Record<string, Record<string, unknown>>;
    expect(props.priority.enum).toEqual(["highest", "high", "medium", "low", "lowest"]);
    expect((props.labels.items as { type: string }).type).toBe("string");
    expect(props.sprint_ref.type).toBe("string");
    const tt = props.time_tracking;
    expect(tt.type).toBe("object");
    expect(tt.additionalProperties).toBe(false);
    const ttProps = tt.properties as Record<string, { type: string; minimum: number }>;
    expect(new Set(Object.keys(ttProps))).toEqual(new Set([
      "logged_h", "remaining_h", "original_estimate_h",
    ]));
    expect(ttProps.logged_h.type).toBe("number");
    expect(ttProps.logged_h.minimum).toBe(0);
    expect(props.business_value.minimum).toBe(0);
    expect(props.business_value.maximum).toBe(1000);
    expect(props.release_target.type).toBe("string");
    expect((props.mockups.items as { type: string }).type).toBe("string");
    // Story s-ac-dod-checklist-state: DoD items now oneOf [string, object].
    expect((props.definition_of_done.items as { oneOf: unknown[] }).oneOf).toHaveLength(2);
  });

  it("Feature v1.5: same rich fields as Story", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const ft = ((k as any)._kinds as Map<string, { schema: () => Record<string, unknown> }>)
      .get("github.com/ruinosus/dna/sdlc/v1\0Feature")!;
    const props = ft.schema().properties as Record<string, unknown>;
    for (const f of [
      "priority", "labels", "reporter", "watchers",
      "created_at", "updated_at", "sprint_ref",
      "time_tracking", "definition_of_done",
      "business_value", "mockups", "release_target",
    ]) {
      expect(props[f]).toBeDefined();
    }
  });

  it("Epic v1.5: subset only — no sprint/time_tracking/mockups/release_target", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const ep = ((k as any)._kinds as Map<string, { schema: () => Record<string, unknown> }>)
      .get("github.com/ruinosus/dna/sdlc/v1\0Epic")!;
    const props = ep.schema().properties as Record<string, unknown>;
    for (const f of [
      "priority", "labels", "reporter", "watchers",
      "created_at", "updated_at",
      "definition_of_done", "business_value",
    ]) {
      expect(props[f]).toBeDefined();
    }
    for (const f of ["sprint_ref", "time_tracking", "mockups", "release_target"]) {
      expect(props[f]).toBeUndefined();
    }
  });

  it("Issue v1.5: only universal common fields (severity is its native classification)", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const iss = ((k as any)._kinds as Map<string, { schema: () => Record<string, unknown> }>)
      .get("github.com/ruinosus/dna/sdlc/v1\0Issue")!;
    const props = iss.schema().properties as Record<string, unknown>;
    for (const f of [
      "priority", "labels", "reporter", "watchers",
      "created_at", "updated_at",
    ]) {
      expect(props[f]).toBeDefined();
    }
    for (const f of [
      "sprint_ref", "time_tracking", "definition_of_done",
      "business_value", "mockups", "release_target",
    ]) {
      expect(props[f]).toBeUndefined();
    }
  });

  // ─── v1.6 Activity Timeline ─────────────────────────────────────────

  it("Timeline field present on Story/Feature/Epic/Issue", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const kinds = (k as any)._kinds as Map<string, { schema: () => Record<string, unknown> }>;
    for (const kn of ["Story", "Feature", "Epic", "Issue"]) {
      const props = kinds.get(`github.com/ruinosus/dna/sdlc/v1\0${kn}`)!.schema().properties as Record<string, unknown>;
      expect(props.timeline).toBeDefined();
      const tl = props.timeline as { type: string; items: { type: string; required: string[] } };
      expect(tl.type).toBe("array");
      expect(tl.items.type).toBe("object");
      expect(new Set(tl.items.required)).toEqual(new Set(["at", "actor", "type"]));
    }
  });

  it("Timeline entry type enum lists Phase 1 events", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const kinds = (k as any)._kinds as Map<string, { schema: () => Record<string, unknown> }>;
    const props = kinds.get("github.com/ruinosus/dna/sdlc/v1\0Story")!.schema().properties as Record<string, unknown>;
    const tl = props.timeline as { items: { properties: Record<string, { enum?: string[] }> } };
    expect(tl.items.properties.type.enum).toEqual([
      "status_change", "groom", "comment", "decision", "artifact_produced",
    ]);
    expect(tl.items.properties.source.enum).toEqual([
      "cli", "studio", "agent-session-extracted", "system",
    ]);
  });

  it("Timeline entry has additionalProperties: true for future fields", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const kinds = (k as any)._kinds as Map<string, { schema: () => Record<string, unknown> }>;
    const props = kinds.get("github.com/ruinosus/dna/sdlc/v1\0Story")!.schema().properties as Record<string, unknown>;
    const tl = props.timeline as { items: { additionalProperties: boolean } };
    expect(tl.items.additionalProperties).toBe(true);
  });

  it("All 5 Kinds are not prompt targets and not root", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    const kinds = ["Roadmap", "Epic", "Feature", "Story", "Issue"];
    for (const kn of kinds) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const kp = ((k as any)._kinds as Map<string, { isPromptTarget: boolean; flattenInContext: boolean; isRoot: boolean }>)
        .get(`github.com/ruinosus/dna/sdlc/v1\0${kn}`)!;
      expect(kp.isPromptTarget).toBe(false);
      expect(kp.flattenInContext).toBe(false);
      expect(kp.isRoot).toBe(false);
    }
  });

  it("LessonLearned has visibility axis (shared|private|pinned|archived, default shared) — Phase 0 parity", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    const ll = ((k as unknown as { _kinds: Map<string, { schema: () => Record<string, unknown> }> })._kinds)
      .get("github.com/ruinosus/dna/sdlc/v1\0LessonLearned")!;
    const props = ll.schema().properties as Record<string, Record<string, unknown>>;
    expect(props.visibility.enum).toEqual(["shared", "private", "pinned", "archived"]);
    expect(props.visibility.default).toBe("shared");
    expect(props.owner).toBeDefined(); // attribution axis stays
  });


  it("Kaizen is a record Kind with body+status required and Issue dep filter (v1.13.0; F3 P2: synthesized from kinds/kaizen.kind.yaml, class deleted)", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const kz = ((k as any)._kinds as Map<string, {
      alias: string; origin: string; plane?: string;
      isPromptTarget: boolean; flattenInContext: boolean;
      schema: () => Record<string, unknown>;
      depFilters: () => Record<string, string>;
      summary: (doc: unknown) => Record<string, unknown>;
      __builtin_descriptor__?: boolean;
      graphStyle?: { fill: string; stroke: string; textColor: string };
    }>).get("github.com/ruinosus/dna/sdlc/v1\0Kaizen")!;
    expect(kz.alias).toBe("sdlc-kaizen");
    // F3 P2 — registered via the descriptor funnel, builtin-marked.
    expect(kz.__builtin_descriptor__).toBe(true);
    // graph_style from the YAML (snake_case text_color accepted — parity fix).
    expect(kz.graphStyle).toEqual({ fill: "#10B981", stroke: "#047857", textColor: "#fff" });
    expect(kz.origin).toBe("github.com/ruinosus/dna/sdlc");
    expect(kz.plane).toBe("record");
    expect(kz.isPromptTarget).toBe(false);
    expect(kz.flattenInContext).toBe(false);
    const schema = kz.schema();
    expect(new Set(schema.required as string[])).toEqual(new Set(["body", "status"]));
    const props = schema.properties as Record<string, Record<string, unknown>>;
    expect(props.status.enum).toEqual(["observed", "routed", "resolved"]);
    expect(props.status.default).toBe("observed");
    expect(schema.additionalProperties).toBe(false); // strict-schema ratchet
    // `work_item` is polymorphic (Kind/slug) — no dep filter for it.
    expect(kz.depFilters()).toEqual({ issue: "sdlc-issue" });
    const s = kz.summary({ spec: {
      body: "step is manual", work_item: "Story/s-x", issue: "i-042",
      status: "routed", actor: "claude-code", labels: ["dx"],
    } });
    expect(s).toEqual({
      status: "routed", work_item: "Story/s-x", issue: "i-042",
      actor: "claude-code", labels: ["dx"],
    });
  });

  it("LessonLearned has CoALA memory_type + bi-temporal fields (Phase 4 parity)", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    const ll = ((k as unknown as { _kinds: Map<string, { schema: () => Record<string, unknown> }> })._kinds)
      .get("github.com/ruinosus/dna/sdlc/v1\0LessonLearned")!;
    const props = ll.schema().properties as Record<string, Record<string, unknown>>;
    expect(props.memory_type.enum).toEqual(["episodic", "semantic", "procedural"]);
    expect(props.valid_from).toBeDefined();
    expect(props.valid_to).toBeDefined();
    expect(props.superseded_by_memory).toBeDefined();
  });

});
