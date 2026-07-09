# Class: KindDefinitionReader

Reader for `kinds/<name>/KIND.yaml` — plain YAML, not frontmatter+body.

## Implements

- [`ReaderPort`](Interface.ReaderPort.md)

## Constructors

### Constructor

```ts
new KindDefinitionReader(fs?): KindDefinitionReader;
```

#### Parameters

| Parameter | Type | Default value |
| ------ | ------ | ------ |
| `fs` | [`FSLike`](Interface.FSLike.md) | `nodeFS` |

#### Returns

`KindDefinitionReader`

## Properties

### \_marker

```ts
readonly _marker: "KIND.yaml" = "KIND.yaml";
```

Exposed for deferred-generic-registration detection.

## Methods

### detect()

```ts
detect(bundle): boolean;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `bundle` | `BundleHandle` |

#### Returns

`boolean`

#### Implementation of

[`ReaderPort`](Interface.ReaderPort.md).[`detect`](Interface.ReaderPort.md#detect)

***

### read()

```ts
read(bundle): Record<string, unknown>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `bundle` | `BundleHandle` |

#### Returns

`Record`\<`string`, `unknown`\>

#### Implementation of

[`ReaderPort`](Interface.ReaderPort.md).[`read`](Interface.ReaderPort.md#read)
