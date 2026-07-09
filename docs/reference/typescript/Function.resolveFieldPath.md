# Function: resolveFieldPath()

```ts
function resolveFieldPath(doc, path): unknown;
```

Walk a dotted `fieldPath` through `doc`. Unprefixed paths resolve under
`spec.`; `name` is a reserved short for `metadata.name`. Returns `null`
when any segment is missing (never `undefined` — parity with Py `None`).

## Parameters

| Parameter | Type |
| ------ | ------ |
| `doc` | `Record`\<`string`, `unknown`\> |
| `path` | `string` |

## Returns

`unknown`
