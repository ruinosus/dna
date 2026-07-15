/**
 * Narrow role-interfaces the kernel's back-ref collaborators depend on — the TS
 * twin of Python's `dna/kernel/collaborator_ports.py`
 * (`s-kernel-decomp-f1`, épico `e-kernel-decomposition`).
 *
 * A kernel collaborator that holds `this._k = kernel` should declare the NARROW
 * slice of the kernel it actually uses, not the whole `Kernel` — otherwise the
 * back-ref is a god-interface pushed one layer down (any collaborator can touch
 * anything → nothing is testable in isolation). Structural typing means the
 * `Kernel` still satisfies each interface, so the kernel keeps passing `this`
 * when it wires the collaborator — zero runtime change.
 *
 * Parity note: the TS kernel decomposition tracks Python. Extracted as back-ref
 * classes with a narrow host today: `CompositionResolver`
 * (`CompositionResolverHost`) and `KindRegistry` (`RegistryHost`). The remaining
 * inline collaborators (instance_builder, query_engine, bundle_io, source_sync,
 * layer_policy, invalidation) gain their narrow interfaces as those extractions
 * land, keeping the contract convergent per spec §6.
 */
import type { HookRegistry } from "./hooks.js";
import type {
  KindPort,
  ReaderPort,
  SourcePort,
  WritableSourcePort,
} from "./protocols.js";

/**
 * The kernel surface `CompositionResolver` consumes (twin of Py
 * `CompositionResolverHost`, though TS is leaner: the resolution-chain walk +
 * composition-rule read touch only these). The static `INHERIT_PARENT_SCOPE`
 * is reached via `(k.constructor as typeof Kernel)` — an explicit cast that does
 * not need to be part of this instance contract.
 */
export interface CompositionResolverHost {
  /** The active read source (getter). */
  readonly activeSource: SourcePort | null;

  /** Granular per-doc cache read: `[scope, kind, name, tenantOrEmpty]`. */
  _granularDoc(
    key: [string, string, string, string],
  ): Promise<Record<string, unknown> | null>;

  /** The ordered Catalog scope set for a tenant (cached, fail-soft). */
  _catalogScopes(
    tenant: string | null,
    opts?: { exclude?: Set<string> },
  ): Promise<Array<[string, string | null]>>;

  /** Persist the materialized composition back through the writable source. */
  writeDocument(
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
  ): Promise<string>;
}

/**
 * The narrow slice of the Kernel the `KindRegistry` registration funnel needs
 * (twin of Py `RegistryHost`, `s-kernel-decomp-f3-kindregistry`). The `kinds`
 * map itself is OWNED by the registry — NOT reached through the host; this host
 * is only the fan-out surface registration touches on the wider kernel: the
 * hook registry (`kinddef_conflict` / `parse_error` events), the `_readers` list
 * (the 2-phase-load rescan return gate), the generic reader/writer wiring, and
 * the `_genericsResolved` flag it flips on every successful register. Every
 * member is a genuine registration dependency; widening it is a code-review
 * event (spec §3.1 / anti-goal §5.3).
 *
 * `_loadingExtOwner` (the per-`load()` alias-owner context) is read via
 * optional chaining, so a kernel outside a `load()` call (where it is null) is
 * still a valid host.
 */
/**
 * The narrow slice of the Kernel the `WritePipeline` consumes (twin of Py
 * `WriteHost`, `s-kernel-decomp-f2-writepipeline` — the anti-cosmetic F1 rule,
 * spec §3.1). The TS write path is thinner than Python's (no invalidate tiers /
 * OTel / catalog / observer fan-out — those "live in Python"), so this host is
 * smaller than the Py `WriteHost`: just tenant reconciliation, the writable-
 * source guard, the layer-policy check, the hook registry (`pre_save` veto +
 * `post_save`/`post_delete`), and Kind identity. Widening it is a code-review
 * event (anti-goal §5.3).
 */
export interface WriteHost {
  readonly hooks: HookRegistry;
  readonly tenant: string | null;
  /** Whether this kernel may key a reserved `personal:<oid>` partition
   *  (ADR-personal-memory) — set only on the authorized personal-memory write
   *  binding, read by the write pipeline's tenant-slug validation. */
  readonly _allowPersonal?: boolean;
  _kindScope(kind: string): string | null;
  kindPortFor(kind: string, apiVersion?: string): KindPort | null;
  _requireWritableSource(): WritableSourcePort;
  _checkLayerPolicyAsync(
    scope: string,
    kind: string,
    name: string,
    raw: unknown,
    layer: [string, string],
  ): Promise<void>;
}

export interface RegistryHost {
  readonly hooks: HookRegistry;
  /** The active reader list — read for the rescan gate; mutated by
   *  `_ensureGenericReadersWriters()`. */
  _readers: ReaderPort[];
  /** Flipped false on every successful register so the next
   *  `_ensureGenericReadersWriters()` re-resolves generic BUNDLE rw. */
  _genericsResolved: boolean;
  /** Per-`load()` alias-owner context (null outside a load). */
  _loadingExtOwner: string | null;
  /** Re-resolve generic BUNDLE readers/writers for newly registered kinds. */
  _ensureGenericReadersWriters(): void;
}
