# Class: FakeEmbeddingProvider

Zero-dependency `EmbeddingPort` — the offline/CI default. Structurally
satisfies `EmbeddingPort` (`modelId`, `dims`, async `embed`).

## Implements

- [`EmbeddingPort`](Interface.EmbeddingPort.md)

## Constructors

### Constructor

```ts
new FakeEmbeddingProvider(dims?): FakeEmbeddingProvider;
```

#### Parameters

| Parameter | Type | Default value |
| ------ | ------ | ------ |
| `dims` | `number` | `FAKE_EMBEDDING_DIMS` |

#### Returns

`FakeEmbeddingProvider`

## Properties

### dims

```ts
readonly dims: number;
```

#### Implementation of

[`EmbeddingPort`](Interface.EmbeddingPort.md).[`dims`](Interface.EmbeddingPort.md#dims)

***

### modelId

```ts
readonly modelId: "dna-fake-hash-v1" = FAKE_EMBEDDING_MODEL_ID;
```

#### Implementation of

[`EmbeddingPort`](Interface.EmbeddingPort.md).[`modelId`](Interface.EmbeddingPort.md#modelid)

## Methods

### embed()

```ts
embed(texts): Promise<number[][]>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `texts` | `string`[] |

#### Returns

`Promise`\<`number`[][]\>

#### Implementation of

[`EmbeddingPort`](Interface.EmbeddingPort.md).[`embed`](Interface.EmbeddingPort.md#embed)
