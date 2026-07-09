/**
 * Deterministic encoding_context stamping — the engraphy conditions snapshot
 * (TS twin of `dna/memory/encoding_context.py`). Encoding-specificity (Semon
 * 1904): conditions at engraphy must be partially reinstated at ecphory.
 *
 * s-memory-verbs (2026-07-09).
 */

type Spec = Record<string, unknown>;

/** Map an hour to {morning, afternoon, evening, night}. */
export function timeOfDay(hour: number): string {
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 18) return "afternoon";
  if (hour >= 18 && hour < 22) return "evening";
  return "night";
}

function hourOfIso(value: unknown): number | null {
  if (typeof value !== "string" || !value) return null;
  const ms = Date.parse(value.replace("Z", "+00:00"));
  if (Number.isNaN(ms)) return null;
  return new Date(ms).getUTCHours();
}

/** Build a deterministic encoding_context from the spec. Fresh object. */
export function deriveEncodingContext(
  spec: Spec,
  opts: { ambient?: Record<string, unknown>; derivedMarker?: string } = {},
): Record<string, unknown> {
  const ambient = opts.ambient ?? {};
  const derivedMarker = opts.derivedMarker ?? "verb-autostamp";

  const hour = hourOfIso(spec.created_at) ?? new Date().getUTCHours();
  const tod = (ambient.time_of_day as string) || timeOfDay(hour);

  const specTags = ((spec.tags as unknown[]) ?? [])
    .filter((t) => typeof t === "string" || typeof t === "number")
    .map((t) => String(t));
  const ambientTopics = ((ambient.recent_turn_topics as unknown[]) ?? [])
    .filter((t) => typeof t === "string" || typeof t === "number")
    .map((t) => String(t));
  const seen: string[] = [];
  for (const t of [...specTags, ...ambientTopics]) {
    if (t && !seen.includes(t)) seen.push(t);
    if (seen.length >= 5) break;
  }

  return {
    area: spec.area ?? "",
    affect: ambient.affect ?? spec.affect ?? "neutral",
    time_of_day: tod,
    co_topics: seen,
    source_refs: [...((spec.source_refs as unknown[]) ?? [])],
    _derived: derivedMarker,
  };
}

/** Mutate `spec` in place: add encoding_context if missing/empty. Idempotent. */
export function stampEncodingContextIfAbsent(
  spec: Spec,
  opts: { ambient?: Record<string, unknown>; derivedMarker?: string } = {},
): Spec {
  const existing = spec.encoding_context;
  if (existing && typeof existing === "object" && Object.keys(existing).length > 0) {
    return spec;
  }
  spec.encoding_context = deriveEncodingContext(spec, opts);
  return spec;
}
