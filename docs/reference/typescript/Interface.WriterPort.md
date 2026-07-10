# Interface: WriterPort

Writes a raw dict back to a bundle directory. Inverse of ReaderPort.

v1.0 BundleHandle migration: write signature takes BundleHandle
(was: filesystem path string). Adapters provide the right handle
for their backend; the writer's job is purely to format files into
`bundle.writeText/writeBytes` calls.

s-dna-rw-roundtrip-suite: `serialize` is REQUIRED — part of the
contract (it was load-bearing but optional: `kernel.serializeDocument`
consumed it behind a presence check, so a conforming writer could
silently miss it and only fail at emission time). `write` and
`serialize` must stay COHERENT: `write(bundle, raw)` must produce
exactly the entries `serialize(raw)` returns. The round-trip
conformance suite enforces this for every registered pair.
Python twin: `WriterPort.serialize` returning
`[{relativePath, content | content_bytes}]`.

## Methods

### canWrite()

```ts
canWrite(raw): boolean;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `raw` | `Record`\<`string`, `unknown`\> |

#### Returns

`boolean`

***

### serialize()

```ts
serialize(raw): SerializedFile[];
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `raw` | `Record`\<`string`, `unknown`\> |

#### Returns

[`SerializedFile`](Interface.SerializedFile.md)[]

***

### write()

```ts
write(bundle, raw): void | Promise<void>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `bundle` | [`BundleHandle`](Interface.BundleHandle.md) |
| `raw` | `Record`\<`string`, `unknown`\> |

#### Returns

`void` \| `Promise`\<`void`\>
