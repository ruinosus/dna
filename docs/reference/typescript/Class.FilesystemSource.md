# Class: FilesystemSource

WHERE — load documents from storage.

v1.0 async refactor: read methods return `Promise<...>` so adapters
with non-local backends (Postgres, HTTP, S3) can implement them
naturally. Filesystem adapter wraps sync impls in `Promise.resolve`
for back-compat.

## Implements

- [`SourcePort`](Interface.SourcePort.md)

## Constructors

### Constructor

```ts
new FilesystemSource(baseDir): FilesystemSource;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `baseDir` | `string` |

#### Returns

`FilesystemSource`

## Properties

### baseDir

```ts
readonly baseDir: string;
```

***

### supportsReaders

```ts
readonly supportsReaders: true = true;
```

#### Implementation of

[`SourcePort`](Interface.SourcePort.md).[`supportsReaders`](Interface.SourcePort.md#supportsreaders)

## Methods

### capabilities()

```ts
capabilities(): SourceCapabilities;
```

Explicit contract declaration (s-sourceport-contract-cleanup) — kept
honest by the adapter conformance test (declaration == structural
derivation). Read-only FS source: in-memory query/count + the L1
granular reads (loadOne + listDocRefs, s-dna-port-surface-parity);
no bundle/write surface on the TS twin yet.

#### Returns

[`SourceCapabilities`](Interface.SourceCapabilities.md)

#### Implementation of

[`SourcePort`](Interface.SourcePort.md).[`capabilities`](Interface.SourcePort.md#capabilities)

***

### close()

```ts
close(): Promise<void>;
```

Documented NO-OP — the FS source holds no pooled resources (each read
opens/closes its own file handles via fs/promises). The member exists
for SourcePort surface parity with Python, where `close` is a
SOURCE_PORT_CORE_MEMBERS boot-gate entry.

#### Returns

`Promise`\<`void`\>

#### Implementation of

[`SourcePort`](Interface.SourcePort.md).[`close`](Interface.SourcePort.md#close)

***

### count()

```ts
count(
   scope, 
   kind, 
opts?): Promise<CountResult>;
```

Two-planes F2 — record-plane count over `loadAll` + `countDocs`
(mirror of the Py protocol-default). Same `opts.tenant` NO-OP
caveat as `query`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |
| `opts` | [`SourceCountOpts`](Interface.SourceCountOpts.md) |

#### Returns

`Promise`\<[`CountResult`](Interface.CountResult.md)\>

#### Implementation of

[`SourcePort`](Interface.SourcePort.md).[`count`](Interface.SourcePort.md#count)

***

### listDocRefs()

```ts
listDocRefs(scope, opts?): Promise<[string, string][]>;
```

L1 granular access — FS impl projects from `loadAll` (mirror of the
Py `FilesystemSource.list_doc_refs`): `[kind, name]` refs only, no
bundle rehydration. No perf gain over `loadAll` on FS, but keeps the
SourcePort contract consistent across adapters (PG is where the gain
lives). Tenant: union of base + overlay with the overlay shadowing
base, same as the Py twin. Result sorted by (kind, name).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `opts?` | \{ `kind?`: `string` \| `null`; `tenant?`: `string` \| `null`; \} |
| `opts.kind?` | `string` \| `null` |
| `opts.tenant?` | `string` \| `null` |

#### Returns

`Promise`\<\[`string`, `string`\][]\>

#### Implementation of

[`SourcePort`](Interface.SourcePort.md).[`listDocRefs`](Interface.SourcePort.md#listdocrefs)

***

### loadAll()

```ts
loadAll(scope, readers?): Promise<Record<string, unknown>[]>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `readers?` | [`ReaderPort`](Interface.ReaderPort.md)[] |

#### Returns

`Promise`\<`Record`\<`string`, `unknown`\>[]\>

#### Implementation of

[`SourcePort`](Interface.SourcePort.md).[`loadAll`](Interface.SourcePort.md#loadall)

***

### loadBootstrapDocs()

```ts
loadBootstrapDocs(scope, opts?): Promise<Record<string, unknown>[]>;
```

Phase 16 — return the docs the kernel needs registered/parsed
BEFORE ``loadAll`` fires (Genome + KindDefinition + LayerPolicy).
Adapters that can filter cheaply (SQL ``WHERE kind IN (...)``)
SHOULD do so. Filesystem adapters MAY return a superset.

Tenant semantics: when ``opts.tenant`` is set, the tenant-published
Genome shadows the platform Genome (Phase 9 multi-tenant
publishing). KindDefinition + LayerPolicy stay platform-only
(non-overlayable per Phase 16).

1:1 parity with Python ``SourcePort.load_bootstrap_docs``.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `opts?` | \{ `tenant?`: `string`; \} |
| `opts.tenant?` | `string` |

#### Returns

`Promise`\<`Record`\<`string`, `unknown`\>[]\>

#### Implementation of

[`SourcePort`](Interface.SourcePort.md).[`loadBootstrapDocs`](Interface.SourcePort.md#loadbootstrapdocs)

***

### loadLayer()

```ts
loadLayer(
   scope, 
   layerId, 
   layerValue, 
readers?): Promise<Record<string, unknown>[]>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `layerId` | `string` |
| `layerValue` | `string` |
| `readers?` | [`ReaderPort`](Interface.ReaderPort.md)[] |

#### Returns

`Promise`\<`Record`\<`string`, `unknown`\>[]\>

#### Implementation of

[`SourcePort`](Interface.SourcePort.md).[`loadLayer`](Interface.SourcePort.md#loadlayer)

***

### loadOne()

```ts
loadOne(
   scope, 
   kind, 
   name, 
opts?): Promise<Record<string, unknown> | null>;
```

L1 granular access — FS impl projects from `loadAll` (mirror of the
Py `FilesystemSource.load_one`). No perf gain over `loadAll` on FS
(cheap in-process disk reads) but keeps the SourcePort contract
consistent across adapters. Tenant overlay shadows base: when
`opts.tenant` is set the tenant layer is consulted first and the
BASE layer is the fallback (same as Python — a tenant read of a doc
with no overlay still returns the base doc).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |
| `name` | `string` |
| `opts?` | \{ `readers?`: [`ReaderPort`](Interface.ReaderPort.md)[]; `tenant?`: `string` \| `null`; \} |
| `opts.readers?` | [`ReaderPort`](Interface.ReaderPort.md)[] |
| `opts.tenant?` | `string` \| `null` |

#### Returns

`Promise`\<`Record`\<`string`, `unknown`\> \| `null`\>

#### Implementation of

[`SourcePort`](Interface.SourcePort.md).[`loadOne`](Interface.SourcePort.md#loadone)

***

### query()

```ts
query(
   scope, 
   kind, 
opts?): AsyncIterable<Record<string, unknown>>;
```

Two-planes F2 — record-plane query over `loadAll` + the shared pure
helpers (mirror of the Py `SourcePort.query` protocol-default). FS
is dev-mode with small scopes; native push-down is the purview of
the SQL adapters.

`opts.tenant` is a documented NO-OP here: the FS TS adapter has no
tenant-aware overlay merge in `loadAll` (divergence from the Py FS
source, which unions base + tenant layer with shadowing) — overlay
support is an F2.5 candidate alongside the writable FS source.

Bundle-format kinds are not visible to this query (no kernel reader
back-ref on the TS source) — record-plane docs are plain YAML.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |
| `opts` | [`SourceQueryOpts`](Interface.SourceQueryOpts.md) |

#### Returns

`AsyncIterable`\<`Record`\<`string`, `unknown`\>\>

#### Implementation of

[`SourcePort`](Interface.SourcePort.md).[`query`](Interface.SourcePort.md#query)

***

### resolveRef()

```ts
resolveRef(scope, ref): Promise<string>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `ref` | `string` |

#### Returns

`Promise`\<`string`\>

#### Implementation of

[`SourcePort`](Interface.SourcePort.md).[`resolveRef`](Interface.SourcePort.md#resolveref)
