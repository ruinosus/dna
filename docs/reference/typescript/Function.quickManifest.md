# Function: quickManifest()

```ts
function quickManifest(scope, baseDir?): Promise<ManifestInstance>;
```

Batteries-included shortcut using Runtime: all built-in extensions +
default filesystem source / cache / resolvers, then returns a
`ManifestInstance` for the given scope.

## Parameters

| Parameter | Type | Default value |
| ------ | ------ | ------ |
| `scope` | `string` | `undefined` |
| `baseDir` | `string` | `".dna"` |

## Returns

`Promise`\<[`ManifestInstance`](Class.ManifestInstance.md)\>
