# Function: createRuntimeWithBuiltins()

```ts
function createRuntimeWithBuiltins(): Runtime;
```

Return a fresh Runtime with all six built-in extensions registered.
No source, cache, or resolvers wired — callers are responsible for
that. Use `quickManifest()` if you want the full batteries-included
shortcut.

## Returns

[`Runtime`](Class.Runtime.md)
