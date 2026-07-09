# Class: ToolDefinition

Concrete ToolPort implementation, stored in the kernel's ToolRegistry.
Twin of the Py `ToolDefinition` dataclass — the `callable` init field
holds the framework-native invocable; `getCallable()` is the canonical
accessor (never serialize or wrap-replace it).

## Implements

- [`ToolPort`](Interface.ToolPort.md)

## Constructors

### Constructor

```ts
new ToolDefinition(init): ToolDefinition;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `init` | \{ `argsSchema?`: `Record`\<`string`, `unknown`\>; `callable?`: `unknown`; `description?`: `string`; `group?`: `string` \| `null`; `hitl?`: `boolean`; `name`: `string`; `scope?`: `string` \| `null`; `source?`: `string`; `summary?`: `string`; \} |
| `init.argsSchema?` | `Record`\<`string`, `unknown`\> |
| `init.callable?` | `unknown` |
| `init.description?` | `string` |
| `init.group?` | `string` \| `null` |
| `init.hitl?` | `boolean` |
| `init.name` | `string` |
| `init.scope?` | `string` \| `null` |
| `init.source?` | `string` |
| `init.summary?` | `string` |

#### Returns

`ToolDefinition`

## Properties

### argsSchema

```ts
readonly argsSchema: Record<string, unknown>;
```

JSON Schema of the tool's arguments (best-effort; may be `{}`).

#### Implementation of

[`ToolPort`](Interface.ToolPort.md).[`argsSchema`](Interface.ToolPort.md#argsschema)

***

### description

```ts
readonly description: string;
```

Full docstring / long description.

#### Implementation of

[`ToolPort`](Interface.ToolPort.md).[`description`](Interface.ToolPort.md#description)

***

### group

```ts
readonly group: string | null;
```

Tool group (cognitive | manifest | code | docs | web | write | eval |
 eval_lab | …). `null` = registered but not group-filterable (rare).

#### Implementation of

[`ToolPort`](Interface.ToolPort.md).[`group`](Interface.ToolPort.md#group)

***

### hitl

```ts
readonly hitl: boolean;
```

Write tool that needs a HumanInTheLoop interrupt at the root graph.

#### Implementation of

[`ToolPort`](Interface.ToolPort.md).[`hitl`](Interface.ToolPort.md#hitl)

***

### name

```ts
readonly name: string;
```

#### Implementation of

[`ToolPort`](Interface.ToolPort.md).[`name`](Interface.ToolPort.md#name)

***

### scope

```ts
readonly scope: string | null;
```

Layer-policy hint — "tenant" respects tenant overlay, "global"
 doesn't. Reserved for future use.

#### Implementation of

[`ToolPort`](Interface.ToolPort.md).[`scope`](Interface.ToolPort.md#scope)

***

### source

```ts
readonly source: string;
```

Module file name that defined the tool (best-effort).

#### Implementation of

[`ToolPort`](Interface.ToolPort.md).[`source`](Interface.ToolPort.md#source)

***

### summary

```ts
readonly summary: string;
```

First paragraph of the description.

#### Implementation of

[`ToolPort`](Interface.ToolPort.md).[`summary`](Interface.ToolPort.md#summary)

## Methods

### getCallable()

```ts
getCallable(): unknown;
```

Return the underlying invocable (framework-native tool or function).

#### Returns

`unknown`

#### Implementation of

[`ToolPort`](Interface.ToolPort.md).[`getCallable`](Interface.ToolPort.md#getcallable)
