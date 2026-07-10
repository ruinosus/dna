# Class: DefaultLayerResolver

Merges layer overlay documents into base documents, applying policies by kind alias.

Policies map: `{ kind_alias_or_kind_name: LayerPolicy }`
- open: deep merge spec (or add new documents)
- restricted: only override existing keys in spec
- locked: block changes (warn only)

## Constructors

### Constructor

```ts
new DefaultLayerResolver(): DefaultLayerResolver;
```

#### Returns

`DefaultLayerResolver`

## Methods

### resolve()

```ts
resolve(
   baseDocuments, 
   layers, 
   source, 
   scope, 
   policies): Record<string, unknown>[];
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `baseDocuments` | `Record`\<`string`, `unknown`\>[] |
| `layers` | `Record`\<`string`, `string`\> |
| `source` | [`LayerSource`](Interface.LayerSource.md) |
| `scope` | `string` |
| `policies` | `Record`\<`string`, `string`\> |

#### Returns

`Record`\<`string`, `unknown`\>[]
