# Function: sourceCapabilities()

```ts
function sourceCapabilities(source): SourceCapabilities;
```

THE kernel-side accessor for a source's capabilities (TS twin of the
Py `source_capabilities`). Resolution order (memoized per instance):

1. the adapter's own `capabilities()` returning a
   [SourceCapabilities](Interface.SourceCapabilities.md) — the explicit declaration;
2. DEPRECATED fallback: [deriveCapabilities](Function.deriveCapabilities.md) structural probing,
   with a once-per-constructor console warning pointing at the
   migration (keeps external adapters working).

## Parameters

| Parameter | Type |
| ------ | ------ |
| `source` | `object` |

## Returns

[`SourceCapabilities`](Interface.SourceCapabilities.md)
