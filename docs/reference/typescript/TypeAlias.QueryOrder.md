# Type Alias: QueryOrder

```ts
type QueryOrder = string[];
```

Ordering — list of field paths optionally prefixed with `-` for
descending. Applied in declaration order. `null`/missing values sort
LAST regardless of direction (parity with PG `DESC NULLS LAST`; the Py
side was fixed in i-121 — TS is born correct).
