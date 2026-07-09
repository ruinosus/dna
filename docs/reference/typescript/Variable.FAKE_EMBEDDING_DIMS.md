# Variable: FAKE\_EMBEDDING\_DIMS

```ts
const FAKE_EMBEDDING_DIMS: 384 = 384;
```

Default dimensionality of the fake space. Matches all-MiniLM-L6-v2 (the real
ONNX provider) so swapping providers keeps the vector length — and any
downstream vector-store column width — stable.
