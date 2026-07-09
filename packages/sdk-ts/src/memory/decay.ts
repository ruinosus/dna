/**
 * Ebbinghaus forgetting curve + bi-temporal validity — pure math (TS twin of
 * `dna/memory/decay.py`). R(t) = e^(-t/S). Bit-identical arithmetic to Python.
 *
 * s-memory-verbs (2026-07-09).
 */
import { DEFAULT_DECAY_POLICY, DecayPolicy, decayTiers } from "./policy.js";

type Spec = Record<string, unknown> | null | undefined;

function parseIso(ts: unknown): number | null {
  if (typeof ts !== "string" || !ts) return null;
  const ms = Date.parse(ts.replace("Z", "+00:00"));
  return Number.isNaN(ms) ? null : ms;
}

/** `confidence_score` → number. Numeric passthrough or tier (faint=1, firm=3, burning=5). */
export function confidenceScoreNumeric(spec: Spec, def = 1.0): number {
  if (!spec || typeof spec !== "object") return def;
  const raw = (spec as Record<string, unknown>).confidence_score;
  if (raw == null) return def;
  if (typeof raw === "number") return raw;
  if (typeof raw === "string") {
    const map: Record<string, number> = { faint: 1.0, firm: 3.0, burning: 5.0 };
    return map[raw.toLowerCase()] ?? def;
  }
  return def;
}

/** Resolve stability (days) from a memory spec — explicit → tier → legacy numeric → default. */
export function stabilityFromSpec(spec: Spec, policy: DecayPolicy = DEFAULT_DECAY_POLICY): number {
  const tiers = decayTiers(policy);
  if (!spec || typeof spec !== "object" || Object.keys(spec).length === 0) {
    return policy.defaultStabilityDays;
  }
  const s = spec as Record<string, unknown>;
  const explicit = s.engram_stability_days;
  if (typeof explicit === "number" && explicit > 0) return explicit;
  const strength = s.confidence_score;
  if (typeof strength === "string") {
    return tiers[strength.toLowerCase()] ?? policy.defaultStabilityDays;
  }
  if (typeof strength === "number") {
    const v = strength;
    if (v <= 1.0) return tiers.faint!;
    if (v <= 5.0) return tiers.faint! + ((v - 1.0) / 4.0) * (tiers.firm! - tiers.faint!);
    if (v <= 10.0) return tiers.firm! + ((v - 5.0) / 5.0) * (tiers.burning! - tiers.firm!);
    return tiers.burning!;
  }
  return policy.defaultStabilityDays;
}

/** Days elapsed since `ts` (ISO). null on unparseable input. `now` in epoch ms. */
export function daysSince(ts: unknown, now: number = Date.now()): number | null {
  const ms = parseIso(ts);
  if (ms === null) return null;
  return Math.max((now - ms) / 86_400_000, 0.0);
}

/** R(t) = e^(-t/S). 1.0 when never recalled (`daysSinceRecall` null/≤0). */
export function ebbinghausRetention(stabilityDays: number, daysSinceRecall: number | null): number {
  if (daysSinceRecall === null || daysSinceRecall <= 0) return 1.0;
  const s = Math.max(0.1, stabilityDays);
  return Math.exp(-daysSinceRecall / s);
}

/** Spacing-effect bump: S_new = S_old × (1 + 0.5 × R(t)); capped. */
export function recallBump(
  currentStability: number,
  daysSinceRecall: number | null,
  policy: DecayPolicy = DEFAULT_DECAY_POLICY,
): number {
  const s = Math.max(0.1, currentStability);
  const r = ebbinghausRetention(s, daysSinceRecall);
  return Math.min(s * (1.0 + 0.5 * r), policy.maxStabilityDays);
}

/** Multiply a ranking score by current retention. Returns `[adjusted, retention]`. */
export function decayAdjustedScore(
  baseScore: number,
  spec: Spec,
  opts: { floor?: number; now?: number; policy?: DecayPolicy } = {},
): [number, number] {
  const { floor = 0.05, now = Date.now(), policy = DEFAULT_DECAY_POLICY } = opts;
  const s = stabilityFromSpec(spec, policy);
  const last = (spec as Record<string, unknown> | null)?.last_surfaced
    ?? (spec as Record<string, unknown> | null)?.last_recall_at;
  const days = daysSince(last, now);
  const retention = ebbinghausRetention(s, days);
  return [baseScore * Math.max(floor, retention), retention];
}

/**
 * Bi-temporal filter (Zep valid_from/valid_to). True when the memory is still
 * current — `valid_to` unset OR in the future. A memory invalidated in the past
 * never surfaces. Unparseable `valid_to` fails OPEN (never hide on a bad stamp).
 */
export function currentlyValid(validTo: unknown, now: number = Date.now()): boolean {
  if (!validTo) return true;
  const ms = parseIso(validTo);
  if (ms === null) return true;
  return ms > now;
}
