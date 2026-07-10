# How-to guides

Task-oriented recipes for people who already know the basics. Each answers a
specific *how do I…?* Read the [Concepts](../concepts/index.md) first if you
want the model behind them; do the [tutorial](../getting-started/first-kind.md)
first if you have never loaded a scope.

## The CLI

- **[A tour of the `dna` CLI](cli-tour.md)** — every command group in five
  minutes, one executed example each, linked to the generated reference.
- **[How to install bundles from a repository](installing-scopes.md)** —
  `dna install github:owner/repo[/subdir][@ref]`: fetch, reader-driven
  detection, validation of untrusted manifests, conflicts, and the
  `installed.lock` provenance record.

## Authoring

- **[How to add a Kind](add-a-kind.md)** — ship a new Kind + Extension (or a
  record-style Kind as pure data) in about thirty minutes.
- **[How to read document data](read-document-data.md)** — the blessed query
  surface: the one documented way to read manifest data in either SDK.

## Adapters and formats

- **[How to write a source adapter](write-a-source-adapter.md)** — implement
  a new storage backend against the port contract, with the conformance kit
  as your safety net.
- **[How to write a Reader/Writer](readers-and-writers.md)** — teach DNA a
  new bundle format and keep the round-trip invariant green.

## Search and memory

- **[How to use semantic recall & memory](semantic-recall.md)** — install
  the extras, search a scope with `dna recall`, drive the memory verbs, and
  register embedding/search providers programmatically.

## Lifecycle

- **[Your git log is your SDLC](sdlc.md)** — how this repo tracks its own
  lifecycle as DNA documents and stamps every commit and PR.
