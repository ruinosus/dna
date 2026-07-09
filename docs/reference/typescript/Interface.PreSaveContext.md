# Interface: PreSaveContext

Typed context for the `pre_save` veto hook (s-write-path-despecialize).
 Handed to every veto listener BEFORE the document reaches the source
 adapter. `raw` is the live payload — listeners may mutate it in place.
 `kernel` is the kernel the write flows through (tenant-bound copy when
 applicable) so guards can read (getDocument, ...). Throwing vetoes the
 write. Py twin: dna.kernel.hooks.PreSaveContext.

## Properties

### kernel

```ts
kernel: unknown;
```

***

### kind

```ts
kind: string;
```

***

### layer?

```ts
optional layer?: [string, string];
```

***

### name

```ts
name: string;
```

***

### raw

```ts
raw: Record<string, unknown>;
```

***

### scope

```ts
scope: string;
```

***

### tenant

```ts
tenant: string | null;
```
