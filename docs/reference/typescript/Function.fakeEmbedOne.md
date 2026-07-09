# Function: fakeEmbedOne()

```ts
function fakeEmbedOne(text, dims?): number[];
```

Deterministic, L2-normalized hash embedding of a single string. Bit-identical
to the Python `fake_embed_one`. Empty/tokenless text → all-zeros (an all-zero
vector is honestly "no signal", never normalized).

## Parameters

| Parameter | Type | Default value |
| ------ | ------ | ------ |
| `text` | `string` | `undefined` |
| `dims` | `number` | `FAKE_EMBEDDING_DIMS` |

## Returns

`number`[]
