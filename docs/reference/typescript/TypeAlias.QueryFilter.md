# Type Alias: QueryFilter

```ts
type QueryFilter = Record<string, unknown>;
```

Filter shape — dict of dotted `field_path` → expected value.

  { "status": "in-progress" }                  // shorthand equality
  { "status": { "in": ["todo", "done"] } }     // operator form
  { "spec.priority": { "gte": 2 } }

Unprefixed paths resolve under `spec.`; `name` is a reserved short for
`metadata.name`. Implicit AND across keys; no OR (issue two queries).
