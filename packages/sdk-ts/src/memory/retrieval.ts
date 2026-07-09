/**
 * BM25 memory ranking — the pure lexical scoring core (TS twin of
 * `dna/memory/retrieval.py`). Bit-identical arithmetic to Python:
 *
 *   final = base_bm25 × recency_decay × affect_weight × surface_damp × confidence
 *
 * s-memory-verbs (2026-07-09).
 */
import { confidenceScoreNumeric } from "./decay.js";

const AFFECT_WEIGHTS: Record<string, number> = {
  triumph: 1.2,
  regret: 1.3,
  surprise: 1.5,
  wistful: 1.0,
  ominous: 1.4,
};
const BM25_K1 = 1.5;
const BM25_B = 0.75;
const RECENCY_HALFLIFE_DAYS = 30.0;
const SURFACE_DAMP_K = 0.1;
const PARTIAL_PREFIX_FLOOR = 0.05;
const PARTIAL_MIN_PREFIX_LEN = 3;

export interface Memory {
  name: string;
  spec: Record<string, unknown>;
}

export interface RankedMemory {
  name: string;
  score: number;
  factors: Record<string, number | boolean>;
}

export function tokenize(text: string): string[] {
  return text.toLowerCase().match(/[a-z0-9]+/g) ?? [];
}

function docText(spec: Record<string, unknown>): string {
  return `${spec.area ?? ""} ${spec.summary ?? ""}`;
}

export function bm25Score(
  queryTokens: string[],
  docTokens: string[],
  docLengths: number[],
  idf: Map<string, number>,
): number {
  if (docTokens.length === 0) return 0.0;
  const avgDl = docLengths.length ? docLengths.reduce((a, b) => a + b, 0) / docLengths.length : 0.0;
  if (avgDl === 0.0) return 0.0;
  const dl = docTokens.length;
  const tf = new Map<string, number>();
  for (const t of docTokens) tf.set(t, (tf.get(t) ?? 0) + 1);
  let score = 0.0;
  for (const term of queryTokens) {
    const termIdf = idf.get(term);
    if (termIdf === undefined) continue;
    const f = tf.get(term) ?? 0;
    if (f === 0) continue;
    const num = f * (BM25_K1 + 1);
    const den = f + BM25_K1 * (1 - BM25_B + (BM25_B * dl) / avgDl);
    score += termIdf * (num / den);
  }
  return score;
}

export function buildIdf(corpusTokens: string[][]): Map<string, number> {
  const n = corpusTokens.length;
  const df = new Map<string, number>();
  for (const tokens of corpusTokens) {
    for (const term of new Set(tokens)) df.set(term, (df.get(term) ?? 0) + 1);
  }
  const idf = new Map<string, number>();
  for (const [term, count] of df) {
    idf.set(term, Math.log((n - count + 0.5) / (count + 0.5) + 1));
  }
  return idf;
}

export function recencyFactor(lastSurfaced: unknown, now: number): number {
  if (!lastSurfaced || typeof lastSurfaced !== "string") return 1.0;
  const ms = Date.parse(lastSurfaced.replace("Z", "+00:00"));
  if (Number.isNaN(ms)) return 1.0;
  const deltaDays = (now - ms) / 86_400_000;
  if (deltaDays <= 0) return 1.0;
  return Math.exp(-deltaDays / RECENCY_HALFLIFE_DAYS);
}

export function affectFactor(affect: unknown): number {
  return AFFECT_WEIGHTS[String(affect ?? "")] ?? 1.0;
}

export function surfaceDamp(count: unknown): number {
  const n = typeof count === "number" ? count : 0;
  return 1.0 / (1.0 + n * SURFACE_DAMP_K);
}

function hasPrefixOverlap(queryTokens: string[], docTokens: string[]): boolean {
  const q = queryTokens.filter((t) => t.length >= PARTIAL_MIN_PREFIX_LEN);
  const d = docTokens.filter((t) => t.length >= PARTIAL_MIN_PREFIX_LEN);
  for (const qt of q) {
    for (const dt of d) {
      if (qt === dt) continue;
      const n = Math.min(qt.length, dt.length);
      let i = 0;
      while (i < n && qt[i] === dt[i]) i += 1;
      if (i >= PARTIAL_MIN_PREFIX_LEN) return true;
    }
  }
  return false;
}

/** Rank memories by `bm25 × recency × affect × surface_damp × confidence`. Pure. */
export function rankMemories(
  memories: Memory[],
  query: string,
  opts: { now?: number; limit?: number; partial?: boolean } = {},
): RankedMemory[] {
  const { now = Date.now(), limit = 5, partial = false } = opts;
  const queryTokens = tokenize(query);
  const corpusTokens = memories.map((m) => tokenize(docText(m.spec)));
  const ranked: RankedMemory[] = [];
  if (queryTokens.length && memories.length) {
    const docLengths = corpusTokens.map((t) => t.length);
    const idf = buildIdf(corpusTokens);
    memories.forEach((mem, i) => {
      const tokens = corpusTokens[i]!;
      let base = bm25Score(queryTokens, tokens, docLengths, idf);
      let partialMatch = false;
      if (base <= 0.0) {
        if (!partial || !hasPrefixOverlap(queryTokens, tokens)) return;
        base = PARTIAL_PREFIX_FLOOR;
        partialMatch = true;
      }
      const spec = mem.spec ?? {};
      const rec = recencyFactor(spec.last_surfaced, now);
      const aff = affectFactor(spec.affect);
      const damp = surfaceDamp(spec.surface_count);
      const conf = confidenceScoreNumeric(spec);
      ranked.push({
        name: mem.name,
        score: base * rec * aff * damp * conf,
        factors: {
          base,
          recency: rec,
          affect: aff,
          surface_damp: damp,
          confidence_score: conf,
          partial_match: partialMatch,
        },
      });
    });
  }
  ranked.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return a.name < b.name ? -1 : a.name > b.name ? 1 : 0;
  });
  return ranked.slice(0, limit);
}
