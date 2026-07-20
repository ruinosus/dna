# Reference

Information-oriented, exhaustive descriptions of the machinery. Reference is
consulted, not read start-to-finish.

Everything here is **generated from source** — docstrings (Python), the `dna`
command definitions (CLI), and the registered Kinds' own schemas (Kinds). It
therefore **cannot drift from the code**: a regeneration runs in CI on every
change (`scripts/gen_cli_docs.py`, `scripts/gen_kinds_docs.py`, and
mkdocstrings inline).

## Pick your surface

<div class="grid cards" markdown>

-   :material-language-python: **[Python API](python/index.md)**

    The `dna` package — `Kernel`, the five ports, `Document`,
    `ManifestInstance`, the extensions and the `dna.testing` conformance kit.
    Rendered inline from the docstrings by mkdocstrings.

-   :material-console: **[CLI](cli/index.md)**

    The `dna` binary — one page per command group (`sdlc`, `research`,
    `doc`, `scope`, `kind`, `docs`, `source`). Introspected from the Click
    command tree, so `--help` and the docs can never disagree.

-   :material-shape: **[Kinds](kinds/index.md)**

    The registered Kinds and their spec schemas, plus the `KindDefinition`
    descriptor format. Introspected from `Kernel.auto()`.

</div>

!!! info "Reaching DNA from another language"

    There is one runtime and it is Python — so there is one API reference.
    Other languages consume DNA through the **REST** and **MCP** faces
    described in [Microkernel &
    ports](../concepts/microkernel-ports.md#one-runtime-any-language). The
    REST surface is described by `docs/openapi.json`, and the `dna-client`
    packages for TypeScript and Python are **generated from it** — their
    reference is the spec itself.

## The stable read surface

The blessed, documented read/query API (`all`, `one`, `root`,
`default_agent`, `build_prompt`, `resolve`) is walked through narratively in
[How to read document data](../guides/read-document-data.md); the Python tree
above is its exhaustive, machine-generated counterpart. What every source
adapter must implement is in
[How to write a source adapter](../guides/write-a-source-adapter.md).
