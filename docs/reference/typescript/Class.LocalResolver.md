# Class: LocalResolver

FROM — fetch external deps. v1.0: async (network IO is inherently
async; sync HTTP would block the event loop).

## Implements

- [`ResolverPort`](Interface.ResolverPort.md)

## Constructors

### Constructor

```ts
new LocalResolver(baseDir?): LocalResolver;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `baseDir?` | `string` |

#### Returns

`LocalResolver`

## Properties

### baseDir

```ts
readonly baseDir: string | null;
```

## Methods

### cacheKey()

```ts
cacheKey(uri): string;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `uri` | `string` |

#### Returns

`string`

#### Implementation of

[`ResolverPort`](Interface.ResolverPort.md).[`cacheKey`](Interface.ResolverPort.md#cachekey)

***

### resolve()

```ts
resolve(uri, dep): Promise<ResolvedItem[]>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `uri` | `string` |
| `dep` | `Record`\<`string`, `unknown`\> |

#### Returns

`Promise`\<[`ResolvedItem`](Interface.ResolvedItem.md)[]\>

#### Implementation of

[`ResolverPort`](Interface.ResolverPort.md).[`resolve`](Interface.ResolverPort.md#resolve)
