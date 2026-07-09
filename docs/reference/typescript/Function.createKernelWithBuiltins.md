# Function: createKernelWithBuiltins()

```ts
function createKernelWithBuiltins(): Kernel;
```

Return a fresh Kernel with all six built-in extensions registered.
No source, cache, or resolvers wired — callers are responsible for
that. Use `quickInstance()` if you want the full batteries-included
shortcut.

## Returns

[`Kernel`](Class.Kernel.md)
