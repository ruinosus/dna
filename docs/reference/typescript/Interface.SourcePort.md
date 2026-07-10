# Interface: SourcePort

WHERE — load documents from storage.

v1.0 async refactor: read methods return `Promise<...>` so adapters
with non-local backends (Postgres, HTTP, S3) can implement them
naturally. Filesystem adapter wraps sync impls in `Promise.resolve`
for back-compat.

## Extended by

- [`WritableSourcePort`](Interface.WritableSourcePort.md)

## Properties

### supportsReaders

```ts
readonly supportsReaders: boolean;
```

## Methods

### capabilities()?

```ts
optional capabilities(): SourceCapabilities;
```

OPTIONAL explicit capability declaration (s-sourceport-contract-cleanup)
— a literal `SourceCapabilities` from `kernel/capabilities.ts`. When
absent, `sourceCapabilities()` derives structurally (deprecated path).
Optional so existing third-party implementers stay source-compatible.

#### Returns

[`SourceCapabilities`](Interface.SourceCapabilities.md)

***

### close()?

```ts
optional close(): Promise<void>;
```

Release adapter-held resources (connection pools, file handles, …).
Mirror of the Py `SourcePort.close` (a SOURCE_PORT_CORE_MEMBERS entry
behind the Py boot gate). OPTIONAL on the TS interface — the kernel
treats a missing `close` as a no-op: `FilesystemSource` implements a
documented no-op (nothing to release), `PostgresSource` ends its
owned pool.

#### Returns

`Promise`\<`void`\>

***

### count()?

```ts
optional count(
   scope, 
   kind, 
opts?): Promise<CountResult>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |
| `opts?` | [`SourceCountOpts`](Interface.SourceCountOpts.md) |

#### Returns

`Promise`\<[`CountResult`](Interface.CountResult.md)\>

***

### listDocRefs()?

```ts
optional listDocRefs(scope, opts?): Promise<[string, string][]>;
```

OPTIONAL L1 granular access — `[kind, name]` refs of every doc in
the scope, metadata only (no bundle entries, no parse). Mirror of
the Py `SourcePort.list_doc_refs`. `opts.kind` filters; tenant is
the union of base + overlay with the overlay shadowing base.
Declared via `SourceCapabilities.granularList`
(s-dna-port-surface-parity closed this TS gap).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `opts?` | \{ `kind?`: `string` \| `null`; `tenant?`: `string` \| `null`; \} |
| `opts.kind?` | `string` \| `null` |
| `opts.tenant?` | `string` \| `null` |

#### Returns

`Promise`\<\[`string`, `string`\][]\>

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

***

### loadOne()?

```ts
optional loadOne(
   scope, 
   kind, 
   name, 
opts?): Promise<Record<string, unknown> | null>;
```

OPTIONAL L1 granular access — one raw doc for (scope, kind, name),
tenant overlay shadowing base (mirror of the Py `SourcePort.load_one`).
The Kernel consults `sourceCapabilities(src).granularOne`
(s-sourceport-contract-cleanup) and falls back to `loadAll` + find
(base layer only) when absent — same as the Python
`_granular_doc_cached` legacy-adapter fallback.

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

***

### query()?

```ts
optional query(
   scope, 
   kind, 
opts?): AsyncIterable<Record<string, unknown>>;
```

Two-planes F2 — OPTIONAL record-plane reads. The Kernel consults the
declared capabilities (`sourceCapabilities(src).queryPushdown`,
s-sourceport-contract-cleanup) and raises a clear capability error
otherwise. `FilesystemSource` implements both over `loadAll` + the
pure helpers (`queryDocs`/`countDocs`); PG TS gets no push-down this
phase (Py-only).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |
| `opts?` | [`SourceQueryOpts`](Interface.SourceQueryOpts.md) |

#### Returns

`AsyncIterable`\<`Record`\<`string`, `unknown`\>\>

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
