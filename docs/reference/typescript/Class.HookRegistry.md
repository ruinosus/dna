# Class: HookRegistry

## Constructors

### Constructor

```ts
new HookRegistry(): HookRegistry;
```

#### Returns

`HookRegistry`

## Properties

### skippedAsyncEmits

```ts
readonly skippedAsyncEmits: Map<string, number>;
```

## Methods

### emit()

```ts
emit(
   hook, 
   ctx, 
   opts?): void;
```

Sync emit. Runs only sync listeners. If async listeners exist for this
hook they CANNOT run here — the caller must use `emitAsync` to reach
them. The skip is loud (s-kernel-fail-soft-audit):

- default: each skipped listener is counted in `skippedAsyncEmits` and
  a console.warn fires once per (hook, listener) — a mis-wired async
  listener is visible, not an invisible no-op.
- `strict: true`: throw instead — for emit sites where skipping a
  listener would be a bug, not lost telemetry.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `hook` | [`HookNameArg`](TypeAlias.HookNameArg.md) |
| `ctx` | [`HookContext`](Interface.HookContext.md) |
| `opts?` | \{ `strict?`: `boolean`; \} |
| `opts.strict?` | `boolean` |

#### Returns

`void`

***

### emitAsync()

```ts
emitAsync(hook, ctx): Promise<void>;
```

Async emit. Runs sync listeners inline, then awaits each async listener.
Use from async call sites (kernel.writeDocument, kernel.deleteDocument).
Errors in any listener are logged and do NOT prevent other listeners.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `hook` | [`HookNameArg`](TypeAlias.HookNameArg.md) |
| `ctx` | [`HookContext`](Interface.HookContext.md) |

#### Returns

`Promise`\<`void`\>

***

### emitVeto()

```ts
emitVeto(hook, ctx): Promise<void>;
```

Run veto listeners for `hook` in priority order. Unlike
`emit`/`emitAsync`, exceptions are NOT swallowed — the first throw
aborts the chain and propagates to the caller (the operation is
vetoed). Listeners may mutate `ctx` in place.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `hook` | [`HookNameArg`](TypeAlias.HookNameArg.md) |
| `ctx` | [`PreSaveContext`](Interface.PreSaveContext.md) |

#### Returns

`Promise`\<`void`\>

***

### has()

```ts
has(hook): boolean;
```

Check if any middleware, events (sync or async) or veto listeners are
 registered.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `hook` | `string` |

#### Returns

`boolean`

***

### hasVeto()

```ts
hasVeto(hook): boolean;
```

Check if any veto listeners are registered for `hook`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `hook` | `string` |

#### Returns

`boolean`

***

### on()

```ts
on(hook, fn): void;
```

Register event subscriber. Fire-and-forget, errors logged but not raised.

Autodetects sync vs async via `fn.constructor.name === "AsyncFunction"`.
Async functions are routed to the async channel — callers using `emit`
(sync) skip them; `emitAsync` runs both.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `hook` | [`HookNameArg`](TypeAlias.HookNameArg.md) |
| `fn` | \| [`EventHandler`](TypeAlias.EventHandler.md) \| [`AsyncEventHandler`](TypeAlias.AsyncEventHandler.md) |

#### Returns

`void`

***

### onAsync()

```ts
onAsync(hook, fn): void;
```

Explicit async-only registration. Prefer `on()` — this is here for
 symmetry and for non-`async function` callables (arrow with Promise
 body, partials) where AsyncFunction detection returns false.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `hook` | [`HookNameArg`](TypeAlias.HookNameArg.md) |
| `fn` | [`AsyncEventHandler`](TypeAlias.AsyncEventHandler.md) |

#### Returns

`void`

***

### onVeto()

```ts
onVeto(
   hook, 
   fn, 
   opts?): void;
```

Register a veto listener on `hook`. Listeners run in ascending
`priority` (ties keep registration order). Throwing from a listener
PROPAGATES to the emitter — that is the veto. Sync and async callables
both work.

`key` (recommended: `"<extension>.<rule>"`) makes registration
idempotent — a second `onVeto` with the same key REPLACES the earlier
listener instead of stacking a duplicate.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `hook` | [`HookNameArg`](TypeAlias.HookNameArg.md) |
| `fn` | [`VetoHandler`](TypeAlias.VetoHandler.md) |
| `opts?` | \{ `key?`: `string`; `priority?`: `number`; \} |
| `opts.key?` | `string` |
| `opts.priority?` | `number` |

#### Returns

`void`

***

### runMiddleware()

```ts
runMiddleware(hook, ctx): HookContext;
```

Run middleware chain. Returns modified context.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `hook` | [`HookNameArg`](TypeAlias.HookNameArg.md) |
| `ctx` | [`HookContext`](Interface.HookContext.md) |

#### Returns

[`HookContext`](Interface.HookContext.md)

***

### use()

```ts
use(hook, fn): void;
```

Register middleware. Called in order, each receives output of previous.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `hook` | [`HookNameArg`](TypeAlias.HookNameArg.md) |
| `fn` | [`Middleware`](TypeAlias.Middleware.md) |

#### Returns

`void`
