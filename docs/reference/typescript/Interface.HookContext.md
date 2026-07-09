# Interface: HookContext

## Properties

### agent?

```ts
optional agent?: string;
```

***

### data

```ts
data: Record<string, unknown>;
```

***

### kind?

```ts
optional kind?: string;
```

***

### layer?

```ts
optional layer?: [string, string];
```

Optional layer tuple when the write targeted a layer overlay.
 `undefined` means the write went to the scope's base. Set by
 Kernel.writeDocument when a layer kwarg is passed (Phase 2a.0).

***

### name?

```ts
optional name?: string;
```

***

### prompt?

```ts
optional prompt?: string;
```

***

### scope

```ts
scope: string;
```
