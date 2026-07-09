# Interface: CountResult

Shape returned by `count()` — groups ordered by count DESC, then key
 ASC with `null` last. `groups` is `null` when no `groupBy` was asked.

## Properties

### groups

```ts
groups: 
  | {
  count: number;
  key: unknown;
}[]
  | null;
```

***

### total

```ts
total: number;
```
