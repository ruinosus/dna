# Running the conformance kit

DNA makes two strong claims:

1. It consumes real marketplace bundles **byte-faithful**, under their
   owners' namespaces — no lossy import.
2. The Python and TypeScript SDKs are **behaviorally identical**.

Neither is aspirational. Both are enforced by test suites you can run
yourself. This tutorial walks you through the two that matter most.

## The market-conformance suite

The market-conformance suite runs the full pipeline — scan → typed access →
prompt composition → write round-trip — against **real marketplace Skills**
(copied verbatim from Anthropic and community collections), the
`openai/codex` `AGENTS.md`, and the soulspec starter templates. The write
round-trip must come back **byte-identical**.

The live fixtures are in
[`scopes/market-integration/`](https://github.com/ruinosus/dna/tree/main/scopes/market-integration);
their provenance is recorded in
[`tests/market-fixtures/NOTICE.md`](https://github.com/ruinosus/dna/blob/main/tests/market-fixtures/NOTICE.md).

=== "Python"

    ```bash
    cd packages/sdk-py && uv sync
    uv run pytest tests/test_market_conformance.py -v
    ```

=== "TypeScript"

    ```bash
    cd packages/sdk-ts && bun install
    bun test market-conformance
    ```

A green run is the proof behind [Market
fidelity](../concepts/market-fidelity.md): DNA read someone else's format,
gave you typed access to it, composed it into a prompt, and wrote it back
without changing a byte.

## The round-trip invariant

The deeper property under that suite is a **fixpoint**: for any bundle, the
writer re-emits exactly what the reader read, and `emit → read → emit`
reaches a fixed point (the first write is the only normalization that ever
happens). Every registered Reader/Writer pair is held to it by the
`reader_writer_conformance_suite` that ships *inside* the SDK — so
third-party format authors run the same battery. See [How to write a
Reader/Writer](../guides/readers-and-writers.md).

## The source conformance kit

Storage backends have their own kit. The port-contract suite runs the same
battery over every source adapter (Filesystem, SQLite, Postgres,
SQLAlchemy), so a new adapter is "production-ready" only when its row is
fully green.

=== "Python"

    ```bash
    # Filesystem + SQLite (always available)
    cd packages/sdk-py && uv run pytest tests/test_port_contract.py -v

    # Add Postgres (requires a running DB)
    DATABASE_URL=postgresql://dna:dna@localhost:5432/dna \
      uv run pytest tests/test_port_contract.py -v
    ```

Postgres cases skip cleanly when `DATABASE_URL` is unset. The full recipe
for authoring a new adapter against this kit is [How to write a source
adapter](../guides/write-a-source-adapter.md).

## Cross-SDK parity

Parity between the Python and TypeScript SDKs is enforced by **shared
fixtures**: descriptor files are byte-identical and hash-checked, and a
kind-registry parity manifest fails the suite on undocumented drift. The
same `hello-genome` example is run by both SDKs' suites and asserted to
produce the same documents and the same composed prompt.

That parity is why the [tutorial](first-kind.md) can honestly show one set of
expected output for two languages: it is a test-enforced invariant, not a
coincidence.
