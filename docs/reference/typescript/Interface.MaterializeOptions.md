# Interface: MaterializeOptions

Options accepted by [materialize](Function.materialize.md).

## Properties

### onConflict?

```ts
readonly optional onConflict?: OnConflict;
```

Conflict policy. Defaults to `"error"`.

***

### targetRoot

```ts
readonly targetRoot: string;
```

Absolute path where files will be written (created if missing).
