# Function: automationTriggerGuard()

```ts
function automationTriggerGuard(ctx): void;
```

Veto an Automation write that is not fully valid.

Checks the semantics JSON Schema cannot express (cron grammar,
hook-name vocabulary). Schema SHAPE is validated by the kernel's
generic write-path step (s-write-path-validation, i-008), which runs
after the veto hooks — this guard no longer duplicates it.

## Parameters

| Parameter | Type |
| ------ | ------ |
| `ctx` | [`PreSaveContext`](Interface.PreSaveContext.md) |

## Returns

`void`
