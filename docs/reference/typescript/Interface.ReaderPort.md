# Interface: ReaderPort

Reads a bundle directory and produces a raw dict.

v1.0 BundleHandle migration: signatures take a `BundleHandle`
instead of a filesystem path string, so adapters with non-FS
backends (Postgres, in-memory) can rehydrate bundles uniformly.

Methods are async because backends may need to fetch entries
from a network/database. Filesystem readers can return
`Promise.resolve(...)` if their existing impl is sync.

## Properties

### \_ownerContainer?

```ts
readonly optional _ownerContainer?: string;
```

Container this Reader's Kind is rooted at (e.g. `"skills"`), or
 undefined for unscoped readers (tried as fallback in every
 container). Lets the scanner route bundles to the right Reader
 without trying every reader's `detect()` on every subdir — H3
 container-aware routing. Formal port member since
 s-dna-rw-roundtrip-suite (the scanner previously duck-typed it);
 Python twin: `ReaderPort._owner_container` (default None).

## Methods

### detect()

```ts
detect(bundle): boolean | Promise<boolean>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `bundle` | `BundleHandle` |

#### Returns

`boolean` \| `Promise`\<`boolean`\>

***

### read()

```ts
read(bundle): 
  | Record<string, unknown>
| Promise<Record<string, unknown>>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `bundle` | `BundleHandle` |

#### Returns

  \| `Record`\<`string`, `unknown`\>
  \| `Promise`\<`Record`\<`string`, `unknown`\>\>
