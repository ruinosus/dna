# Function: deriveCapabilities()

```ts
function deriveCapabilities(source, label): SourceCapabilities;
```

Build a [SourceCapabilities](Interface.SourceCapabilities.md) for `source` by structural probing —
the reflection oracle. In-repo adapters declare literals instead; the
conformance test asserts declaration == derivation.

## Parameters

| Parameter | Type |
| ------ | ------ |
| `source` | `unknown` |
| `label` | `string` |

## Returns

[`SourceCapabilities`](Interface.SourceCapabilities.md)
