# Interface: CompositionResult

## Properties

### deferred

```ts
deferred: string[];
```

Refs whose target Kind is plane="record" (two-planes F2.5, spec D6).
Records are excluded from the MI materialization on the Py side, so
the engine can't check them against the doc index — they resolve
lazily via the kernel record plane at read time. Deferred refs are
NOT missing: `isCompositionValid` ignores them.

***

### missing

```ts
missing: string[];
```

***

### resolved

```ts
resolved: string[];
```

***

### warnings

```ts
warnings: string[];
```
