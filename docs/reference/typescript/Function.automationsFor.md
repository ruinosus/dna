# Function: automationsFor()

```ts
function automationsFor(
   instance, 
   triggerType?, 
   opts?): Document<Record<string, unknown>>[];
```

List the scope's Automation docs, filtered for a host executor.

- `triggerType` — keep only automations whose `on.type` matches
  (`"cron"` / `"hook"` / `"tool"`); `null`/omitted returns all.
- `enabledOnly` (default true) — drop docs with `enabled: false`
  (declared but paused; hosts must not fire them).

`instance` is a `ManifestInstance` — the blessed query surface. Source
order is preserved (inherited `_lib` defaults resolve like any other
Kind; a tenant overlay wins per the layer policy).

## Parameters

| Parameter | Type | Default value |
| ------ | ------ | ------ |
| `instance` | `QueryableInstance` | `undefined` |
| `triggerType` | `"cron"` \| `"hook"` \| `"tool"` \| `null` | `null` |
| `opts` | \{ `enabledOnly?`: `boolean`; \} | `{}` |
| `opts.enabledOnly?` | `boolean` | `undefined` |

## Returns

[`Document`](Class.Document.md)\<`Record`\<`string`, `unknown`\>\>[]
