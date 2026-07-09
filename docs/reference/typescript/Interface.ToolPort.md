# Interface: ToolPort

An invocable tool exposed to agents. This port carries the DNA discovery
metadata (group, hitl, scope); the underlying callable stays framework-
native and is never wrapped or serialized.

## Properties

### argsSchema

```ts
readonly argsSchema: Record<string, unknown>;
```

JSON Schema of the tool's arguments (best-effort; may be `{}`).

***

### description

```ts
readonly description: string;
```

Full docstring / long description.

***

### group

```ts
readonly group: string | null;
```

Tool group (cognitive | manifest | code | docs | web | write | eval |
 eval_lab | …). `null` = registered but not group-filterable (rare).

***

### hitl

```ts
readonly hitl: boolean;
```

Write tool that needs a HumanInTheLoop interrupt at the root graph.

***

### name

```ts
readonly name: string;
```

***

### scope

```ts
readonly scope: string | null;
```

Layer-policy hint — "tenant" respects tenant overlay, "global"
 doesn't. Reserved for future use.

***

### source

```ts
readonly source: string;
```

Module file name that defined the tool (best-effort).

***

### summary

```ts
readonly summary: string;
```

First paragraph of the description.

## Methods

### getCallable()

```ts
getCallable(): unknown;
```

Return the underlying invocable (framework-native tool or function).

#### Returns

`unknown`
