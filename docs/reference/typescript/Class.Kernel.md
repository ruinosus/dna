# Class: Kernel

DNA SDK v3 — TypeScript entry point.

Re-exports the microkernel (5-port architecture), adapters, and extensions.

## Extended by

- [`Runtime`](Class.Runtime.md)

## Constructors

### Constructor

```ts
new Kernel(opts?): Kernel;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `opts?` | \{ `tenant?`: `string` \| `null`; \} |
| `opts.tenant?` | `string` \| `null` |

#### Returns

`Kernel`

## Properties

### hooks

```ts
readonly hooks: HookRegistry;
```

***

### INHERIT\_PARENT\_SCOPE

```ts
readonly static INHERIT_PARENT_SCOPE: "_lib" = DEFAULT_BASE_SCOPE;
```

***

### tenant

```ts
tenant: string | null = null;
```

Tenant binding (Phase 1 — tenant-as-first-class).

`null` means unbound — only GLOBAL kinds may be written; TENANTED
kinds raise `TenantRequired`. Set via the constructor (Sanity
`withConfig` pattern) or per-call via `withTenant(other)` (Stripe
Connect pattern).

## Accessors

### \_kinds

#### Get Signature

```ts
get _kinds(): Map<string, KindPort>;
```

The registered-Kind dict — proxied to `this._kindreg` so the ~20 inline
 `this._kinds` read sites across the kernel keep working after the Fase 3
 extraction. Key: "apiVersion\0kind". Py twin: `Kernel._kinds` property.

##### Returns

`Map`\<`string`, [`KindPort`](Interface.KindPort.md)\>

***

### activeReaders

#### Get Signature

```ts
get activeReaders(): readonly ReaderPort[];
```

ReaderPorts registered via reader(r). Frozen snapshot — mirror of
 activeWriters (s-dna-rw-roundtrip-suite: the round-trip conformance
 suite enumerates registered pairs through this surface).
 Parity: python Kernel.active_readers.

##### Returns

readonly [`ReaderPort`](Interface.ReaderPort.md)[]

***

### activeSource

#### Get Signature

```ts
get activeSource(): SourcePort | null;
```

The SourcePort registered via source(), or null. Read-only getter.
 The setter method is `source(src)`. Named `activeSource` to avoid
 collision between a method and a property of the same name.
 Parity: python Kernel.active_source.

##### Returns

[`SourcePort`](Interface.SourcePort.md) \| `null`

***

### activeWriters

#### Get Signature

```ts
get activeWriters(): readonly WriterPort[];
```

WriterPorts registered via writer(w). Returns a FROZEN snapshot of
 the internal writer list — mutating the returned array throws in
 strict mode and never affects the Kernel's internal state.
 Parity: python Kernel.active_writers (which returns a tuple).

##### Returns

readonly [`WriterPort`](Interface.WriterPort.md)[]

***

### INHERITABLE\_KINDS

#### Get Signature

```ts
get INHERITABLE_KINDS(): {
  has: boolean;
};
```

`k.INHERITABLE_KINDS.has(kind)` — denylist-backed membership (everything
 inherits EXCEPT NON_INHERITABLE_KINDS). 1:1 with Python _INHERITABLE_KINDS.

##### Returns

```ts
{
  has: boolean;
}
```

###### has()

```ts
has(kind): boolean;
```

###### Parameters

| Parameter | Type |
| ------ | ------ |
| `kind` | `string` |

###### Returns

`boolean`

***

### NON\_INHERITABLE\_KINDS

#### Get Signature

```ts
get NON_INHERITABLE_KINDS(): ReadonlySet<string>;
```

Per-scope ledger + structural Kinds that do NOT inherit across scopes.
 Derived from KindPort.scopeInheritable. 1:1 with Python
 Kernel._NON_INHERITABLE_KINDS.

##### Returns

`ReadonlySet`\<`string`\>

***

### NON\_OVERLAYABLE\_KINDS

#### Get Signature

```ts
get NON_OVERLAYABLE_KINDS(): ReadonlySet<string>;
```

Kinds structurally never overlayable. Derived from KindPort.isOverlayable
 (s-kernel-kindport-classification-attrs). 1:1 with Python
 Kernel._NON_OVERLAYABLE_KINDS.

##### Returns

`ReadonlySet`\<`string`\>

## Methods

### \_catalogScopes()

```ts
_catalogScopes(tenant, opts?): Promise<[string, string | null][]>;
```

Internal — the ordered Catalog scope set for `tenant` (Phase 3b ch1,
i-112 on the Py side). The TS kernel has NO catalog machinery yet
(Genome scan + tenant lockfile — TS parity tracked as `i-185`), so
this hook returns `[]`: the resolver's Catalog splice is fully
implemented but contributes no layers on TS today (see
composition-resolver.ts module docstring, divergence #3).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `tenant` | `string` \| `null` |
| `opts?` | \{ `exclude?`: `Set`\<`string`\>; \} |
| `opts.exclude?` | `Set`\<`string`\> |

#### Returns

`Promise`\<\[`string`, `string` \| `null`\][]\>

***

### \_fillDerivedDescription()

```ts
static _fillDerivedDescription(raw, kindPort): void;
```

If a kind declares `descriptionFallbackField` and metadata.description
is missing/empty, derive it from the named spec field. Mutates `raw`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `raw` | `Record`\<`string`, `unknown`\> |
| `kindPort` | `unknown` |

#### Returns

`void`

***

### \_granularDoc()

```ts
_granularDoc(key): Promise<Record<string, unknown> | null>;
```

Internal — one raw doc for a `(scope, kind, name, tenant)` layer key
(tenant is "" for the base layer). TS twin of the Py
`_granular_doc_cached` MINUS the cache: the TS kernel has no
kernel-level doc cache, so this is a direct source read on every
call. PERF divergence only — same inputs, same outputs (see
composition-resolver.ts module docstring, divergence #1).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `key` | \[`string`, `string`, `string`, `string`\] |

#### Returns

`Promise`\<`Record`\<`string`, `unknown`\> \| `null`\>

***

### \_parseDoc()

```ts
_parseDoc(raw, origin?): Document;
```

#### Parameters

| Parameter | Type | Default value |
| ------ | ------ | ------ |
| `raw` | `Record`\<`string`, `unknown`\> | `undefined` |
| `origin` | `string` | `"local"` |

#### Returns

[`Document`](Class.Document.md)

***

### \_targetLocator()

```ts
_targetLocator(
   scope, 
   kind, 
   name): string;
```

Stable human-readable locator for a document.

- Filesystem sources (detected by the presence of a `baseDir`
  property) → "<baseDir>/<scope>/<kindSubdir>/<name>"
- Other sources → "<scheme>://<scope>/<kind>/<name>" where scheme
  comes from source.urlScheme, falling back to the class name with
  the trailing "source" suffix stripped.

Parity: python Kernel._target_locator.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |
| `name` | `string` |

#### Returns

`string`

***

### cache()

```ts
cache(c): void;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `c` | [`CachePort`](Interface.CachePort.md) |

#### Returns

`void`

***

### compositionProfile()

```ts
compositionProfile(profile): void;
```

Register a composition profile that declares how an orchestrator
 kind connects to other kinds. Called by extensions (e.g.
 HelixExtension) during register().

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `profile` | `CompositionProfile` |

#### Returns

`void`

***

### compositionSummary()

```ts
compositionSummary(scope, opts?): Promise<Record<string, unknown>>;
```

Cheap aggregate of the scope's parent chain + per-Kind local /
inherited / installed counts (Py twin: `Kernel.composition_summary`;
same snake_case wire shape:
`{scope, parent_chain, resources: {Kind: {local, inherited, installed,
total}}}`). The Py twin rides its QueryEngine origin filters; the TS
kernel has no origin machinery, so the three passes are computed here
directly with the SAME dedup semantics (local names shadow catalog +
parent names; catalog names do NOT shadow inherited — mirroring the
three independent origin-filtered queries Python makes). `installed`
is always 0 until the TS catalog surface lands (i-185).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `opts?` | \{ `tenant?`: `string` \| `null`; \} |
| `opts.tenant?` | `string` \| `null` |

#### Returns

`Promise`\<`Record`\<`string`, `unknown`\>\>

***

### computeResolutionChain()

```ts
computeResolutionChain(scope, tenant?): Promise<[string, string | null][]>;
```

Walk `Genome.spec.parent_scope` transitively → ordered resolution
chain of `[scope, tenant]` pairs, HIGHEST priority first:
  [[scope, tenant], [scope, null], [parent, tenant], [parent, null], …]
When `tenant` is null, only base layers are emitted per scope.
Cycle detection via visited set; depth capped at MAX_RESOLUTION_DEPTH;
missing Genome / missing parent_scope terminates the walk (with the
V1 back-compat escalation to `_lib`).
Py twin: `Kernel._compute_resolution_chain`.

#### Parameters

| Parameter | Type | Default value |
| ------ | ------ | ------ |
| `scope` | `string` | `undefined` |
| `tenant` | `string` \| `null` | `null` |

#### Returns

`Promise`\<\[`string`, `string` \| `null`\][]\>

***

### containerForKind()

```ts
containerForKind(kindName): string | null;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kindName` | `string` |

#### Returns

`string` \| `null`

***

### count()

```ts
count(
   scope, 
   kind, 
opts?): Promise<CountResult>;
```

F2 D2 — public aggregation count alongside `query` (TS twin of the
Py `kernel.count`). Push-down to `source.count` (FS: in-memory core).

Returns `CountResult`: `{ total, groups }` — groups by count DESC,
key ASC with `null` last; `groups` is `null` without `groupBy`.

NO origin/inheritance on purpose — records are per-scope (spec D5:
derived views build on top of `kernel.query` in code). Cross-scope
via `scopes` (totals SUMMED, groups MERGED by key and re-sorted;
`scopes` wins over a diverging positional `scope`).

Example (Studio velocity):
  const res = await kernel.count("dna-development", "Story", {
    groupBy: "spec.status",
  });
  // { total: 950, groups: [{ key: "done", count: 700 }, …] }

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |
| `opts` | \{ `filter?`: [`QueryFilter`](TypeAlias.QueryFilter.md); `groupBy?`: `string`; `scopes?`: `string`[]; `tenant?`: `string`; \} |
| `opts.filter?` | [`QueryFilter`](TypeAlias.QueryFilter.md) |
| `opts.groupBy?` | `string` |
| `opts.scopes?` | `string`[] |
| `opts.tenant?` | `string` |

#### Returns

`Promise`\<[`CountResult`](Interface.CountResult.md)\>

***

### deleteDocument()

```ts
deleteDocument(
   scope, 
   kind, 
   name, 
options?): Promise<void>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |
| `name` | `string` |
| `options?` | \{ `author?`: `string`; `layer?`: \[`string`, `string`\]; `skipHooks?`: `boolean`; `tenant?`: `string` \| `null`; \} |
| `options.author?` | `string` |
| `options.layer?` | \[`string`, `string`\] |
| `options.skipHooks?` | `boolean` |
| `options.tenant?` | `string` \| `null` |

#### Returns

`Promise`\<`void`\>

***

### describeKind()

```ts
describeKind(kindName): Record<string, unknown> | null;
```

Summary dict for a registered kind, including resolved docs. Facade
 over `this._kindreg.describe()` (Fase 3).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kindName` | `string` |

#### Returns

`Record`\<`string`, `unknown`\> \| `null`

***

### embeddableKinds()

```ts
embeddableKinds(): Set<string>;
```

F3 D4 (spec 2026-06-10-kinds-descriptor-f3): kind names whose port
 declares `embedFields` — via descriptor `embed:` or a class-level
 `embedFields` (the KindBase parity hook for not-yet-migrated
 classes). Py twin: `Kernel.embeddable_kinds()` (frozenset).

#### Returns

`Set`\<`string`\>

***

### fs()

```ts
fs(f): void;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `f` | [`FSLike`](Interface.FSLike.md) |

#### Returns

`void`

***

### getCompositionRule()

```ts
getCompositionRule(scope, kind): Promise<[string, string, string]>;
```

Resolve the composition rule `[scope_inheritance, merge_strategy,
tenant_overlay]` for (scope, kind) — the scope's
`LayerPolicy.composition_rules[kind]`, else the inherit-by-default
denylist. Py twin: `Kernel._get_composition_rule`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |

#### Returns

`Promise`\<\[`string`, `string`, `string`\]\>

***

### getTool()

```ts
getTool(name): ToolDefinition | null;
```

Return a tool definition by name, or `null` if unknown.
 Py twin: `Kernel.get_tool`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `name` | `string` |

#### Returns

[`ToolDefinition`](Class.ToolDefinition.md) \| `null`

***

### getTools()

```ts
getTools(opts?): ToolDefinition[];
```

Return registered tool definitions, optionally filtered by group(s)
 (`groups: ["read"]` expands the umbrella alias).
 Py twin: `Kernel.get_tools`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `opts` | \{ `group?`: `string` \| `null`; `groups?`: `Iterable`\<`string`, `any`, `any`\> \| `null`; \} |
| `opts.group?` | `string` \| `null` |
| `opts.groups?` | `Iterable`\<`string`, `any`, `any`\> \| `null` |

#### Returns

[`ToolDefinition`](Class.ToolDefinition.md)[]

***

### instance()

```ts
instance(scope, layers?): Promise<ManifestInstance>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `layers?` | `Record`\<`string`, `string`\> |

#### Returns

`Promise`\<[`ManifestInstance`](Class.ManifestInstance.md)\>

***

### kind()

```ts
kind(k): void;
```

Register a Kind (H1 validation funnel). Thin facade over
 `this._kindreg.registerKind()` (Fase 3, s-kernel-decomp-ts-parity —
 the funnel moved into the KindRegistry; Py twin: `Kernel.kind()`
 delegating to `self._kindreg.register_kind`).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `k` | [`KindPort`](Interface.KindPort.md) |

#### Returns

`void`

***

### kindByContainer()

```ts
kindByContainer(container): string | null;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `container` | `string` |

#### Returns

`string` \| `null`

***

### kindFromDescriptor()

```ts
kindFromDescriptor(raw): KindPort;
```

F3 (spec D3): register a BUILTIN Kind from a KindDefinition
 descriptor (`kinds/*.kind.yaml` package data). Thin facade over the
 KindRegistry funnel (Fase 3). Py twin: `Kernel.kind_from_descriptor`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `raw` | `Record`\<`string`, `unknown`\> |

#### Returns

[`KindPort`](Interface.KindPort.md)

***

### kindPortFor()

```ts
kindPortFor(kind, apiVersion?): KindPort | null;
```

Public lookup for a registered KindPort by kind name. Use from
 tooling that needs to consult Kind metadata (isRuntimeArtifact,
 scope, storage, ...) without reaching into Kernel internals. Pass
 apiVersion for exact resolution on ambiguous names (i-195).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kind` | `string` |
| `apiVersion?` | `string` |

#### Returns

[`KindPort`](Interface.KindPort.md) \| `null`

***

### kindPorts()

```ts
kindPorts(): KindPort[];
```

All registered KindPorts. Order matches registration. Facade over
 `this._kindreg.allPorts()` (Fase 3).

#### Returns

[`KindPort`](Interface.KindPort.md)[]

***

### listTemplates()

```ts
listTemplates(): Template[];
```

Aggregate `templates()` from every loaded extension.

The `templates()` method is feature-tested via
`typeof ext.templates === "function"` so extensions that predate
Phase 0 (and don't declare the method) still work. A misbehaving
extension that throws inside its `templates()` is logged to
`console.warn` but never breaks discovery for the other
extensions.

#### Returns

[`Template`](Interface.Template.md)[]

***

### listToolGroups()

```ts
listToolGroups(): Record<string, string[]>;
```

Reverse-build `{group: [toolNames…]}` from the registry.
 Py twin: `Kernel.list_tool_groups`.

#### Returns

`Record`\<`string`, `string`[]\>

***

### load()

```ts
load(ext): void;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `ext` | [`Extension`](Interface.Extension.md) |

#### Returns

`void`

***

### modelProfile()

```ts
modelProfile(modelIdOrAlias): Promise<
  | Document<Record<string, unknown>>
| null>;
```

Resolve a ModelProfile from the `_lib` scope by `model_id` (pass 1)
or `aliases[]` (pass 2). Returns the matching Document or null on miss.

Always queries `MODEL_REGISTRY_SCOPE` ("_lib") directly — ModelProfile
is GLOBAL and NOT in `INHERITABLE_KINDS`; any caller scope is irrelevant.

1:1 parity with Python `Kernel.model_profile(model_id_or_alias)`.

#### Parameters

| Parameter | Type | Description |
| ------ | ------ | ------ |
| `modelIdOrAlias` | `string` | The model_id string or an alias declared in the profile. |

#### Returns

`Promise`\<
  \| [`Document`](Class.Document.md)\<`Record`\<`string`, `unknown`\>\>
  \| `null`\>

The matching Document, or null on miss or error.

***

### on()

```ts
on(hook, fn): void;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `hook` | [`HookNameArg`](TypeAlias.HookNameArg.md) |
| `fn` | (`ctx`) => `void` |

#### Returns

`void`

***

### onVeto()

```ts
onVeto(
   hook, 
   fn, 
   opts?): void;
```

Register a veto listener (e.g. 'pre_save') — throwing vetoes the
 operation. See HookRegistry.onVeto for priority/key semantics.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `hook` | [`HookNameArg`](TypeAlias.HookNameArg.md) |
| `fn` | [`VetoHandler`](TypeAlias.VetoHandler.md) |
| `opts?` | \{ `key?`: `string`; `priority?`: `number`; \} |
| `opts.key?` | `string` |
| `opts.priority?` | `number` |

#### Returns

`void`

***

### personalizeDocument()

```ts
personalizeDocument(
   targetScope, 
   kind, 
   name, 
opts?): Promise<ResolvedDocument>;
```

Clone an inherited doc into `targetScope` as a local override.
Throws when the doc isn't inherited or the target already exists
(without `overwrite`). Py twin: `Kernel.personalize_document`
(bundle-entry payload cloning is Py-only — divergence #4 in
composition-resolver.ts).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `targetScope` | `string` |
| `kind` | `string` |
| `name` | `string` |
| `opts?` | \{ `overwrite?`: `boolean`; `tenant?`: `string` \| `null`; \} |
| `opts.overwrite?` | `boolean` |
| `opts.tenant?` | `string` \| `null` |

#### Returns

`Promise`\<[`ResolvedDocument`](Class.ResolvedDocument.md)\>

***

### previewDocument()

```ts
previewDocument(
   scope, 
   kind, 
   name, 
raw): Promise<PreviewResult>;
```

Pure preview — returns target, serialized files, existsAlready.

Does NOT touch disk. ``existsAlready`` is a UI hint so callers can
render "create" vs "overwrite" affordances. Parity: Python
Kernel.preview_document.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |
| `name` | `string` |
| `raw` | `Record`\<`string`, `unknown`\> |

#### Returns

`Promise`\<`PreviewResult`\>

***

### query()

```ts
query(
   scope, 
   kind, 
opts?): AsyncIterable<Record<string, unknown>>;
```

Kernel-level record query — push-down delegated to `source.query`
(two-planes F2; TS twin of the Py `kernel.query`).

Adds on top of the source:
- Tenant binding auto-stamp: `opts.tenant` > `Kernel.tenant` > unset
  (Stripe Connect pattern, same as writeDocument).
- Cross-scope `scopes` (F2.4): iterates the scopes with per-scope
  queries and CONCATENATES without dedup — records from distinct
  scopes are distinct docs. Mutually exclusive with a diverging
  positional `scope`: `scopes` wins (the positional is ignored).
  `limit`/`offset` apply PER scope.

Divergence from Py (documented): the TS kernel has NO
origin/inheritance machinery (no `origin=` param, no scope-inheritance
chain, no catalog pass) — those live in the Py QueryEngine only.
Records are per-scope, so the record plane loses nothing.

Sources without the optional `query` capability (e.g. PostgresSource
TS, no push-down this phase) raise a clear capability error.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |
| `opts` | \{ `filter?`: [`QueryFilter`](TypeAlias.QueryFilter.md); `limit?`: `number`; `offset?`: `number`; `orderBy?`: `string`[]; `scopes?`: `string`[]; `tenant?`: `string`; \} |
| `opts.filter?` | [`QueryFilter`](TypeAlias.QueryFilter.md) |
| `opts.limit?` | `number` |
| `opts.offset?` | `number` |
| `opts.orderBy?` | `string`[] |
| `opts.scopes?` | `string`[] |
| `opts.tenant?` | `string` |

#### Returns

`AsyncIterable`\<`Record`\<`string`, `unknown`\>\>

***

### reader()

```ts
reader(r): void;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `r` | [`ReaderPort`](Interface.ReaderPort.md) |

#### Returns

`void`

***

### recordSearchProvider()

```ts
recordSearchProvider(provider): void;
```

Register the semantic-search provider (two-planes F2). One per
kernel; later registration replaces (boot-time wiring) and resets
the failure-warning damper (new provider → fresh episode).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `provider` | [`RecordSearchProvider`](Interface.RecordSearchProvider.md) |

#### Returns

`void`

***

### resolveDepFilterTarget()

```ts
resolveDepFilterTarget(value): KindPort | null;
```

Canonical dep_filter target resolution (s-alias-generated-not-typed).

 The CONTRACT is alias-valued dep_filters (`"soulspec-soul"`). The
 legacy `"kind=<Name>"` format resolves through a DEPRECATED shim so
 per-scope KindDefinition docs keep working. Builtin extensions must
 be alias-pure (validateDepFilters rejects `kind=` there). Delegates
 to the shared `resolveDepFilterTargetOver` — since
 s-unify-composition-subsystems the ONE resolver every dep_filter
 reader (`validateRefs` / `mi.composition` / the Kernel) consumes.
 Facade over `this._kindreg.resolveDepFilterTarget()` (Fase 3).
 Py twin: KindRegistry.resolve_dep_filter_target.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `value` | `string` |

#### Returns

[`KindPort`](Interface.KindPort.md) \| `null`

***

### resolveDocument()

```ts
resolveDocument(
   scope, 
   kind, 
   name, 
opts?): Promise<ResolvedDocument>;
```

Resolve a doc through the composition chain — Phase 17 primitive.
Returns `ResolvedDocument` with merged doc + full provenance.
Bootstrap Kinds (Genome, LayerPolicy, KindDefinition) bypass
inheritance entirely (local-only, single-layer provenance).
Py twin: `Kernel.resolve_document`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |
| `name` | `string` |
| `opts?` | \{ `tenant?`: `string` \| `null`; \} |
| `opts.tenant?` | `string` \| `null` |

#### Returns

`Promise`\<[`ResolvedDocument`](Class.ResolvedDocument.md)\>

***

### resolveLayers()

```ts
resolveLayers(mi, layers): Promise<ManifestInstance>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `mi` | [`ManifestInstance`](Class.ManifestInstance.md) |
| `layers` | `Record`\<`string`, `string`\> |

#### Returns

`Promise`\<[`ManifestInstance`](Class.ManifestInstance.md)\>

***

### resolver()

```ts
resolver(scheme, r): void;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scheme` | `string` |
| `r` | [`ResolverPort`](Interface.ResolverPort.md) |

#### Returns

`void`

***

### scaffold()

```ts
scaffold(templateId, opts): string[];
```

Materialize a template by id into `opts.targetRoot`.

Throws `Error("template not found: <id>")` if no loaded extension
advertises a template with the given id (the TS equivalent of
Python's `KeyError`). `opts.onConflict` is passed through to
[materialize](Function.materialize.md).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `templateId` | `string` |
| `opts` | [`MaterializeOptions`](Interface.MaterializeOptions.md) |

#### Returns

`string`[]

***

### search()

```ts
search(
   scope, 
   queryText, 
   opts?): Promise<{
  degraded: boolean;
  hits: Record<string, unknown>[];
}>;
```

Public record search (F2 D2; TS twin of the Py `kernel.search`).
Provider registered → semantic (degraded=false). No provider OR
provider error → lexical token-match fallback over `query()`
(degraded=true; requires `kind` — without it returns empty
degraded). Tenant binding same as `query()`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `queryText` | `string` |
| `opts` | \{ `k?`: `number`; `kind?`: `string` \| `null`; `tenant?`: `string`; \} |
| `opts.k?` | `number` |
| `opts.kind?` | `string` \| `null` |
| `opts.tenant?` | `string` |

#### Returns

`Promise`\<\{
  `degraded`: `boolean`;
  `hits`: `Record`\<`string`, `unknown`\>[];
\}\>

***

### serializeDocument()

```ts
serializeDocument(
   _scope, 
   kind, 
   name, 
   raw): SerializedDocument;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `_scope` | `string` |
| `kind` | `string` |
| `name` | `string` |
| `raw` | `Record`\<`string`, `unknown`\> |

#### Returns

[`SerializedDocument`](Interface.SerializedDocument.md)

***

### source()

```ts
source(s): void;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `s` | [`SourcePort`](Interface.SourcePort.md) |

#### Returns

`void`

***

### storageForKind()

```ts
storageForKind(kindName): StorageDescriptor | null;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kindName` | `string` |

#### Returns

[`StorageDescriptor`](Interface.StorageDescriptor.md) \| `null`

***

### tool()

```ts
tool(td): void;
```

Register a tool definition (delegates to the ToolRegistry;
 last-write-wins on same name). Py twin: `Kernel.tool`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `td` | [`ToolDefinition`](Class.ToolDefinition.md) |

#### Returns

`void`

***

### use()

```ts
use(hook, fn): void;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `hook` | [`HookNameArg`](TypeAlias.HookNameArg.md) |
| `fn` | (`ctx`) => [`HookContext`](Interface.HookContext.md) |

#### Returns

`void`

***

### validateDepFilters()

```ts
validateDepFilters(): void;
```

s-alias-generated-not-typed — every dep_filter target of an
 EXTENSION-registered Kind must resolve to a registered alias.

 Aliases are the wire key of dep_filters / Mustache sections /
 LayerPolicy — a typo used to degrade the prompt SILENTLY (the dep
 just vanished from the context, warning buried in logs). Called at
 the end of `loadBuiltins()` (the TS twin of `Kernel.auto()`).

 - Extension/builtin port with an unknown alias OR the legacy
   `kind=` format → `KindRegistrationError` (boot fails loud).
 - Per-scope declarative ports (user KindDefinition docs) only WARN
   — user docs never take the boot down (same posture as the
   parse_error / plane-lint funnels).
 Facade over `this._kindreg.validateDepFilters()` (Fase 3).
 Py twin: Kernel.validate_dep_filters.

#### Returns

`void`

***

### voicePolicy()

```ts
voicePolicy(name?): Promise<
  | Document<Record<string, unknown>>
| null>;
```

Resolve a VoicePolicy from the `_lib` scope by metadata name.
Returns the matching Document, the first policy as a fallback, or null
on miss/error. Always queries `VOICE_POLICY_SCOPE` ("_lib")
directly — VoicePolicy is GLOBAL and NOT in `INHERITABLE_KINDS`.

1:1 parity with Python `Kernel.voice_policy(name)`.

#### Parameters

| Parameter | Type | Default value |
| ------ | ------ | ------ |
| `name` | `string` | `"default"` |

#### Returns

`Promise`\<
  \| [`Document`](Class.Document.md)\<`Record`\<`string`, `unknown`\>\>
  \| `null`\>

***

### withTenant()

```ts
withTenant(tenant): Kernel;
```

Return a shallow-copy Kernel bound to `tenant`. Original Kernel is
unchanged — call sites can hand off the copy to per-request
handlers without mutating shared state (Sanity `client.withConfig`
pattern).

Pass `tenant=null` to obtain an unbound kernel (writes only allowed
for GLOBAL kinds).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `tenant` | `string` \| `null` |

#### Returns

`Kernel`

***

### writableSource()

```ts
writableSource(ws): void;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `ws` | [`WritableSourcePort`](Interface.WritableSourcePort.md) |

#### Returns

`void`

***

### writeDocument()

```ts
writeDocument(
   scope, 
   kind, 
   name, 
   raw, 
options?): Promise<string>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |
| `name` | `string` |
| `raw` | `Record`\<`string`, `unknown`\> |
| `options?` | \{ `author?`: `string`; `layer?`: \[`string`, `string`\]; `skipHooks?`: `boolean`; `tenant?`: `string` \| `null`; \} |
| `options.author?` | `string` |
| `options.layer?` | \[`string`, `string`\] |
| `options.skipHooks?` | `boolean` |
| `options.tenant?` | `string` \| `null` |

#### Returns

`Promise`\<`string`\>

***

### writer()

```ts
writer(w): void;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `w` | [`WriterPort`](Interface.WriterPort.md) |

#### Returns

`void`
