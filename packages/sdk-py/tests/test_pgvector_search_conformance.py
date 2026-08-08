"""The public RecordSearchProvider conformance kit × the pgvector provider.

Runs the whole ``record_search_conformance_suite`` against
``PgVecRecordSearchProvider`` with the deterministic ``FakeEmbeddingProvider``
floor — offline embeddings, real Postgres. The SAME 8 cases the sqlite-vec
provider passes: that's the point of the port — one contract, many stores.

Gated on a Postgres DSN via the shared ``requires_postgres`` marker
(``tests/conftest.py``): skips cleanly with no DB (local without Postgres), and
runs FOR REAL in the CI ``postgres`` job — which MUST use a pgvector-enabled
image (``pgvector/pgvector:pg16``) so ``CREATE EXTENSION vector`` succeeds.

Each case gets a FRESH, DISPOSABLE schema (``dna_search_ci_<uuid>``) that is
created, MIGRATED TO HEAD, and dropped after — never touching another project's
tables (the CI database is a throwaway ``dna_test``).

⭐ ``s-indice-por-dimensao`` changed what "the store exists" means. The provider
used to apply its own numbered ladder on first index/search; it no longer runs
DDL at all, and the tables (one per embedding WIDTH) come from alembic revision
``0013_uma_tabela_por_dimensao``. So the three properties this file now proves,
beyond the shared kit:

* the width routes — two widths write to two tables and never see each other;
* ⚠️ the SPACE filters — same width, different ``model_id``, same table, and
  still never in the same result. That co-existence is the product: a tenant
  can pick its own embedder;
* an unmigrated schema, or an unseen width, fails LOUD and creates NOTHING.
"""
from __future__ import annotations

import hashlib

import pytest

pytestmark = pytest.mark.requires_postgres

asyncpg = pytest.importorskip(
    "asyncpg",
    reason="postgres extra not installed (pip install 'dna-sdk[search-pgvector]')",
)

from dna.testing import record_search_conformance_suite  # noqa: E402

from tests import _search_schema  # noqa: E402


async def _pgvector_factory():
    """Build a fresh PgVecRecordSearchProvider on a disposable MIGRATED schema.

    Each case is isolated in its own schema so index/delete state never bleeds
    across cases. The provider owns its own pool (built from the DSN); cleanup
    closes it and drops the schema.
    """
    from dna.kernel import Kernel
    from dna.adapters.search.pgvector import PgVecRecordSearchProvider

    kernel = Kernel.auto()  # no embedding provider → deterministic fake floor
    dsn, schema, drop_schema = await _search_schema.migrated_schema("dna_search_ci")

    provider = PgVecRecordSearchProvider(kernel, dsn=dsn, schema=schema)

    async def cleanup() -> None:
        await provider.close()
        await drop_schema()

    return provider, cleanup


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    record_search_conformance_suite(_pgvector_factory),
    ids=lambda c: c.name,
)
async def test_pgvector_record_search_conformance(case):
    await case.run()


@pytest.mark.asyncio
async def test_programmatic_runner_reports_all_pass():
    from dna.testing import run_record_search_conformance

    report = await run_record_search_conformance(_pgvector_factory)
    report.raise_if_failed()
    assert report.ok
    assert "index_search_round_trip" in report.passed
    assert "tenant_overlay_shadows_base" in report.passed


# ---------------------------------------------------------------------------
# s-indice-por-dimensao — the schema is the migration's, and the store reads it
# ---------------------------------------------------------------------------

class _Fake:
    """An ``EmbeddingPort`` with a chosen width and space.

    Deterministic and token-shaped: the vector is a bag of hashed tokens, so a
    query drawn from a doc's vocabulary really is nearer to it. Two of these
    with the same ``dims`` produce vectors of the same LENGTH — which is exactly
    the condition under which a missing ``model_id`` filter would silently
    compare them and no error would ever fire.

    ``sha256``, not ``hash``: Python salts ``hash`` on str per process, and a
    vector that differs between the write and the read would make these flaky
    for a reason that has nothing to do with what they measure.
    """

    def __init__(self, model_id: str, dims: int) -> None:
        self.model_id = model_id
        self.dims = dims

    async def embed(self, texts):
        out = []
        for text in texts:
            vec = [0.0] * self.dims
            for token in text.lower().split():
                slot = int(hashlib.sha256(token.encode()).hexdigest(), 16)
                vec[slot % self.dims] += 1.0
            out.append(vec)
        return out


async def _provider_on(schema_dsn, schema, model_id, dims):
    from dna.kernel import Kernel
    from dna.adapters.search.pgvector import PgVecRecordSearchProvider

    kernel = Kernel.auto()
    kernel.embedding_provider(_Fake(model_id, dims))
    return PgVecRecordSearchProvider(kernel, dsn=schema_dsn, schema=schema)


@pytest.mark.asyncio
async def test_the_migration_creates_one_table_per_width_and_the_store_creates_none():
    """The acceptance criterion, read straight from the catalog: after the
    migration the five tables are there — and the OLD single ``dna_search_docs``
    is not, because 0013 renamed it into its dimension."""
    from dna.adapters.search.dimensions import SUPPORTED_DIMS, search_table

    dsn, schema, cleanup = await _search_schema.migrated_schema("dna_dims_ci")
    try:
        tables = await _search_schema.table_names(dsn, schema)
        for dims in SUPPORTED_DIMS:
            assert search_table(dims) in tables, (
                f"{search_table(dims)} missing after migration: {sorted(tables)}"
            )
        assert "dna_search_docs" not in tables, (
            "the unsuffixed table survived — two names for the same thing is "
            "the exception that never dies"
        )
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_a_schema_without_the_migration_refuses_and_creates_nothing():
    """⛔ MUTANT: DDL at runtime.

    Against a schema at revision zero the store must fail LOUD and name the
    revision — and the schema must be exactly as empty afterwards as before. A
    provider that "helpfully" created its table would make this pass by
    creating the very thing the rule forbids.
    """
    dsn, schema, cleanup = await _search_schema.bare_schema("dna_nomig_ci")
    try:
        before = await _search_schema.table_names(dsn, schema)
        provider = await _provider_on(dsn, schema, "m-any", 384)
        with pytest.raises(RuntimeError, match="0013"):
            await provider.index([
                {"scope": "s", "kind": "Story", "name": "a", "text": "hello"},
            ])
        with pytest.raises(RuntimeError, match="0013"):
            await provider.search(scope="s", query_text="hello", k=5)
        await provider.close()
        assert await _search_schema.table_names(dsn, schema) == before, (
            "the store created schema objects — data-access code never runs DDL"
        )
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_an_unseen_width_fails_high_and_points_at_the_missing_migration():
    """⛔ MUTANT: an unseen dimension creates a table.

    777 has no migration. The refusal must arrive BEFORE any row is touched,
    name the width, and leave the schema untouched — never round to 768.
    """
    from dna.adapters.search.dimensions import UnsupportedEmbeddingDims

    dsn, schema, cleanup = await _search_schema.migrated_schema("dna_odd_ci")
    try:
        before = await _search_schema.table_names(dsn, schema)
        provider = await _provider_on(dsn, schema, "m-odd", 777)
        with pytest.raises(UnsupportedEmbeddingDims, match="777"):
            await provider.index([
                {"scope": "s", "kind": "Story", "name": "a", "text": "hello"},
            ])
        with pytest.raises(UnsupportedEmbeddingDims, match="777"):
            await provider.search(scope="s", query_text="hello", k=5)
        await provider.close()
        assert await _search_schema.table_names(dsn, schema) == before
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_two_widths_write_to_two_tables_and_never_see_each_other():
    """⛔ MUTANT: routing ignores ``dims`` and mixes spaces.

    Same scope, same words, two widths. Each search returns ONLY its own
    width's document. Make the routing constant (ignore ``dims``) and this
    turns red twice over: the wrong-width INSERT is a type error, and if it
    somehow landed, the foreign doc would show up here.
    """
    from dna.adapters.search.dimensions import search_table

    dsn, schema, cleanup = await _search_schema.migrated_schema("dna_two_ci")
    try:
        small = await _provider_on(dsn, schema, "m-small", 384)
        large = await _provider_on(dsn, schema, "m-large", 1536)
        await small.index([{"scope": "s", "kind": "Story", "name": "doc-384",
                            "text": "memory similarity vector recall"}])
        await large.index([{"scope": "s", "kind": "Story", "name": "doc-1536",
                            "text": "memory similarity vector recall"}])

        small_hits = {h["name"] for h in await small.search(
            scope="s", query_text="memory similarity vector recall", k=10)}
        large_hits = {h["name"] for h in await large.search(
            scope="s", query_text="memory similarity vector recall", k=10)}
        assert small_hits == {"doc-384"}, small_hits
        assert large_hits == {"doc-1536"}, large_hits

        # And the rows really are in the two tables the widths name — the
        # behaviour above could in principle be produced by a filter on one
        # table, which is NOT what was decided.
        conn = await asyncpg.connect(dsn)
        try:
            for dims, name in ((384, "doc-384"), (1536, "doc-1536")):
                got = await conn.fetchval(
                    f"SELECT name FROM {schema}.{search_table(dims)} "
                    "WHERE name = $1", name,
                )
                assert got == name, f"{name} is not in {search_table(dims)}"
        finally:
            await conn.close()
        await small.close()
        await large.close()
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_same_width_different_model_id_coexist_and_never_mix():
    """⭐⛔ THE mutant the story cares most about, after routing.

    Two embedders at the SAME width. They share a table (same column type) and
    their vectors have the same length, so nothing about them is malformed —
    the port's contract is the only thing that says they are incomparable.
    Delete the ``model_id`` filter from either plane and this goes red; nothing
    else would ever have complained.

    That both CAN live here is the product half: a tenant picks its own
    embedder without an architecture decision.
    """
    dsn, schema, cleanup = await _search_schema.migrated_schema("dna_space_ci")
    try:
        alpha = await _provider_on(dsn, schema, "embedder-alpha", 1536)
        beta = await _provider_on(dsn, schema, "embedder-beta", 1536)
        await alpha.index([{"scope": "s", "kind": "Story", "name": "only-alpha",
                            "text": "banana smoothie fruit blender"}])
        await beta.index([{"scope": "s", "kind": "Story", "name": "only-beta",
                           "text": "banana smoothie fruit blender"}])

        query = "banana smoothie fruit blender"
        alpha_hits = {h["name"] for h in await alpha.search(
            scope="s", query_text=query, k=10)}
        beta_hits = {h["name"] for h in await beta.search(
            scope="s", query_text=query, k=10)}
        assert alpha_hits == {"only-alpha"}, (
            f"alpha saw another embedding space: {alpha_hits}"
        )
        assert beta_hits == {"only-beta"}, (
            f"beta saw another embedding space: {beta_hits}"
        )

        # Same table, both rows: co-existence, not separation by storage.
        conn = await asyncpg.connect(dsn)
        try:
            rows = await conn.fetch(
                f"SELECT name, model_id FROM {schema}.dna_search_docs_1536 "
                "ORDER BY name"
            )
            assert [(r["name"], r["model_id"]) for r in rows] == [
                ("only-alpha", "embedder-alpha"),
                ("only-beta", "embedder-beta"),
            ], rows
        finally:
            await conn.close()
        await alpha.close()
        await beta.close()
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_the_same_record_under_two_embedders_is_two_rows_not_an_overwrite():
    """``model_id`` is IN the unique key. Re-indexing a record under a second
    embedder must ADD the second space's vector, never replace the first with
    one it cannot be compared to."""
    dsn, schema, cleanup = await _search_schema.migrated_schema("dna_dual_ci")
    try:
        alpha = await _provider_on(dsn, schema, "embedder-alpha", 768)
        beta = await _provider_on(dsn, schema, "embedder-beta", 768)
        record = {"scope": "s", "kind": "Story", "name": "shared",
                  "text": "one record two spaces"}
        await alpha.index([dict(record)])
        await beta.index([dict(record)])

        conn = await asyncpg.connect(dsn)
        try:
            count = await conn.fetchval(
                f"SELECT count(*) FROM {schema}.dna_search_docs_768 "
                "WHERE name = 'shared'"
            )
        finally:
            await conn.close()
        assert count == 2, f"expected one row per space, got {count}"

        # …and a delete takes BOTH: delete is about the RECORD, not the space.
        assert await alpha.delete([
            {"scope": "s", "kind": "Story", "name": "shared"},
        ]) == 2
        await alpha.close()
        await beta.close()
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_delete_sweeps_every_width_not_just_the_active_one():
    """A record indexed at 384 and at 1536 is gone from both after one delete —
    a record removed from the source has no business staying indexed in a
    space nobody is currently searching."""
    dsn, schema, cleanup = await _search_schema.migrated_schema("dna_del_ci")
    try:
        small = await _provider_on(dsn, schema, "m-small", 384)
        large = await _provider_on(dsn, schema, "m-large", 1536)
        record = {"scope": "s", "kind": "Story", "name": "everywhere",
                  "text": "indexed in two widths"}
        await small.index([dict(record)])
        await large.index([dict(record)])

        removed = await small.delete([
            {"scope": "s", "kind": "Story", "name": "everywhere"},
        ])
        assert removed == 2, removed
        assert not await large.search(
            scope="s", query_text="indexed in two widths", k=5,
        )
        await small.close()
        await large.close()
    finally:
        await cleanup()


