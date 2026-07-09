/**
 * Recall/decay tuning knobs — pure declarative defaults (TS twin of
 * `dna/memory/policy.py`). The kernel-reading resolvers are deliberately left
 * behind (service concern); these defaults ARE the calibrated values and the
 * pure scoring functions fall back to them.
 *
 * s-memory-verbs (2026-07-09). Parity-critical numeric constants.
 */

export interface RecallPolicy {
  directThreshold: number;
  cosineWeight: number;
  contentWeight: number;
  summaryPartialWeight: number;
  coTopicsWeight: number;
  sourceRefsWeight: number;
  affectWeight: number;
  timeWeight: number;
  noveltyBoost: number;
  recencyBoost: number;
  saturationDecay: number;
  saturationThreshold: number;
  limitDirect: number;
  limitHomophonic: number;
}

export const DEFAULT_RECALL_POLICY: RecallPolicy = {
  directThreshold: 0.3,
  cosineWeight: 0.61,
  contentWeight: 0.55,
  summaryPartialWeight: 0.28,
  coTopicsWeight: 0.2,
  sourceRefsWeight: 0.15,
  affectWeight: 0.05,
  timeWeight: 0.05,
  noveltyBoost: 0.05,
  recencyBoost: 0.1,
  saturationDecay: 0.6,
  saturationThreshold: 3,
  limitDirect: 8,
  limitHomophonic: 6,
};

export interface DecayPolicy {
  tierFaint: number;
  tierFirm: number;
  tierBurning: number;
  defaultStabilityDays: number;
  maxStabilityDays: number;
  relevanceDecaySeed: number;
}

export const DEFAULT_DECAY_POLICY: DecayPolicy = {
  tierFaint: 5.0,
  tierFirm: 15.0,
  tierBurning: 45.0,
  defaultStabilityDays: 15.0,
  maxStabilityDays: 60.0,
  relevanceDecaySeed: 0.95,
};

export function decayTiers(policy: DecayPolicy = DEFAULT_DECAY_POLICY): Record<string, number> {
  return { faint: policy.tierFaint, firm: policy.tierFirm, burning: policy.tierBurning };
}
