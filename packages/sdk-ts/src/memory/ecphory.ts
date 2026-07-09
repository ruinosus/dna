/**
 * Deterministic ecphory — Semon's Law of Ecphory as a pure function (TS twin of
 * `dna/memory/ecphory.py`). Partial-match between a cue context and an engram's
 * encoding_context, weighted overlap, saturation/novelty/recency adjustments,
 * homophony propagation. No LLM, no kernel — the verb layer owns persistence.
 *
 * s-memory-verbs (2026-07-09).
 */
import { DEFAULT_RECALL_POLICY, RecallPolicy } from "./policy.js";

export interface EngramRef {
  name: string;
  spec: Record<string, unknown>;
}

export interface EcphoryScore {
  engram: EngramRef;
  score: number;
  matchedDims: string[];
  reasonTags: string[];
}

function tokenize(s: string): Set<string> {
  return new Set(s.toLowerCase().split(/[\s/_-]+/).filter(Boolean));
}

function withinWindow(atIso: unknown, now: number, hours: number): boolean {
  if (typeof atIso !== "string" || !atIso) return false;
  const ms = Date.parse(atIso.replace("Z", "+00:00"));
  if (Number.isNaN(ms)) return false;
  return now - ms <= hours * 3_600_000;
}

/** Partial-match score between an engram's encoding_context and a cue. */
export function scoreEngram(
  engram: EngramRef,
  cueCtx: Record<string, unknown>,
  semanticScores?: Record<string, number>,
  policy: RecallPolicy = DEFAULT_RECALL_POLICY,
): EcphoryScore {
  const spec = engram.spec;
  const ec = (spec.encoding_context as Record<string, unknown>) ?? {};
  const matched: string[] = [];
  let score = 0.0;

  const ecArea = String(ec.area ?? spec.area ?? "").trim();
  const cueArea = String(cueCtx.area_inferred ?? cueCtx.query ?? "").trim();
  const cueQ = cueArea.toLowerCase();

  // Path 1: area token overlap.
  let areaScore = 0.0;
  let areaLabel = "";
  if (ecArea && cueArea) {
    const ecTokens = tokenize(ecArea);
    const cueTokens = tokenize(cueArea);
    if (ecTokens.size && cueTokens.size) {
      const common = new Set([...ecTokens].filter((t) => cueTokens.has(t)));
      const union = new Set([...ecTokens, ...cueTokens]);
      const isSuperset = common.size === ecTokens.size || common.size === cueTokens.size;
      if (isSuperset) {
        areaScore = policy.contentWeight;
        areaLabel = "area";
      } else if (common.size) {
        const jaccard = common.size / union.size;
        areaScore = policy.contentWeight * jaccard;
        areaLabel = `area~${jaccard.toFixed(2)}`;
      }
    }
  }

  // Path 2: query phrase in summary/title/body.
  let summaryScore = 0.0;
  let summaryLabel = "";
  if (cueQ && cueQ.length >= 3) {
    const haystack = ["summary", "title", "body"]
      .map((f) => String(spec[f] ?? ""))
      .join(" ")
      .toLowerCase();
    if (haystack && haystack.includes(cueQ)) {
      summaryScore = policy.contentWeight;
      summaryLabel = "summary";
    } else if (haystack) {
      const qTokens = tokenize(cueQ);
      const contentTokens = tokenize(haystack);
      if (qTokens.size && [...qTokens].every((t) => contentTokens.has(t))) {
        summaryScore = policy.summaryPartialWeight;
        summaryLabel = "summary-tokens";
      }
    }
  }

  // Path 3: embedding cosine (only when caller feeds semanticScores).
  let semanticScore = 0.0;
  let semanticLabel = "";
  if (semanticScores) {
    const cos = Number(semanticScores[engram.name] ?? 0.0);
    if (cos > 0.0) {
      semanticScore = policy.cosineWeight * cos;
      semanticLabel = `semantic~${cos.toFixed(2)}`;
    }
  }

  const primary = Math.max(areaScore, summaryScore, semanticScore);
  if (primary > 0) {
    score += primary;
    if (primary === areaScore && areaLabel) matched.push(areaLabel);
    else if (primary === summaryScore && summaryLabel) matched.push(summaryLabel);
    else if (semanticLabel) matched.push(semanticLabel);
  }

  // co_topics jaccard.
  const ecTopics = new Set((ec.co_topics as unknown[]) ?? []);
  const cueTopics = new Set((cueCtx.co_topics as unknown[]) ?? []);
  if (ecTopics.size && cueTopics.size) {
    const overlap = new Set([...ecTopics].filter((t) => cueTopics.has(t)));
    const union = new Set([...ecTopics, ...cueTopics]);
    if (union.size) {
      score += policy.coTopicsWeight * (overlap.size / union.size);
      if (overlap.size) matched.push(`co_topics(${overlap.size})`);
    }
  }

  // source_refs distinctiveness.
  const ecRefs = new Set(((ec.source_refs ?? spec.source_refs) as unknown[]) ?? []);
  const cueRefs = new Set((cueCtx.source_refs as unknown[]) ?? []);
  if (ecRefs.size && cueRefs.size && [...ecRefs].some((r) => cueRefs.has(r))) {
    score += policy.sourceRefsWeight;
    matched.push("source_refs");
  }

  // affect mood (marginal boost).
  const ecAffect = ec.affect ?? spec.affect;
  const cueAffect = cueCtx.affect_mood;
  if (ecAffect && cueAffect && ecAffect !== "neutral" && cueAffect !== "neutral" && ecAffect === cueAffect) {
    score += policy.affectWeight;
    matched.push("affect");
  }

  // time_of_day (perceptual, marginal).
  if (ec.time_of_day && cueCtx.time_of_day && ec.time_of_day === cueCtx.time_of_day) {
    score += policy.timeWeight;
    matched.push("time");
  }

  return { engram, score, matchedDims: matched, reasonTags: [] };
}

/** Saturation / novelty / recency / high-fidelity modifiers. */
export function applySemonAdjustments(
  s: EcphoryScore,
  now: number,
  policy: RecallPolicy = DEFAULT_RECALL_POLICY,
): EcphoryScore {
  const spec = s.engram.spec;
  const cues = (spec.cues_history as unknown[]) ?? [];
  const recent24h = cues.filter(
    (c) => c && typeof c === "object" && withinWindow((c as Record<string, unknown>).at, now, 24),
  ).length;
  if (recent24h >= policy.saturationThreshold) {
    s.score *= policy.saturationDecay;
    s.reasonTags.push("saturation_decay");
  }
  if (cues.length === 0) {
    s.score += policy.noveltyBoost;
    s.reasonTags.push("novelty_boost");
  }
  if (withinWindow(spec.created_at, now, 24)) {
    s.score += policy.recencyBoost;
    s.reasonTags.push("recency_boost");
  }
  const strength = spec.confidence_score;
  if (typeof strength === "number" && strength > 1.1) {
    s.score += 0.05;
    s.reasonTags.push("high_fidelity");
  }
  return s;
}

/** Surface homophonic neighbors via `homophonic_links`. Score = direct × 0.7 × resonance. */
export function expandHomophony(
  directs: EcphoryScore[],
  engramByName: Map<string, EngramRef>,
): EcphoryScore[] {
  const homo = new Map<string, EcphoryScore>();
  for (const d of directs) {
    const links = (d.engram.spec.homophonic_links as unknown[]) ?? [];
    for (const link of links) {
      if (!link || typeof link !== "object") continue;
      const l = link as Record<string, unknown>;
      const targetName = String(l.target_name ?? l.engram_name ?? "").trim();
      if (!targetName || targetName === d.engram.name) continue;
      const target = engramByName.get(targetName);
      if (!target) continue;
      const resonance = Number(l.resonance_score ?? 0.5);
      const newScore = d.score * 0.7 * resonance;
      const existing = homo.get(targetName);
      if (!existing || newScore > existing.score) {
        homo.set(targetName, {
          engram: target,
          score: newScore,
          matchedDims: ["homophonic"],
          reasonTags: [`via=${d.engram.name}`, `basis=${l.basis ?? "co-area"}`],
        });
      }
    }
  }
  return [...homo.values()].sort((a, b) => b.score - a.score);
}
