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
battery over every source adapter (Filesystem and `SqlAlchemySource` on
both of its dialects — sqlite and postgres), so a new adapter is
"production-ready" only when its row is fully green.

=== "Python"

    ```bash
    # Filesystem + the sqlite dialect (always available)
    cd packages/sdk-py && uv run pytest tests/test_port_contract.py -v

    # Add the postgres dialect (requires a running DB)
    DATABASE_URL=postgresql://dna:dna@localhost:5432/dna \
      uv run pytest tests/test_port_contract.py -v
    ```

Postgres cases skip cleanly when `DATABASE_URL` is unset. The full recipe
for authoring a new adapter against this kit is [How to write a source
adapter](../guides/write-a-source-adapter.md).

## The record-search conformance kit

`RecordSearchProvider` is the search plane's port: the kernel ships it with an
honest lexical fallback, and any real implementation must pass one shared
behavioral battery — `record_search_conformance_suite` (Python) /
`recordSearchConformanceSuite` (TypeScript). It runs a provider through its OWN
`index` / `search` / `delete` surface and asserts relative ranking, kind and
tenant filtering (overlay shadows base), the `k` limit, idempotent re-indexing,
and empty-query handling. The same suite that grades the embeddable sqlite-vec
provider today will grade a pgvector provider tomorrow.

The default provider — `SqliteVecRecordSearchProvider` — is **embeddable and
offline**: one SQLite file per scope, dense KNN via the
[sqlite-vec](https://github.com/asg017/sqlite-vec) `vec0` virtual table, lexical
BM25 via FTS5, fused with Reciprocal Rank Fusion (a pure, Py↔TS-identical
function). Its store schema is owned by a numbered migration, and it embeds
through `kernel.embed()` — the deterministic `FakeEmbeddingProvider` floor by
default, so the whole suite runs in CI with no network and no model download.

sqlite-vec is a loadable C extension delivered as an **opt-in extra**:

=== "Python"

    ```bash
    pip install "dna-sdk[search-sqlite]"    # brings the `sqlite-vec` package
    cd packages/sdk-py && uv run pytest tests/test_record_search_conformance.py -v
    ```

    The extension is loaded per connection via the `sqlite-vec` package
    (`enable_load_extension` + `sqlite_vec.load`); the conformance test
    `importorskip`s when the extra is absent.

=== "TypeScript"

    ```bash
    cd packages/sdk-ts && bun add sqlite-vec && bun test record-search-conformance
    ```

    The driver (`src/adapters/search/driver.ts`) loads the extension through
    `bun:sqlite` (test runner) or `node:sqlite` (Node ≥22.5, `allowExtension`).
    On **macOS under Bun**, Apple's system SQLite disables extension loading, so
    set `DNA_SQLITE_LIB` to a libsqlite3 that permits it (e.g. Homebrew's
    `/opt/homebrew/opt/sqlite/lib/libsqlite3.dylib`) or install `sqlite`; on
    Linux, Bun's bundled SQLite already allows it. When no runtime can load the
    extension the suite skips with a clear reason.

### The scale provider — pgvector

`PgVecRecordSearchProvider` is the server-side sibling for scale: it swaps the
embeddable one-file-per-scope SQLite store for a shared Postgres database
(reusing the DNA Postgres that already backs the source plane), and it passes the
**same** `record_search_conformance_suite` — one contract, many stores. Dense
search is pgvector's `<=>` cosine distance (accelerated by an IVFFlat index);
the lexical plane is a generated `tsvector` column ranked by `ts_rank`
(accelerated by GIN); fusion reuses the **same** pure RRF function as sqlite-vec.
Its store schema is owned by a numbered migration in the store's own
`dna_search_migrations` control table (re-boot is a no-op), and `CREATE EXTENSION
vector` is the migration's first statement — so a database without pgvector fails
loud rather than silently degrading.

```bash
pip install "dna-sdk[search-pgvector]"    # asyncpg (via the `postgres` extra)
# against a pgvector-enabled Postgres (e.g. the `pgvector/pgvector:pg16` image):
DATABASE_URL=postgresql://dna:dna@localhost/dna_test \
  cd packages/sdk-py && uv run pytest tests/test_pgvector_search_conformance.py -v
```

The conformance test is gated on a Postgres DSN (the shared `requires_postgres`
marker): it skips cleanly with no database and runs **for real** in the CI
`postgres` job, which uses the `pgvector/pgvector:pg16` service image. Each case
runs in a fresh, disposable schema so index/delete state never bleeds across
cases or projects.

!!! note "Py-primary, behavioral parity via the kit"
    Unlike sqlite-vec, the pgvector provider is **Python-only by design**.
    sqlite-vec has a TS twin because it is the *embeddable offline floor* both
    SDKs ship and run in-process; pgvector is the *scale/server* adapter, only
    meaningful against a running Postgres (which the TS SDK reaches through a
    different driver, `pg`). Behavioral parity is guaranteed the way the port
    intends — the **same** conformance kit is the contract, and the only
    ranking-affecting logic (RRF) is already bit-identical Py↔TS and reused
    unchanged. A TS pgvector twin, if ever needed, must pass the same eight
    cases; the kit is the parity guarantee, not a hand-diffed second impl.

## The memory conformance kit

Memory is the layer where the search plane, the embedding port and the
kernel's write path all meet — so it gets its own kit, in two halves.

**The verb suite** — `memory_conformance_suite` — is the behavioral contract
of the four memory verbs (`remember` / `recall` / `forget` / `consolidate`,
plus the lazy `backfill_index`). Hand it an async factory that returns a
kernel wired with **your** writable source (and, optionally, your
`RecordSearchProvider` / `EmbeddingPort`) and it proves the memory lifecycle
holds over your stack: the remember→recall roundtrip with deterministic
enrichment, deterministic recall, the untouched base shape with
`semantic=False` vs. RRF-fused annotations in auto mode, bi-temporal `forget`
(soft demotion — never a delete, never resurfaces, idempotent),
reconsolidation side-effects, an idempotent `consolidate` pass, retention
that decays monotonically in **simulated** time (the kit never reads the wall
clock), and idempotent lazy backfill. Cases are capability-aware, like the
source kit: with no search provider the fusion/backfill cases skip cleanly
and the honest lexical-fallback case runs instead (and vice versa) — probed
through the public surface only (`remember` reports `indexed`).

```python
from dna.testing import memory_conformance_suite

async def my_factory():
    kernel = ...   # your writable source (+ your provider, if any)
    async def cleanup(): ...
    return kernel, cleanup

import pytest
CASES = memory_conformance_suite(my_factory)

@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
async def test_memory_conformance(case):
    await case.run()
```

The SDK holds its own builtins to it: the suite runs against the filesystem
source without a provider (lexical branch), with the sqlite-vec provider
(`tests/test_memory_conformance_kit.py`), and against pgvector in the CI
`postgres` job (`tests/test_pgvector_memory_conformance.py`) — one contract,
many stores, same as the search kit. There is also a programmatic runner,
`run_memory_conformance(factory)`, for scripts and CI without pytest.

**The scoring suite** — `memory_scoring_conformance_suite` (Python) /
`memoryScoringConformanceSuite` (TypeScript) — pins the PURE deterministic
core the verbs compose: ecphory weights and the `direct_threshold` gate,
deterministic ordering, the semantic hook that lifts a paraphrase the
cue-match paths cannot see, RRF fusion invariants (no candidate ever
disappears; exact reciprocal-rank arithmetic; both ranks + the cosine
annotated), monotonic Ebbinghaus decay, and fail-open bi-temporal validity.
It is twinned 1:1 — same case names, same assertions in both SDKs — so the
kit itself is a parity artifact: anyone evolving the scoring runs the same
battery on both sides.

Pass an embedder factory to certify a custom `EmbeddingPort` for memory; omit
it to run on the deterministic fake floor, fully offline. The two
embedder-driven cases assert **relative** similarity only (identical text is
maximally similar; a paraphrase beats unrelated text), search-kit style, so a
real model passes too — with one honest exception:
`semantic_hook_lifts_paraphrase` requires the embedder to score an easy
paraphrase above the ecphory gate (`cos ≥ (direct_threshold − novelty_boost)
/ cosine_weight` ≈ 0.41). An embedder that cannot clear that bar cannot power
semantic recall, and the kit says so rather than passing vacuously.

=== "Python"

    ```python
    from dna.testing import run_memory_scoring_conformance

    report = await run_memory_scoring_conformance()          # fake floor
    report = await run_memory_scoring_conformance(my_embedder_factory)
    report.raise_if_failed()
    ```

=== "TypeScript"

    ```typescript
    import { memoryScoringConformanceSuite } from "dna-sdk/testing";

    for (const c of memoryScoringConformanceSuite(/* factory? */)) {
      test(c.name, () => c.run());
    }
    ```

!!! note "Why the verb suite is Python-only"
    The memory **verbs** are Python-only by the SDK's declared boundary (the
    TS SDK ships the pure scoring core; the kernel-bound verbs live with the
    `dna` CLI). The TS kit therefore mirrors exactly the half that exists in
    TS — the scoring core — and the verb behaviors are pinned where the verbs
    are. Same policy as the pgvector provider above: the kit is the parity
    guarantee, not a hand-diffed second implementation.

## Cross-SDK parity

Parity between the Python and TypeScript SDKs is enforced by **shared
fixtures**: descriptor files are byte-identical and hash-checked, and a
kind-registry parity manifest fails the suite on undocumented drift. The
same `hello-genome` example is run by both SDKs' suites and asserted to
produce the same documents and the same composed prompt.

That parity is why the [tutorial](first-kind.md) can honestly show one set of
expected output for two languages: it is a test-enforced invariant, not a
coincidence.
