# Interface: SourceCapabilities

Typed view of what a source adapter supports — TS twin of the Py
`SourceCapabilities` dataclass (s-sourceport-contract-cleanup).

Adapters DECLARE this explicitly (`capabilities()` returns a literal);
the kernel consults [sourceCapabilities](Function.sourceCapabilities.md) instead of scattering
`typeof src.query === "function"` feature-tests. [deriveCapabilities](Function.deriveCapabilities.md)
(structural probing) survives as (a) the conformance-test oracle that
keeps declarations honest and (b) the deprecated fallback for external
adapters that don't declare yet.

Py-only fields with no TS meaning are omitted on purpose:
`write_kwargs`/`delete_kwargs`/`tenant_layer_writes` exist in Python
because optional kwargs must be probed via `inspect.signature`; the TS
write surface is an options bag, so there is nothing to probe.

## Properties

### bundleRead

```ts
bundleRead: boolean;
```

***

### bundleWrite

```ts
bundleWrite: boolean;
```

***

### drafts

```ts
drafts: boolean;
```

***

### granularList

```ts
granularList: boolean;
```

Implements the L1 granular reads (independent flags on purpose —
 the TS FS source ships `loadOne` but not `listDocRefs`).

***

### granularOne

```ts
granularOne: boolean;
```

***

### kernelAttachable

```ts
kernelAttachable: boolean;
```

***

### layers

```ts
layers: boolean;
```

***

### queryPushdown

```ts
queryPushdown: boolean;
```

Implements `query`/`count` natively (FS: native but in-memory).

***

### source

```ts
source: string;
```

Human-readable adapter label ("filesystem", "postgres", ...).

***

### versions

```ts
versions: boolean;
```
