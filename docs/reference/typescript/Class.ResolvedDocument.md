# Class: ResolvedDocument

Result of `kernel.resolveDocument` — the doc plus full provenance.

 Studio renders banner/badge directly from `provenance` + `isInherited` —
 no client-side detection logic needed.

## Constructors

### Constructor

```ts
new ResolvedDocument(opts): ResolvedDocument;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `opts` | \{ `contributionsByField?`: `Record`\<`string`, `string`\>; `doc`: [`Raw`](TypeAlias.Raw.md) \| `null`; `isInherited`: `boolean`; `provenance`: [`ResolutionPath`](Class.ResolutionPath.md); \} |
| `opts.contributionsByField?` | `Record`\<`string`, `string`\> |
| `opts.doc` | [`Raw`](TypeAlias.Raw.md) \| `null` |
| `opts.isInherited` | `boolean` |
| `opts.provenance` | [`ResolutionPath`](Class.ResolutionPath.md) |

#### Returns

`ResolvedDocument`

## Properties

### contributionsByField

```ts
contributionsByField: Record<string, string>;
```

Field-path → scope name. Populated when merge_strategy=field_level. Lets
 the Detail page show `spec.persona ← _lib` annotations.

***

### doc

```ts
doc: Raw | null;
```

The merged document (or null if not found in any layer).

***

### isInherited

```ts
isInherited: boolean;
```

True when `effectiveLayer.scope != requestedScope`. Convenience derived
 from provenance; Studio uses this for badge/banner toggle.

***

### provenance

```ts
provenance: ResolutionPath;
```

Full ordered resolution path. Includes layers consulted but not
 contributing.

## Methods

### serialize()

```ts
serialize(): Record<string, unknown>;
```

#### Returns

`Record`\<`string`, `unknown`\>
