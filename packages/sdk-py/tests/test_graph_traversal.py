"""Walking the derived graph — and the three things the walk must REFUSE.

The traversal is one recursive CTE in standard SQL, which is why it runs
unchanged on Postgres and SQLite and why no graph extension was adopted. The
risk of that query shape is not performance, it is that each of its three
guards is a single line somebody can forget:

* **depth**, because ``Spec.supersedes → Spec`` and ``Story.dependencies →
  Story`` are self-referential BY DESIGN — an unbounded walk here is a
  production incident, not a hypothetical;
* **the anti-cycle**, because a two-node cycle would otherwise burn the entire
  depth budget producing duplicates before the cap noticed;
* **``scope`` and ``tenant`` in the RECURSIVE step**, not merely in the anchor
  — this is the classic cross-tenant leak of a recursive CTE, and it is one
  easy line to leave out.

Each has a test that fails if the line is removed. The tenant one writes two
tenants holding documents with the SAME names, because a leak is invisible when
the names differ.
"""
from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio

from dna.kernel import Kernel
from dna.kernel.query.graph import GraphUnsupported
from tests import _graph_store

_SDLC_API = "github.com/ruinosus/dna/sdlc/v1"
_PORTFOLIO_API = "github.com/ruinosus/dna/portfolio/v1"
SCOPE = "graph-walk"


def _doc(kind: str, name: str, **spec: Any) -> dict[str, Any]:
    base = {"description": "d", "status": "todo"}
    base.update(spec)
    return {
        "apiVersion": _SDLC_API, "kind": kind,
        "metadata": {"name": name}, "spec": base,
    }


def _portfolio(kind: str, name: str, **spec: Any) -> dict[str, Any]:
    """The portfolio Kinds — the only TENANTED ones that declare references.

    The apiVersion is stated exactly, not approximated: a document whose
    apiVersion resolves to no registered port produces no edges at all (the
    write path cannot read a declaration it cannot find), so a wrong value here
    would make a cross-tenant leak test pass by finding nothing anywhere.
    """
    base = {"description": "d"}
    base.update(spec)
    return {
        "apiVersion": _PORTFOLIO_API, "kind": kind,
        "metadata": {"name": name}, "spec": base,
    }


@pytest.fixture(autouse=True)
def _modes(monkeypatch):
    monkeypatch.delenv("DNA_REF_VALIDATION", raising=False)
    monkeypatch.delenv("DNA_GRAPH_MAX_DEPTH", raising=False)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")


@pytest_asyncio.fixture(params=_graph_store.DIALECTS)
async def store(request):
    """A kernel over a real store, on BOTH dialects.

    Postgres runs when ``DATABASE_URL`` is set and is skipped otherwise — the
    same gate the adapter conformance matrix uses. The claim this feature rests
    on is that the producer and the recursive CTE are dialect-neutral, and a
    claim like that is worth what its second dialect proves.
    """
    src, cleanup = await _graph_store.build_store(request.param, "walk")
    kernel = Kernel.auto()
    kernel.source(src)
    try:
        yield kernel, src
    finally:
        await cleanup()


async def _chain(kernel) -> None:
    """``Task/t-1 → Story/s-x → Feature/f-y → Epic/e-1`` — three hops."""
    await kernel.write_document(SCOPE, "Epic", "e-1", _doc("Epic", "e-1"))
    await kernel.write_document(
        SCOPE, "Feature", "f-y", _doc("Feature", "f-y", epic="e-1"),
    )
    await kernel.write_document(
        SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"),
    )
    await kernel.write_document(
        SCOPE, "Task", "t-1", _doc("Task", "t-1", story_ref="s-x"),
    )


class TestTheProductQuestion:
    @pytest.mark.anyio
    async def test_what_points_at_this_document(self, store):
        """The read nothing could answer before: the Kind screen could say
        ``Story.feature → Feature`` exists as a RULE, never that THIS Story
        points at THIS Feature."""
        kernel, _ = store
        await _chain(kernel)
        result = await kernel.graph_refs(SCOPE, "Feature", "f-y", direction="in")
        assert [(e["from_kind"], e["from_name"]) for e in result.edges] == [
            ("Story", "s-x"),
        ]
        assert result.stop == "depth_reached"  # depth 1 and there IS more

    @pytest.mark.anyio
    async def test_depth_two_reaches_the_grandchild(self, store):
        kernel, _ = store
        await _chain(kernel)
        result = await kernel.graph_refs(
            SCOPE, "Feature", "f-y", direction="in", depth=2,
        )
        assert {(e["from_name"], e["depth"]) for e in result.edges} == {
            ("s-x", 1), ("t-1", 2),
        }

    @pytest.mark.anyio
    async def test_out_walks_the_other_way(self, store):
        kernel, _ = store
        await _chain(kernel)
        result = await kernel.graph_refs(
            SCOPE, "Task", "t-1", direction="out", depth=3,
        )
        assert {(e["to_kind"], e["to_name"]) for e in result.edges} == {
            ("Story", "s-x"), ("Feature", "f-y"), ("Epic", "e-1"),
        }

    @pytest.mark.anyio
    async def test_a_document_nothing_points_at_answers_empty_but_says_so(
        self, store,
    ):
        """An empty list is a legitimate answer HERE — the store keeps edges,
        so it is entitled to say "none". What it must also say is the producer
        mode, so the caller can tell this from a producer that is off."""
        kernel, _ = store
        await _chain(kernel)
        result = await kernel.graph_refs(SCOPE, "Task", "t-1", direction="in")
        assert result.edges == []
        assert result.graph_producer == "warn"
        assert result.stop == "complete"


class TestTheThreeRefusals:
    @pytest.mark.anyio
    async def test_a_walk_never_crosses_a_tenant(self, store):
        """⚠️ The cross-tenant leak, made visible.

        Both tenants hold ``Project/p-1`` and ``Membership/m-1`` under the SAME
        names, deliberately: with different names a leak is invisible, because
        the join would find nothing to leak. Two hops, so the RECURSIVE step is
        exercised and not merely the anchor — remove ``ee.tenant == :tenant``
        from that step and this test goes red, which is the only reason it
        exists.

        The edges are written through the adapter's own ``replace_edges``
        rather than by two tenanted kernel writes, and that is a deliberate
        acknowledgement of a PRE-EXISTING limitation, not a shortcut around
        this feature: on SQLite the ``documents`` primary key does not include
        ``tenant`` (i-092, carried as a strict xfail in the conformance
        matrix), so two tenants CANNOT hold the same document name in that
        store at all — the second write overwrites the first. The edge table's
        key does include ``tenant``, which is exactly what this test is about.
        """
        _, src = store
        from dna.kernel.query.references import ResolvedEdge

        for tenant in ("acme", "globex"):
            await src.replace_edges(
                SCOPE, "Project", "p-1",
                [ResolvedEdge(
                    field="org_ref", ordinal=0, value=f"org-{tenant}",
                    to_kind="Organization", to_scope=SCOPE,
                    declared=("Organization",),
                )],
                api_version=_PORTFOLIO_API, tenant=tenant, from_version=1,
            )
            await src.replace_edges(
                SCOPE, "Membership", "m-1",
                [ResolvedEdge(
                    field="scope_ref", ordinal=0, value="p-1",
                    to_kind="Project", to_scope=SCOPE,
                    declared=("Organization", "Project"),
                )],
                api_version=_PORTFOLIO_API, tenant=tenant, from_version=1,
            )

        for tenant in ("acme", "globex"):
            result = await src.traverse_edges(
                SCOPE, "Membership", "m-1",
                tenant=tenant, direction="out", depth=3,
            )
            reached = {e["to_name"] for e in result}
            assert reached == {"p-1", f"org-{tenant}"}, (
                f"cross-tenant leak walking as {tenant}: {reached}"
            )

    @pytest.mark.anyio
    async def test_a_cycle_terminates_and_reports_each_edge_once(self, store):
        """``Story.dependencies → Story`` is self-referential by design, so a
        cycle is ordinary data, not a corrupt state. The walk must end, and it
        must not report the same edge once per lap."""
        kernel, _ = store
        # Seed first, wire second: a cycle cannot be created by forward
        # references — the first write would resolve to nothing and the edge
        # would be dangling, which is a different test than this one.
        for n in ("s-a", "s-b", "s-c"):
            await kernel.write_document(SCOPE, "Story", n, _doc("Story", n))
        for src_name, dst in (("s-a", "s-b"), ("s-b", "s-c"), ("s-c", "s-a")):
            await kernel.write_document(
                SCOPE, "Story", src_name,
                _doc("Story", src_name, dependencies=[dst]),
            )
        result = await kernel.graph_refs(
            SCOPE, "Story", "s-a", direction="out", depth=5,
        )
        edges = {(e["from_name"], e["to_name"]) for e in result.edges}
        assert edges == {("s-a", "s-b"), ("s-b", "s-c"), ("s-c", "s-a")}
        assert len(result.edges) == 3, "the cycle produced duplicates"

    @pytest.mark.anyio
    async def test_a_self_loop_terminates(self, store):
        """The tightest cycle there is: a document depending on itself."""
        kernel, _ = store
        await kernel.write_document(SCOPE, "Story", "s-a", _doc("Story", "s-a"))
        await kernel.write_document(
            SCOPE, "Story", "s-a", _doc("Story", "s-a", dependencies=["s-a"]),
        )
        result = await kernel.graph_refs(
            SCOPE, "Story", "s-a", direction="out", depth=5,
        )
        assert len(result.edges) == 1

    @pytest.mark.anyio
    async def test_depth_is_clamped_to_the_ceiling(self, store, monkeypatch):
        """A caller cannot ask for an unbounded walk — the ceiling is
        configuration, never request input."""
        kernel, _ = store
        await _chain(kernel)
        monkeypatch.setenv("DNA_GRAPH_MAX_DEPTH", "2")
        result = await kernel.graph_refs(
            SCOPE, "Feature", "f-y", direction="in", depth=9999,
        )
        assert result.depth == 2
        assert max(e["depth"] for e in result.edges) <= 2

    @pytest.mark.anyio
    async def test_depth_defaults_to_one(self, store):
        kernel, _ = store
        await _chain(kernel)
        result = await kernel.graph_refs(SCOPE, "Feature", "f-y", direction="in")
        assert result.depth == 1


class TestDanglingEdges:
    @pytest.mark.anyio
    async def test_a_dangling_edge_is_returned_and_not_walked_through(
        self, store,
    ):
        """It is reported — it is the list of what is broken — and the walk
        does not continue through a target that does not exist."""
        kernel, _ = store
        await kernel.write_document(
            SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-ghost"),
        )
        result = await kernel.graph_refs(
            SCOPE, "Story", "s-x", direction="out", depth=3,
        )
        assert len(result.edges) == 1
        assert result.edges[0]["resolved"] is False
        assert result.dangling == result.edges


class TestUnsupportedIsNotEmpty:
    @pytest.mark.anyio
    async def test_a_store_without_edges_refuses_instead_of_answering_none(
        self, tmp_path,
    ):
        """⚠️ The refusal that matters most.

        ``[]`` reads as "nothing points at this document" — a claim only a
        store that actually records edges may make. The filesystem adapter has
        neither a transaction to write edges in nor a table to write them to,
        so it says so.
        """
        from dna.adapters.filesystem.writable import FilesystemWritableSource

        kernel = Kernel.auto()
        kernel.source(FilesystemWritableSource(str(tmp_path)))
        with pytest.raises(GraphUnsupported) as exc:
            await kernel.graph_refs(SCOPE, "Feature", "f-y", direction="in")
        assert "not the same as" in str(exc.value)

    @pytest.mark.anyio
    async def test_an_unknown_direction_is_refused(self, store):
        kernel, _ = store
        with pytest.raises(ValueError):
            await kernel.graph_refs(SCOPE, "Feature", "f-y", direction="sideways")
