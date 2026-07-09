# Function: countDocs()

```ts
function countDocs(
   docs, 
   kind, 
   opts?): CountResult;
```

In-memory count core — mirror of the Py `SourcePort.count`
protocol-default: total of docs matching the filter, optionally
grouped by a field path. Groups ordered by count DESC, then key ASC
with `null` LAST (matches PG `ORDER BY count DESC, key ASC NULLS
LAST` and the spirit of i-121).

## Parameters

| Parameter | Type |
| ------ | ------ |
| `docs` | `Record`\<`string`, `unknown`\>[] |
| `kind` | `string` |
| `opts` | `Omit`\<[`SourceCountOpts`](Interface.SourceCountOpts.md), `"tenant"`\> |

## Returns

[`CountResult`](Interface.CountResult.md)
