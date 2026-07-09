# Variable: MAX\_RESOLUTION\_DEPTH

```ts
const MAX_RESOLUTION_DEPTH: 16 = 16;
```

Hard limit on parent_scope chain depth — guards against runaway loops
 (cycle detection runs first, but this is a belt-and-suspenders cap).
