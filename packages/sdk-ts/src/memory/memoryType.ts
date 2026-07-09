/**
 * CoALA memory_type inference — heuristic, pure, conservative (TS twin of
 * `dna/memory/memory_type.py`). Never overwrites an explicit `memory_type`.
 *
 * s-memory-verbs (2026-07-09).
 */

const RULE_WORDS = [
  "always", "never", "must", "should", "don't", "do not", "ensure",
  "sempre", "nunca", "deve", "não ", "garanta", "evite", "prefira",
];
const EPISODIC_AREAS = ["feature/", "epic/", "story/", "issue/", "roadmap/"];

export function classifyMemoryType(spec: Record<string, unknown>): string {
  const existing = spec.memory_type;
  if (existing === "episodic" || existing === "semantic" || existing === "procedural") {
    return existing;
  }
  const text = `${spec.summary ?? ""} ${spec.body ?? ""}`.toLowerCase();
  if (RULE_WORDS.some((w) => text.includes(w))) return "procedural";
  const area = String(spec.area ?? "").toLowerCase();
  if (EPISODIC_AREAS.some((p) => area.startsWith(p))) return "episodic";
  return "semantic";
}
