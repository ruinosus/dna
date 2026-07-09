/**
 * Reciprocal Rank Fusion — the pure, deterministic hybrid-fusion core.
 *
 * TypeScript twin of `dna/adapters/search/rrf.py`. RRF (Cormack et al. 2009)
 * fuses several independently-ranked lists using only each item's RANK within
 * each list — never the raw scores, which are incomparable across a cosine
 * dense list and a BM25 lexical list. Each item accrues `1 / (k + rank)` (rank
 * 1-based) from every list it appears in; items are ordered by descending fused
 * score, ties broken by id ascending — fully deterministic and bit-identical to
 * the Python implementation.
 */

/** RRF smoothing constant (the paper's value; the de-facto default). */
export const DEFAULT_RRF_K = 60;

/**
 * Fuse ranked id-lists into one ranking via Reciprocal Rank Fusion.
 *
 * @param rankedLists each inner array is item ids in rank order (best first).
 *   An id may appear across lists; duplicates WITHIN one list count at their
 *   first (best) rank only.
 * @param k RRF smoothing constant (`DEFAULT_RRF_K`); must be > 0.
 * @returns `[id, fusedScore]` pairs sorted by fused score desc, ties by id asc.
 */
export function reciprocalRankFusion(
  rankedLists: string[][],
  k: number = DEFAULT_RRF_K,
): Array<[string, number]> {
  if (k <= 0) throw new Error(`RRF k must be positive, got ${k}`);
  const scores = new Map<string, number>();
  for (const ranked of rankedLists) {
    const seen = new Set<string>();
    ranked.forEach((docId, i) => {
      if (seen.has(docId)) return; // first (best) rank wins for a repeated id
      seen.add(docId);
      const rank = i + 1;
      scores.set(docId, (scores.get(docId) ?? 0) + 1 / (k + rank));
    });
  }
  return [...scores.entries()].sort((a, b) => {
    if (b[1] !== a[1]) return b[1] - a[1]; // score desc
    return a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0; // id asc
  });
}
