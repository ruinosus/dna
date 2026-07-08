/**
 * T1 (TS twin) — schema parity for Cognitive Memory Triad.
 *
 * Mirrors python/tests/test_cognitive_kinds.py. The enums and required
 * field sets MUST match Py byte-for-byte — Cross-Stack Parity oracle
 * verifies version + Kind set parity; this test pins the fields the Py
 * tests check. Current SdlcExtension version is 1.13.0 (s-kaizen-kind).
 */
import { describe, it, expect } from "bun:test";
import { Kernel } from "../src/kernel/index.js";
import { SdlcExtension } from "../src/extensions/sdlc.js";
// F3 lote-1/lote-2: the enum const exports (REMEMBRANCE_*, DREAM_*,
// FORGETTING_*) died with the classes — the enums now live ONLY in the
// kinds/*.kind.yaml descriptors; assertions below read them from the
// synthesized port's schema (the single source).

type KindKey = "LessonLearned" | "SynthesisRun" | "ArchiveProposal" | "Forecast";

function getKind(k: Kernel, name: KindKey) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return ((k as any)._kinds as Map<string, {
    alias: string;
    storage: { pattern: { value?: string } | string; container?: string; marker?: string };
    schema: () => Record<string, unknown>;
    displayLabel: string;
  }>).get(`github.com/ruinosus/dna/sdlc/v1\0${name}`)!;
}

describe("Cognitive Memory Triad — TS parity", () => {
  it("declares a semver version", () => {
    // Anchor: SdlcExtension introduced Cognitive Memory Triad at
    // 1.9.0 and has bumped since. Lock to the current literal so a
    // regression below 1.13.0 is caught — bump both when releasing.
    expect(new SdlcExtension().version).toBe("1.14.0");
  });

  it("LessonLearned: alias + storage + display label", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    const kp = getKind(k, "LessonLearned");
    expect(kp.alias).toBe("sdlc-lesson-learned");
    const sd = kp.storage;
    expect(typeof sd.pattern === "string" ? sd.pattern : sd.pattern.value).toBe("bundle");
    expect(sd.container).toBe("lessons-learned");
    expect(sd.marker).toBe("LESSON_LEARNED.md");
    // enterprise pt-BR (PMBOK 'Lessons Learned'); s-sdlcv2-memorias-market-viz
    expect(kp.displayLabel).toBe("Lições Aprendidas");
  });

  it("SynthesisRun: alias + storage + display label", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    const kp = getKind(k, "SynthesisRun");
    expect(kp.alias).toBe("sdlc-synthesis-run");
    const sd = kp.storage;
    expect(typeof sd.pattern === "string" ? sd.pattern : sd.pattern.value).toBe("bundle");
    expect(sd.container).toBe("synthesis-runs");
    expect(sd.marker).toBe("SYNTHESIS_RUN.md");
    expect(kp.displayLabel).toBe("Sínteses");
  });

  it("ArchiveProposal: alias + storage + display label", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    const kp = getKind(k, "ArchiveProposal");
    expect(kp.alias).toBe("sdlc-archive-proposal");
    const sd = kp.storage;
    expect(typeof sd.pattern === "string" ? sd.pattern : sd.pattern.value).toBe("bundle");
    expect(sd.container).toBe("archive-proposals");
    expect(sd.marker).toBe("ARCHIVE_PROPOSAL.md");
    expect(kp.displayLabel).toBe("Arquivamento");
  });

  // ---- enums (must match Py byte-for-byte) -----------------------------

  it("LessonLearned: affect enum is evocative palette (parity with Py)", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    const props = getKind(k, "LessonLearned").schema()
      .properties as Record<string, { enum?: string[] }>;
    expect(new Set(props.affect.enum)).toEqual(
      new Set(["triumph", "regret", "surprise", "wistful", "ominous"]),
    );
  });

  it("LessonLearned: surface_when triggers (parity with Py)", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    const props = getKind(k, "LessonLearned").schema()
      .properties as Record<string, { items?: { enum?: string[] } }>;
    expect(new Set(props.surface_when.items?.enum)).toEqual(
      new Set(["feature_touched", "cycle_open", "session_start", "oracle_consult"]),
    );
  });

  it("LessonLearned: descriptor carries affect_reason/affect_evidence_refs (drift vs old TS class CURED)", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    const props = getKind(k, "LessonLearned").schema()
      .properties as Record<string, unknown>;
    expect(props.affect_reason).toBeDefined();
    expect(props.affect_evidence_refs).toBeDefined();
  });

  // F3 lote-2 NOTE (drift CURED): the old TS SynthesisRunKind still carried
  // the PRE-redesign predictive shape (timeframe/status/would_change). The
  // canonical (Py) surface moved that to Forecast in s-dream-redesign; the
  // byte-identical descriptors unify TS on the canonical shape — TS gains
  // the Forecast kind for free (was Py-only).
  it("Forecast: timeframes + status lifecycle (parity with Py — read from descriptor schema)", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    const props = getKind(k, "Forecast").schema()
      .properties as Record<string, { enum?: string[] }>;
    expect(new Set(props.timeframe.enum)).toEqual(
      new Set(["in-7d", "in-30d", "in-90d", "in-1y"]),
    );
    expect(new Set(props.status.enum)).toEqual(
      new Set(["drafted", "observing", "fulfilled", "refuted", "expired"]),
    );
  });

  it("SynthesisRun: oneiric affect enum (no predictive fields — drift cured)", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    const props = getKind(k, "SynthesisRun").schema()
      .properties as Record<string, { enum?: string[] }>;
    expect(new Set(props.affect.enum)).toEqual(
      new Set(["anxiety", "longing", "triumph", "eerie", "vertigo",
               "wistful", "ominous", "dread", "wonder"]),
    );
    expect(props.timeframe).toBeUndefined();
    expect(props.would_change).toBeUndefined();
  });

  it("ArchiveProposal: reason enum (parity with Py — read from descriptor schema)", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    const props = getKind(k, "ArchiveProposal").schema()
      .properties as Record<string, { enum?: string[] }>;
    expect(new Set(props.reason.enum)).toEqual(
      new Set(["orphan", "superseded", "stale", "contradicted", "duplicate"]),
    );
  });

  it("ArchiveProposal: status lifecycle (parity with Py — read from descriptor schema)", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    const props = getKind(k, "ArchiveProposal").schema()
      .properties as Record<string, { enum?: string[] }>;
    expect(new Set(props.status.enum)).toEqual(
      new Set(["proposed", "approved", "vetoed", "executed"]),
    );
  });

  // ---- required fields per Kind ----------------------------------------

  it("LessonLearned: required fields match Py", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    const schema = getKind(k, "LessonLearned").schema();
    expect(new Set(schema.required as string[])).toEqual(
      new Set(["area", "surface_when", "source_refs", "affect", "summary"]),
    );
  });

  it("SynthesisRun: required fields match Py (canonical oneiric shape)", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    const schema = getKind(k, "SynthesisRun").schema();
    expect(new Set(schema.required as string[])).toEqual(
      new Set(["dreamer", "affect", "symbol", "scenario", "fragments"]),
    );
  });

  it("ArchiveProposal: required fields match Py", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    const schema = getKind(k, "ArchiveProposal").schema();
    expect(new Set(schema.required as string[])).toEqual(
      new Set([
        "target_kind", "target_name", "reason", "evidence",
        "proposed_by", "status", "review_deadline",
      ]),
    );
  });

  it("SynthesisRun: no kind_of field in v1 (Spec §15 decision)", () => {
    const k = new Kernel();
    k.load(new SdlcExtension());
    const schema = getKind(k, "SynthesisRun").schema();
    const props = schema.properties as Record<string, unknown>;
    expect(props.kind_of).toBeUndefined();
  });
});
