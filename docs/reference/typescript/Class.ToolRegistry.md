# Class: ToolRegistry

Name → ToolDefinition registry with group-aware filtering.

## Constructors

### Constructor

```ts
new ToolRegistry(): ToolRegistry;
```

#### Returns

`ToolRegistry`

## Methods

### get()

```ts
get(name): ToolDefinition | null;
```

Return a tool definition by name, or `null` if unknown.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `name` | `string` |

#### Returns

[`ToolDefinition`](Class.ToolDefinition.md) \| `null`

***

### getMany()

```ts
getMany(opts?): ToolDefinition[];
```

Return registered tool definitions, optionally filtered.

- `{ group: "cognitive" }` — exactly that group
- `{ groups: ["cognitive", "manifest"] }` — union of groups
- `{ groups: ["read"] }` — expands via the 'read' umbrella alias

Pass nothing to get the full catalog. 1:1 with the Py `get_many`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `opts` | \{ `group?`: `string` \| `null`; `groups?`: `Iterable`\<`string`, `any`, `any`\> \| `null`; \} |
| `opts.group?` | `string` \| `null` |
| `opts.groups?` | `Iterable`\<`string`, `any`, `any`\> \| `null` |

#### Returns

[`ToolDefinition`](Class.ToolDefinition.md)[]

***

### groups()

```ts
groups(): Record<string, string[]>;
```

Reverse-build `{group: [toolNames…]}` (names sorted) from the registry.

#### Returns

`Record`\<`string`, `string`[]\>

***

### register()

```ts
register(td): void;
```

Register a tool definition. Last-write-wins on same name (idempotent —
 factory-pattern registrants may re-register on every factory call).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `td` | [`ToolDefinition`](Class.ToolDefinition.md) |

#### Returns

`void`
