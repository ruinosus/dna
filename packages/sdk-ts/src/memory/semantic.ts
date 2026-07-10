/**
 * Semantic recall — embedding similarity fed into the EXISTING ecphory ranking
 * (TS twin of `dna/memory/semantic.py`, s-memory-semantic-recall).
 *
 * Activates the inert semantic hook: `scoreEngram`'s Path 3 blends an embedding
 * cosine into the primary content score (`RecallPolicy.cosineWeight`), and the
 * two rankings — the recall verb's and ecphory's — are fused with the same
 * `reciprocalRankFusion` the search provider uses for its dense + lexical
 * planes. Pure: no kernel, no IO; parity is pinned by the shared
 * `memory-scoring-parity.json` fixture.
 */
import { DEFAULT_RRF_K, reciprocalRankFusion } from "../adapters/search/rrf.js";
import { applySemonAdjustments, EcphoryScore, EngramRef, scoreEngram } from "./ecphory.js";
import { DEFAULT_RECALL_POLICY, RecallPolicy } from "./policy.js";

/**
 * The spec fields that carry an engram's semantic payload — the SAME planes
 * the ecphory content paths score (`area` for Path 1; `summary`/`title`/`body`
 * for Path 2). The cue-side cosine embeds exactly this text, NOT the index's
 * full `documentText` blob: names, dates, affect labels and other metadata
 * strings would dilute the similarity without carrying meaning.
 */
export const ENGRAM_TEXT_FIELDS = ["area", "title", "summary", "body"] as const;

/** The text a memory means, for cue-side embedding (see `ENGRAM_TEXT_FIELDS`). */
export function engramText(spec: Record<string, unknown>): string {
  return ENGRAM_TEXT_FIELDS
    .filter((f) => spec[f])
    .map((f) => String(spec[f]))
    .join(" ")
    .trim();
}

/**
 * Cosine similarity between two vectors. 0.0 when either has no signal
 * (all-zero — the fake embedder's honest "no tokens" vector). Accumulation
 * order is index order, so the result is bit-identical to the Py twin.
 */
export function cosineSimilarity(a: readonly number[], b: readonly number[]): number {
  let dot = 0.0;
  let normA = 0.0;
  let normB = 0.0;
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  if (normA === 0.0 || normB === 0.0) return 0.0;
  return dot / Math.sqrt(normA) / Math.sqrt(normB);
}

/**
 * Per-name cosine against the cue vector, in the shape `scoreEngram`'s Path 3
 * consumes. Non-positive cosines are dropped (no signal, never a penalty).
 * On a duplicate name the FIRST vector wins (deterministic).
 */
export function semanticScoresFromVectors(
  names: readonly string[],
  vectors: readonly (readonly number[])[],
  queryVector: readonly number[],
): Record<string, number> {
  const scores: Record<string, number> = {};
  const n = Math.min(names.length, vectors.length);
  for (let i = 0; i < n; i++) {
    const name = names[i];
    if (name in scores) continue;
    const cos = cosineSimilarity(queryVector, vectors[i] as number[]);
    if (cos > 0.0) scores[name] = cos;
  }
  return scores;
}

/**
 * The existing ecphory ranking over candidate engrams, with the semantic hook
 * fed. `scoreEngram` (cue = the query) + Semon adjustments, gated by
 * `RecallPolicy.directThreshold`, sorted (score desc, name asc — fully
 * deterministic, Py↔TS identical). Pure — the shared parity core.
 */
export function ecphoryRank(
  engrams: readonly EngramRef[],
  query: string,
  semanticScores?: Record<string, number>,
  policy: RecallPolicy = DEFAULT_RECALL_POLICY,
  now: number = Date.now(),
): EcphoryScore[] {
  const cueCtx = { query };
  const ranked: EcphoryScore[] = [];
  for (const engram of engrams) {
    let s = scoreEngram(engram, cueCtx, semanticScores, policy);
    s = applySemonAdjustments(s, now, policy);
    if (s.score >= policy.directThreshold) ranked.push(s);
  }
  ranked.sort((x, y) => y.score - x.score || (x.engram.name < y.engram.name ? -1 : x.engram.name > y.engram.name ? 1 : 0));
  return ranked;
}

/** A recall hit as the fusion sees it — `name` + `score` plus passthrough keys. */
export interface RecallHit {
  name?: string;
  score?: number;
  [key: string]: unknown;
}

/**
 * Fuse the existing recall ranking with the semantic ecphory ranking.
 *
 * `hits` is the recall ranking (best-first); `engrams` are the same candidates
 * as `EngramRef` views. The two rank lists are fused with
 * `reciprocalRankFusion` — a candidate below the ecphory threshold keeps its
 * recall rank (one-list RRF), never disappears. Returns NEW hit objects in
 * fused order, annotated: `score` = fused RRF score, `score_recall` = the
 * pre-fusion score, `rank_recall` / `rank_ecphory` (1-based), `score_ecphory`
 * and `semantic` (cue↔memory cosine) when present. Rankings are keyed by hit
 * `name`; on a duplicate the first (best) hit wins. Pure; the caller owns
 * truncation to top-k.
 */
export function fuseSemanticRecall(
  hits: readonly RecallHit[],
  engrams: readonly EngramRef[],
  query: string,
  semanticScores: Record<string, number>,
  policy: RecallPolicy = DEFAULT_RECALL_POLICY,
  now: number = Date.now(),
  rrfK: number = DEFAULT_RRF_K,
): RecallHit[] {
  if (!hits.length) return [];
  const recallOrder: string[] = [];
  const firstByName = new Map<string, RecallHit>();
  for (const hit of hits) {
    const name = String(hit.name ?? "");
    if (!name || firstByName.has(name)) continue;
    firstByName.set(name, hit);
    recallOrder.push(name);
  }

  const directs = ecphoryRank(engrams, query, semanticScores, policy, now);
  const ecphoryOrder = directs.map((s) => s.engram.name);

  const fused = reciprocalRankFusion([recallOrder, ecphoryOrder], rrfK);
  const recallPos = new Map(recallOrder.map((name, i) => [name, i + 1]));
  const ecphoryPos = new Map(ecphoryOrder.map((name, i) => [name, i + 1]));
  const ecphoryScore = new Map(directs.map((s) => [s.engram.name, s.score]));

  const out: RecallHit[] = [];
  for (const [name, fusedScore] of fused) {
    const src = firstByName.get(name);
    if (!src) continue; // ecphory-only name — impossible when engrams ⊆ hits
    const hit: RecallHit = { ...src };
    hit.score_recall = Number(src.score ?? 0.0);
    hit.score = fusedScore;
    hit.rank_recall = recallPos.get(name);
    if (ecphoryPos.has(name)) {
      hit.rank_ecphory = ecphoryPos.get(name);
      hit.score_ecphory = ecphoryScore.get(name);
    }
    const cos = semanticScores[name] ?? 0.0;
    if (cos > 0.0) hit.semantic = cos;
    out.push(hit);
  }
  return out;
}
