/**
 * Meta-kind machinery: DeclarativeKindPort synthesized from a
 * TypedKindDefinition. 1:1 parity with Python dna.kernel.meta.
 */

import Ajv from "ajv";
import type { Document } from "./document.js";

/** Convert HSL (h: 0-360, s: 0-100, l: 0-100) to a hex color string.
 *  Mermaid classDef doesn't support hsl(), so we need hex. */
function hslToHex(h: number, s: number, l: number): string {
  const sn = s / 100;
  const ln = l / 100;
  const c = (1 - Math.abs(2 * ln - 1)) * sn;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = ln - c / 2;
  let r = 0, g = 0, b = 0;
  if (h < 60) { r = c; g = x; }
  else if (h < 120) { r = x; g = c; }
  else if (h < 180) { g = c; b = x; }
  else if (h < 240) { g = x; b = c; }
  else if (h < 300) { r = x; b = c; }
  else { r = c; b = x; }
  const toHex = (v: number) => Math.round((v + m) * 255).toString(16).padStart(2, "0");
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}
import { DEFAULT_VOLATILE_SPEC_FIELDS } from "./kind_base.js";
import { StudioUIMetadata, type StudioUIMetadataInit } from "./studio_ui.js";
import type { TypedKindDefinition } from "./models.js";
import type { PreviewBlock } from "./preview.js";
import {
  type BodyMode,
  type KindPort,
  type LayerPolicy,
  type StorageDescriptor,
  type TenantScope,
  SD,
} from "./protocols.js";

/** Convert a literal YAML storage dict into a StorageDescriptor. */
export function storageDictToDescriptor(
  storage: Record<string, unknown>,
): StorageDescriptor {
  if (storage == null || typeof storage !== "object") {
    throw new Error(`storage must be a dict, got ${typeof storage}`);
  }
  const stype = storage.type as string | undefined;
  if (!stype) {
    throw new Error("storage dict must have a 'type' field");
  }

  const bodyAs = (val: unknown): BodyMode => {
    if (val == null) return "text";
    if (val === "text" || val === "list" || val === "sections") return val;
    throw new Error(`unknown body_as=${String(val)} (expected text|list|sections)`);
  };

  if (stype === "bundle") {
    const container = (storage.container as string) ?? (storage.dir as string);
    const marker = storage.marker as string | undefined;
    if (!container || !marker) {
      throw new Error("storage type=bundle requires 'container' (or 'dir') and 'marker'");
    }
    return SD.bundle(
      container,
      marker,
      bodyAs(storage.body_as),
      (storage.body_field as string) ?? "instruction",
    );
  }

  if (stype === "yaml") {
    const container = (storage.container as string) ?? (storage.dir as string);
    if (!container) throw new Error("storage type=yaml requires 'container'");
    return SD.yaml(container);
  }

  if (stype === "standalone") {
    const filename =
      (storage.path as string) ??
      (storage.filename as string) ??
      (storage.marker as string);
    if (!filename) throw new Error("storage type=standalone requires 'path' (or 'filename')");
    return SD.standalone(
      filename,
      bodyAs(storage.body_as),
      (storage.body_field as string) ?? "content",
    );
  }

  if (stype === "root") {
    return SD.root((storage.marker as string) ?? "manifest.yaml");
  }

  throw new Error(
    `unknown storage type=${stype} (expected: bundle, yaml, standalone, root)`,
  );
}

/** Marker used by the 2-phase loader to distinguish synthetic ports from
 *  extension-registered ones for conflict resolution. */
export interface DeclarativeMarker {
  readonly __declarative__: true;
}

export class DeclarativeKindPort implements KindPort, DeclarativeMarker {
  readonly __declarative__ = true as const;
  readonly apiVersion: string;
  readonly kind: string;
  readonly alias: string;
  readonly origin: string;
  readonly docs?: string;
  readonly isRoot: boolean;
  readonly isPromptTarget: boolean;
  // F3 (spec D2): was hardcoded 5 — now declarable, default 5 preserved.
  readonly promptTargetPriority: number;
  readonly flattenInContext: boolean;
  readonly storage: StorageDescriptor;
  // F3 (spec D2): KindDefinitionSpec now populates is_runtime_artifact.
  readonly isRuntimeArtifact: boolean;

  // ---- F3 descriptor fields (spec 2026-06-10-kinds-descriptor-f3, D2) --
  // `plane`: mirrors KindBase.plane ("composition" default).
  readonly plane: "composition" | "record";
  // `scope`: mirrors the class attribute (e.g. KaizenKind declares
  // `scope = TenantScope.GLOBAL`). Only set when tenant_scope was
  // EXPLICITLY declared — undeclared kinds stay permissive (Phase 1
  // back-compat: the Kernel reads kp.scope ?? undefined).
  readonly scope?: TenantScope;
  // Kernel classification flags — mirror KindBase defaults.
  readonly scopeInheritable: boolean;
  readonly isOverlayable: boolean;
  // `embedFields`: source fields for embedding text (D4 derivation).
  readonly embedFields: string[] | null;
  // `summary`: declarative list-endpoint projection {field: default}.
  private readonly _summary: Record<string, unknown> | null;
  // Declared volatile fields union the KindBase defaults so the
  // canonical digest contract matches hand-written record Kinds.
  readonly volatileSpecFields: ReadonlySet<string>;

  // -- Rendering hints (auto-derived from KindDefinition spec) ---
  readonly graphStyle: { fill: string; stroke: string; textColor: string };
  readonly asciiIcon: string;
  readonly displayLabel: string;

  private readonly _depFilters: Record<string, string> | null;
  private readonly _defaultAgent: string | null;
  /** Public read-only view of the JSON Schema authored in the KindDefinition.
   *  Consumers like the Studio's NewDocumentWizard use this to pre-populate
   *  required fields with empty-but-valid stubs. */
  readonly jsonSchema: Record<string, unknown>;
  private readonly _validate: ((spec: unknown) => boolean) | null;
  private readonly _ajv: Ajv | null;
  readonly uiSchema?: Record<string, Record<string, unknown>>;

  // ---- Descriptor expressiveness fields (spec 2026-06-11, D1/D3-D7) ----
  // D1 `ui`: reconstructed StudioUIMetadata (or undefined) — byte-identical
  // /kinds/manifest output vs the deleted class.
  readonly ui?: StudioUIMetadata;
  // D3 `describe`: template string OR {path} projection.
  private readonly _describe: string | Record<string, unknown> | null;
  // D5 `spec_defaults`: shallow-merge map applied in parse() before validation.
  private readonly _specDefaults: Record<string, unknown> | null;
  // D6 `default_agent_field`: spec field returned VERBATIM by getDefaultAgentName.
  private readonly _defaultAgentField: string | null;
  // D7 `description_fallback_field`: pass-through string attr for Studio.
  readonly descriptionFallbackField?: string;

  constructor(typedDef: TypedKindDefinition) {
    const spec = typedDef.spec;
    this.apiVersion = spec.target_api_version;
    this.kind = spec.target_kind;
    this.alias = spec.alias;
    this.origin = spec.origin;
    this.isRoot = spec.is_root;
    this.isPromptTarget = spec.prompt_target;
    this.flattenInContext = spec.flatten_in_context;
    this.isRuntimeArtifact = Boolean(
      (spec as unknown as { is_runtime_artifact?: boolean }).is_runtime_artifact ?? false,
    );
    // F3 fields read defensively (Python getattr twin) — specs are
    // duck-typed in tests (hand-built objects), so stay defensive with
    // the same defaults KindDefinitionSpecSchema declares.
    const f3 = spec as unknown as {
      plane?: "composition" | "record";
      tenant_scope?: string;
      tenant_scope_declared?: boolean;
      prompt_target_priority?: number;
      scope_inheritable?: boolean;
      is_overlayable?: boolean;
      embed?: string[] | null;
      summary?: Record<string, unknown> | null;
      volatile_spec_fields?: string[] | null;
    };
    // F3 (spec D2): was hardcoded 5 — default 5 preserved.
    this.promptTargetPriority = Math.trunc(f3.prompt_target_priority ?? 5);
    this.plane = f3.plane ?? "composition";
    if (f3.tenant_scope_declared) {
      this.scope = f3.tenant_scope as TenantScope;
    }
    this.scopeInheritable = Boolean(f3.scope_inheritable ?? true);
    this.isOverlayable = Boolean(f3.is_overlayable ?? true);
    this.embedFields = f3.embed ?? null;
    this._summary = f3.summary ?? null;
    // Values MAY be projection objects (spec D2); lint them at load so a bad
    // descriptor fails fast (unknown key / exclusivity). Twin of Python.
    DeclarativeKindPort._lintSummary(this._summary);
    // Declared ∪ KindBase defaults — read the defaults FROM kind_base
    // (never re-hardcode; C1 review carry-over, twin of Python meta.py).
    this.volatileSpecFields = new Set([
      ...DEFAULT_VOLATILE_SPEC_FIELDS,
      ...(f3.volatile_spec_fields ?? []),
    ]);
    this.docs = spec.docs ?? undefined;
    this._depFilters = spec.dep_filters ?? null;
    this._defaultAgent = spec.default_agent ?? null;
    this.jsonSchema = (spec.schema as Record<string, unknown>) ?? {};
    this.storage = storageDictToDescriptor(spec.storage as Record<string, unknown>);

    // ---- Descriptor expressiveness fields (spec 2026-06-11, D1/D3-D7) ----
    const exprSpec = spec as unknown as {
      ui?: Record<string, unknown> | null;
      describe?: string | Record<string, unknown> | null;
      spec_defaults?: Record<string, unknown> | null;
      default_agent_field?: string | null;
      description_fallback_field?: string | null;
    };
    // D1: reconstruct the real StudioUIMetadata from the validated mapping so
    // /kinds/manifest output is byte-identical to the deleted class version.
    this.ui =
      exprSpec.ui != null
        ? new StudioUIMetadata(exprSpec.ui as StudioUIMetadataInit)
        : undefined;
    // D3 describe (template string OR {path} mapping).
    this._describe = exprSpec.describe ?? null;
    // D5 spec_defaults — lint NOW (load time), fail fast on a bad descriptor.
    this._specDefaults = exprSpec.spec_defaults ?? null;
    if (this._specDefaults != null && Object.keys(this._specDefaults).length > 0) {
      this._lintSpecDefaults(this._specDefaults, this.jsonSchema);
    }
    // D6 default_agent_field.
    this._defaultAgentField = exprSpec.default_agent_field ?? null;
    // D7 description_fallback_field pass-through.
    this.descriptionFallbackField = exprSpec.description_fallback_field ?? undefined;

    // Rendering hints — read from KindDefinition spec if user-provided,
    // otherwise auto-derive. Custom kinds get a deterministic color from
    // their origin hash so they're visually distinct in diagrams.
    const rawSpec = spec as unknown as Record<string, unknown>;
    const userStyle = rawSpec.graph_style as Record<string, string> | undefined;
    // F3 parity fix: YAML descriptors are byte-identical Py↔TS, so the
    // canonical key is snake_case `text_color` (what Python reads);
    // `textColor` stays accepted for back-compat. Gate on fill+stroke only
    // (mirrors Python — text_color defaults to "#fff").
    const userTextColor = userStyle?.text_color ?? userStyle?.textColor;
    if (userStyle?.fill && userStyle?.stroke) {
      this.graphStyle = {
        fill: userStyle.fill,
        stroke: userStyle.stroke,
        textColor: userTextColor ?? "#fff",
      };
    } else {
      // Deterministic color from origin hash — output as HEX because
      // mermaid classDef doesn't support hsl() syntax.
      let h = 0;
      for (let i = 0; i < this.origin.length; i++) {
        h = (h * 31 + this.origin.charCodeAt(i)) | 0;
      }
      const hue = Math.abs(h) % 360;
      this.graphStyle = {
        fill: hslToHex(hue, 55, 55),
        stroke: hslToHex(hue, 55, 40),
        textColor: "#fff",
      };
    }
    this.asciiIcon = (typeof rawSpec.ascii_icon === "string" ? rawSpec.ascii_icon : null) ?? "📄";
    this.displayLabel = (typeof rawSpec.display_label === "string" ? rawSpec.display_label : null) ?? (this.kind + "s");

    if (Object.keys(this.jsonSchema).length > 0) {
      // strict:false to accept lenient JSON Schema shapes users author in YAML
      this._ajv = new Ajv({ strict: false, allErrors: true });
      this._validate = this._ajv.compile(this.jsonSchema);
    } else {
      this._ajv = null;
      this._validate = null;
    }

    // Derive a uiSchema from the JSON Schema so the Studio's
    // SchemaDrivenEditor can render a form for this custom kind with zero
    // per-kind code. Users can still override individual fields via a
    // `ui_schema:` block in the KindDefinition spec (takes precedence).
    const derived = deriveUiSchemaFromJsonSchema(this.jsonSchema);
    const userHints =
      ((spec as Record<string, unknown>).ui_schema as Record<
        string,
        Record<string, unknown>
      > | undefined) ?? {};
    const merged: Record<string, Record<string, unknown>> = { ...derived };
    for (const [field, hint] of Object.entries(userHints)) {
      merged[field] = { ...(merged[field] ?? {}), ...hint };
    }
    this.uiSchema = Object.keys(merged).length > 0 ? merged : undefined;
  }

  /** Load-time lint for `spec_defaults` (spec D5). Each default KEY must
   *  exist in schema.properties and its VALUE must validate against THAT
   *  property's subschema. `required` is intentionally IGNORED — defaults are
   *  a *partial* spec (autolab's real _DEFAULTS doesn't satisfy required).
   *  Twin of Python DeclarativeKindPort._lint_spec_defaults. */
  private _lintSpecDefaults(
    specDefaults: Record<string, unknown>,
    jsonSchema: Record<string, unknown>,
  ): void {
    const props =
      (jsonSchema.properties as Record<string, unknown> | undefined) ?? {};
    const ajv = new Ajv({ strict: false, allErrors: true });
    for (const [key, value] of Object.entries(specDefaults)) {
      if (!(key in props)) {
        throw new Error(
          `KindDefinition spec_defaults key '${key}' is not a property in schema.properties`,
        );
      }
      const subschema = props[key];
      if (subschema != null && typeof subschema === "object") {
        const validate = ajv.compile(subschema as Record<string, unknown>);
        if (!validate(value)) {
          throw new Error(
            `KindDefinition spec_defaults['${key}']=${JSON.stringify(value)} ` +
              `fails its property subschema: ${ajv.errorsText(validate.errors)}`,
          );
        }
      }
    }
  }

  depFilters(): Record<string, string> | null {
    return this._depFilters;
  }

  getDefaultAgentName(doc: Document): string | null {
    // D6: when default_agent_field is declared, return the spec field VERBATIM
    // (no `?? null` coercion — "" stays "", mirroring the eval-evalexperiment
    // class). Otherwise fall back to the static default_agent.
    if (this._defaultAgentField != null) {
      const rawSpec = (doc as unknown as { spec?: unknown }).spec;
      const spec: Record<string, unknown> =
        rawSpec != null && typeof rawSpec === "object" && !Array.isArray(rawSpec)
          ? (rawSpec as Record<string, unknown>)
          : {};
      return this._defaultAgentField in spec
        ? (spec[this._defaultAgentField] as string)
        : null;
    }
    return this._defaultAgent;
  }

  getLayerPolicies(_doc: Document): Record<string, LayerPolicy | string> | null {
    return null;
  }

  parse(raw: Record<string, unknown>): unknown {
    let spec = (raw.spec as Record<string, unknown> | undefined) ?? {};
    // D5: shallow-merge {...spec_defaults, ...spec} BEFORE validation —
    // exactly autolab-run's class behavior (defaults fill, spec overrides).
    if (this._specDefaults != null && Object.keys(this._specDefaults).length > 0) {
      spec = { ...this._specDefaults, ...spec };
      raw = { ...raw, spec };
    }
    if (this._validate) {
      const ok = this._validate(spec);
      if (!ok) {
        const errs = this._ajv?.errorsText(
          (this._validate as unknown as { errors?: unknown[] }).errors as never,
        );
        throw new Error(
          `DeclarativeKind '${this.kind}' spec validation failed: ${errs}`,
        );
      }
    }
    return raw;
  }

  /** Display string for a doc (spec D3).
   *  - Template form (string): substitute `{field}` placeholders from the
   *    spec top level; a missing/None field renders as "".
   *  - Projection form ({path: field}): return the spec field verbatim (or
   *    null if absent).
   *  - No `describe` declared → null (today's behavior).
   *  Twin of Python DeclarativeKindPort.describe. */
  describe(doc: Document): string | null {
    if (this._describe == null) return null;
    const rawSpec = (doc as unknown as { spec?: unknown }).spec;
    const spec: Record<string, unknown> =
      rawSpec != null && typeof rawSpec === "object" && !Array.isArray(rawSpec)
        ? (rawSpec as Record<string, unknown>)
        : {};
    if (typeof this._describe === "object") {
      const fieldName = this._describe.path as string | undefined;
      if (fieldName == null) return null;
      const val = spec[fieldName];
      return val != null ? (val as string) : null;
    }
    // Template form: replace {field} with the spec value (missing/null → "").
    return this._describe.replace(/\{([^}]+)\}/g, (_m, key: string) => {
      const v = spec[key];
      return v == null ? "" : String(v);
    });
  }
  // -- Summary projection vocabulary (spec D2) -----------------------------
  // A value in `summary:` MAY be a projection object. Plain values keep
  // today's meaning (the projected default). The closed vocabulary + FIXED
  // combinator order: resolve (`path`|`count_of`) → `default` → `round` →
  // `truncate`. `format` is exclusive of the others. Twin of Python meta.py.
  private static readonly _PROJECTION_KEYS: ReadonlySet<string> = new Set([
    "count_of",
    "path",
    "paths",
    "format",
    "truncate",
    "round",
    "default",
    "filter_falsy",
    "all_or_empty",
    "placeholder_defaults",
  ]);
  // A dict VALUE is a projection only if it carries one of these markers
  // (else it's a plain default that happens to be a dict).
  private static readonly _PROJECTION_MARKERS: ReadonlySet<string> = new Set([
    "count_of",
    "path",
    "paths",
    "format",
  ]);

  private static _isProjection(value: unknown): value is Record<string, unknown> {
    if (value == null || typeof value !== "object" || Array.isArray(value)) {
      return false;
    }
    for (const k of Object.keys(value as Record<string, unknown>)) {
      if (DeclarativeKindPort._PROJECTION_MARKERS.has(k)) return true;
    }
    return false;
  }

  /** Load-time lint for projection objects in `summary:` (spec D2). Unknown
   *  key → throw; exactly one resolver; `format`/`paths` exclusivity. Twin of
   *  Python `_lint_summary`. */
  private static _lintSummary(summary: Record<string, unknown> | null): void {
    if (summary == null || typeof summary !== "object") return;
    for (const [field, value] of Object.entries(summary)) {
      if (!DeclarativeKindPort._isProjection(value)) continue;
      const keys = new Set(Object.keys(value));
      const unknown = [...keys].filter(
        (k) => !DeclarativeKindPort._PROJECTION_KEYS.has(k),
      );
      if (unknown.length > 0) {
        throw new Error(
          `KindDefinition summary['${field}'] projection has unknown key(s) ` +
            `${JSON.stringify(unknown.sort())}; allowed: ` +
            `${JSON.stringify([...DeclarativeKindPort._PROJECTION_KEYS].sort())}`,
        );
      }
      const resolvers = [...keys].filter((k) =>
        ["count_of", "path", "paths", "format"].includes(k),
      );
      if (resolvers.length !== 1) {
        throw new Error(
          `KindDefinition summary['${field}'] projection must have exactly ` +
            `one of count_of/path/paths/format, got ${JSON.stringify(resolvers.sort())}`,
        );
      }
      if (
        keys.has("format") &&
        [...keys].some(
          (k) => !["format", "all_or_empty", "placeholder_defaults"].includes(k),
        )
      ) {
        throw new Error(
          `KindDefinition summary['${field}'] format projection is exclusive ` +
            `of path/count_of/round/truncate/default`,
        );
      }
      if (
        keys.has("paths") &&
        [...keys].some((k) => !["paths", "filter_falsy"].includes(k))
      ) {
        throw new Error(
          `KindDefinition summary['${field}'] paths projection only supports ` +
            `filter_falsy`,
        );
      }
    }
  }

  /** Dict-only walk over a dotted `a.b.c` path. Missing → null. */
  private static _walkPath(spec: Record<string, unknown>, path: string): unknown {
    let cur: unknown = spec;
    for (const seg of path.split(".")) {
      if (
        cur == null ||
        typeof cur !== "object" ||
        Array.isArray(cur) ||
        !(seg in (cur as Record<string, unknown>))
      ) {
        return null;
      }
      cur = (cur as Record<string, unknown>)[seg];
    }
    return cur;
  }

  /** Decimal rounding that is byte-behavior-identical to CPython's built-in
   *  `round(value, ndigits)` — i.e. a faithful port of CPython `double_round`.
   *
   *  CPython rounds the EXACT stored IEEE-754 double to `ndigits` decimal
   *  places, ties-to-even, on the *true binary* value. A naive
   *  `Math.round(value * 10^n) / 10^n` (round-half-away, and on the *scaled*
   *  double) diverges on the genuine half cases — e.g. `0.125@2` is exactly
   *  1/8 so CPython ties to even → `0.12`, whereas `Math.round` gives `0.13`;
   *  and `2.675@2` stores as `2.67499…` so CPython → `2.67`. To match all of
   *  these we decompose the double into its exact rational `mantissa·2^exp2`,
   *  scale by `10^ndigits` with exact BigInt arithmetic, and round-half-to-even
   *  on the exact remainder. Verified against CPython `round` over a 20k-case
   *  Monte-Carlo (n∈{1,2,3,4}) plus the pinned hard cases: 0 mismatches.
   *
   *  Real consumers only use round:4 (avg_score/cost); this keeps the deeper
   *  depths (round:2, the spec's #1 parity risk) identical too. */
  private static _bankersRound(value: number, ndigits: number): number {
    if (!Number.isFinite(value)) return value;
    if (value === 0) return value;
    const neg = value < 0 || Object.is(value, -0);
    const v = Math.abs(value);

    // Decompose v exactly into mantissa * 2^exp2 via its IEEE-754 bits.
    const buf = new ArrayBuffer(8);
    const dv = new DataView(buf);
    dv.setFloat64(0, v);
    const hi = dv.getUint32(0);
    const lo = dv.getUint32(4);
    const rawExp = (hi >>> 20) & 0x7ff;
    let mantissa = ((BigInt(hi & 0xfffff) << 32n) | BigInt(lo >>> 0));
    let exp2: number;
    if (rawExp === 0) {
      exp2 = -1074; // subnormal
    } else {
      mantissa |= 1n << 52n;
      exp2 = rawExp - 1075;
    }

    // We want round(value * 10^ndigits) to nearest integer, ties-to-even,
    // computed exactly as a rational num/den.
    const ten = 10n ** BigInt(Math.abs(ndigits));
    let num = mantissa;
    let den = 1n;
    if (exp2 >= 0) num <<= BigInt(exp2);
    else den <<= BigInt(-exp2);
    if (ndigits >= 0) num *= ten;
    else den *= ten;

    let q = num / den;
    const r = num - q * den; // 0 <= r < den
    const twice = r * 2n;
    if (twice > den) q += 1n;
    else if (twice === den && q % 2n === 1n) q += 1n; // tie → even

    // Reassemble q / 10^ndigits as the exact decimal string, then parse — this
    // lands on the same double CPython produces (no scaled-division ULP drift).
    let result: number;
    if (ndigits > 0) {
      const s = q.toString().padStart(ndigits + 1, "0");
      const cut = s.length - ndigits;
      result = Number(`${s.slice(0, cut)}.${s.slice(cut)}`);
    } else if (ndigits === 0) {
      result = Number(q);
    } else {
      result = Number(q) * Number(ten);
    }
    return neg ? -result : result;
  }

  private static _resolveProjection(
    spec: Record<string, unknown>,
    proj: Record<string, unknown>,
  ): unknown {
    // -- format (exclusive) -------------------------------------------------
    if ("format" in proj) {
      const template = proj.format as string;
      const allOrEmpty = Boolean(proj.all_or_empty);
      const phDefaults =
        (proj.placeholder_defaults as Record<string, unknown> | undefined) ?? {};
      const names = [...template.matchAll(/\{([^}]+)\}/g)].map((m) => m[1]);
      const resolved: Record<string, unknown> = {};
      for (const name of names) {
        const present = name in spec && spec[name] != null;
        if (present) {
          resolved[name] = spec[name];
        } else if (allOrEmpty) {
          return "";
        } else if (name in phDefaults) {
          resolved[name] = phDefaults[name];
        } else {
          resolved[name] = "";
        }
      }
      return template.replace(/\{([^}]+)\}/g, (_m, key: string) => {
        const v = resolved[key];
        return v == null ? "" : String(v);
      });
    }

    // -- paths + filter_falsy (leaf-keyed) ----------------------------------
    if ("paths" in proj) {
      const out: Record<string, unknown> = {};
      const filterFalsy = Boolean(proj.filter_falsy);
      for (const path of proj.paths as string[]) {
        const leaf = path.split(".").pop() as string;
        const val = DeclarativeKindPort._walkPath(spec, path);
        if (filterFalsy && !val) continue;
        out[leaf] = val;
      }
      return out;
    }

    // -- resolve: count_of | path -------------------------------------------
    let value: unknown;
    if ("count_of" in proj) {
      const target = spec[proj.count_of as string];
      value =
        target == null
          ? 0
          : typeof target === "string" || Array.isArray(target)
            ? target.length
            : 0;
    } else {
      value = DeclarativeKindPort._walkPath(spec, proj.path as string);
    }

    // -- default (fires on missing OR None, post-resolve) -------------------
    if ("default" in proj && value == null) {
      value = proj.default;
    }

    // -- round (numeric; null passes through) -------------------------------
    if (
      "round" in proj &&
      typeof value === "number" &&
      Number.isFinite(value)
    ) {
      value = DeclarativeKindPort._bankersRound(value, proj.round as number);
    }

    // -- truncate (string[:N]) ----------------------------------------------
    if ("truncate" in proj && typeof value === "string") {
      value = value.slice(0, proj.truncate as number);
    }

    return value;
  }

  /** Declarative projection (F3 spec D2): when the KindDefinition declares
   *  `summary: {field: <plain default | projection object>}`, project the
   *  doc's spec. A PLAIN value keeps today's meaning (present field from
   *  spec, else the declared default). A PROJECTION object runs the closed
   *  vocabulary (count_of/path/paths/format + combinators). No declaration →
   *  null (today's behavior). Twin of Python DeclarativeKindPort.summary. */
  summary(doc: Document): Record<string, unknown> | null {
    if (this._summary == null) return null;
    const rawSpec = (doc as unknown as { spec?: unknown }).spec;
    const spec: Record<string, unknown> =
      rawSpec != null && typeof rawSpec === "object" && !Array.isArray(rawSpec)
        ? (rawSpec as Record<string, unknown>)
        : {};
    const out: Record<string, unknown> = {};
    for (const [c, d] of Object.entries(this._summary)) {
      if (DeclarativeKindPort._isProjection(d)) {
        out[c] = DeclarativeKindPort._resolveProjection(spec, d);
      } else {
        out[c] = c in spec ? spec[c] : d;
      }
    }
    return out;
  }
  promptTemplate(): string | null {
    return null;
  }

  dependencies(): Record<string, string> | null {
    return this.depFilters();
  }

  schema(): Record<string, unknown> | null {
    return Object.keys(this.jsonSchema).length > 0 ? this.jsonSchema : null;
  }

  /**
   * Preview blocks derived from the kind's JSON schema. Walks the
   * top-level `properties` of `jsonSchema` and renders each one based on
   * its declared type:
   *   - string with format=markdown OR maxLength>=400 → markdown block
   *   - string                                       → fields entry
   *   - integer / number / boolean                    → fields entry
   *   - array of strings                              → fields entry (bullets)
   *   - array of objects / object                     → code block (json)
   *   - enum                                          → fields entry
   *
   * Required fields surface first, optional after.
   */
  preview(doc: Document): PreviewBlock[] {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const props = this.jsonSchema.properties as
      | Record<string, Record<string, unknown>>
      | undefined;

    if (!props || Object.keys(props).length === 0) {
      // No schema info — just dump the spec
      if (!spec || Object.keys(spec).length === 0) {
        return [{ kind: "empty", title: `${this.kind} (empty)` }];
      }
      return [
        {
          kind: "code",
          title: `${this.kind} spec`,
          body: JSON.stringify(spec, null, 2),
          language: "json",
        },
      ];
    }

    const required = new Set((this.jsonSchema.required as string[] | undefined) ?? []);
    const ordered = Object.entries(props).sort(([a], [b]) => {
      const ar = required.has(a) ? 0 : 1;
      const br = required.has(b) ? 0 : 1;
      if (ar !== br) return ar - br;
      return a.localeCompare(b);
    });

    const blocks: PreviewBlock[] = [];
    const fields: Array<{ label: string; value: string }> = [];

    for (const [field, propSchema] of ordered) {
      const value = spec[field];
      if (value == null || value === "") continue;
      const type = propSchema.type as string | undefined;
      const format = propSchema.format as string | undefined;
      const maxLength = (propSchema.maxLength as number | undefined) ?? 0;
      const isEnum = Array.isArray(propSchema.enum);

      // Long markdown / multi-line strings → standalone markdown block
      if (
        type === "string" &&
        typeof value === "string" &&
        (format === "markdown" || maxLength >= 400 || value.length > 200)
      ) {
        blocks.push({
          kind: "markdown",
          title: (propSchema.title as string) ?? field,
          body: value,
        });
        continue;
      }

      if (type === "string" && typeof value === "string") {
        fields.push({
          label: (propSchema.title as string) ?? field,
          value: isEnum ? value : value,
        });
        continue;
      }

      if (type === "integer" || type === "number") {
        fields.push({ label: field, value: String(value) });
        continue;
      }

      if (type === "boolean") {
        fields.push({ label: field, value: value ? "true" : "false" });
        continue;
      }

      if (type === "array" && Array.isArray(value)) {
        const items = (propSchema.items as Record<string, unknown> | undefined) ?? {};
        if (items.type === "string" && !items.enum) {
          fields.push({
            label: (propSchema.title as string) ?? field,
            value: (value as unknown[]).map((v) => `• ${String(v)}`).join("\n"),
          });
        } else {
          blocks.push({
            kind: "code",
            title: (propSchema.title as string) ?? field,
            body: JSON.stringify(value, null, 2),
            language: "json",
          });
        }
        continue;
      }

      if (type === "object" || (typeof value === "object" && value != null)) {
        blocks.push({
          kind: "code",
          title: (propSchema.title as string) ?? field,
          body: JSON.stringify(value, null, 2),
          language: "json",
        });
        continue;
      }

      // Fallback
      fields.push({ label: field, value: String(value) });
    }

    if (fields.length > 0) {
      blocks.unshift({ kind: "fields", title: this.kind, fields });
    }

    if (blocks.length === 0) {
      return [{ kind: "empty", title: `${this.kind} (empty)` }];
    }
    return blocks;
  }

  static fromTyped(typedDef: TypedKindDefinition): DeclarativeKindPort {
    return new DeclarativeKindPort(typedDef);
  }
}

// ---------------------------------------------------------------------------
// JSON Schema → uiSchema derivation
// ---------------------------------------------------------------------------

/**
 * Map a single JSON Schema property node to a `SchemaDrivenEditor` field hint.
 * Conservative by default — unknown shapes fall back to a YAML editor so
 * nothing is ever lost.
 */
function fieldHintForJsonSchemaProp(
  prop: Record<string, unknown>,
): Record<string, unknown> {
  const type = prop.type as string | string[] | undefined;
  const format = prop.format as string | undefined;
  const title = prop.title as string | undefined;
  const description = prop.description as string | undefined;
  const enumVals = prop.enum as unknown[] | undefined;

  const hint: Record<string, unknown> = {};
  if (title) hint.label = title;
  if (description) hint.help = description;

  // Enum → select (dropdown)
  if (enumVals && enumVals.length > 0) {
    hint.widget = "select";
    hint.options = enumVals;
    return hint;
  }

  if (type === "string") {
    if (format === "markdown" || format === "md") {
      hint.widget = "markdown";
      hint.height = 300;
    } else if (format === "yaml") {
      hint.widget = "code";
      hint.language = "yaml";
      hint.height = 240;
    } else if (format === "code") {
      hint.widget = "code";
      hint.height = 240;
    } else if (format === "textarea" || (prop.maxLength as number | undefined ?? 0) > 200) {
      hint.widget = "textarea";
    } else {
      hint.widget = "input";
    }
    return hint;
  }

  if (type === "integer" || type === "number") {
    hint.widget = "number";
    return hint;
  }

  if (type === "boolean") {
    hint.widget = "checkbox";
    return hint;
  }

  if (type === "array") {
    const items = (prop.items as Record<string, unknown> | undefined) ?? {};
    if (items.type === "string" && !items.enum) {
      hint.widget = "tags";
      return hint;
    }
    // arrays of objects or anything richer → fallback to yaml editor
    hint.widget = "yaml";
    hint.height = 200;
    return hint;
  }

  if (type === "object") {
    hint.widget = "yaml";
    hint.height = 240;
    return hint;
  }

  // Unknown / polymorphic → safe yaml fallback
  hint.widget = "yaml";
  hint.height = 200;
  return hint;
}

/**
 * Walk a JSON Schema's top-level `properties` and produce a uiSchema map
 * keyed by field name. Required fields get `required: true` so the
 * SchemaDrivenEditor can mark them visually if it chooses to.
 */
export function deriveUiSchemaFromJsonSchema(
  jsonSchema: Record<string, unknown>,
): Record<string, Record<string, unknown>> {
  const out: Record<string, Record<string, unknown>> = {};
  const props = jsonSchema.properties as
    | Record<string, Record<string, unknown>>
    | undefined;
  if (!props) return out;
  const required = new Set((jsonSchema.required as string[] | undefined) ?? []);
  let order = 0;
  for (const [field, prop] of Object.entries(props)) {
    const hint = fieldHintForJsonSchemaProp(prop);
    hint.order = order++;
    if (required.has(field)) hint.required = true;
    out[field] = hint;
  }
  return out;
}
