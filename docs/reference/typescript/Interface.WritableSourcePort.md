# Interface: WritableSourcePort

WHERE — load documents from storage.

v1.0 async refactor: read methods return `Promise<...>` so adapters
with non-local backends (Postgres, HTTP, S3) can implement them
naturally. Filesystem adapter wraps sync impls in `Promise.resolve`
for back-compat.

## Extends

- [`SourcePort`](Interface.SourcePort.md)

## Properties

### supportsReaders

```ts
readonly supportsReaders: boolean;
```

#### Inherited from

[`SourcePort`](Interface.SourcePort.md).[`supportsReaders`](Interface.SourcePort.md#supportsreaders)

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

`SourceCapabilities`

#### Inherited from

[`SourcePort`](Interface.SourcePort.md).[`capabilities`](Interface.SourcePort.md#capabilities)

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

#### Inherited from

[`SourcePort`](Interface.SourcePort.md).[`close`](Interface.SourcePort.md#close)

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

#### Inherited from

[`SourcePort`](Interface.SourcePort.md).[`count`](Interface.SourcePort.md#count)

***

### deleteDocument()

```ts
deleteDocument(
   scope, 
   kind, 
   name, 
options?): Promise<void>;
```

Delete a document. Adapters handle the mechanics (rm -rf for
bundle filesystems, DELETE for HTTP, DELETE FROM for SQL, etc.).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |
| `name` | `string` |
| `options?` | \{ `author?`: `string`; `layer?`: \[`string`, `string`\]; `tenant?`: `string` \| `null`; \} |
| `options.author?` | `string` |
| `options.layer?` | \[`string`, `string`\] |
| `options.tenant?` | `string` \| `null` |

#### Returns

`Promise`\<`void`\>

***

### getVersion()?

```ts
optional getVersion(
   scope, 
   kind, 
   name, 
versionId): Promise<Record<string, unknown>>;
```

Optional single-version fetch (the `Versionable` capability;
`PostgresSource` implements it). Mirror of the Py
`WritableSourcePort.get_version`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |
| `name` | `string` |
| `versionId` | `string` |

#### Returns

`Promise`\<`Record`\<`string`, `unknown`\>\>

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

#### Inherited from

[`SourcePort`](Interface.SourcePort.md).[`listDocRefs`](Interface.SourcePort.md#listdocrefs)

***

### listVersions()?

```ts
optional listVersions(
   scope, 
   kind, 
   name): Promise<{
  id: string;
}[]>;
```

Optional version history. Stub adapters return []; real adapters
(Postgres, etc.) return { id: string }[] newest first.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |
| `name` | `string` |

#### Returns

`Promise`\<\{
  `id`: `string`;
\}[]\>

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

#### Inherited from

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

#### Inherited from

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

#### Inherited from

[`SourcePort`](Interface.SourcePort.md).[`loadLayer`](Interface.SourcePort.md#loadlayer)

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

#### Inherited from

[`SourcePort`](Interface.SourcePort.md).[`loadOne`](Interface.SourcePort.md#loadone)

***

### publish()?

```ts
optional publish(
   scope, 
   kind, 
name): Promise<string>;
```

Optional draft→published promotion. Mirror of the Py
`WritableSourcePort.publish`. The TS PG adapter is a documented
single-step no-op (writes go live immediately; no draft state) —
adapters with a real draft store return the published version id.
The Py-only `save_manifest` / `load_drafts` / `list_scopes` half is
a JUSTIFIED asymmetry — see
tests/parity-fixtures/port-surface-parity.json.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |
| `name` | `string` |

#### Returns

`Promise`\<`string`\>

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

#### Inherited from

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

#### Inherited from

[`SourcePort`](Interface.SourcePort.md).[`resolveRef`](Interface.SourcePort.md#resolveref)

***

### saveDocument()

```ts
saveDocument(
   scope, 
   kind, 
   name, 
   raw, 
options?): Promise<string>;
```

Persist a raw document. Adapters decide their own serialization
strategy (filesystem writes bundles, HTTP adapters POST raw JSON,
DB adapters insert rows). Returns an opaque version id; adapters
without real versioning return "1".

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |
| `name` | `string` |
| `raw` | `Record`\<`string`, `unknown`\> |
| `options?` | \{ `author?`: `string`; `layer?`: \[`string`, `string`\]; `tenant?`: `string` \| `null`; \} |
| `options.author?` | `string` |
| `options.layer?` | \[`string`, `string`\] |
| `options.tenant?` | `string` \| `null` |

#### Returns

`Promise`\<`string`\>
