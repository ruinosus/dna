# Interface: SerializedFile

## Properties

### content?

```ts
optional content?: string;
```

Text content (UTF-8). Mutually exclusive with `contentBytes`.

***

### contentBytes?

```ts
optional contentBytes?: Uint8Array<ArrayBufferLike>;
```

Binary content. Set when the entry is a non-text payload (PNG,
audio, etc). Mutually exclusive with `content`. Introduced in L3
(s-writer-binary-entries 2026-05-25) for parity with Python.

***

### relativePath

```ts
relativePath: string;
```
