# Function: shouldCapture()

```ts
function shouldCapture(policySpec, eventType): boolean;
```

Check whether *eventType* should be auto-captured per *policySpec*.

Generic policy-evaluation logic (reads a plain EvidencePolicy spec dict),
kernel-owned so the microkernel's capture handler needs no extension
import (s-invert-evidence-capture-dep). EvidenceExtension re-exports this
as its public API.

## Parameters

| Parameter | Type |
| ------ | ------ |
| `policySpec` | `Record`\<`string`, `unknown`\> |
| `eventType` | `string` |

## Returns

`boolean`
