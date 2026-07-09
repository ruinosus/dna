# Ports &amp; protocols

The kernel is a mediator over **five ports** plus a `KindPort`. Each is a
`typing.Protocol` — a host wires concrete adapters (filesystem, SQLite,
Postgres, …) into the kernel that satisfy these contracts. What every source
adapter must implement is walked through narratively in
[How to write a source adapter](../../guides/write-a-source-adapter.md); the
exhaustive contract is below.

## SourcePort

::: dna.kernel.protocols.SourcePort
    options:
      show_root_heading: true
      show_source: false

## WritableSourcePort

::: dna.kernel.protocols.WritableSourcePort
    options:
      show_root_heading: true
      show_source: false

## CachePort

::: dna.kernel.protocols.CachePort
    options:
      show_root_heading: true
      show_source: false

## ResolverPort

::: dna.kernel.protocols.ResolverPort
    options:
      show_root_heading: true
      show_source: false

## ReaderPort

::: dna.kernel.protocols.ReaderPort
    options:
      show_root_heading: true
      show_source: false

## WriterPort

::: dna.kernel.protocols.WriterPort
    options:
      show_root_heading: true
      show_source: false

## KindPort

::: dna.kernel.protocols.KindPort
    options:
      show_root_heading: true
      show_source: false

## Supporting types

::: dna.kernel.protocols.Extension
    options:
      show_root_heading: true
      show_source: false

::: dna.kernel.protocols.Template
    options:
      show_root_heading: true
      show_source: false

::: dna.kernel.protocols.ToolDefinition
    options:
      show_root_heading: true
      show_source: false

::: dna.kernel.protocols.StorageDescriptor
    options:
      show_root_heading: true
      show_source: false

::: dna.kernel.protocols.StoragePattern
    options:
      show_root_heading: true
      show_source: false
