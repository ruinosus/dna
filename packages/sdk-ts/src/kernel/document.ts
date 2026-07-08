/**
 * Document — unified wrapper for all manifest documents.
 *
 * 1:1 parity with Python dna.v3.kernel.document.
 *
 * v1.0 — `Document<SpecT>` generic typing. Consumers can declare
 * spec type at the call site without a runtime cost:
 *
 *     const doc = mi.documents.find((d) => d.kind === "Asset" && d.name === "x") as Document<AssetSpec>;
 *     doc.spec.summary?.byte_count;  // type-checker validated
 *
 * Bare `Document` defaults to `Record<string, unknown>` so existing
 * untyped code continues working. Purely additive — no API change
 * for callers that don't opt in.
 */
export class Document<SpecT extends Record<string, unknown> = Record<string, unknown>> {
  readonly apiVersion: string;
  readonly kind: string;
  readonly name: string;
  readonly raw: Record<string, unknown>;
  readonly typed: unknown;
  readonly origin: string;

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
  }) {
    this.apiVersion = opts.apiVersion;
    this.kind = opts.kind;
    this.name = opts.name;
    this._metadataRaw = opts.metadata ?? {};
    this._specRaw = opts.spec ?? {};
    this.raw = opts.raw ?? {};
    this.typed = opts.typed ?? null;
    this.origin = opts.origin ?? "local";
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

  /** Returns the spec, typed as `SpecT` when consumers parameterize
   *  the Document. Runtime: still a plain dict. */
  get spec(): SpecT {
    if (
      this.typed != null &&
      typeof this.typed === "object" &&
      "spec" in (this.typed as Record<string, unknown>)
    ) {
      return (this.typed as Record<string, unknown>).spec as SpecT;
    }
    return this._specRaw as SpecT;
  }

  /** Create a Document from a raw dict. */
  static fromRaw(raw: Record<string, unknown>, typed?: unknown, origin?: string): Document {
    const metadata = (raw.metadata as Record<string, unknown>) ?? {};
    return new Document({
      apiVersion: (raw.apiVersion as string) ?? "",
      kind: (raw.kind as string) ?? "",
      name: (metadata.name as string) ?? "",
      metadata,
      spec: (raw.spec as Record<string, unknown>) ?? {},
      raw,
      typed,
      origin,
    });
  }

  toString(): string {
    return `Document(${this.apiVersion}/${this.kind}: ${this.name})`;
  }
}
