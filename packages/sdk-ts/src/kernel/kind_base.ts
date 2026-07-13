/**
 * Kind base class with sensible defaults.
 *
 * 1:1 parity with python/dna/kernel/kind_base.py.
 *
 * Cuts the boilerplate that every Kind implementation duplicated.
 * Subclassing pattern:
 *
 *     class AssetKind extends KindBase {
 *       readonly apiVersion = "github.com/ruinosus/dna/asset/v1";
 *       readonly kind = "Asset";
 *       readonly alias = "asset-asset";
 *       readonly storage = StorageDescriptorImpl.bundle(
 *         "assets", "ASSET.md",
 *       );
 *       readonly asciiIcon = "🖼️";
 *       readonly displayLabel = "Assets";
 *     }
 *
 * That's the minimum-viable Kind. Everything else inherits sensible
 * defaults from this base.
 *
 * The base is **purely additive**: existing Kind impls keep working
 * as plain objects (they declare every field explicitly). Migrating
 * a Kind to `KindBase` is a strict simplification — no API changes.
 *
 * Mandatory overrides (no default available):
 *   - `apiVersion`  — globally unique namespace string
 *   - `kind`        — CamelCase Kind name
 *   - `alias`       — globally unique alias
 *   - `storage`     — StorageDescriptor (call StorageDescriptorImpl.bundle/yaml/root)
 *
 * Everything else has defaults that match the most common case.
 */

import { createHash } from "node:crypto";
import Ajv from "ajv";
import type { Document } from "./document.js";
import type { KindPort, LayerPolicy, StorageDescriptor } from "./protocols.js";

/** Default volatile spec fields shared by every Kind (s-sync-s1). Exported
 *  so DeclarativeKindPort (meta.ts) unions the SAME set instead of
 *  re-hardcoding it — twin of Python's KindBase.VOLATILE_SPEC_FIELDS
 *  class attribute (C1 review carry-over). */
export const DEFAULT_VOLATILE_SPEC_FIELDS: ReadonlySet<string> = new Set([
  "updated_at",
  "version",
  "created_at",
]);

/** JSON Schema `format` values that appear in real Kind schemas across the
 *  repo (builtin kind descriptors, KindDefinition YAMLs, tests). ajv v8 ships
 *  ZERO built-in formats, and the Python twin (`jsonschema`) treats `format`
 *  as annotation-only by default — so parity is "formats never validate".
 *  Registering each as `true` keeps exactly that semantics (always-valid
 *  annotation) while silencing ajv's per-compile
 *  `unknown format "X" ignored in schema` warning (s-public-ci).
 *  NOTE: deliberately NOT ajv-formats — that would start rejecting values and
 *  break Py↔TS validation parity. */
export const SCHEMA_ANNOTATION_FORMATS: readonly string[] = [
  "date-time",
  "date",
  "email",
  "markdown",
];

/** Canonical Ajv factory for the SDK — every `new Ajv(...)` in the kernel
 *  goes through here so options stay in one place. strict:false accepts the
 *  lenient JSON Schema shapes users author in YAML. */
export function createAjv(): Ajv {
  const formats: Record<string, true> = {};
  for (const f of SCHEMA_ANNOTATION_FORMATS) formats[f] = true;
  return new Ajv({ strict: false, allErrors: true, formats });
}

/** Stable, sorted-key, compact JSON — twin of Python's
 *  `json.dumps(sort_keys=True, separators=(",",":"))`. Logically-equal objects
 *  serialize identically regardless of insertion order (s-sync-s1). */
function _stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value) ?? "null";
  }
  if (Array.isArray(value)) {
    return "[" + value.map(_stableStringify).join(",") + "]";
  }
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj).sort();
  return (
    "{" +
    keys.map((k) => JSON.stringify(k) + ":" + _stableStringify(obj[k])).join(",") +
    "}"
  );
}

/** Normalize a spec for hashing: drop volatile + transport fields and fold a
 *  resolved instruction_file into its inline body (s-sync-s1). Shared by
 *  KindBase and DeclarativeKindPort so both digest identically — never a second
 *  copy. Twin of Python KindBase._canonical_spec. */
export function canonicalSpecOf(
  volatileSpecFields: ReadonlySet<string>,
  spec: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(spec ?? {})) {
    if (volatileSpecFields.has(k)) continue;
    out[k] = v;
  }
  delete out["source_files"]; // pure transport, never identity
  if (out["instruction_file"] && out["instruction"]) {
    delete out["instruction_file"]; // file-backed == inline once resolved
  }
  return out;
}

/** Stable SHA-256 of a doc's authored identity — the source diff/sync basis
 *  (s-sync-s1). Invariant to key order, formatting, volatile stamps, and
 *  instruction_file-vs-inline; sensitive to real content. Twin of Python
 *  KindBase.canonical_digest. */
export function canonicalDigestOf(
  kind: string,
  volatileSpecFields: ReadonlySet<string>,
  doc: Document,
): string {
  const spec = ((doc as { spec?: unknown }).spec ?? {}) as Record<string, unknown>;
  const payload = {
    kind: (doc as { kind?: string }).kind ?? kind,
    name: (doc as { name?: string }).name ?? null,
    spec: canonicalSpecOf(volatileSpecFields, { ...spec }),
  };
  return createHash("sha256").update(_stableStringify(payload), "utf8").digest("hex");
}

export abstract class KindBase implements Omit<KindPort, "apiVersion" | "kind" | "alias" | "storage"> {
  // ---- Identity (subclasses MUST set these) -----------------------
  // abstract apiVersion: string;
  // abstract kind: string;
  // abstract alias: string;
  // abstract storage: StorageDescriptor;

  // ---- Optional identity ------------------------------------------
  readonly origin?: string;

  // ---- Behavior flags (sensible defaults) -------------------------
  // ``isRoot`` was an explicit boolean Phase 0–15. Phase 16 derives
  // it from the storage descriptor: a Kind is the scope root iff its
  // storage pattern is ROOT (single file at scope root). GenomeKind
  // is the only one today; the getter keeps the existing read API
  // (``kp.isRoot``) working for all consumers.
  readonly isPromptTarget: boolean = false;
  readonly promptTargetPriority: number = 0;
  readonly flattenInContext: boolean = false;

  get isRoot(): boolean {
    const storage = (this as unknown as { storage?: { pattern?: string } }).storage;
    return storage?.pattern === "root";
  }
  // See KindPort.isRuntimeArtifact in protocols.ts. Override to `true`
  // only on Kinds whose documents are generated by runtime workflows
  // (EvalRun, Finding, Evidence, AssessmentRun, ...).
  readonly isRuntimeArtifact: boolean = false;

  // ---- Two-planes (spec 2026-06-09-kinds-two-planes-design) --------
  // "composition" (default) — participates in agent composition.
  // "record" — pure typed document; writes never invalidate scope
  // caches (Python kernel branches on this; TS has no cache machinery,
  // the attr exists for 1:1 parity + the registration lint below).
  readonly plane: "record" | "composition" = "composition";

  // ---- Kernel classification (s-kernel-kindport-classification-attrs) ----
  // The kernel DERIVES its classification sets from these per-Kind attributes
  // instead of matching hardcoded Kind names. 1:1 parity with the Python
  // KindBase. Defaults match the common case; the few Kinds that differ override.
  // `isSchemaAffecting`: writing this Kind invalidates the schema cache.
  readonly isSchemaAffecting: boolean = false;
  // `isOverlayable`: a tenant overlay may fork this Kind. False only for the
  // structural bootstrap Kinds (scope identity / schema / policy).
  readonly isOverlayable: boolean = true;
  // `scopeInheritable`: documents inherit across scopes by default. False for the
  // per-scope SDLC ledger + structural Kinds.
  readonly scopeInheritable: boolean = true;
  // `isCatalogIdentity`: writing a doc of this Kind changes the Catalog
  // tier's scope/mandatory set (s-write-path-despecialize — replaces the
  // hardcoded `kind == "Genome"` check in the Python write path; the TS
  // kernel keeps no catalog cache, the attribute exists for 1:1 Kind
  // metadata parity). True only on the scope-root identity Kind.
  readonly isCatalogIdentity: boolean = false;

  // ---- Embedding source fields (F3 spec D4) ------------------------
  // Fields of `spec` that compose the doc's embedding text. null =
  // not embeddable (or still covered by the legacy EMBEDDABLE_KINDS
  // frozenset in harness-shared). Declared here so the D4 derivation
  // covers still-class Kinds as well as descriptor-synthesized ports.
  readonly embedFields: string[] | null = null;

  // ---- Validation (s-typed-models-for-dict-kinds) -----------------
  // When true, parse() validates the doc's `spec` against schema() (ajv) before
  // returning — a malformed doc throws a clear error. 1:1 parity with the
  // Python KindBase.validate_on_parse. Opt-in (default false).
  readonly validateOnParse: boolean = false;
  private _parseValidator?: ((d: unknown) => boolean) | null;
  private _parseAjv?: Ajv;

  // ---- Optional rendering hints (duck-typed by Studio) -----------
  readonly docs?: string;
  readonly descriptionFallbackField?: string;
  readonly graphStyle?: { fill: string; stroke: string; textColor: string };
  readonly asciiIcon?: string;
  readonly displayLabel?: string;
  readonly uiSchema?: Record<string, Record<string, unknown>>;

  // ---- H1 opt-in for shared bundle markers -----------------------
  readonly markerSharedAllowed: boolean = false;

  // ---- Source-sync identity (s-sync-s1) --------------------------
  // Write-/runtime-stamped spec fields, NOT part of authored identity —
  // excluded from canonicalDigest so the same doc in two sources hashes
  // identically. Kinds override to extend (e.g. a Forecast adds generated_at).
  readonly volatileSpecFields: ReadonlySet<string> = DEFAULT_VOLATILE_SPEC_FIELDS;

  // ---- Behavior methods (default implementations) ----------------

  depFilters(): Record<string, string> | null {
    return null;
  }

  dependencies(): Record<string, string> | null {
    return this.depFilters();
  }

  schema(): Record<string, unknown> | null {
    return null;
  }

  getDefaultAgentName(_doc: Document): string | null {
    return null;
  }

  getLayerPolicies(_doc: Document): Record<string, LayerPolicy | string> | null {
    return null;
  }

  parse(raw: Record<string, unknown>): unknown {
    if (this.validateOnParse) this._validateSpec(raw);
    return raw;
  }

  /** Validate `raw.spec` against `schema()` (ajv). No-op when no schema.
   *  Throws a clear error for a malformed spec (s-typed-models-for-dict-kinds). */
  private _validateSpec(raw: Record<string, unknown>): void {
    const schema = this.schema();
    if (!schema) return;
    if (this._parseValidator === undefined) {
      this._parseAjv = createAjv();
      this._parseValidator = this._parseAjv.compile(schema);
    }
    if (!this._parseValidator) return;
    // Accept a full envelope ({apiVersion, kind, spec}) OR a flat spec dict
    // (mirrors the gaia Kinds' defensive parse + the Python twin).
    const spec =
      "apiVersion" in raw && raw.spec && typeof raw.spec === "object"
        ? (raw.spec as Record<string, unknown>)
        : raw;
    if (!this._parseValidator(spec)) {
      const errs = this._parseAjv?.errorsText(
        (this._parseValidator as unknown as { errors?: unknown[] }).errors as never,
      );
      throw new Error(`Kind '${this.kind}' spec validation failed: ${errs}`);
    }
  }

  describe(_doc: Document): string | null {
    return null;
  }

  summary(doc: Document): Record<string, unknown> | null {
    const spec = (doc as { spec?: unknown }).spec;
    if (spec && typeof spec === "object" && !Array.isArray(spec)) {
      return { ...(spec as Record<string, unknown>) };
    }
    return null;
  }

  promptTemplate(): string | null {
    return null;
  }

  /**
   * Resolve a NAMED composition layout to an embedded template
   * (s-dx-named-layouts). Prompt-target Kinds override this to expose
   * author-friendly presets (persona-first, instruction-first) so the common
   * case never hand-writes Mustache. Returns null for an unknown name (the
   * prompt builder fails loud). Twin of Python ``KindBase.layout_template``.
   */
  layoutTemplate(_name: string): string | null {
    return null;
  }

  /**
   * Public layout names this Kind offers (s-dx-named-layouts) — powers
   * discovery + fail-loud error messages. Twin of Python ``layout_names``.
   */
  layoutNames(): string[] {
    return [];
  }

  // ---- Source-sync digest (s-sync-s1; twin of Python canonical_digest) ----
  // The algorithm lives in the module-level `canonicalSpecOf`/`canonicalDigestOf`
  // helpers so DeclarativeKindPort (meta.ts) shares the SAME code instead of a
  // divergent copy — a descriptor Kind digests byte-identically to its
  // hand-written twin (twin of Python meta.py delegating to KindBase).

  protected canonicalSpec(spec: Record<string, unknown>): Record<string, unknown> {
    return canonicalSpecOf(this.volatileSpecFields, spec);
  }

  /** Stable SHA-256 of the doc's authored identity — basis for source
   *  diff/sync. Invariant to key order, formatting, volatile stamps, and
   *  instruction_file-vs-inline; sensitive to real content. */
  canonicalDigest(doc: Document): string {
    return canonicalDigestOf(this.kind, this.volatileSpecFields, doc);
  }

  // Required-by-interface but unused — subclasses override.
  abstract readonly apiVersion: string;
  abstract readonly kind: string;
  abstract readonly alias: string;
  abstract readonly storage: StorageDescriptor;
}
