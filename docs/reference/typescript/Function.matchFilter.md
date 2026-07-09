# Function: matchFilter()

```ts
function matchFilter(doc, filter): boolean;
```

Evaluate a `QueryFilter` against a single doc. Unknown operators throw
`QueryError` so callers can debug instead of silently matching. 1:1
port of the Py `_match_filter` (only single-key dicts enter the
operator branch; anything else is shorthand equality).

## Parameters

| Parameter | Type |
| ------ | ------ |
| `doc` | `Record`\<`string`, `unknown`\> |
| `filter` | [`QueryFilter`](TypeAlias.QueryFilter.md) |

## Returns

`boolean`
