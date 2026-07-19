/**
 * Memory-scoring conformance kit (TS twin of the pure half of
 * `dna/testing/memory_conformance.py`, s-memory-conformance-kit).
 *
 * The behavioral contract of the deterministic memory-scoring core — ecphory
 * weights + threshold, deterministic ordering, the semantic hook, RRF fusion,
 * Ebbinghaus decay, bi-temporal fail-open. Twinned 1:1 with the Python
 * `memory_scoring_conformance_suite`: SAME case names, SAME assertions — the
 * kit itself is a parity artifact. For anyone evolving the scoring (a public
 * regression pin) or shipping a custom embedder (the two embedder-driven
 * cases assert RELATIVE similarity, search-kit style, so a real model passes
 * too).
 *
 * The kernel-bound memory VERB suite (`memory_conformance_suite`) has no TS
 * twin by design: the verbs (remember/recall/forget/consolidate) are Py-only
 * by the SDK's declared boundary — TypeScript ships the pure scoring core
 * only.
 *
 * A `factory` is an async zero-arg callable returning `{ embedder, cleanup }`
 * where `embedder` exposes async `embed(texts) -> vectors` (an
 * `EmbeddingPort` works as-is). Omit it to run against the deterministic
 * fake floor — fully offline. Note that `semantic_hook_lifts_paraphrase`
 * honestly requires the embedder to score an easy paraphrase above the
 * ecphory gate (`cos >= (directThreshold - noveltyBoost) / cosineWeight`
 * ~ 0.41) — an embedder that can't clear it cannot power semantic recall.
 */
import { fakeEmbedOne } from "../kernel/embedding.js";
import {
  currentlyValid,
  ebbinghausRetention,
  recallBump,
} from "../memory/decay.js";
import type { EngramRef } from "../memory/ecphory.js";
import {
  DEFAULT_DECAY_POLICY,
  DEFAULT_RECALL_POLICY,
} from "../memory/policy.js";
import {
  cosineSimilarity,
  ecphoryRank,
  engramText,
  fuseSemanticRecall,
  semanticScoresFromVectors,
} from "../memory/semantic.js";

/** An embedder, structurally: async texts → vectors. */
export interface ConformanceEmbedder {
  embed(texts: string[]): Promise<number[][]>;
}

export type EmbedderFactory = () => Promise<{
  embedder: ConformanceEmbedder;
  cleanup?: () => void | Promise<void>;
}>;

type EmbedFn = (texts: string[]) => Promise<number[][]>;

/** Simulated clock anchor — the kit never reads the wall clock. */
export const KIT_NOW = Date.UTC(2026, 6, 10, 12, 0, 0);
const CREATED_AT = "2026-07-01T00:00:00+00:00";

class SkipCase extends Error {}

function assert(cond: unknown, msg: string): void {
  if (!cond) throw new Error(msg);
}

async function defaultEmbed(texts: string[]): Promise<number[][]> {
  return texts.map((t) => fakeEmbedOne(t));
}

const PARAPHRASE_QUERY = "mutating documents safely";

/**
 * Target/decoy pair: the query is a PARAPHRASE of the target (no shared
 * phrase, no token-subset — the cue-match paths score it 0 + novelty) and
 * unrelated to the decoy. Never-recalled engrams, so Semon's novelty boost
 * applies to both equally (the decoy still stays under the gate).
 */
function paraphraseEngrams(): EngramRef[] {
  return [
    { name: "rem-target", spec: {
      area: "Feature/kernel",
      summary: "deep-copy before mutating documents",
      created_at: CREATED_AT,
    } },
    { name: "rem-decoy", spec: {
      area: "Feature/ops",
      summary: "safely archive old reports nightly",
      created_at: CREATED_AT,
    } },
  ];
}

// ---------------------------------------------------------------------------
// cases — names + assertions twinned with the Python scoring suite
// ---------------------------------------------------------------------------

async function cosineTracksSimilarity(embed: EmbedFn): Promise<void> {
  const texts = [
    "deep copy before mutating documents",
    "mutating documents safely",
    "banana tropical smoothie breakfast",
  ];
  const vecs = await embed(texts);
  const again = await embed([texts[0]!]);
  const selfCos = cosineSimilarity(vecs[0]!, again[0]!);
  assert(selfCos > 1.0 - 1e-6, `identical text must be maximally similar, got ${selfCos}`);
  const para = cosineSimilarity(vecs[0]!, vecs[1]!);
  const unrelated = cosineSimilarity(vecs[0]!, vecs[2]!);
  assert(para > unrelated,
    `paraphrase must be closer than unrelated text: ${para} !> ${unrelated}`);
}

async function ecphoryWeightsAndThreshold(_embed: EmbedFn): Promise<void> {
  const pol = DEFAULT_RECALL_POLICY;
  const oldCue = [{ at: "2020-01-01T00:00:00+00:00", cue: "old", actor: "kit" }];
  const eArea: EngramRef = { name: "rem-area", spec: {
    area: "kernel cache mutation", summary: "",
    created_at: CREATED_AT, cues_history: oldCue,
  } };
  const eSem: EngramRef = { name: "rem-sem", spec: {
    area: "Feature/elsewhere", summary: "totally unrelated words entirely",
    created_at: CREATED_AT, cues_history: oldCue,
  } };
  const eBelow: EngramRef = { name: "rem-below", spec: {
    area: "Feature/nowhere", summary: "different disjoint vocabulary again",
    created_at: CREATED_AT, cues_history: oldCue,
  } };
  const sem = { "rem-sem": 0.8, "rem-below": 0.4 };
  const ranked = ecphoryRank(
    [eArea, eSem, eBelow], "kernel cache mutation", sem, pol, KIT_NOW,
  );
  const byName = new Map(ranked.map((s) => [s.engram.name, s]));
  assert(
    byName.size === 2 && byName.has("rem-area") && byName.has("rem-sem"),
    `0.61×0.4 < directThreshold must gate rem-below out, got ${[...byName.keys()].sort().join(",")}`,
  );
  const area = byName.get("rem-area")!;
  assert(Math.abs(area.score - pol.contentWeight) < 1e-9,
    `exact area match must score contentWeight, got ${area.score}`);
  assert(area.matchedDims[0] === "area", `expected 'area', got ${area.matchedDims[0]}`);
  const semHit = byName.get("rem-sem")!;
  assert(Math.abs(semHit.score - pol.cosineWeight * 0.8) < 1e-9,
    `Path 3 must blend cosineWeight × cos, got ${semHit.score}`);
  assert(semHit.matchedDims[0]!.startsWith("semantic~"),
    `expected semantic~ label, got ${semHit.matchedDims[0]}`);
}

async function ecphoryDeterministicOrdering(_embed: EmbedFn): Promise<void> {
  const oldCue = [{ at: "2020-01-01T00:00:00+00:00", cue: "old", actor: "kit" }];
  const spec = {
    area: "kernel cache mutation", summary: "",
    created_at: CREATED_AT, cues_history: oldCue,
  };
  const engrams: EngramRef[] = [
    { name: "rem-b", spec: { ...spec } },
    { name: "rem-a", spec: { ...spec } },
  ];
  const first = ecphoryRank(engrams, "kernel cache mutation", undefined,
    DEFAULT_RECALL_POLICY, KIT_NOW);
  assert(
    first.map((s) => s.engram.name).join(",") === "rem-a,rem-b",
    "equal scores must order by name ascending",
  );
  const second = ecphoryRank(engrams, "kernel cache mutation", undefined,
    DEFAULT_RECALL_POLICY, KIT_NOW);
  assert(
    JSON.stringify(first.map((s) => [s.engram.name, s.score])) ===
      JSON.stringify(second.map((s) => [s.engram.name, s.score])),
    "rerun must be identical",
  );
}

async function semanticHookLiftsParaphrase(embed: EmbedFn): Promise<void> {
  const engrams = paraphraseEngrams();
  const without = ecphoryRank(engrams, PARAPHRASE_QUERY, undefined,
    DEFAULT_RECALL_POLICY, KIT_NOW);
  assert(without.length === 0,
    "the cue-match paths must NOT find a paraphrase on their own");
  const vecs = await embed(
    [PARAPHRASE_QUERY, ...engrams.map((e) => engramText(e.spec))],
  );
  const sem = semanticScoresFromVectors(
    engrams.map((e) => e.name), vecs.slice(1), vecs[0]!,
  );
  const ranked = ecphoryRank(engrams, PARAPHRASE_QUERY, sem,
    DEFAULT_RECALL_POLICY, KIT_NOW);
  const names = ranked.map((s) => s.engram.name);
  assert(names.includes("rem-target"),
    `the embedder's paraphrase similarity must lift the target over the ` +
    `ecphory threshold (cos×${DEFAULT_RECALL_POLICY.cosineWeight} + novelty ≥ ` +
    `${DEFAULT_RECALL_POLICY.directThreshold}); got [${names.join(",")}] ` +
    `from cosines ${JSON.stringify(sem)}`);
  if (names.includes("rem-decoy")) {
    assert(names.indexOf("rem-target") < names.indexOf("rem-decoy"),
      `the paraphrase target must outrank the decoy: ${names.join(",")}`);
  }
}

async function fusionPreservesAndAnnotates(_embed: EmbedFn): Promise<void> {
  const engrams = paraphraseEngrams();
  const hits = [
    { kind: "Engram", name: "rem-decoy", score: 0.048 },
    { kind: "Engram", name: "rem-target", score: 0.033 },
  ];
  const sem = { "rem-target": 0.9 };
  const fused = fuseSemanticRecall(hits, engrams, PARAPHRASE_QUERY, sem,
    DEFAULT_RECALL_POLICY, KIT_NOW);
  assert(
    fused.map((h) => h.name).join(",") === "rem-target,rem-decoy",
    `fusion must promote the semantic match, got ${fused.map((h) => h.name).join(",")}`,
  );
  const [target, decoy] = fused as [Record<string, unknown>, Record<string, unknown>];
  // RRF (k=60): target = 1/(60+2) [recall #2] + 1/(60+1) [ecphory #1].
  assert(Math.abs((target.score as number) - (1 / 62 + 1 / 61)) < 1e-12,
    `fused score must be the reciprocal-rank sum, got ${target.score}`);
  assert(target.rank_recall === 2 && target.rank_ecphory === 1,
    `expected ranks (2, 1), got (${target.rank_recall}, ${target.rank_ecphory})`);
  assert(Math.abs((target.score_recall as number) - 0.033) < 1e-12,
    "score_recall must preserve the pre-fusion score");
  assert(Math.abs((target.semantic as number) - 0.9) < 1e-12,
    "the cue↔memory cosine must be annotated");
  // The decoy is under the ecphory gate: recall rank only, never dropped.
  assert(Math.abs((decoy.score as number) - 1 / 61) < 1e-12,
    `one-list RRF must keep the below-threshold hit, got ${decoy.score}`);
  assert(decoy.rank_recall === 1 && !("rank_ecphory" in decoy),
    "the below-threshold hit rides its recall rank only");
  assert(
    fuseSemanticRecall([], engrams, PARAPHRASE_QUERY, sem,
      DEFAULT_RECALL_POLICY, KIT_NOW).length === 0,
    "empty hits fuse to empty",
  );
}

async function decayRetentionMonotonic(_embed: EmbedFn): Promise<void> {
  assert(ebbinghausRetention(10.0, null) === 1.0, "never recalled → R = 1");
  assert(ebbinghausRetention(10.0, 0.0) === 1.0, "just recalled → R = 1");
  const [r1, r5, r50] = [1.0, 5.0, 50.0].map((d) => ebbinghausRetention(10.0, d));
  assert(1.0 > r1! && r1! > r5! && r5! > r50! && r50! > 0.0,
    `retention must decay monotonically: ${[r1, r5, r50].join(", ")}`);
  const cap = DEFAULT_DECAY_POLICY.maxStabilityDays;
  assert(recallBump(cap - 1.0, 0.001) <= cap, "the spacing bump must respect the cap");
  assert(recallBump(10.0, 1.0) > 10.0, "a recall must strengthen the engram");
}

async function bitemporalFailOpen(_embed: EmbedFn): Promise<void> {
  assert(currentlyValid(null, KIT_NOW) === true, "unset valid_to → valid");
  assert(currentlyValid("", KIT_NOW) === true, "empty valid_to → valid");
  assert(currentlyValid("2026-07-09T00:00:00+00:00", KIT_NOW) === false,
    "past valid_to → invalid");
  assert(currentlyValid("2026-07-11T00:00:00+00:00", KIT_NOW) === true,
    "future valid_to → valid");
  assert(currentlyValid("not-a-timestamp", KIT_NOW) === true,
    "unparseable valid_to must NEVER hide a memory (fail-open)");
}

const CASES: Array<{ name: string; requires: string; fn: (embed: EmbedFn) => Promise<void> }> = [
  { name: "cosine_tracks_similarity", requires: "embedder", fn: cosineTracksSimilarity },
  { name: "ecphory_weights_and_threshold", requires: "pure", fn: ecphoryWeightsAndThreshold },
  { name: "ecphory_deterministic_ordering", requires: "pure", fn: ecphoryDeterministicOrdering },
  { name: "semantic_hook_lifts_paraphrase", requires: "embedder", fn: semanticHookLiftsParaphrase },
  { name: "fusion_preserves_and_annotates", requires: "pure", fn: fusionPreservesAndAnnotates },
  { name: "decay_retention_monotonic", requires: "pure", fn: decayRetentionMonotonic },
  { name: "bitemporal_fail_open", requires: "pure", fn: bitemporalFailOpen },
];

export interface MemoryScoringCase {
  name: string;
  requires: string;
  run(): Promise<void>;
}

/**
 * THE public conformance suite for the pure memory-scoring core.
 *
 * @param factory optional async factory returning `{ embedder, cleanup }`;
 *   omit to run against the deterministic fake floor (fully offline).
 * @returns one runnable case per invariant — feed them to your test runner
 *   and `await case.run()`.
 */
export function memoryScoringConformanceSuite(
  factory?: EmbedderFactory,
): MemoryScoringCase[] {
  return CASES.map(({ name, requires, fn }) => ({
    name,
    requires,
    async run(): Promise<void> {
      if (!factory) {
        await fn(defaultEmbed);
        return;
      }
      const { embedder, cleanup } = await factory();
      try {
        await fn((texts) => embedder.embed(texts));
      } finally {
        if (cleanup) await cleanup();
      }
    },
  }));
}

export { SkipCase as MemoryCaseNotApplicable };
