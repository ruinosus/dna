# Function: serializeRawToFiles()

```ts
function serializeRawToFiles(raw, kernel): readonly SerializedFile[];
```

Turn a raw document into the files a file-based adapter should write.

Pure computation — no I/O, no mutation of `raw`. Adapters compose this
with their filesystem I/O (TauriWritableSource, FilesystemWritableSource
when it ports to TS, etc.).

Internally delegates to `kernel.serializeDocument`, which already
encapsulates the Kind/Writer lookup + StorageDescriptor path prefixing.
Extracting this as a named helper is a contract move: adapters should
import `serializeRawToFiles`, not reach into the Kernel's internals.

The scope argument is intentionally NOT exposed here — scope is a
path-prefix concern the ADAPTER applies. `serializeDocument` treats it
as "" internally, so paths come back relative to the scope root.

## Parameters

| Parameter | Type |
| ------ | ------ |
| `raw` | `Record`\<`string`, `unknown`\> |
| `kernel` | [`Kernel`](Class.Kernel.md) |

## Returns

readonly [`SerializedFile`](Interface.SerializedFile.md)[]
