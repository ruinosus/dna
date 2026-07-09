# Interface: ExtensionHost

The registration-time surface the Kernel offers to `Extension.register()`.

This is the *explicit contract* of what an extension may call while it is
being loaded (s-dna-extension-host-contract). It is a narrow slice of the
Kernel — the registration vocabulary — NOT the whole Kernel API. Derived
from actual usage across every builtin extension:

- `kind(kp)`              — register a KindPort (identity + composition)
- `kindFromDescriptor()`  — register a record Kind from a
                            `kinds/*.kind.yaml` descriptor (F3 — Kinds as
                            data). Pair with `loadDescriptors()` from
                            `./descriptor-loader.js`.
- `reader(r)`             — register a ReaderPort (detect/scan a format)
- `writer(w)`             — register a WriterPort (write a format)
- `on(hook, fn)`          — subscribe to an event (e.g. `post_save`)
- `onVeto(hook, fn)`      — register a veto listener (e.g. `pre_save`
                            write guards — throwing vetoes the operation)
- `tool(td)`              — register a ToolDefinition (DNA tool discovery
                            metadata; queried via `kernel.getTools()`)
- `compositionProfile()`  — register orchestrator kind wiring
- `hooks`                 — the HookRegistry itself, for advanced listener
                            management (`kernel.hooks.onVeto(..., {key})`)

The real `Kernel` satisfies this interface structurally (statically
asserted in `tests/extension-host-contract.test.ts`). Py twin:
`ExtensionHost` in `dna/kernel/protocols.py`.

## Properties

### hooks

```ts
readonly hooks: HookRegistry;
```

The HookRegistry the `on`/`onVeto` conveniences delegate to.

## Methods

### compositionProfile()

```ts
compositionProfile(profile): void;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `profile` | `CompositionProfile` |

#### Returns

`void`

***

### kind()

```ts
kind(kp): void;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kp` | [`KindPort`](Interface.KindPort.md) |

#### Returns

`void`

***

### kindFromDescriptor()

```ts
kindFromDescriptor(raw): KindPort;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `raw` | `Record`\<`string`, `unknown`\> |

#### Returns

[`KindPort`](Interface.KindPort.md)

***

### on()

```ts
on(hook, fn): void;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `hook` | [`HookNameArg`](TypeAlias.HookNameArg.md) |
| `fn` | (`ctx`) => `void` |

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

### reader()

```ts
reader(r): void;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `r` | [`ReaderPort`](Interface.ReaderPort.md) |

#### Returns

`void`

***

### tool()

```ts
tool(td): void;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `td` | [`ToolDefinition`](Class.ToolDefinition.md) |

#### Returns

`void`

***

### writer()

```ts
writer(w): void;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `w` | [`WriterPort`](Interface.WriterPort.md) |

#### Returns

`void`
