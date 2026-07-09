# Function: deepMerge()

```ts
function deepMerge(base, overlay): Record<string, unknown>;
```

Deep merge two plain objects. Overlay wins.
Lists are replaced (not concatenated), dicts are merged recursively.

## Parameters

| Parameter | Type |
| ------ | ------ |
| `base` | `Record`\<`string`, `unknown`\> |
| `overlay` | `Record`\<`string`, `unknown`\> |

## Returns

`Record`\<`string`, `unknown`\>
