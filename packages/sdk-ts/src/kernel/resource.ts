/**
 * Resource — self-aware document wrapper that knows its own dependencies.
 *
 * Replaces Document with added kindRef linkage: a Resource can resolve
 * its own dep_filters via `deps()` without needing the full ManifestInstance.
 */

// ---------------------------------------------------------------------------
// KindLike — minimal interface a Resource needs from a KindPort
// ---------------------------------------------------------------------------

export interface KindLike {
  readonly apiVersion: string;
  readonly kind: string;
  readonly alias: string;
  depFilters(): Record<string, string> | null;
}

// ---------------------------------------------------------------------------
// ResourceDep — one resolved dependency edge
// ---------------------------------------------------------------------------

export interface ResourceDep {
  /** The spec field name (e.g. "skills", "soul"). */
  field: string;
  /** The target kind alias (e.g. "agentskills-skill"). */
  targetAlias: string;
  /** Concrete names referenced (e.g. ["greet", "search"]). */
  names: string[];
}

// ---------------------------------------------------------------------------
// Resource
// ---------------------------------------------------------------------------

export class Resource {
  readonly apiVersion: string;
  readonly kind: string;
  readonly name: string;
  readonly raw: Record<string, unknown>;
  readonly typed: unknown;
  readonly origin: string;
  readonly kindRef: KindLike | null;

  private readonly _metadataRaw: Record<string, unknown>;
  private readonly _specRaw: Record<string, unknown>;

  constructor(opts: {
    apiVersion: string;
    kind: string;
    name: string;
    metadata?: Record<string, unknown>;
    spec?: Record<string, unknown>;
    raw?: Record<string, unknown>;
    typed?: unknown;
    origin?: string;
    kindRef?: KindLike | null;
  }) {
    this.apiVersion = opts.apiVersion;
    this.kind = opts.kind;
    this.name = opts.name;
    this._metadataRaw = opts.metadata ?? {};
    this._specRaw = opts.spec ?? {};
    this.raw = opts.raw ?? {};
    this.typed = opts.typed ?? null;
    this.origin = opts.origin ?? "local";
    this.kindRef = opts.kindRef ?? null;
  }

  /** Always returns Record<string, unknown> — typed metadata when available, raw dict otherwise. */
  get metadata(): Record<string, unknown> {
    if (
      this.typed != null &&
      typeof this.typed === "object" &&
      "metadata" in (this.typed as Record<string, unknown>)
    ) {
      return (this.typed as Record<string, unknown>).metadata as Record<string, unknown>;
    }
    return this._metadataRaw;
  }

  /** Always returns Record<string, unknown> — typed spec when available, raw dict otherwise. */
  get spec(): Record<string, unknown> {
    if (
      this.typed != null &&
      typeof this.typed === "object" &&
      "spec" in (this.typed as Record<string, unknown>)
    ) {
      return (this.typed as Record<string, unknown>).spec as Record<string, unknown>;
    }
    return this._specRaw;
  }

  /**
   * Resolve this resource's outgoing dependency edges using kindRef.depFilters().
   *
   * Returns one entry per dep_filter field that has a non-empty value in spec.
   * Scalar spec values (e.g. `soul: "brad"`) become single-element name lists.
   * Returns empty array when kindRef is null or depFilters() returns null.
   */
  deps(): ResourceDep[] {
    if (!this.kindRef) return [];
    const filters = this.kindRef.depFilters();
    if (!filters) return [];

    const spec = this.spec;
    const result: ResourceDep[] = [];

    for (const [field, targetAlias] of Object.entries(filters)) {
      const value = spec[field];
      let names: string[] = [];
      if (Array.isArray(value)) {
        names = value.filter((v): v is string => typeof v === "string");
      } else if (typeof value === "string" && value) {
        names = [value];
      }
      if (names.length === 0) continue;
      result.push({ field, targetAlias, names });
    }
    return result;
  }

  /** Create a Resource from a raw dict. */
  static fromRaw(
    raw: Record<string, unknown>,
    typed?: unknown,
    origin?: string,
    kindRef?: KindLike | null,
  ): Resource {
    const metadata = (raw.metadata as Record<string, unknown>) ?? {};
    return new Resource({
      apiVersion: (raw.apiVersion as string) ?? "",
      kind: (raw.kind as string) ?? "",
      name: (metadata.name as string) ?? "",
      metadata,
      spec: (raw.spec as Record<string, unknown>) ?? {},
      raw,
      typed,
      origin,
      kindRef,
    });
  }

  toString(): string {
    return `Resource(${this.apiVersion}/${this.kind}: ${this.name})`;
  }
}
