# Class: KindDefinitionWriter

Writer for KindDefinition bundles — plain YAML.

## Implements

- [`WriterPort`](Interface.WriterPort.md)

## Constructors

### Constructor

```ts
new KindDefinitionWriter(fs?): KindDefinitionWriter;
```

#### Parameters

| Parameter | Type | Default value |
| ------ | ------ | ------ |
| `fs` | [`FSLike`](Interface.FSLike.md) | `nodeFS` |

#### Returns

`KindDefinitionWriter`

## Properties

### \_kind

```ts
readonly _kind: "KindDefinition" = KIND_DEFINITION_KIND;
```

Exposed for deferred-generic-registration detection.

## Methods

### canWrite()

```ts
canWrite(raw): boolean;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `raw` | `Record`\<`string`, `unknown`\> |

#### Returns

`boolean`

#### Implementation of

[`WriterPort`](Interface.WriterPort.md).[`canWrite`](Interface.WriterPort.md#canwrite)

***

### serialize()

```ts
serialize(raw): SerializedFile[];
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `raw` | `Record`\<`string`, `unknown`\> |

#### Returns

[`SerializedFile`](Interface.SerializedFile.md)[]

#### Implementation of

[`WriterPort`](Interface.WriterPort.md).[`serialize`](Interface.WriterPort.md#serialize)

***

### write()

```ts
write(bundle, raw): void;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `bundle` | [`BundleHandle`](Interface.BundleHandle.md) |
| `raw` | `Record`\<`string`, `unknown`\> |

#### Returns

`void`

#### Implementation of

[`WriterPort`](Interface.WriterPort.md).[`write`](Interface.WriterPort.md#write)
