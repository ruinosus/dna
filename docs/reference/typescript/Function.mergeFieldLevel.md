# Function: mergeFieldLevel()

```ts
function mergeFieldLevel(contributions): [Raw | null, ResolutionLayer | null, Record<string, string>];
```

Deep-merge `spec` dicts. Higher-priority layers shadow lower per-field.
 Returns [mergedDoc, primaryOriginLayer, fieldsByOrigin].

 Algorithm:
   - First pass: find the PRIMARY layer (highest-priority hit). Its metadata
     + envelope (apiVersion, kind) carry over wholesale.
   - Second pass: iterate contributions LOWEST → HIGHEST priority, overwriting
     spec keys in a fresh merged dict. After the loop the highest-priority
     layer's values win per-field.
   - Track which layer each FINAL spec field came from so the UI can render
     `spec.persona ← _lib` annotations.

 Edge cases:
   - All-null contributions → [null, null, {}].
   - Single hit → equivalent to override_full.
   - Spec missing or non-object → that layer skipped silently.

## Parameters

| Parameter | Type |
| ------ | ------ |
| `contributions` | [`Contribution`](TypeAlias.Contribution.md)[] |

## Returns

\[`Raw` \| `null`, [`ResolutionLayer`](Class.ResolutionLayer.md) \| `null`, `Record`\<`string`, `string`\>\]
