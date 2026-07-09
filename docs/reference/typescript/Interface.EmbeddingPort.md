# Interface: EmbeddingPort

Sibling port to `RecordSearchProvider` (rsh-memory-similarity-evolution →
rec-embedding-port): turn text into dense vectors so the search plane can do
real similarity instead of the lexical fallback. The kernel core gains NO ML
deps — a real provider (ONNX all-MiniLM-L6-v2 via `@huggingface/transformers`,
an optional peer dep) registers itself on the kernel at app boot; when none
is registered, `kernel.embed()` uses the deterministic hash-based
`FakeEmbeddingProvider` (the zero-dep offline floor that runs in CI).

Parity: the FAKE is bit-exact Py↔TS by construction (integer feature-hashing
+ IEEE-754 ops — see `src/kernel/embedding.ts`); a real ONNX provider is
parity-by-artifact (same model id, cosine ≈ 1). 1:1 with the Py
`EmbeddingPort` Protocol.

Contract:
 - `embed(texts)` returns one vector per input text, each of length `dims`,
   in input order. Empty input → empty array.
 - `dims` is the fixed output dimensionality (same for every vector).
 - `modelId` identifies the embedding space; vectors from providers with
   different `modelId` are NOT comparable.

## Properties

### dims

```ts
readonly dims: number;
```

***

### modelId

```ts
readonly modelId: string;
```

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
