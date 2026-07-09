# Type Alias: VetoHandler

```ts
type VetoHandler = (ctx) => void | Promise<void>;
```

Veto listener: sync or async; throwing vetoes the operation.

## Parameters

| Parameter | Type |
| ------ | ------ |
| `ctx` | [`PreSaveContext`](Interface.PreSaveContext.md) |

## Returns

`void` \| `Promise`\<`void`\>
