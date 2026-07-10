# Function: triggerKey()

```ts
function triggerKey(doc): string | null;
```

The trigger's identifying value: the cron expression (`cron`), the
hook name (`hook`) or the dispatch tool name (`tool`). Null when the
trigger is missing/unknown.

## Parameters

| Parameter | Type |
| ------ | ------ |
| `doc` | [`Document`](Class.Document.md) |

## Returns

`string` \| `null`
