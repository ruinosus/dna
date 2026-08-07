"""Backfilling the graph for instances that predate the producer.

An instance written before the producer existed has no edges, and the screen
must be able to tell "nothing points at this" from "nobody has written since
Tuesday". The backfill is what makes the first statement true — derived from
the SAME ``x-dna-ref`` declaration the producer reads, never from a scan that
guesses at slug prefixes (the mechanism i-039 refused, and the reason the first
``dna_edges`` was dropped).

The instances here are written with the producer DISABLED, which is how a
pre-producer database is honestly simulated: rows in ``instances``, nothing in
``edges``. If the backfill were secretly relying on the write path having been
warm, these tests would catch it.
"""
from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa

from dna.kernel import Kernel
from tests import _graph_store

_SDLC_API = "github.com/ruinosus/dna/sdlc/v1"
SCOPE = "graph-backfill"


def _doc(kind: str, name: str, **spec: Any) -> dict[str, Any]:
    base = {"description": "d", "status": "todo"}
    base.update(spec)
    return {
        "apiVersion": _SDLC_API, "kind": kind,
        "metadata": {"name": name}, "spec": base,
    }


@pytest.fixture(autouse=True)
def _modes(monkeypatch):
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")
    monkeypatch.delenv("DNA_REF_VALIDATION", raising=False)


@pytest_asyncio.fixture(params=_graph_store.DIALECTS)
async def store(request):
    """A kernel over a real store, on BOTH dialects.

    Postgres runs when ``DATABASE_URL`` is set and is skipped otherwise — the
    same gate the adapter conformance matrix uses. The claim this feature rests
    on is that the producer and the recursive CTE are dialect-neutral, and a
    claim like that is worth what its second dialect proves.
    """
    src, cleanup = await _graph_store.build_store(request.param, "backfill")
    kernel = Kernel.auto()
    kernel.source(src)
    try:
        yield kernel, src
    finally:
        await cleanup()


async def _edge_count(src) -> int:
    async with src._engine.connect() as conn:
        return int((await conn.execute(
            sa.select(sa.func.count()).select_from(src.edges)
        )).scalar_one())


async def _seed_without_edges(kernel, monkeypatch) -> None:
    """Write instances with the producer OFF — a pre-producer database."""
    monkeypatch.setenv("DNA_REF_VALIDATION", "off")
    await kernel.write_instance(SCOPE, "Epic", "e-1", _doc("Epic", "e-1"))
    await kernel.write_instance(
        SCOPE, "Feature", "f-y", _doc("Feature", "f-y", epic="e-1"),
    )
    await kernel.write_instance(
        SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"),
    )
    await kernel.write_instance(
        SCOPE, "Story", "s-ghost", _doc("Story", "s-ghost", feature="f-gone"),
    )
    monkeypatch.setenv("DNA_REF_VALIDATION", "warn")


class TestThePairsAreDerived:
    def test_the_declared_pairs_come_from_the_registry(self):
        """DERIVED, never enumerated: a hand-kept list is how a guard goes
        green while going blind."""
        from dna.kernel.query.backfill import declared_pairs

        pairs = declared_pairs(Kernel.auto())
        assert ("Story", "feature") in pairs
        assert ("Feature", "epic") in pairs
        assert ("Membership", "scope_ref") in pairs
        # A Kind that declares nothing must contribute nothing.
        assert not [p for p in pairs if p[0] == "Engram"]

    def test_a_kernel_that_cannot_enumerate_kinds_raises(self):
        """"0 pairs, 0 instances" would look like a successful run that filled
        nothing — precisely the failure this whole degree is about."""
        from dna.kernel.query.backfill import declared_pairs

        class _Blind:
            pass

        with pytest.raises(RuntimeError, match="refusing"):
            declared_pairs(_Blind())


class TestTheBackfillFills:
    @pytest.mark.anyio
    async def test_documents_written_before_the_producer_get_their_edges(
        self, store, monkeypatch,
    ):
        from dna.kernel.query.backfill import backfill_edges

        kernel, src = store
        await _seed_without_edges(kernel, monkeypatch)
        assert await _edge_count(src) == 0, "the seed already produced edges"

        report = await backfill_edges(kernel, scope=SCOPE)

        assert report.instances == 3          # Feature/f-y + the two Stories
        assert report.edges == 3
        assert report.dangling == 1           # s-ghost → f-gone
        assert report.skipped == 0
        assert report.pending == set()
        assert await _edge_count(src) == 3

        # ...and the graph now answers the product question.
        result = await kernel.graph_refs(SCOPE, "Feature", "f-y", direction="in")
        assert [e["from_name"] for e in result.edges] == ["s-x"]

    @pytest.mark.anyio
    async def test_a_dry_run_reads_everything_and_writes_nothing(
        self, store, monkeypatch,
    ):
        """Same reads, so the numbers it reports are the numbers a real run
        would produce — a dry run that guessed would be worse than none."""
        from dna.kernel.query.backfill import backfill_edges

        kernel, src = store
        await _seed_without_edges(kernel, monkeypatch)
        dry = await backfill_edges(kernel, scope=SCOPE, dry_run=True)
        assert await _edge_count(src) == 0
        wet = await backfill_edges(kernel, scope=SCOPE)
        assert (dry.instances, dry.edges, dry.dangling) == (
            wet.instances, wet.edges, wet.dangling,
        )

    @pytest.mark.anyio
    async def test_running_twice_changes_nothing(self, store, monkeypatch):
        """Idempotent by construction — the same DELETE+INSERT per instance
        the producer uses."""
        from dna.kernel.query.backfill import backfill_edges

        kernel, src = store
        await _seed_without_edges(kernel, monkeypatch)
        await backfill_edges(kernel, scope=SCOPE)
        first = await _edge_count(src)
        await backfill_edges(kernel, scope=SCOPE)
        assert await _edge_count(src) == first

    @pytest.mark.anyio
    async def test_it_runs_cold(self, store, monkeypatch):
        """Nothing in the backfill needs the write path to have been warm: a
        FRESH kernel over the same store fills the graph."""
        from dna.adapters.sqlalchemy_ import SqlAlchemySource
        from dna.kernel.query.backfill import backfill_edges

        kernel, src = store
        await _seed_without_edges(kernel, monkeypatch)
        # ``str(url)`` masks the password as ``***``, so a cold reconnect built
        # from it fails to authenticate — which would read as a backfill bug.
        url = src._engine.url.render_as_string(hide_password=False)

        cold_src = SqlAlchemySource(url, schema=src._schema)
        await cold_src.connect()
        cold = Kernel.auto()
        cold.source(cold_src)
        try:
            report = await backfill_edges(cold, scope=SCOPE)
            assert report.edges == 3
        finally:
            await cold_src.close()


class TestIncompleteIsSaid:
    @pytest.mark.anyio
    async def test_an_unresolvable_document_is_skipped_and_its_scope_marked(
        self, store, monkeypatch,
    ):
        """A partial edge set stored as if it were whole is a graph that lies
        while looking finished. The scope is marked instead, so the screen can
        say "still being filled" rather than showing a confident nothing."""
        from dna.kernel.query.backfill import backfill_edges

        kernel, src = store
        await _seed_without_edges(kernel, monkeypatch)

        async def _boom(*a, **kw):
            raise RuntimeError("store unavailable")

        monkeypatch.setattr(kernel, "get_instance", _boom)
        report = await backfill_edges(kernel, scope=SCOPE)
        assert report.instances == 0
        assert report.skipped == 3
        assert report.pending == {SCOPE}
        assert await _edge_count(src) == 0

    @pytest.mark.anyio
    async def test_a_store_without_an_edge_table_refuses(self, tmp_path):
        from dna.adapters.filesystem.writable import FilesystemWritableSource
        from dna.kernel.query.backfill import backfill_edges
        from dna.kernel.query.graph import GraphUnsupported

        kernel = Kernel.auto()
        kernel.source(FilesystemWritableSource(str(tmp_path)))
        with pytest.raises(GraphUnsupported):
            await backfill_edges(kernel)


class TestTheReaderAsksTheDeclaration:
    @pytest.mark.anyio
    async def test_only_documents_that_actually_carry_the_field_come_back(
        self, store, monkeypatch,
    ):
        """The per-``(Kind, field)`` query is what makes the backfill
        affordable: on Postgres it is a JSONB key-existence predicate the
        existing GIN index serves, so it visits the instances that HAVE the
        field rather than every instance in the database.
        """
        kernel, src = store
        await _seed_without_edges(kernel, monkeypatch)
        await kernel.write_instance(SCOPE, "Story", "s-bare", _doc("Story", "s-bare"))

        rows = await src.list_instances_with_spec_field("Story", "feature")
        assert {r["name"] for r in rows} == {"s-x", "s-ghost"}
        assert "s-bare" not in {r["name"] for r in rows}
        # The identity travels whole — apiVersion included, because two
        # workspaces may each declare a Kind of the same name.
        assert all(r["api_version"] == _SDLC_API for r in rows)
