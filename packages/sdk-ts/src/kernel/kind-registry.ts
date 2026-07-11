/**
 * KindRegistry — the kernel's registered-Kind identity map + the full
 * registration funnel, extracted from the Kernel god-object (kernel
 * decomposition, Fase 3 — `s-kernel-decomp-ts-parity`; Py twin:
 * `dna/kernel/kind_registry.py`).
 *
 * Two surfaces live here:
 *
 * - **Lookup** (pre-F3): the `kinds` map + the read surface (port lookup,
 *   alias, storage/container resolution, container→kind, describe). Also
 *   exported as the PURE functions `kindPortForOver` / `resolveDepFilterTargetOver`
 *   so a registry VIEW over an existing map (CompositionEngine / nav_kernel /
 *   the ManifestInstance) shares the ONE canonical resolver without holding a
 *   class instance.
 * - **Registration** (this slice): `registerKind` (the H1 validation funnel —
 *   interface/dup-key/dup-alias/BUNDLE-marker/plane/i-195-name-collision +
 *   alias generation), the static `_lintPlane` helper, `registerFromDescriptor`
 *   (builtin `*.kind.yaml` descriptors) and `registerKindDefinitions` (the
 *   per-scope KindDefinition funnel — warn+skip instead of throw). The kernel
 *   keeps `kind()` / `kindFromDescriptor()` / `_registerKindDefinitions()` /
 *   `_registerCustomKinds()` as THIN facades delegating here.
 *
 * Registration mutates `this.kinds` directly (the registry OWNS the map; the
 * kernel's `_kinds` getter proxies to it, so the ~20 inline `this._kinds` read
 * sites across the kernel keep working unchanged). Side effects that touch the
 * wider kernel — hooks (`kinddef_conflict` / `parse_error` events), the
 * `_readers` list (the rescan return gate), the generic reader/writer wiring,
 * the `_genericsResolved` flag, and the `_loadingExtOwner` alias-owner context —
 * route through a NARROW `RegistryHost` back-ref (the anti-cosmetic rule, spec
 * §3.1): the kernel satisfies it structurally. View-only registries pass no host
 * and use only the lookup surface / pure functions.
 *
 * One registry per kernel, shared across `withTenant` shallow copies (Kinds are
 * global — registered once at boot on the base kernel).
 *
 * The map is keyed `${apiVersion}\0${kind}` — the same shape held by both the
 * Kernel and the ManifestInstance.
 */

import { fileURLToPath } from "node:url";
import { dirname, basename, join } from "node:path";
import { existsSync, readFileSync } from "node:fs";

import { KindRegistrationError } from "./errors.js";
import { SD } from "./protocols.js";
import type { KindPort, StorageDescriptor } from "./protocols.js";
import type { RegistryHost } from "./collaborator-ports.js";
import { DeclarativeKindPort } from "./meta.js";
import { documentHash } from "./lock.js";
import {
  KindDefinitionSchema,
  KIND_DEFINITION_API_VERSION,
  KIND_DEFINITION_KIND,
} from "./models.js";

// ---------------------------------------------------------------------------
// Kind documentation resolution (Py twin: `kind_registry._load_kind_docs`).
// ---------------------------------------------------------------------------

/**
 * Resolve a kind's prose documentation.
 *
 * Resolution order:
 *   1. DOCS-<KindName>.md next to the extension's source file
 *      (inside `<basename>/`, where basename is the extension .ts stem)
 *   2. DOCS.md in that same directory
 *   3. The `docs` attribute on the KindPort
 *   4. null
 *
 * Browser consumers (Tauri Studio / Vite) stub node:fs/path/url via
 * `nodeStubPlugin` in vite.config.ts — filesystem reads return empty and
 * the loader transparently falls through to `kp.docs`.
 */
export function loadKindDocs(kp: KindPort): string | null {
  const sourceUrl = (kp as unknown as { _sourceUrl?: string })._sourceUrl;
  if (sourceUrl) {
    try {
      const file = fileURLToPath(sourceUrl);
      const dir = dirname(file);
      const stem = basename(file).replace(/\.[tj]s$/, "");
      const extDir = join(dir, stem);
      const candidates = [join(extDir, `DOCS-${kp.kind}.md`), join(extDir, "DOCS.md")];
      for (const candidate of candidates) {
        if (existsSync(candidate)) {
          const text = readFileSync(candidate, "utf-8").trim();
          if (text) return text;
        }
      }
    } catch {
      // fall through to docs attr
    }
  }
  return kp.docs ?? null;
}

// ---------------------------------------------------------------------------
// s-alias-generated-not-typed — alias generation + canonical dep_filter
// resolution. Aliases used to be hand-typed strings on every Kind class
// (~46 divergences from the <owner>-<kebab(kind)> convention + one
// recorded bug: "policy-layer" reversed/truncated). New Kinds OMIT the
// alias and get it generated; legacy aliases stay untouched (live wire
// format in dep_filters / Mustache / LayerPolicy docs). Py twin:
// dna.kernel.kind_registry.
// ---------------------------------------------------------------------------

/** CamelCase kind name → kebab-case: EvalCase → eval-case, ADR → adr,
 *  HTMLThing → html-thing. */
export function kebabKindName(kind: string): string {
  let s = kind.replace(/(?<=[a-z0-9])(?=[A-Z])/g, "-");
  s = s.replace(/(?<=[A-Z])(?=[A-Z][a-z])/g, "-");
  return s.toLowerCase();
}

/** The canonical alias for a Kind: `<owner>-<kebab(kind)>`. */
export function generateAlias(owner: string, kind: string): string {
  return `${owner}-${kebabKindName(kind)}`;
}

/** Ratchet (shrink-only): every builtin CLASS Kind that still hand-types
 *  its alias — the live wire format that CANNOT be renamed without a doc
 *  migration. New Kinds must OMIT the alias (generation). Entries leave
 *  as classes migrate to generation/descriptors — NEVER add one
 *  (tests/alias-generation.test.ts, ratchet test). Py twin:
 *  dna.kernel.kind_registry.EXPLICIT_ALIAS_ALLOWLIST — the TS set
 *  excludes the Py-only extensions (gaia-*, collab-comment) and includes
 *  every TS class port, per kind-registry-parity.json. */
export const EXPLICIT_ALIAS_ALLOWLIST: ReadonlySet<string> = new Set([
  // helix
  "helix-genome", "helix-agent", "helix-actor",
  // helix-tool migrated to a descriptor (s-tool-kind-descriptor): its alias
  // lives in helix/kinds/tool.kind.yaml (parity-critical) — shrink-only.
  "helix-usecase", "policy-layer-policy",
  "helix-canvas",
  "helix-setting", "helix-theme", "helix-user-profile",
  // sdlc (classes; descriptors are outside the ratchet)
  "sdlc-roadmap", "sdlc-epic", "sdlc-feature", "sdlc-story",
  "sdlc-issue", "sdlc-bug", "sdlc-task", "sdlc-spike",
  "sdlc-initiative", "sdlc-spec", "sdlc-plan", "sdlc-agent-session",
  "sdlc-reference",
  // eval
  
  
  // blocks
  
  // single-kind extensions
  "agentskills-skill", "soulspec-soul", "agentsmd-agent",
  "guardrails-guardrail", "helix-hook",
  "helix-safety-policy", "presidio-recognizer",
  "kinddef-kinddefinition",
  
  
  "evidence-policy", "federation-mcp",
  // s-automation-trio-extinction: jobs-jobtype / hooktype-hooktype /
  // scheduletype-scheduletype extintos (unificados no Kind Automation).
  
  
  
  "lesson-lesson",
  
  "tenant-tenant", "tenant-membership",
  "audit-userroleassignment", 
  "testkit-test-guide", "testkit-test-run",
  
]);

/** i-195 — kind names allowed to exist under MULTIPLE apiVersions in the
 *  extension/builtin funnel. SHRINK-ONLY ratchet: the Reference pair
 *  (github.com/ruinosus/dna/research/v1 + github.com/ruinosus/dna/sdlc/v1) predates the guard and is scheduled
 *  to be merged by the Reference-family unification follow-up; when that
 *  lands, empty this set. NEVER add a name here — rename the new Kind
 *  instead (bare-name lookups become ambiguous the moment two
 *  apiVersions share a kind name). Py twin:
 *  dna.kernel.kind_registry.KIND_NAME_COLLISION_ALLOWLIST. */
export const KIND_NAME_COLLISION_ALLOWLIST: ReadonlySet<string> =
  new Set(["Reference"]);

// ---------------------------------------------------------------------------
// Pure lookup functions — shared with registry VIEWS (CompositionEngine /
// nav_kernel / the ManifestInstance) that wrap a kinds map WITHOUT a class
// instance. The KindRegistry methods below delegate to these so there is ONE
// canonical implementation. Py twin: `KindRegistry.port_for` /
// `KindRegistry.resolve_dep_filter_target`.
// ---------------------------------------------------------------------------

/**
 * Lookup a registered KindPort by kind name (case-sensitive) over `kinds`.
 * With `apiVersion` the lookup is EXACT on (apiVersion, kind) — bare
 * lookups on a name shared by multiple apiVersions resolve
 * extension-first then registration order (i-195, Py twin:
 * `KindRegistry.port_for`).
 */
export function kindPortForOver(
  kinds: Map<string, KindPort>,
  kind: string,
  apiVersion?: string,
): KindPort | null {
  if (apiVersion !== undefined) {
    return kinds.get(`${apiVersion}\0${kind}`) ?? null;
  }
  const matches: KindPort[] = [];
  for (const kp of kinds.values()) {
    if (kp.kind === kind) matches.push(kp);
  }
  if (matches.length === 0) return null;
  if (matches.length > 1) {
    // per-scope DeclarativeKindPorts carry __declarative__ WITHOUT
    // __builtin_descriptor__; extension classes + builtin descriptors
    // must win the bare name (i-195).
    const extensionFirst = matches.filter((kp) => {
      const p = kp as unknown as {
        __declarative__?: boolean; __builtin_descriptor__?: boolean;
      };
      return p.__declarative__ !== true || p.__builtin_descriptor__ === true;
    });
    if (extensionFirst.length > 0) return extensionFirst[0];
  }
  return matches[0];
}

/**
 * Canonical dep_filter target resolution (s-alias-generated-not-typed).
 *
 * The CONTRACT is alias-valued dep_filters (`"soulspec-soul"`). The
 * legacy `"kind=<Name>"` format resolves through a DEPRECATED shim so
 * per-scope KindDefinition docs keep working (builtin extensions must be
 * alias-pure — `validateDepFilters` rejects `kind=` there). Since
 * s-unify-composition-subsystems this is THE resolver for every
 * dep_filter reader — `validateRefs` / `mi.composition` and the Kernel.
 * Py twin: `KindRegistry.resolve_dep_filter_target`.
 */
export function resolveDepFilterTargetOver(
  kinds: Map<string, KindPort>,
  value: string,
): KindPort | null {
  if (value.startsWith("kind=")) {
    console.warn(
      `dep_filter value ${JSON.stringify(value)} uses the legacy 'kind=' ` +
      `format — use the target Kind's alias instead ` +
      `(s-alias-generated-not-typed).`,
    );
    return kindPortForOver(kinds, value.slice("kind=".length));
  }
  for (const kp of kinds.values()) {
    if (kp.alias === value) return kp;
  }
  return null;
}

/**
 * Holds the registered KindPorts + the lookups + the registration funnel.
 */
export class KindRegistry {
  /** Key: "apiVersion\0kind" for uniqueness. OWNED here; the kernel's
   *  `_kinds` getter proxies to it. */
  readonly kinds: Map<string, KindPort>;

  /** The NARROW `RegistryHost` back-ref used ONLY by the registration
   *  funnel (hooks fan-out, the `_readers` rescan gate, generic
   *  reader/writer wiring, `_genericsResolved`, the `_loadingExtOwner`
   *  alias-owner context). Only read at registration time (boot) — so the
   *  kernel may pass `this` before its `hooks`/`_readers` are fully wired.
   *  View-only registries pass `null` and never call `register*`. */
  private readonly _host: RegistryHost | null;

  constructor(kinds?: Map<string, KindPort>, host?: RegistryHost | null) {
    this.kinds = kinds ?? new Map<string, KindPort>();
    this._host = host ?? null;
  }

  // -- Lookup ---------------------------------------------------------------

  /** Lookup a registered KindPort by kind name (case-sensitive). With
   *  apiVersion the lookup is EXACT on (apiVersion, kind); bare lookups on
   *  an ambiguous name resolve extension-first then registration order
   *  (i-195). Py twin: `KindRegistry.port_for`. */
  portFor(kind: string, apiVersion?: string): KindPort | null {
    return kindPortForOver(this.kinds, kind, apiVersion);
  }

  /** All registered KindPorts. Order matches registration. */
  allPorts(): KindPort[] {
    return Array.from(this.kinds.values());
  }

  /** Resolve a kind name to its globally-unique alias (`<owner>-<kind>`).
   *  Falls back to `kind.toLowerCase()` when no registered port provides
   *  one. Py twin: `KindRegistry.alias_for`. */
  aliasFor(kind: string, apiVersion?: string): string {
    const port = this.portFor(kind, apiVersion);
    const alias = port ? port.alias : null;
    return alias ? alias : kind.toLowerCase();
  }

  /** Return the storage container directory for a kind, or null. */
  containerFor(kindName: string): string | null {
    const kp = this.portFor(kindName);
    if (!kp) return null;
    return kp.storage?.container ?? null;
  }

  /** Return the StorageDescriptor for a kind, or null if unknown. */
  storageFor(kindName: string): StorageDescriptor | null {
    const kp = this.portFor(kindName);
    return kp ? (kp.storage ?? null) : null;
  }

  /** Return the kind name whose StorageDescriptor.container matches.
   *  null for empty container (ROOT kinds) or unregistered containers. */
  byContainer(container: string): string | null {
    if (!container) return null;
    for (const kp of this.kinds.values()) {
      const sd = kp.storage ?? null;
      if (sd !== null && sd.container === container) return kp.kind;
    }
    return null;
  }

  /** Canonical dep_filter target resolution (s-alias-generated-not-typed).
   *  Delegates to the shared `resolveDepFilterTargetOver`. Py twin:
   *  `KindRegistry.resolve_dep_filter_target`. */
  resolveDepFilterTarget(value: string): KindPort | null {
    return resolveDepFilterTargetOver(this.kinds, value);
  }

  /** Summary dict for a registered kind, including resolved docs. Py twin:
   *  `KindRegistry.describe`. */
  describe(kindName: string): Record<string, unknown> | null {
    for (const kp of this.kinds.values()) {
      if (kp.kind === kindName) {
        const resolved = (kp as unknown as { _resolvedDocs?: string | null })._resolvedDocs;
        return {
          kind: kp.kind,
          alias: kp.alias,
          apiVersion: kp.apiVersion,
          isRoot: kp.isRoot,
          isPromptTarget: kp.isPromptTarget,
          docs: resolved ?? kp.docs ?? null,
        };
      }
    }
    return null;
  }

  /** s-alias-generated-not-typed — every dep_filter target of an
   *  EXTENSION-registered Kind must resolve to a registered alias.
   *
   *  Aliases are the wire key of dep_filters / Mustache sections /
   *  LayerPolicy — a typo used to degrade the prompt SILENTLY (the dep
   *  just vanished from the context, warning buried in logs). Called at
   *  the end of `loadBuiltins()` (the TS twin of `Kernel.auto()`).
   *
   *  - Extension/builtin port with an unknown alias OR the legacy
   *    `kind=` format → `KindRegistrationError` (boot fails loud).
   *  - Per-scope declarative ports (user KindDefinition docs) only WARN
   *    — user docs never take the boot down (same posture as the
   *    parse_error / plane-lint funnels).
   *  Py twin: `KindRegistry.validate_dep_filters`. */
  validateDepFilters(): void {
    const problems: string[] = [];
    for (const kp of this.allPorts()) {
      let filters: Record<string, string> | null;
      try {
        filters = kp.depFilters();
      } catch {
        // port quebrado não derruba os demais
        continue;
      }
      if (!filters) continue;
      const p = kp as unknown as {
        __declarative__?: boolean; __builtin_descriptor__?: boolean;
      };
      const isDeclarative =
        p.__declarative__ === true && p.__builtin_descriptor__ !== true;
      for (const [field, value] of Object.entries(filters)) {
        if (typeof value !== "string") continue;
        let msg: string;
        if (value.startsWith("kind=")) {
          msg =
            `${kp.kind}.depFilters[${JSON.stringify(field)}] uses the ` +
            `legacy 'kind=' format (${JSON.stringify(value)}) — use the ` +
            `target Kind's alias (builtin extensions are alias-pure).`;
        } else {
          // Polymorphic refs (WorkflowEvent.ref) declare a PIPE-UNION of
          // aliases — validate each term.
          const unknown = value
            .split("|")
            .filter((part) => this.resolveDepFilterTarget(part) === null);
          if (unknown.length === 0) continue;
          msg =
            `${kp.kind}.depFilters[${JSON.stringify(field)}] points at ` +
            `unknown alias(es) ${JSON.stringify(unknown)} — the dep would ` +
            `silently vanish from prompts/composition.`;
        }
        if (isDeclarative) {
          console.warn(`[kernel] dep_filter (per-scope): ${msg}`);
        } else {
          problems.push(msg);
        }
      }
    }
    if (problems.length > 0) {
      throw new KindRegistrationError(
        "dep_filter validation failed (s-alias-generated-not-typed):\n  " +
        problems.join("\n  "),
      );
    }
  }

  // -- Registration funnel (Fase 3) -----------------------------------------

  /** H1 registration funnel — moved verbatim from `Kernel.kind()`. The
   *  kernel keeps `kind()` as a thin facade delegating here. Py twin:
   *  `KindRegistry.register_kind`. */
  registerKind(k: KindPort): void {
    // H1 — Boot-time validation (interface + uniqueness + marker collision).
    // Catches the failure modes that previously surfaced at runtime as
    // silent overwrites or first-match-wins scanner bugs:
    //   1. Object doesn't satisfy KindPort interface  → registration error
    //   2. Duplicate (apiVersion, kind) tuple          → registration error
    //   3. Duplicate alias across registered Kinds     → registration error
    //   4. BUNDLE-pattern (container, marker) clash    → registration error
    const required = [
      "apiVersion", "kind", "alias", "isRoot", "isPromptTarget",
      "promptTargetPriority", "flattenInContext", "storage",
    ] as const;
    for (const attr of required) {
      if (!(attr in (k as object))) {
        throw new KindRegistrationError(
          `Kind ${(k as { constructor?: { name?: string } })?.constructor?.name ?? typeof k} ` +
          `does not satisfy KindPort interface (missing ${attr}). See ` +
          `typescript/src/kernel/protocols.ts.`,
        );
      }
    }
    const requiredMethods = [
      "depFilters", "getDefaultAgentName", "getLayerPolicies",
      "parse", "describe", "summary", "promptTemplate",
    ] as const;
    for (const m of requiredMethods) {
      if (typeof (k as unknown as Record<string, unknown>)[m] !== "function") {
        throw new KindRegistrationError(
          `Kind ${(k as { constructor?: { name?: string } })?.constructor?.name ?? typeof k} ` +
          `does not satisfy KindPort interface (missing ${m}() method). See ` +
          `typescript/src/kernel/protocols.ts.`,
        );
      }
    }

    // s-alias-generated-not-typed — Kind sem alias declarado ganha o
    // gerado <owner>-<kebab(kind)>. Owner: attr explícito no port →
    // contexto da Extension sendo carregada (kernel.load) → 1º token
    // do apiVersion. Aliases legados digitados ficam intocados (wire
    // format vivo); o ratchet EXPLICIT_ALIAS_ALLOWLIST impede Kind
    // NOVO de digitar um. Py twin: Kernel.kind().
    if (!k.alias) {
      const owner =
        (k as unknown as { aliasOwner?: string | null }).aliasOwner ??
        this._host?._loadingExtOwner ??
        k.apiVersion.split(".")[0].split("/")[0];
      (k as unknown as { alias: string }).alias = generateAlias(owner, k.kind);
      (k as unknown as { __alias_generated__?: boolean }).__alias_generated__ = true;
    }

    // Two-planes lint (spec D1) — extracted to a helper (F3 spec D3) so
    // the per-scope KindDefinition funnel (registerKindDefinitions)
    // runs the SAME validation.
    KindRegistry._lintPlane(k);

    const key = `${k.apiVersion}\0${k.kind}`;
    if (this.kinds.has(key)) {
      const existing = this.kinds.get(key)!;
      // F3 (spec D3) — declarative ports are ALL the same class
      // (DeclarativeKindPort), so the constructor check below would
      // silently no-op two DIFFERENT descriptors claiming the same key.
      // Real identity on the declarative path is the descriptor digest:
      // same digest → idempotent no-op; different digest → error.
      const existingDecl = (existing as unknown as { __declarative__?: boolean }).__declarative__ === true;
      const newDecl = (k as unknown as { __declarative__?: boolean }).__declarative__ === true;
      if (existingDecl && newDecl) {
        const existingDigest =
          (existing as unknown as { __descriptor_digest__?: string }).__descriptor_digest__ ?? null;
        const newDigest =
          (k as unknown as { __descriptor_digest__?: string }).__descriptor_digest__ ?? null;
        if (existingDigest === newDigest) {
          return;
        }
        throw new KindRegistrationError(
          `Kind (${JSON.stringify(k.apiVersion)}, ${JSON.stringify(k.kind)}) ` +
          `already registered from a DIFFERENT descriptor (existing alias ` +
          `${JSON.stringify(existing.alias)}, new alias ${JSON.stringify(k.alias)}). ` +
          `Two descriptors cannot claim the same (apiVersion, kind) key — ` +
          `pick a distinct apiVersion namespace.`,
        );
      }
      // Idempotent re-registration: same class re-registering is a
      // silent no-op + debug log. A *different* class trying to claim
      // the same key IS still a registration error.
      if (existing.constructor === k.constructor) {
        return;
      }
      throw new KindRegistrationError(
        `Kind (${JSON.stringify(k.apiVersion)}, ${JSON.stringify(k.kind)}) ` +
        `already registered by ${(existing as { constructor?: { name?: string } })?.constructor?.name}; ` +
        `refusing to overwrite with ` +
        `${(k as { constructor?: { name?: string } })?.constructor?.name}. ` +
        `Two extensions cannot share the same (apiVersion, kind) pair.`,
      );
    }

    if (k.alias) {
      for (const [existingKey, existingKind] of this.kinds) {
        if ((existingKind as { alias?: string }).alias === k.alias) {
          throw new KindRegistrationError(
            `Kind alias ${JSON.stringify(k.alias)} already registered by ` +
            `${(existingKind as { constructor?: { name?: string } })?.constructor?.name} ` +
            `(${existingKey.replace("\0", ", ")}); refusing to register ` +
            `${(k as { constructor?: { name?: string } })?.constructor?.name}.`,
          );
        }
      }
    }

    // 6. Kind-NAME collision across apiVersions (i-195, Py twin in
    // Kernel.kind()). Bare-name lookups become ambiguous the moment two
    // apiVersions share a kind name — new extension Kinds must pick a
    // unique name; the legacy Reference pair is allowlisted (shrink-only
    // ratchet, emptied by the Reference-family merge). Collisions where
    // the EXISTING port is a per-scope declarative shadow don't block
    // the extension from claiming its canonical name.
    if (!KIND_NAME_COLLISION_ALLOWLIST.has(k.kind)) {
      for (const [, existingKind] of this.kinds) {
        const p = existingKind as unknown as {
          __declarative__?: boolean; __builtin_descriptor__?: boolean;
        };
        const isExtensionPort =
          p.__declarative__ !== true || p.__builtin_descriptor__ === true;
        if (
          existingKind.kind === k.kind &&
          existingKind.apiVersion !== k.apiVersion &&
          isExtensionPort
        ) {
          throw new KindRegistrationError(
            `Kind NAME ${JSON.stringify(k.kind)} already registered under ` +
            `apiVersion ${JSON.stringify(existingKind.apiVersion)} (alias ` +
            `${JSON.stringify(existingKind.alias)}); refusing ` +
            `${JSON.stringify(k.apiVersion)}. Two apiVersions sharing a ` +
            `kind name makes every bare-name lookup ambiguous — pick a ` +
            `distinct kind name (i-195).`,
          );
        }
      }
    }

    const sd = k.storage as StorageDescriptor | undefined;
    if (sd && sd.pattern === "bundle") {
      const newPair = `${sd.container}\0${sd.marker}`;
      const newSharedOk = Boolean((k as { markerSharedAllowed?: boolean }).markerSharedAllowed);
      for (const [existingKey, existingKind] of this.kinds) {
        const existingSd = (existingKind as { storage?: StorageDescriptor }).storage;
        if (!existingSd || existingSd.pattern !== "bundle") continue;
        const existingPair = `${existingSd.container}\0${existingSd.marker}`;
        if (existingPair !== newPair) continue;
        // H1 — explicit opt-in: only allow shared marker if BOTH
        // colliding Kinds set markerSharedAllowed = true.
        const existingSharedOk = Boolean(
          (existingKind as { markerSharedAllowed?: boolean }).markerSharedAllowed,
        );
        if (newSharedOk && existingSharedOk) {
          continue;
        }
        throw new KindRegistrationError(
          `BUNDLE storage (container=${JSON.stringify(sd.container)}, ` +
          `marker=${JSON.stringify(sd.marker)}) already registered by ` +
          `${(existingKind as { constructor?: { name?: string } })?.constructor?.name} ` +
          `(${existingKey.replace("\0", ", ")}); refusing to register ` +
          `${(k as { constructor?: { name?: string } })?.constructor?.name}. ` +
          `Pick a unique container OR marker — OR set ` +
          `markerSharedAllowed = true on BOTH Kinds AND ensure their ` +
          `Reader.detect() implementations disambiguate at read time.`,
        );
      }
    }

    this.kinds.set(key, k);
    if (this._host) this._host._genericsResolved = false;
    try {
      (k as unknown as { _resolvedDocs?: string | null })._resolvedDocs = loadKindDocs(k);
    } catch {
      (k as unknown as { _resolvedDocs?: string | null })._resolvedDocs = k.docs ?? null;
    }
  }

  /** Two-planes lint (spec D1) — plane is explicit and validated, never
   *  derived. A "record" Kind cannot carry any composition signal;
   *  contradictions fail registration loudly instead of silently
   *  mis-routing the write path.
   *
   *  F3 (spec D3): extracted from `registerKind()` so BOTH funnels run it —
   *  `registerKind()` (extension classes + builtin descriptors) throws;
   *  `registerKindDefinitions` (per-scope) catches → warn + skip
   *  (per-scope docs never take the boot down). Mirrors Python
   *  KindRegistry._lint_plane. */
  static _lintPlane(k: KindPort): void {
    const plane = k.plane ?? "composition";
    if (plane !== "composition" && plane !== "record") {
      throw new KindRegistrationError(
        `Kind ${k.kind} has invalid plane=${JSON.stringify(plane)}; ` +
        `expected 'composition' or 'record'.`,
      );
    }
    if (plane === "record") {
      const contradictions: string[] = [];
      if (k.isPromptTarget) contradictions.push("isPromptTarget=true");
      if (k.flattenInContext) contradictions.push("flattenInContext=true");
      if (k.isSchemaAffecting) {
        contradictions.push("isSchemaAffecting=true");
      }
      if (k.isRoot) contradictions.push("storage.pattern==root");
      if (contradictions.length > 0) {
        throw new KindRegistrationError(
          `Kind ${k.kind} declares plane="record" but carries composition ` +
          `signals: ${contradictions.join(", ")}. Records never compose ` +
          `into agent prompts — drop the signal or remove plane="record".`,
        );
      }
    }
  }

  /** F3 (spec D3): register a BUILTIN Kind from a KindDefinition
   *  descriptor (`kinds/*.kind.yaml` package data). Same format + same
   *  funnel as everything else. Py twin:
   *  `KindRegistry.register_from_descriptor`. */
  registerFromDescriptor(raw: Record<string, unknown>): KindPort {
    const typed = KindDefinitionSchema.parse(raw);
    const port = DeclarativeKindPort.fromTyped(typed);
    (port as unknown as { __builtin_descriptor__?: boolean }).__builtin_descriptor__ = true;
    (port as unknown as { __descriptor_digest__?: string }).__descriptor_digest__ =
      documentHash((raw.spec as Record<string, unknown>) ?? {});
    this.registerKind(port);
    // registerKind() no-ops on an idempotent re-register — hand back
    // whatever is actually registered for the key.
    return this.kinds.get(`${port.apiVersion}\0${port.kind}`)!;
  }

  /** Phase 1 of 2-phase loading: parse KindDefinition docs + register
   *  synthetic DeclarativeKindPorts. Extension-registered kinds win on
   *  conflict. Returns true iff new BUNDLE readers were added (the rescan
   *  gate). Py twin: `KindRegistry.register_kind_definitions`. */
  registerKindDefinitions(rawDocs: Record<string, unknown>[]): boolean {
    const host = this._host!;
    const readersBefore = host._readers.length;
    let registered = false;

    for (const raw of rawDocs) {
      if (raw.apiVersion !== KIND_DEFINITION_API_VERSION) continue;
      if (raw.kind !== KIND_DEFINITION_KIND) continue;

      let typed;
      try {
        typed = KindDefinitionSchema.parse(raw);
      } catch (e) {
        console.warn(`Failed to parse KindDefinition: ${e}`);
        if (host.hooks.has("parse_error")) {
          host.hooks.emit("parse_error", {
            scope: "",
            kind: KIND_DEFINITION_KIND,
            name: ((raw.metadata as Record<string, unknown> | undefined)?.name as string) ?? "",
            data: { error: String(e) },
          });
        }
        continue;
      }

      // Use typed.spec.<field> here: we just Zod-validated the KindDefinition
      // so the typed model is authoritative. The readSpec* helpers exist for
      // code that operates across kinds without knowing the type.
      const key = `${typed.spec.target_api_version}\0${typed.spec.target_kind}`;
      if (this.kinds.has(key)) {
        const existing = this.kinds.get(key)!;
        const isDeclarative = (existing as unknown as { __declarative__?: boolean }).__declarative__ === true;
        const isBuiltinDescriptor =
          (existing as unknown as { __builtin_descriptor__?: boolean }).__builtin_descriptor__ === true;
        if (!isDeclarative || isBuiltinDescriptor) {
          // Extension-registered kind wins on conflict — and so does a
          // BUILTIN descriptor (F3 spec D3: builtin descriptors are
          // extension-registered Kinds that happen to be declarative).
          // PARITY FIX: before F3 this branch fell through for any
          // declarative `existing` and OVERWROTE it — a per-scope
          // KindDefinition would silently replace a builtin (Python
          // skipped instead). Now: skip + warn + kinddef_conflict event.
          console.warn(
            `KindDefinition ${typed.spec.target_api_version}/${typed.spec.target_kind} ` +
              `conflicts with ${isBuiltinDescriptor ? "builtin-descriptor" : "extension-registered"} kind; ` +
              `keeping it and skipping the per-scope declarative port.`,
          );
          host.hooks.emit("kinddef_conflict", {
            scope: "",
            kind: typed.spec.target_kind,
            name: typed.metadata.name,
            data: {
              apiVersion: typed.spec.target_api_version,
              reason: isBuiltinDescriptor ? "builtin_descriptor_wins" : "extension_wins",
            },
          });
          continue;
        }
      }

      let port: DeclarativeKindPort;
      try {
        port = DeclarativeKindPort.fromTyped(typed);
      } catch (e) {
        console.error(
          `Failed to synthesize DeclarativeKindPort for ${typed.spec.target_api_version}/${typed.spec.target_kind}: ${e}`,
        );
        continue;
      }
      // F3 (spec D3): the per-scope funnel writes straight into
      // this.kinds (bypassing registerKind()), so the F1 plane lint never
      // ran here. Run the SAME helper — but warn + skip instead of
      // throwing: per-scope docs never take the boot down (same contract
      // as the parse_error path above).
      try {
        KindRegistry._lintPlane(port);
      } catch (e) {
        console.warn(
          `KindDefinition ${typed.spec.target_api_version}/${typed.spec.target_kind} ` +
            `failed the plane lint: ${e} — skipping registration.`,
        );
        if (host.hooks.has("parse_error")) {
          host.hooks.emit("parse_error", {
            scope: "",
            kind: KIND_DEFINITION_KIND,
            name: typed.metadata.name,
            data: { error: String(e) },
          });
        }
        continue;
      }
      this.kinds.set(key, port);
      host._genericsResolved = false;
      registered = true;
      try {
        (port as unknown as { _resolvedDocs?: string | null })._resolvedDocs = loadKindDocs(port);
      } catch {
        (port as unknown as { _resolvedDocs?: string | null })._resolvedDocs = port.docs ?? null;
      }
    }

    // Re-resolve generic readers/writers for newly declared BUNDLE kinds
    host._ensureGenericReadersWriters();
    return registered && host._readers.length > readersBefore;
  }

  /** Register dynamic kinds from `Module.spec.custom_kinds`. Py twin:
   *  `KindRegistry.register_custom_kinds`. */
  registerCustomKinds(manifest: Record<string, unknown>): void {
    const spec = (manifest.spec as Record<string, unknown>) ?? {};
    const customKinds = (spec.custom_kinds as Record<string, unknown>[]) ?? [];

    for (const ck of customKinds) {
      const av = (ck.apiVersion as string) ?? "custom/v1";
      const kn = (ck.kind as string) ?? "";
      const alias = (ck.alias as string) ?? kn.toLowerCase();
      if (!kn) continue;

      const key = `${av}\0${kn}`;
      if (this.kinds.has(key)) continue;

      this.kinds.set(key, KindRegistry._makeDynamicKind(av, kn, alias));
    }
  }

  static _makeDynamicKind(av: string, kn: string, al: string): KindPort {
    return {
      apiVersion: av,
      kind: kn,
      alias: al,
      origin: "custom",
      isRoot: false,
      isPromptTarget: false,
      promptTargetPriority: 0,
      flattenInContext: false,
      isRuntimeArtifact: false,
      storage: SD.yaml(""),
      depFilters: () => null,
      dependencies: () => null,
      schema: () => null,
      getDefaultAgentName: () => null,
      getLayerPolicies: () => null,
      parse: (raw) => raw,
      describe: () => null,
      summary: () => null,
      promptTemplate: () => null,
    };
  }
}
