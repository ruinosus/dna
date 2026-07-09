# Function: mergeOverrideFull()

```ts
function mergeOverrideFull(contributions): [Raw | null, ResolutionLayer | null];
```

First non-null contribution wins entirely.

 Used for assetic Kinds (LottieAsset, ImagePrompt) where partial override
 makes no sense (binary payload is atomic).

 Input: contributions highest-priority-first.
 Output: [winningRawDoc, winningLayer] or [null, null] if all miss.

## Parameters

| Parameter | Type |
| ------ | ------ |
| `contributions` | [`Contribution`](TypeAlias.Contribution.md)[] |

## Returns

\[`Raw` \| `null`, [`ResolutionLayer`](Class.ResolutionLayer.md) \| `null`\]
