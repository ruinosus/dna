# Class: ResolutionPath

Ordered list of layers consulted, highest-priority-first.

 Layer order is:
   [local+tenant, local+base, parent+tenant, parent+base,
    grandparent+tenant, grandparent+base, ...]
 The HIGHEST priority layer is first — local-tenant beats everything else.

## Constructors

### Constructor

```ts
new ResolutionPath(steps?): ResolutionPath;
```

#### Parameters

| Parameter | Type | Default value |
| ------ | ------ | ------ |
| `steps` | [`ResolutionLayer`](Class.ResolutionLayer.md)[] | `[]` |

#### Returns

`ResolutionPath`

## Properties

### steps

```ts
steps: ResolutionLayer[];
```

## Accessors

### effectiveLayer

#### Get Signature

```ts
get effectiveLayer(): ResolutionLayer | null;
```

The single layer that became the doc's primary origin. For override_full
 this is the layer whose doc was returned wholesale; for field_level it is
 the highest-priority layer that contributed metadata/envelope (semantic
 primary owner).

##### Returns

[`ResolutionLayer`](Class.ResolutionLayer.md) \| `null`

## Methods

### serialize()

```ts
serialize(): Record<string, unknown>;
```

JSON-friendly serialization for HTTP responses (snake_case = Python).

#### Returns

`Record`\<`string`, `unknown`\>
