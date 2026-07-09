# Class: ResolutionLayer

One step in the resolution chain — a single (scope, tenant) pair consulted
 by the resolver.

 - `found` records whether the source had ANY doc at this layer.
 - `contributed` flips true when this layer ACTUALLY influenced the final
   merged doc (override_full: only the winning layer; field_level: possibly
   several).

## Constructors

### Constructor

```ts
new ResolutionLayer(opts): ResolutionLayer;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `opts` | \{ `contributed?`: `boolean`; `found`: `boolean`; `scope`: `string`; `tenant?`: `string` \| `null`; `versionSha?`: `string` \| `null`; \} |
| `opts.contributed?` | `boolean` |
| `opts.found` | `boolean` |
| `opts.scope` | `string` |
| `opts.tenant?` | `string` \| `null` |
| `opts.versionSha?` | `string` \| `null` |

#### Returns

`ResolutionLayer`

## Properties

### contributed

```ts
readonly contributed: boolean;
```

***

### found

```ts
readonly found: boolean;
```

***

### scope

```ts
readonly scope: string;
```

***

### tenant

```ts
readonly tenant: string | null;
```

***

### versionSha

```ts
readonly versionSha: string | null;
```

Version sha or content hash if the source exposes it (best-effort).
