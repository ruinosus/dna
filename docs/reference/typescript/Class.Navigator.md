# Class: Navigator

## Constructors

### Constructor

```ts
new Navigator(host): Navigator;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `host` | [`ManifestInstance`](Class.ManifestInstance.md) |

#### Returns

`Navigator`

## Methods

### describe()

```ts
describe(kind, name): string;
```

Describe a single document.
Equivalent to `mi.describe(kind, name)`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kind` | `string` |
| `name` | `string` |

#### Returns

`string`

***

### inventory()

```ts
inventory(): Record<string, unknown>;
```

Produce a structured inventory of the manifest.
Equivalent to `mi.inventory()`.

#### Returns

`Record`\<`string`, `unknown`\>

***

### renderDoc()

```ts
renderDoc(kind, name): PreviewBlock[];
```

Polymorphic per-kind preview.
Equivalent to `mi.renderDoc(kind, name)`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kind` | `string` |
| `name` | `string` |

#### Returns

[`PreviewBlock`](Interface.PreviewBlock.md)[]

***

### summary()

```ts
summary(): string;
```

Produce a text summary of the manifest.
Equivalent to `mi.summary()`.

#### Returns

`string`
