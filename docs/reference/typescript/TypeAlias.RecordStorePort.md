# ~~Type Alias: RecordStorePort~~

```ts
type RecordStorePort = Pick<WritableSourcePort, "saveDocument" | "deleteDocument"> & Required<Pick<SourcePort, "query" | "count">>;
```

## Deprecated

s-sourceport-contract-cleanup — the record-plane contract was
UNIFIED into `WritableSourcePort` (+ the `query`/`count` read half declared
on `SourcePort`). This alias preserves the old name for existing importers;
its shape is exactly the four ops the F2 D2 port formalized:
`saveDocument`/`deleteDocument` (write half) + non-optional `query`/`count`
(read half). The fifth record-plane operation, `search`, still lives on
`RecordSearchProvider` registered on the kernel. New code should reference
`WritableSourcePort` / `SourcePort` directly.
