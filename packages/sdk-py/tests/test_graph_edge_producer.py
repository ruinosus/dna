"""The edge PRODUCER — an edge exists because somebody wrote an instance.

``dna_edges`` was created once before, in migration 7, and dropped in migration
10 with zero rows in it: the table shipped, the producer never did, and for
fourteen months "the graph has no edges" and "the table was never filled" were
indistinguishable. So the load-bearing assertion of this module is not that the
table exists — it is that **writing an instance puts a row in it**. Delete the
producer and these tests go red; ship the table alone and they never go green.

Everything here runs against a REAL SQLite store through a REAL kernel write.
A fake source that accepted an ``edges=`` kwarg and remembered it would pass a
producer test without proving that anything was ever persisted, which is the
precise shape of the mistake being corrected.
"""
from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa

from dna.kernel import Kernel
from tests import _graph_store

_SDLC_API = "github.com/ruinosus/dna/sdlc/v1"
SCOPE = "graph-producer"


def _doc(kind: str, name: str, **spec: Any) -> dict[str, Any]:
    base = {"description": "d", "status": "todo"}
    base.update(spec)
    return {
        "apiVersion": _SDLC_API, "kind": kind,
        "metadata": {"name": name}, "spec": base,
    }


@pytest.fixture(autouse=True)
def _modes(monkeypatch):
    # Reference validation at its DEFAULT (warn): a dangling reference must
    # persist, which is exactly the case whose edge this module cares about.
    monkeypatch.delenv("DNA_REF_VALIDATION", raising=False)
    # Shape validation off — these instances are about references, not schemas.
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")


@pytest_asyncio.fixture(params=_graph_store.DIALECTS)
async def store(request):
    """A kernel over a real store, on BOTH dialects.

    Postgres runs when ``DATABASE_URL`` is set and is skipped otherwise — the
    same gate the adapter conformance matrix uses. The claim this feature rests
    on is that the producer and the recursive CTE are dialect-neutral, and a
    claim like that is worth what its second dialect proves.
    """
    src, cleanup = await _graph_store.build_store(request.param, "edges")
    kernel = Kernel.auto()
    kernel.source(src)
    try:
        yield kernel, src
    finally:
        await cleanup()


async def _rows(src) -> list[dict[str, Any]]:
    async with src._engine.connect() as conn:
        result = (await conn.execute(
            sa.select(src.edges).order_by(
                src.edges.c.from_kind, src.edges.c.from_name,
                src.edges.c.source_field, src.edges.c.ordinal,
            )
        )).all()
    return [dict(r._mapping) for r in result]


class TestTheRowExistsBecauseSomebodyWrote:
    @pytest.mark.anyio
    async def test_writing_a_story_with_a_feature_writes_one_edge(self, store):
        """The acceptance criterion, verbatim, and the guard against i-039.

        Write ``Story/s-x`` with ``spec.feature = "f-y"`` ⇒ ONE row, carrying
        the field the reference was declared on and the Kind it resolved to.
        """
        kernel, src = store
        await kernel.write_instance(
            SCOPE, "Feature", "f-y", _doc("Feature", "f-y"),
        )
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"),
        )
        rows = [r for r in await _rows(src) if r["from_kind"] == "Story"]
        assert len(rows) == 1, rows
        row = rows[0]
        assert row["source_field"] == "feature"
        assert row["to_kind"] == "Feature"
        assert row["to_name"] == "f-y"
        assert row["from_name"] == "s-x"
        assert row["from_version"] == 1

    @pytest.mark.anyio
    async def test_the_resolved_scope_is_recorded_when_it_is_local(self, store):
        """``to_scope`` is a FACT, not the writer's scope copied over.

        A reference resolving in THIS scope records it; the column exists so
        that an inherited resolution can decline to claim otherwise.
        """
        kernel, src = store
        await kernel.write_instance(SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"),
        )
        row = [r for r in await _rows(src) if r["from_kind"] == "Story"][0]
        assert row["to_scope"] == SCOPE

    @pytest.mark.anyio
    async def test_an_array_reference_keeps_its_order(self, store):
        """``ordinal`` preserves the author's ordering of an array field, and
        keeps two items of the same field from colliding on the primary key."""
        kernel, src = store
        for n in ("s-a", "s-b"):
            await kernel.write_instance(SCOPE, "Story", n, _doc("Story", n))
        await kernel.write_instance(
            SCOPE, "Story", "s-x",
            _doc("Story", "s-x", dependencies=["s-a", "s-b"]),
        )
        rows = [
            r for r in await _rows(src)
            if r["from_name"] == "s-x" and r["source_field"] == "dependencies"
        ]
        assert [(r["ordinal"], r["to_name"]) for r in rows] == [
            (0, "s-a"), (1, "s-b"),
        ]


class TestDanglingIsRecorded:
    @pytest.mark.anyio
    async def test_a_dangling_reference_persists_as_a_row_with_null_to_kind(
        self, store,
    ):
        """With ``warn`` (the DEFAULT) the instance persists, so the edge must
        too. Dropping it would render a graph tidier than the data deserves —
        and these rows are the list of what is broken."""
        kernel, src = store
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-nope"),
        )
        rows = [r for r in await _rows(src) if r["from_name"] == "s-x"]
        assert len(rows) == 1
        assert rows[0]["to_kind"] is None
        assert rows[0]["to_name"] == "f-nope"
        # The declaration travels even unresolved: the screen can still say
        # WHAT was expected.
        assert rows[0]["declared_to"] == "Feature"
        assert rows[0]["to_scope"] is None

    @pytest.mark.anyio
    async def test_deleting_the_target_leaves_the_edge_dangling(self, store):
        """The third clause of the acceptance criterion.

        Delete ``f-y`` and the Story's edge STAYS, now unresolved. The delete
        path validates no references at all, so this row is the only trace that
        something broke.
        """
        kernel, src = store
        await kernel.write_instance(SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"),
        )
        await kernel.delete_instance(SCOPE, "Feature", "f-y")
        rows = [r for r in await _rows(src) if r["from_name"] == "s-x"]
        assert len(rows) == 1, "the incoming edge was destroyed with its target"
        # It still says Feature/f-y — the row is a record of what the Story
        # asserts, and the Story still asserts it.
        assert rows[0]["to_name"] == "f-y"


class TestDeleteTakesOutgoingAndLeavesIncoming:
    @pytest.mark.anyio
    async def test_deleting_a_document_removes_only_its_own_assertions(
        self, store,
    ):
        kernel, src = store
        await kernel.write_instance(SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"),
        )
        await kernel.write_instance(
            SCOPE, "Task", "t-1", _doc("Task", "t-1", story_ref="s-x"),
        )
        await kernel.delete_instance(SCOPE, "Story", "s-x")

        rows = await _rows(src)
        outgoing = [r for r in rows if r["from_name"] == "s-x"]
        incoming = [r for r in rows if r["to_name"] == "s-x"]
        assert outgoing == [], "the deleted instance's own edges survived"
        assert len(incoming) == 1, (
            "the Task's edge was deleted along with its target — that erases "
            "the evidence that this delete broke something"
        )
        assert incoming[0]["from_kind"] == "Task"


class TestReplacementIsExact:
    @pytest.mark.anyio
    async def test_removing_the_reference_removes_the_row(self, store):
        """DELETE+INSERT, not INSERT-only: an instance that stops asserting a
        relation must stop having one."""
        kernel, src = store
        await kernel.write_instance(SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"),
        )
        assert [r for r in await _rows(src) if r["from_name"] == "s-x"]
        await kernel.write_instance(SCOPE, "Story", "s-x", _doc("Story", "s-x"))
        assert [r for r in await _rows(src) if r["from_name"] == "s-x"] == []

    @pytest.mark.anyio
    async def test_rewriting_does_not_duplicate(self, store):
        kernel, src = store
        await kernel.write_instance(SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))
        for _ in range(3):
            await kernel.write_instance(
                SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"),
            )
        rows = [r for r in await _rows(src) if r["from_name"] == "s-x"]
        assert len(rows) == 1
        # ...and the version tracks the instance, so drift is detectable.
        assert rows[0]["from_version"] == 3


class TestAPartialSetIsNeverStored:
    @pytest.mark.anyio
    async def test_a_read_failure_leaves_the_previous_edges_alone(
        self, store, monkeypatch,
    ):
        """``complete=False`` ⇒ do not replace.

        A partial edge set stored as if it were whole is a graph that lies
        while looking finished — worse than one that is honestly absent,
        because the absent one can be labelled.
        """
        kernel, src = store
        await kernel.write_instance(SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"),
        )
        before = [r for r in await _rows(src) if r["from_name"] == "s-x"]
        assert before

        async def _boom(*a, **kw):
            raise RuntimeError("the store went away mid-resolution")

        monkeypatch.setattr(kernel, "get_instance", _boom)
        # The write itself must still succeed — a derivation failure is not a
        # reason to refuse to store the instance.
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-other"),
        )
        after = [r for r in await _rows(src) if r["from_name"] == "s-x"]
        assert after and after[0]["to_name"] == "f-y", (
            "a partial resolution replaced a known-good edge set"
        )

    @pytest.mark.anyio
    async def test_producer_off_does_not_wipe_what_is_stored(
        self, store, monkeypatch,
    ):
        """``DNA_REF_VALIDATION=off`` performs no lookups, so it can produce no
        edges — and must therefore not DESTROY any either. The face reports the
        mode so the emptiness is never read as "no relations"."""
        kernel, src = store
        await kernel.write_instance(SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"),
        )
        monkeypatch.setenv("DNA_REF_VALIDATION", "off")
        await kernel.write_instance(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"),
        )
        assert [r for r in await _rows(src) if r["from_name"] == "s-x"]


class TestTheKwargIsCapabilityGated:
    def test_the_filesystem_adapter_does_not_claim_the_edges_kwarg(self, tmp_path):
        """It has no transaction to write edges in and no table to write them
        to. Claiming the kwarg would make the kernel hand over edges the
        adapter silently drops, and a face would then read the resulting
        nothing as "this instance has no relations"."""
        from dna.adapters.filesystem.writable import FilesystemWritableSource
        from dna.kernel.capabilities import (
            derive_capabilities, source_capabilities, write_kwarg_support,
        )

        src = FilesystemWritableSource(str(tmp_path))
        caps = source_capabilities(src)
        assert "edges" not in caps.write_kwargs
        assert not write_kwarg_support(src).edges
        assert not caps.edge_graph
        # The declaration must agree with what the code actually accepts —
        # a declaration nobody checks is the drift this repo has paid for.
        assert derive_capabilities(src, label="fs").write_kwargs == caps.write_kwargs

    def test_the_sql_adapter_claims_both_halves(self):
        """Write AND read. Half of it would let the face serve an empty list it
        cannot back."""
        from dna.adapters.sqlalchemy_ import SqlAlchemySource
        from dna.kernel.capabilities import source_capabilities

        caps = source_capabilities(SqlAlchemySource("sqlite+aiosqlite:///:memory:"))
        assert "edges" in caps.write_kwargs
        assert caps.edge_graph
