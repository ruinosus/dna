/**
 * WritePipeline — the kernel's document write/delete execution, extracted from
 * the Kernel god-object (kernel decomposition Fase 2 —
 * `s-kernel-decomp-f2-writepipeline`). TS twin of
 * `packages/sdk-py/dna/kernel/write_pipeline.py`.
 *
 * The TS write path is materially THINNER than Python's: it has no
 * invalidate-mode tiers, no OTel span, no catalog cache, no version-retention,
 * no holder-reload / observer fan-out (those "live in Python" per the kernel
 * comments). What DOES live here and matches Python 1:1 is the write/delete
 * execution: tenant reconciliation, the layer-policy check, the `pre_save`
 * veto gate (writes only — deletes never veto), `saveDocument` /
 * `deleteDocument`, and the `post_save` / `post_delete` emission.
 *
 * Topology parity: the Kernel keeps the public `writeDocument` /
 * `deleteDocument` as thin facades that delegate here, exactly like the Python
 * layout. Following the anti-cosmetic F1 rule (spec §3.1), the pipeline holds a
 * NARROW `WriteHost` back-ref — the small slice of the kernel the write path
 * actually touches — not the whole `Kernel`. The kernel satisfies it
 * structurally, so it keeps passing `this`; zero runtime change. Stateless: the
 * kernel re-instantiates the pipeline in `withTenant` so a tenant-bound copy
 * resolves its own tenant.
 */
import type { ValidateFunction } from "ajv";
import type { WriteHost } from "./collaborator-ports.js";
import { deriveEventType } from "./events.js";
import { createAjv } from "./kind_base.js";
import {
  type KindPort,
  type WritableSourcePort,
  SpecValidationError,
  TenantScope,
  TenantRequired,
  TenantNotAllowed,
  validateTenantSlug,
} from "./protocols.js";

/** Compiled-validator cache for the generic write-path schema check
 *  (s-write-path-validation, i-008) — keyed by KindPort identity so each
 *  port's schema compiles once per process, not once per write. `null`
 *  marks a schema-less (permissive) port. */
const _writeValidators = new WeakMap<object, ValidateFunction | null>();

export class WritePipeline {
  private readonly _k: WriteHost;

  constructor(kernel: WriteHost) {
    this._k = kernel;
  }

  /** Read the write-validation mode knob. `enforce` (default) vetoes an
   *  invalid write; `warn` logs and persists; `off` skips the step. Read
   *  per-write (not memoized) so tests / operators can flip it live. */
  private static _validationMode(): "enforce" | "warn" | "off" {
    const mode = (process.env.DNA_WRITE_VALIDATION ?? "enforce").trim().toLowerCase();
    return mode === "warn" || mode === "off" ? mode : "enforce";
  }

  /**
   * Validate `raw.spec` against the Kind's declared JSON Schema at WRITE
   * time (s-write-path-validation, i-008 — the systemic gap found on the
   * Automation work: the kernel only schema-validated at scan/read via the
   * fail-soft `parse_error` channel, so a shape-broken doc persisted and
   * exploded later, far from the author). Twin of Python
   * `WritePipeline._validate_spec_schema`.
   *
   * Contract:
   * - Kinds without a schema (`schema()` null/empty, or throwing) stay
   *   PERMISSIVE — validation is opt-in by data, as always.
   * - `spec_defaults` (descriptor D5) are shallow-merged into the spec
   *   BEFORE validating, mirroring `DeclarativeKindPort.parse`.
   * - Runs AFTER the `pre_save` veto hooks (Kind-owned cures mutate
   *   ctx.raw first), BEFORE persistence.
   * - Didactic failure (install #26 pattern): names the field, the
   *   violation, and points at `dna kind show <Kind>`.
   */
  private _validateSpecSchema(
    scope: string,
    kind: string,
    name: string,
    raw: Record<string, unknown>,
    port: KindPort | null,
  ): void {
    const mode = WritePipeline._validationMode();
    if (mode === "off" || port === null || typeof raw !== "object" || raw === null) {
      return;
    }
    let validate = _writeValidators.get(port);
    if (validate === undefined) {
      let schema: Record<string, unknown> | null = null;
      try {
        schema = port.schema?.() ?? null;
      } catch {
        schema = null; // a Kind whose schema errors stays permissive
      }
      validate =
        schema !== null && typeof schema === "object" && Object.keys(schema).length > 0
          ? createAjv().compile(schema)
          : null;
      _writeValidators.set(port, validate);
    }
    if (validate === null) return;
    const rawSpec = raw.spec;
    let spec: Record<string, unknown> =
      rawSpec !== null && typeof rawSpec === "object" && !Array.isArray(rawSpec)
        ? (rawSpec as Record<string, unknown>)
        : {};
    // Descriptor D5: defaults fill, spec overrides — exactly what the
    // validating parse sees.
    const defaults = (port as { _specDefaults?: Record<string, unknown> | null })
      ._specDefaults;
    if (defaults != null && Object.keys(defaults).length > 0) {
      spec = { ...defaults, ...spec };
    }
    if (validate(spec)) return;
    const first = validate.errors?.[0];
    const path = (first?.instancePath ?? "").replace(/^\//, "").replace(/\//g, ".");
    const loc = path ? `spec.${path}` : "spec";
    const detail = first?.message ?? "spec does not match the Kind's schema";
    const msg =
      `write vetoed for ${scope}/${kind}/${name}: schema validation failed ` +
      `at ${loc}: ${detail} — see \`dna kind show ${kind}\` for the expected shape`;
    if (mode === "warn") {
      // eslint-disable-next-line no-console
      console.warn(`${msg} (DNA_WRITE_VALIDATION=warn — persisted anyway)`);
      return;
    }
    throw new SpecValidationError(msg);
  }

  /**
   * Reconcile tenant + layer args + Kernel.tenant + KindPort.scope.
   * Returns `[effectiveTenant, residualLayer]`. Back-compat:
   * `layer=("tenant", X)` is rewritten to `tenant=X` with a deprecation
   * console.warn. Validation: TENANTED kind requires a tenant; GLOBAL kind
   * forbids it. Moved verbatim from `Kernel._resolveTenantArg`.
   */
  resolveTenantArg(
    kind: string,
    tenant: string | null | undefined,
    layer: [string, string] | undefined,
  ): [string | null, [string, string] | undefined] {
    const k = this._k;
    let residualLayer = layer;
    let explicitTenant: string | null | undefined = tenant;

    // Back-compat: layer=("tenant", X) → tenant=X
    if (layer !== undefined && layer[0] === "tenant") {
      // eslint-disable-next-line no-console
      console.warn(
        "[DEPRECATION] layer=('tenant', X) is deprecated — pass tenant=X to writeDocument/deleteDocument instead",
      );
      if (explicitTenant === null || explicitTenant === undefined) {
        explicitTenant = layer[1];
      }
      residualLayer = undefined;
    }

    // Effective tenant: explicit per-call > Kernel.tenant binding
    const effective =
      explicitTenant !== null && explicitTenant !== undefined
        ? explicitTenant
        : k.tenant;
    validateTenantSlug(effective);

    // Validate against KindPort.scope when EXPLICITLY declared.
    const scopeDecl = k._kindScope(kind);
    if (scopeDecl === TenantScope.TENANTED && effective === null) {
      throw new TenantRequired(
        `Kind ${JSON.stringify(kind)} is TENANTED — pass tenant=<slug> to ` +
          `writeDocument() or bind one via new Kernel({tenant: ...}) / ` +
          `kernel.withTenant(...)`,
      );
    }
    if (scopeDecl === TenantScope.GLOBAL && effective !== null) {
      throw new TenantNotAllowed(
        `Kind ${JSON.stringify(kind)} is GLOBAL — must NOT pass a tenant. ` +
          `Use the unbound kernel (new Kernel() with no tenant) or ` +
          `kernel.withTenant(null) for global writes.`,
      );
    }
    return [effective, residualLayer];
  }

  /** Real writeDocument body — the facade (`Kernel.writeDocument`) is a thin
   *  delegator. Persists through the writable source with the `pre_save` veto
   *  gate + `post_save` emission. */
  async write(
    scope: string,
    kind: string,
    name: string,
    raw: Record<string, unknown>,
    options?: {
      skipHooks?: boolean;
      author?: string;
      tenant?: string | null;
      layer?: [string, string];
    },
  ): Promise<string> {
    const k = this._k;
    const src: WritableSourcePort = k._requireWritableSource();
    // Resolve tenant + validate against KindPort.scope (back-compat for
    // layer=("tenant", X) → tenant=X with deprecation warning)
    const [effectiveTenant, residualLayer] = this.resolveTenantArg(
      kind, options?.tenant, options?.layer,
    );
    const policyCheckLayer: [string, string] | undefined =
      effectiveTenant !== null ? ["tenant", effectiveTenant] : residualLayer;
    if (policyCheckLayer !== undefined) {
      await k._checkLayerPolicyAsync(scope, kind, name, raw, policyCheckLayer);
    }
    // pre_save veto hooks (s-write-path-despecialize) — Kind-specific write
    // rules (platform-agent fork guard, Kind-Writer contract, ...) live in
    // the extension that OWNS the Kind and register here via
    // `kernel.onVeto("pre_save", fn, {priority})`. A throw vetoes the
    // write; listeners may mutate `ctx.raw` in place. Fires regardless of
    // `skipHooks` — these are integrity gates, not notifications
    // (`skipHooks` only silences post_save).
    if (k.hooks.hasVeto("pre_save")) {
      await k.hooks.emitVeto("pre_save", {
        scope, kind, name, raw,
        tenant: effectiveTenant,
        ...(policyCheckLayer !== undefined ? { layer: policyCheckLayer } : {}),
        kernel: k,
      });
    }
    // --- generic spec↔schema validation (s-write-path-validation, i-008) ---
    // AFTER the veto hooks (Kind-owned cures mutate ctx.raw first), BEFORE
    // persistence: what gets validated is the exact shape that would be
    // saved. i-195: resolve the port by the doc's own apiVersion.
    this._validateSpecSchema(
      scope, kind, name, raw,
      k.kindPortFor(kind, raw?.apiVersion as string | undefined),
    );
    const version = await src.saveDocument(
      scope, kind, name, raw,
      {
        author: options?.author,
        tenant: effectiveTenant ?? undefined,
        layer: residualLayer,
      },
    );
    // Cache invalidation only for true base writes (no tenant + no overlay)
    if (effectiveTenant === null && residualLayer === undefined) {
      // Base instance cache lives in Python; TS kernel doesn't cache here.
    }
    if (!options?.skipHooks) {
      // Hook layer keeps legacy shape for back-compat with subscribers.
      const hookLayer = policyCheckLayer;
      await this.emitPostSave(scope, kind, name, raw, options?.author, false, hookLayer);
    }
    return version;
  }

  /** Real deleteDocument body — the facade is a thin delegator. NOTE: deletes
   *  have NO pre_save veto gate (only writes do). */
  async delete(
    scope: string,
    kind: string,
    name: string,
    options?: {
      skipHooks?: boolean;
      author?: string;
      tenant?: string | null;
      layer?: [string, string];
    },
  ): Promise<void> {
    const k = this._k;
    const src: WritableSourcePort = k._requireWritableSource();
    // Resolve tenant + validate against KindPort.scope.
    const [effectiveTenant, residualLayer] = this.resolveTenantArg(
      kind, options?.tenant, options?.layer,
    );
    const policyCheckLayer: [string, string] | undefined =
      effectiveTenant !== null ? ["tenant", effectiveTenant] : residualLayer;
    if (policyCheckLayer !== undefined) {
      await k._checkLayerPolicyAsync(scope, kind, name, null, policyCheckLayer);
    }
    await src.deleteDocument(
      scope, kind, name,
      {
        author: options?.author,
        tenant: effectiveTenant ?? undefined,
        layer: residualLayer,
      },
    );
    if (!options?.skipHooks) {
      await this.emitPostDelete(scope, kind, name, policyCheckLayer);
    }
  }

  /** Emit the post_save hook (shared by the new and legacy write paths).
   *  Async so async listeners (event bus publishers etc.) can await I/O. */
  private async emitPostSave(
    scope: string,
    kind: string,
    name: string,
    raw: Record<string, unknown>,
    author?: string,
    isUpdate?: boolean,
    layer?: [string, string],
  ): Promise<void> {
    const k = this._k;
    if (!k.hooks.has("post_save")) return;
    await k.hooks.emitAsync("post_save", {
      scope,
      kind,
      name,
      data: {
        event_type: deriveEventType(kind, isUpdate ?? false),
        author: author ?? "sdk",
        is_update: isUpdate ?? false,
        spec: raw,
      },
      ...(layer !== undefined ? { layer } : {}),
    });
  }

  /** Emit the post_delete hook (only from the new delegation path). */
  private async emitPostDelete(
    scope: string,
    kind: string,
    name: string,
    layer?: [string, string],
  ): Promise<void> {
    const k = this._k;
    if (!k.hooks.has("post_delete")) return;
    await k.hooks.emitAsync("post_delete", {
      scope,
      kind,
      name,
      data: {},
      ...(layer !== undefined ? { layer } : {}),
    });
  }

  /** Validate a SINGLE Kind-Writer target's slot↔schema contract. Moved from
   *  `Kernel._validateOneKindWriterEntry`. */
  validateOneKindWriterEntry(
    target: string,
    creativeSlots: string[],
    systemSlots: Record<string, unknown>,
  ): void {
    const port: KindPort | null = this._k.kindPortFor(target);
    const schema = port?.schema?.() ?? null;
    if (schema === null || typeof schema !== "object") {
      throw new Error(
        `Kind-Writer Agent writes_kind=${JSON.stringify(target)} has no ` +
        `schema (Kind is unknown or schema-less); a Kind-Writer must target a ` +
        `schema-bearing Kind.`,
      );
    }
    const properties = (schema.properties as Record<string, unknown>) ?? {};
    for (const slot of creativeSlots) {
      if (!(slot in properties)) {
        throw new Error(
          `Kind-Writer Agent creative_slot ${JSON.stringify(slot)} is not ` +
          `a property of Kind ${JSON.stringify(target)}'s schema.`,
        );
      }
    }
    const covered = new Set([...creativeSlots, ...Object.keys(systemSlots ?? {})]);
    const required = (schema.required as string[]) ?? [];
    for (const req of required) {
      if (!covered.has(req)) {
        throw new Error(
          `Kind-Writer Agent: required field ${JSON.stringify(req)} of ` +
          `Kind ${JSON.stringify(target)} is unmapped — cover it via ` +
          `creative_slots or system_slots.`,
        );
      }
    }
  }

  /** Validate a Kind-Writer Agent's slot↔schema contract. Fired by the
   *  Helix extension's Kind-Writer `pre_save` guard via the
   *  `kernel._validateKindWriter` shim. Moved from `Kernel._validateKindWriter`. */
  validateKindWriter(spec: Record<string, unknown>): void {
    // Multi-Kind (writes_kinds): validate EACH {kind: {creative_slots,
    // system_slots}} entry the same way. An agent uses EITHER writes_kind
    // (single) OR writes_kinds (multi). Twin of Python validate_kind_writer.
    const writesKinds = spec.writes_kinds as
      | Record<string, Record<string, unknown>>
      | undefined;
    if (writesKinds && Object.keys(writesKinds).length > 0) {
      for (const [target, entry] of Object.entries(writesKinds)) {
        const e = entry ?? {};
        this.validateOneKindWriterEntry(
          target,
          (e.creative_slots as string[]) ?? [],
          (e.system_slots as Record<string, unknown>) ?? {},
        );
      }
      return;
    }
    this.validateOneKindWriterEntry(
      spec.writes_kind as string,
      (spec.creative_slots as string[]) ?? [],
      (spec.system_slots as Record<string, unknown>) ?? {},
    );
  }
}
