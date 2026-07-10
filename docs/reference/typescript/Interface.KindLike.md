# Interface: KindLike

Resource — self-aware document wrapper that knows its own dependencies.

Replaces Document with added kindRef linkage: a Resource can resolve
its own dep_filters via `deps()` without needing the full ManifestInstance.

## Properties

### alias

```ts
readonly alias: string;
```

***

### apiVersion

```ts
readonly apiVersion: string;
```

***

### kind

```ts
readonly kind: string;
```

## Methods

### depFilters()

```ts
depFilters(): Record<string, string> | null;
```

#### Returns

`Record`\<`string`, `string`\> \| `null`
