# Class: CompositionEngine

## Constructors

### Constructor

```ts
new CompositionEngine(host): CompositionEngine;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `host` | [`ManifestInstance`](Class.ManifestInstance.md) |

#### Returns

`CompositionEngine`

## Methods

### consumersOf()

```ts
consumersOf(kind, name): {
  kind: string;
  name: string;
}[];
```

Walk the manifest and return every doc that references this one.
Equivalent to `mi.consumersOf(kind, name)`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kind` | `string` |
| `name` | `string` |

#### Returns

\{
  `kind`: `string`;
  `name`: `string`;
\}[]

***

### dependencyTree()

```ts
dependencyTree(): Record<string, unknown>;
```

Build a dependency tree for the manifest.
Equivalent to `mi.dependencyTree()`.

#### Returns

`Record`\<`string`, `unknown`\>

***

### iterDocDeps()

```ts
iterDocDeps(doc): {
  label: string;
  names: string[];
  targetKind: string;
}[];
```

Iterate a document's declared dep_filters dynamically.
Equivalent to `mi.iterDocDeps(doc)`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `doc` | [`Document`](Class.Document.md) |

#### Returns

\{
  `label`: `string`;
  `names`: `string`[];
  `targetKind`: `string`;
\}[]

***

### validate()

```ts
validate(): CompositionResult;
```

Validate all composition references over the MI plane.
Equivalent to `mi.compositionResult`. Delegates to `validateRefs` —
records are excluded from the MI materialization, so record-target
refs land in `deferred` (they resolve lazily via the kernel record
plane at read time).

#### Returns

[`CompositionResult`](Interface.CompositionResult.md)
