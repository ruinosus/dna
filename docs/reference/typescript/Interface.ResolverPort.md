# Interface: ResolverPort

FROM — fetch external deps. v1.0: async (network IO is inherently
async; sync HTTP would block the event loop).

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
