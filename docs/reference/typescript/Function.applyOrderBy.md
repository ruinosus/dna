# Function: applyOrderBy()

```ts
function applyOrderBy(rows, orderBy): Record<string, unknown>[];
```

Stable sort `rows` by each `orderBy` field, last-first to achieve the
desired primary/secondary precedence. Prefixed `-` means descending.
`null` values sort LAST regardless of direction: the None-flag is
`(v === null) !== descending` — immune to the reversed comparator
(i-121: parity with PG `DESC NULLS LAST`; a plain `v === null` flag
would flip under reversal and shove nulls to the FRONT in DESC).

Mixed-type values (number + string across rows on the same field) fall
back to stringified compare to mirror the Py TypeError fallback. Does
not mutate the input. Best-effort like the Py protocol-default —
adapters with native push-down use the backend's type semantics.

## Parameters

| Parameter | Type |
| ------ | ------ |
| `rows` | `Record`\<`string`, `unknown`\>[] |
| `orderBy` | [`QueryOrder`](TypeAlias.QueryOrder.md) |

## Returns

`Record`\<`string`, `unknown`\>[]
