# Function: queryDocs()

```ts
function queryDocs(
   docs, 
   kind, 
   opts?): Record<string, unknown>[];
```

In-memory query core — mirror of the Py `SourcePort.query`
protocol-default minus the IO: kind filter first (cheap), then
`matchFilter`, then `applyOrderBy`, then limit/offset paging.
`FilesystemSource.query` is `loadAll` + this; the shared parity
fixture drives it directly.

## Parameters

| Parameter | Type |
| ------ | ------ |
| `docs` | `Record`\<`string`, `unknown`\>[] |
| `kind` | `string` |
| `opts` | `Omit`\<[`SourceQueryOpts`](Interface.SourceQueryOpts.md), `"tenant"`\> |

## Returns

`Record`\<`string`, `unknown`\>[]
