# Python API

Generated from the `dna` package docstrings with
[mkdocstrings](https://mkdocstrings.github.io/). The **docstrings in the
source are the single source of truth** — this page cannot drift from the
code because it is rebuilt from it on every `mkdocs build`.

!!! tip "This is one of two sibling trees"

    DNA ships Python and TypeScript SDKs with 1:1 behavioural parity. Their
    reference is **kept per-language, never fused** — the same concept is
    documented against the exact names, types and defaults of each runtime.
    The TypeScript twin lives under [TypeScript API](../typescript/index.md).

## Where to start

- **[Kernel & Runtime](kernel.md)** — the mediator over the five ports, and
  the thin `Runtime` convenience wrapper. This is the object you construct
  (`Kernel.auto()`) and the entry point to everything else.
- **[Document & ManifestInstance](document.md)** — the universal document
  wrapper and the blessed read/query surface (`all`, `one`, `root`,
  `default_agent`, `build_prompt`, `resolve`).
- **[Ports & protocols](ports.md)** — the five port `Protocol`s a host wires
  into the kernel (`SourcePort`, `CachePort`, `ResolverPort`, `ReaderPort`,
  `WriterPort`) plus `KindPort` and the supporting value types.
- **[Extensions](extensions.md)** — the built-in extensions that register
  Kinds (skills, souls, guardrails, SDLC, …).
- **[Testing / conformance kit](testing.md)** — the ship-with-the-SDK
  compliance suites (`dna.testing`) an adapter author runs against their own
  port implementation.

The stable, documented **read surface** is described narratively in
[How to read document data](../../guides/read-document-data.md); this page is
the exhaustive, machine-generated counterpart.
