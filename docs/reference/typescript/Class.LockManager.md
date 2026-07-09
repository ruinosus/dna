# Class: LockManager

## Constructors

### Constructor

```ts
new LockManager(host): LockManager;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `host` | [`ManifestInstance`](Class.ManifestInstance.md) |

#### Returns

`LockManager`

## Methods

### generate()

```ts
generate(): Lockfile;
```

Generate a lockfile snapshot from the current documents.
Equivalent to `mi.generateLock()`.

#### Returns

[`Lockfile`](Interface.Lockfile.md)
