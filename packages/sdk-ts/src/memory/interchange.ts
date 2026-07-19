/**
 * `dna/memory/interchange` — the Engram <-> MIF projection (TS twin of
 * `dna/memory/interchange.py`). Pure, deterministic, no network, no LLM.
 *
 * Mirrored to TypeScript following this package's precedent for the pure
 * memory-scoring core (decay/ecphory/encodingContext/memoryType/personal/
 * policy/retrieval/semantic all have TS twins; only the kernel-bound
 * `verbs.py` orchestration layer does not, because it has no TS caller). This
 * module is squarely in the "pure" category the precedent mirrors, AND has a
 * concrete TS-side consumer in view: dna-cloud's Next.js portal (PRODUCT.md
 * §8 "Minha memória" surface) is TypeScript and will want to render/parse MIF
 * docs without a Python round-trip.
 *
 * See the Python twin's module docstring for the full field-mapping
 * rationale, the §6 id-stability decision, and the two further divergences
 * found against `docs/design/2026-07-18-portable-memory-design.md` §2 (the
 * id pin's real home, and `homophonic_links` needing no vault because
 * `relationships[].strength` already fits `resonance_score`). Kept in sync
 * by hand (no fixture-generation script exists yet for this shape); a
 * dedicated Py<->TS parity fixture (`tests/fixtures/memory-interchange-parity.json`)
 * pins numeric/structural equality the same way `memory-scoring-parity.json`
 * does for the scoring core.
 *
 * s-memory-interchange-verbs (2026-07-19, feature f-portable-memory).
 */
import { classifyMemoryType } from "./memoryType.js";

const ALLOWED_MEMORY_TYPES = ["episodic", "semantic", "procedural"] as const;
type MemoryType = (typeof ALLOWED_MEMORY_TYPES)[number];

function isMemoryType(v: unknown): v is MemoryType {
  return typeof v === "string" && (ALLOWED_MEMORY_TYPES as readonly string[]).includes(v);
}

const NAMESPACE_ROOTS = ALLOWED_MEMORY_TYPES;

/** Engram fields with no MIF-side field — the "cognitive physics" vault. */
const VAULT_FIELDS = [
  "confidence_score",
  "relevance_decay_seed",
  "surface_count",
  "cues_history",
  "affect",
  "affect_reason",
  "affect_evidence_refs",
  "visibility",
  "surface_when",
  "revisions",
  "last_surfaced",
] as const;

const DEFAULT_IMPORT_AFFECT = "surprise";

export type Spec = Record<string, unknown>;
export type MifDoc = Record<string, unknown>;

// ─────────────────────────── id stability (§6) ───────────────────────────

export interface ResolveOrMintMifIdOptions {
  idFactory?: () => string;
}

/**
 * Resolve the MIF id an export should use for this Engram spec. Returns
 * `[mifId, newlyMinted]`. Reuses `encoding_context.mif_id` when already
 * pinned; otherwise mints via `idFactory` (default: `crypto.randomUUID`,
 * injectable for deterministic tests). Pure GIVEN a factory. Does not
 * mutate `spec` or persist anything — the caller pins a newly-minted id
 * back onto storage so the NEXT export sees it.
 */
export function resolveOrMintMifId(
  spec: Spec,
  options: ResolveOrMintMifIdOptions = {},
): [string, boolean] {
  const ec = spec.encoding_context;
  const existing =
    ec && typeof ec === "object" && !Array.isArray(ec)
      ? (ec as Record<string, unknown>).mif_id
      : undefined;
  if (existing) return [String(existing), false];
  const factory = options.idFactory ?? (() => crypto.randomUUID());
  return [factory(), true];
}

// ─────────────────────────── namespace <-> area ───────────────────────────

function namespaceFor(area: string, memoryType: string): string {
  const root = (NAMESPACE_ROOTS as readonly string[]).includes(memoryType)
    ? memoryType
    : "semantic";
  return area ? `_${root}/${area}` : `_${root}`;
}

function areaFromNamespace(namespace: string | null | undefined): string | null {
  if (!namespace) return null;
  if (namespace.startsWith("_")) {
    const rest = namespace.slice(1);
    const slash = rest.indexOf("/");
    const root = slash === -1 ? rest : rest.slice(0, slash);
    if ((NAMESPACE_ROOTS as readonly string[]).includes(root)) {
      return slash === -1 ? "" : rest.slice(slash + 1);
    }
  }
  return namespace;
}

// ─────────────────────────── relationships <-> refs ───────────────────────

interface Relationship {
  type: string;
  target: string;
  strength?: number;
  metadata?: { basis?: string; [k: string]: unknown };
}

interface HomophonicLink {
  target_name: string;
  resonance_score?: number;
  basis?: string;
  [k: string]: unknown;
}

function relationshipsForExport(
  spec: Spec,
  idLookup: Record<string, string> | undefined,
): Relationship[] {
  const lookup = idLookup ?? {};
  const rels: Relationship[] = [];
  const sourceRefs = (spec.source_refs as string[] | undefined) ?? [];
  for (const ref of sourceRefs) {
    rels.push({ type: "derived-from", target: lookup[ref] ?? ref });
  }
  const supersededBy = spec.superseded_by_memory as string | undefined;
  if (supersededBy) {
    rels.push({ type: "supersedes", target: lookup[supersededBy] ?? supersededBy });
  }
  const links = (spec.homophonic_links as HomophonicLink[] | undefined) ?? [];
  for (const link of links) {
    const targetName = link.target_name;
    if (!targetName) continue;
    const rel: Relationship = { type: "relates-to", target: lookup[targetName] ?? targetName };
    if (link.resonance_score !== undefined && link.resonance_score !== null) {
      rel.strength = link.resonance_score;
    }
    if (link.basis) rel.metadata = { basis: link.basis };
    rels.push(rel);
  }
  return rels;
}

function projectRelationships(
  relationships: Relationship[] | undefined,
): [string[], string | null, HomophonicLink[]] {
  const sourceRefs: string[] = [];
  let supersededByMemory: string | null = null;
  const homophonicLinks: HomophonicLink[] = [];
  for (const rel of relationships ?? []) {
    const target = rel.target;
    if (!target) continue;
    if (rel.type === "derived-from") {
      sourceRefs.push(target);
    } else if (rel.type === "supersedes") {
      supersededByMemory = target;
    } else if (rel.type === "relates-to") {
      const link: HomophonicLink = { target_name: target };
      if (rel.strength !== undefined && rel.strength !== null) {
        link.resonance_score = rel.strength;
      }
      const basis = rel.metadata?.basis;
      if (basis) link.basis = basis;
      homophonicLinks.push(link);
    }
  }
  return [sourceRefs, supersededByMemory, homophonicLinks];
}

// ─────────────────────────── provenance <-> owner/refs ────────────────────

function provenanceForExport(spec: Spec): Record<string, unknown> | null {
  const prov: Record<string, unknown> = {};
  if (spec.owner) prov.wasAttributedTo = spec.owner;
  if (spec.source_refs && (spec.source_refs as unknown[]).length) {
    prov.wasDerivedFrom = [...(spec.source_refs as string[])];
  }
  return Object.keys(prov).length ? prov : null;
}

function deriveSummary(content: string): string {
  for (const rawLine of (content ?? "").split("\n")) {
    const line = rawLine.trim().replace(/^#+/, "").trim();
    if (line) return line.slice(0, 280);
  }
  return (content ?? "").slice(0, 280);
}

// ─────────────────────────── the vault ─────────────────────────────────────

function buildXDna(spec: Spec): Record<string, unknown> {
  const vault: Record<string, unknown> = {};
  for (const field of VAULT_FIELDS) {
    if (spec[field] !== undefined && spec[field] !== null) {
      vault[field] = structuredClone(spec[field]);
    }
  }
  const ec = spec.encoding_context;
  if (ec && typeof ec === "object" && !Array.isArray(ec)) {
    const { mif_id: _mifId, ...ecClean } = ec as Record<string, unknown>;
    if (Object.keys(ecClean).length) vault.encoding_context = structuredClone(ecClean);
  }
  return vault;
}

function applyXDna(vault: Record<string, unknown>, spec: Spec): void {
  for (const field of VAULT_FIELDS) {
    if (field in vault) spec[field] = structuredClone(vault[field]);
  }
  const ec = vault.encoding_context;
  if (ec && typeof ec === "object" && !Array.isArray(ec)) {
    spec.encoding_context = structuredClone(ec);
  }
}

// ─────────────────────────── the public projection ────────────────────────

export interface ToMifOptions {
  idLookup?: Record<string, string>;
}

/** Project a native Engram spec to a MIF Memory Unit dict. Pure + deterministic. */
export function toMif(spec: Spec, mifId: string, options: ToMifOptions = {}): MifDoc {
  let memoryType = (spec.memory_type as string | undefined) || classifyMemoryType(spec);
  if (!isMemoryType(memoryType)) memoryType = "semantic";
  const area = (spec.area as string | undefined) || "";
  const body = spec.body as string | undefined;
  const summary = (spec.summary as string | undefined) || "";

  const doc: MifDoc = {
    id: mifId,
    type: memoryType,
    content: body ? body : summary,
    created: (spec.created_at as string | undefined) || "",
  };
  if (summary) doc.title = summary;
  doc.namespace = namespaceFor(area, memoryType);
  if (spec.tags && (spec.tags as unknown[]).length) doc.tags = [...(spec.tags as string[])];

  const temporal: Record<string, unknown> = {};
  if (spec.valid_from) temporal.validFrom = spec.valid_from;
  if (spec.valid_to) temporal.validUntil = spec.valid_to;
  if (Object.keys(temporal).length) doc.temporal = temporal;

  const relationships = relationshipsForExport(spec, options.idLookup);
  if (relationships.length) doc.relationships = relationships;

  const provenance = provenanceForExport(spec);
  if (provenance) doc.provenance = provenance;

  const vault = buildXDna(spec);
  if (Object.keys(vault).length) doc.extensions = { "x-dna": vault };

  return doc;
}

/** Project a MIF Memory Unit dict back to a native Engram spec. Pure + deterministic. */
export function fromMif(doc: MifDoc): Spec {
  const docId = (doc.id as string | undefined) || "";
  let memoryType = doc.type as string | undefined;
  if (!isMemoryType(memoryType)) memoryType = "semantic";

  const namespace = doc.namespace as string | undefined;
  const area = areaFromNamespace(namespace);
  const content = (doc.content as string | undefined) || "";
  const title = doc.title as string | undefined;

  const spec: Spec = {
    memory_type: memoryType,
    area: area ? area : "imported/mif",
    summary: (title || deriveSummary(content) || "(untitled MIF memory)").slice(0, 280),
    body: content,
    created_at: (doc.created as string | undefined) || "",
  };
  if (doc.tags && (doc.tags as unknown[]).length) spec.tags = [...(doc.tags as string[])];

  const temporal = (doc.temporal as Record<string, unknown> | undefined) || {};
  if (temporal.validFrom) spec.valid_from = temporal.validFrom;
  if (temporal.validUntil) spec.valid_to = temporal.validUntil;

  const [projSourceRefs, supersededByMemory, homophonicLinks] = projectRelationships(
    doc.relationships as Relationship[] | undefined,
  );
  let sourceRefs = projSourceRefs;
  const provenance = (doc.provenance as Record<string, unknown> | undefined) || {};
  if (!sourceRefs.length) {
    const wdf = provenance.wasDerivedFrom;
    if (Array.isArray(wdf)) sourceRefs = wdf.map(String);
    else if (typeof wdf === "string") sourceRefs = [wdf];
  }
  if (!sourceRefs.length) sourceRefs = [docId ? `mif:${docId}` : "mif:unknown"];
  spec.source_refs = sourceRefs;

  if (supersededByMemory) spec.superseded_by_memory = supersededByMemory;
  if (homophonicLinks.length) spec.homophonic_links = homophonicLinks;

  const owner = provenance.wasAttributedTo;
  if (typeof owner === "string") spec.owner = owner;

  const vault = ((doc.extensions as Record<string, unknown> | undefined)?.["x-dna"] ?? {}) as Record<
    string,
    unknown
  >;
  if (vault && typeof vault === "object") applyXDna(vault, spec);

  if (spec.affect === undefined) spec.affect = DEFAULT_IMPORT_AFFECT;
  if (spec.surface_when === undefined) spec.surface_when = ["feature_touched"];
  if (!spec.affect_reason) {
    spec.affect_reason =
      `Imported from external MIF memory ${docId || "unknown"} (mif-spec.dev/v1) — ` +
      "no affect/reason was carried on the source doc's x-dna vault.";
  }

  const ec = { ...((spec.encoding_context as Record<string, unknown> | undefined) ?? {}) };
  ec.mif_id = docId;
  spec.encoding_context = ec;

  return spec;
}
