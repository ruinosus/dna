# Function: quickInstance()

```ts
function quickInstance(scope, baseDir?): Promise<ManifestInstance>;
```

Batteries-included shortcut: kernel + all built-in extensions +
default filesystem source / cache / resolvers, then returns a
`ManifestInstance` for the given scope. Equivalent to the old
`Kernel.quick(scope, baseDir)` static method that used to live on
the kernel class itself.

## Parameters

| Parameter | Type | Default value |
| ------ | ------ | ------ |
| `scope` | `string` | `undefined` |
| `baseDir` | `string` | `".dna"` |

## Returns

`Promise`\<[`ManifestInstance`](Class.ManifestInstance.md)\>
