# Reference

Information-oriented, exhaustive descriptions of the machinery. Reference is
consulted, not read start-to-finish.

!!! note "Coming soon — generated from source"

    The reference section is being built in a **later wave** and is
    deliberately empty for now. It will be **generated from source**, not
    written by hand, so it cannot drift from the code:

    - **Python API** — from the `dna` package docstrings.
    - **TypeScript API** — from the `@dna/sdk` public surface.
    - **CLI** — the `dna` command reference, generated from the command
      definitions (so `--help` and the docs can never disagree).
    - **Parity matrix** — a *language × requirement* grid generated from the
      byte-parity conformance suite: published proof of what each SDK
      implements, in the spirit of the OpenTelemetry spec-compliance matrix.

    This page is a reserved slot in the navigation so links to it stay
    stable once the generated reference lands.

!!! success "Available now — the parity matrix"

    The first generated reference page has landed:
    **[Parity matrix — Python × TypeScript](parity-matrix.md)** — a
    *member × language* grid generated from the byte-parity fixtures that CI
    enforces, in the spirit of the OpenTelemetry spec-compliance matrix.

## In the meantime

The current source of truth for the API is the code and its tests:

- **Python SDK** — [`packages/sdk-py`](https://github.com/ruinosus/dna/tree/main/packages/sdk-py)
  (`import dna`).
- **TypeScript SDK** — [`packages/sdk-ts`](https://github.com/ruinosus/dna/tree/main/packages/sdk-ts)
  (`@dna/sdk`).
- **CLI** — [`packages/cli`](https://github.com/ruinosus/dna/tree/main/packages/cli)
  (the `dna` binary).
- **Blessed query surface** — the stable, documented read API is described
  in [How to read document data](../guides/read-document-data.md).
- **Port contract** — what every source adapter must implement is in
  [How to write a source adapter](../guides/write-a-source-adapter.md).
