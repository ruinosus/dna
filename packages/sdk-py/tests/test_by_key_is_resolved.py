"""``by: <chave>`` resolvido — fatia 5 de ``spec-topologia-do-grafo``.

Thirteen relations across five Kinds declared an address the kernel would not
follow. They now produce edges. This file is what stops each half of that from
arriving without the other, and every class here names the mutant it kills
rather than the feature it likes.

⚠️ **The mutant that matters most is the tie-break.** Nothing in the schema
makes a spec key unique, and nothing in this slice makes it unique either — a
UNIQUE index would refuse the tenant overlay that legitimately forks an
instance carrying the same key. So two instances CAN carry one key, and a
resolver that quietly picked the first would produce an edge indistinguishable
from a correct one: no error, no stack trace, nothing in the diff. ``limit=2``
exists for exactly this, and ``TestTwoIsARefusalNotATieBreak`` is what keeps it
from being quietly optimized to 1.

The whole file runs on BOTH dialects. Postgres serves the lookup from
``dna_insts_spec_gin_idx`` (a GIN over ``content::jsonb->'spec'``, generic over
the key, in the baseline schema since revision 0001 — which is why this slice
needed no migration); SQLite has neither GIN nor containment and scans. Same
answers, different costs, and only running both proves the first half.
"""
from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa

from dna import Kernel
from dna.kernel.errors import AmbiguousInstanceKey, KeyLookupUnsupported
from dna.kernel.query.references import ResolvedEdge, resolve_relations

from tests import _graph_store
from tests.test_kernel_invalidate_modes import _FakeWritableSource

SCOPE = "bykey"
# ``Project`` is a TENANTED Kind, so every write of one carries a tenant. The
# ``Workspace`` it points at is GLOBAL — which is the ordinary shape of this
# relation and the reason the lookup has to fall back from the tenant overlay
# to the base layer rather than only asking one of them.
TENANT = "acme"
_TENANT_API = "github.com/ruinosus/dna/tenant/v1"
_PORTFOLIO_API = "github.com/ruinosus/dna/portfolio/v1"


@pytest_asyncio.fixture(params=_graph_store.DIALECTS)
async def store(request):
    src, cleanup = await _graph_store.build_store(request.param, "bykey")
    k = Kernel.auto()
    k.source(src)
    try:
        yield k, src
    finally:
        await cleanup()


@pytest.fixture(autouse=True)
def _modes(monkeypatch):
    # ``enforce`` throughout, deliberately: the slice's central claim is that a
    # by-key miss survives the STRICTEST mode. Testing it under ``warn`` would
    # prove nothing, since warn persists everything.
    monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")


def _workspace(name: str, workspace_id: str) -> dict[str, Any]:
    return {
        "apiVersion": _TENANT_API, "kind": "Workspace",
        "metadata": {"name": name},
        "spec": {
            "workspace_id": workspace_id, "name": name,
            "created_by": "a@b.c", "created_at": "2026-08-07T00:00:00Z",
        },
    }


def _project(name: str, workspace_id: str) -> dict[str, Any]:
    return {
        "apiVersion": _PORTFOLIO_API, "kind": "Project",
        "metadata": {"name": name},
        "spec": {"name": name, "slug": name, "workspace_id": workspace_id},
    }


async def _edges(src, field: str | None = None) -> list[dict[str, Any]]:
    async with src._engine.connect() as conn:
        rows = (await conn.execute(sa.select(src.edges))).all()
    out = [dict(r._mapping) for r in rows]
    return [r for r in out if field is None or r["source_field"] == field]


# ---------------------------------------------------------------------------
# 1. The edge is born, and it points at the INSTANCE rather than at the key
# ---------------------------------------------------------------------------


class TestTheEdgePointsAtTheInstanceNotAtTheKey:
    """⚠️ The mutant: persist ``edge.value`` into ``dna_edges.to_name``.

    That is what the producer did before fatia 5, correctly, because ``value``
    and the target's name were the same string for every relation it followed.
    They are two different strings now — ``Project.workspace_id`` holds
    ``ws-3f9a`` and the Workspace is named ``barnabe-labs`` — and the reverse
    index is ``(scope, tenant, to_kind, to_name)``.

    A row carrying the KEY there is not merely imprecise: it is a row that no
    backlink query can ever return. The graph would gain thirteen relations'
    worth of edges and answer nothing new, which reads as success from every
    angle except the one that matters.
    """

    @pytest.mark.anyio
    async def test_to_name_is_the_targets_own_name(self, store):
        k, src = store
        await k.write_instance(
            SCOPE, "Workspace", "barnabe-labs",
            _workspace("barnabe-labs", "ws-3f9a"),
        )
        await k.write_instance(
            SCOPE, "Project", "p-1", _project("p-1", "ws-3f9a"), tenant=TENANT,
        )
        rows = await _edges(src, "workspace_id")
        assert len(rows) == 1, rows
        assert rows[0]["to_kind"] == "Workspace"
        assert rows[0]["to_name"] == "barnabe-labs", (
            "the edge recorded the KEY instead of the instance name — the "
            "reverse index is built on to_name, so this row is unreachable "
            "from every backlink query that exists"
        )
        assert rows[0]["to_api_version"] == _TENANT_API

    @pytest.mark.anyio
    async def test_the_backlink_query_actually_finds_it(self, store):
        """The property the column exists for, asserted THROUGH the door.

        The assertion above reads the row; this one asks the question a user
        asks. Without it, a producer that wrote a plausible-but-wrong
        ``to_name`` would still be green on the first test if somebody changed
        what it compares against."""
        k, src = store
        await k.write_instance(
            SCOPE, "Workspace", "barnabe-labs",
            _workspace("barnabe-labs", "ws-3f9a"),
        )
        await k.write_instance(
            SCOPE, "Project", "p-1", _project("p-1", "ws-3f9a"), tenant=TENANT,
        )
        back = await src.traverse_edges(
            SCOPE, "Workspace", "barnabe-labs", direction="in", depth=1,
            tenant=TENANT,
        )
        assert [e["from_name"] for e in back] == ["p-1"], (
            f"nothing points at the Workspace according to the graph: {back}"
        )

    @pytest.mark.anyio
    async def test_a_miss_records_what_it_was_POINTED_AT(self, store):
        """Dangling, and the row keeps the key rather than inventing a name.

        ``to_kind IS NULL`` says nothing resolved; ``to_name`` then has only
        one honest value, which is the address the author actually wrote."""
        k, src = store
        await k.write_instance(
            SCOPE, "Project", "p-2", _project("p-2", "ws-none"), tenant=TENANT,
        )
        rows = await _edges(src, "workspace_id")
        assert len(rows) == 1, rows
        assert rows[0]["to_kind"] is None
        assert rows[0]["to_name"] == "ws-none"


# ---------------------------------------------------------------------------
# 2. ⭐ Two is a refusal, never a tie-break
# ---------------------------------------------------------------------------


class TestTwoIsARefusalNotATieBreak:
    """⭐ THE mutant of this slice: ``limit=2`` quietly becoming ``limit=1``,
    or the resolver taking ``candidates[0]``.

    Either change makes every test above still pass. Nothing goes red, no
    exception is raised, and the graph fills with edges that point at whichever
    row the store happened to order first — a resolution indistinguishable from
    a correct one in the diff, on the screen and in the table. That is the
    precise failure shape ``AmbiguousInstanceId`` was built to prevent for ids,
    and it is worse here, because an id prefix is a query the caller can
    lengthen while a duplicated key is a state the data is already in.
    """

    @pytest.mark.anyio
    async def test_two_workspaces_one_key_refuse_at_the_kernel_door(self, store):
        k, _src = store
        await k.write_instance(SCOPE, "Workspace", "ws-a", _workspace("ws-a", "dup"))
        await k.write_instance(SCOPE, "Workspace", "ws-b", _workspace("ws-b", "dup"))
        with pytest.raises(AmbiguousInstanceKey) as exc:
            await k.find_instance_by_key(SCOPE, "Workspace", "workspace_id", "dup")
        # The remedy IS the list — a refusal that says "two" without saying
        # which two has told the caller they cannot proceed without telling
        # them how to.
        assert sorted(m["name"] for m in exc.value.matches) == ["ws-a", "ws-b"]
        assert "refusing to guess" in str(exc.value)

    @pytest.mark.anyio
    async def test_the_write_leaves_the_edge_UNRESOLVED_rather_than_picking(
        self, store,
    ):
        """The refusal reaching the graph, which is where it is observable.

        An ambiguous key produces a DANGLING row, never a row pointing at one
        of the two candidates. If this ever comes back with ``to_kind`` set,
        somebody has installed a tie-break — and a tie-break here is a lie the
        table will repeat forever."""
        k, src = store
        await k.write_instance(SCOPE, "Workspace", "ws-a", _workspace("ws-a", "dup"))
        await k.write_instance(SCOPE, "Workspace", "ws-b", _workspace("ws-b", "dup"))
        await k.write_instance(
            SCOPE, "Project", "p-3", _project("p-3", "dup"), tenant=TENANT,
        )
        rows = await _edges(src, "workspace_id")
        assert len(rows) == 1, rows
        assert rows[0]["to_kind"] is None, (
            f"the resolver broke the tie and pointed at "
            f"{rows[0]['to_name']!r} — an ambiguous resolution that chooses "
            f"one is worse than none, because it cannot be told from a right one"
        )

    @pytest.mark.anyio
    async def test_the_ambiguous_write_still_PERSISTS(self, store):
        """Two instances claiming a key is not the WRITER's fault, and this
        write is under ``enforce``. Refusing it would punish an author for a
        state two other instances are in."""
        k, src = store
        await k.write_instance(SCOPE, "Workspace", "ws-a", _workspace("ws-a", "dup"))
        await k.write_instance(SCOPE, "Workspace", "ws-b", _workspace("ws-b", "dup"))
        await k.write_instance(
            SCOPE, "Project", "p-3", _project("p-3", "dup"), tenant=TENANT,
        )
        assert await k.get_instance(
            SCOPE, "Project", "p-3", tenant=TENANT,
        ) is not None

    @pytest.mark.anyio
    async def test_ambiguous_and_missing_are_two_different_reports(self, store):
        """⚠️ The second mutant, and the quieter one: collapsing the two
        reasons into "dangling".

        Both produce ``to_kind IS NULL``, so the row cannot tell them apart —
        but the remedies are in different files. ``missing`` is fixed in the
        instance that points; ``ambiguous`` is fixed in the two instances
        pointed at. A report that said "dangling" for both would send half its
        readers to edit the wrong thing.
        """
        k, _src = store
        await k.write_instance(SCOPE, "Workspace", "ws-a", _workspace("ws-a", "dup"))
        await k.write_instance(SCOPE, "Workspace", "ws-b", _workspace("ws-b", "dup"))
        port = k.kind_port_for("Project", scope=SCOPE)

        async def _resolve(value: str) -> ResolvedEdge:
            edges, problems, discords, complete = await resolve_relations(
                port, _project("p", value),
                scope=SCOPE, name="p", tenant=TENANT,
                getter=k.get_instance, port_for=k.kind_port_for,
                key_getter=k.find_instance_by_key,
            )
            assert complete and problems == [], (problems, discords)
            by_field = {e.field: e for e in edges}
            return by_field["workspace_id"]

        ambiguous = await _resolve("dup")
        missing = await _resolve("ws-nobody-has")
        assert ambiguous.unresolved_reason == "ambiguous"
        assert missing.unresolved_reason == "missing"
        assert ambiguous.to_kind is missing.to_kind is None


# ---------------------------------------------------------------------------
# 3. Followed, and never enforced
# ---------------------------------------------------------------------------


class TestFollowedIsNotEnforced:
    """The asymmetry the slice is built on, exercised end to end under the
    strictest mode.

    ⚠️ Mutant: route the by-key notes into ``problems`` instead of
    ``discords``. One character of difference in ``references.py``, and every
    ``PlanBinding`` whose ``tier_id`` names an ALIAS starts failing to write —
    a class of data ``kernel.tier()`` resolves happily.
    """

    @pytest.mark.anyio
    async def test_a_miss_is_a_note_and_never_a_problem(self, store):
        k, _src = store
        port = k.kind_port_for("Project", scope=SCOPE)
        edges, problems, discords, complete = await resolve_relations(
            port, _project("p", "ws-nobody-has"),
            scope=SCOPE, name="p", tenant=TENANT,
            getter=k.get_instance, port_for=k.kind_port_for,
            key_getter=k.find_instance_by_key,
        )
        assert complete
        assert problems == [], (
            "a by-key miss landed in `problems`, which is the list the "
            "validator VETOES on"
        )
        assert any("workspace_id" in d for d in discords), (
            f"…and it was not reported anywhere either: {discords}. Silent is "
            f"not the same as non-vetoing"
        )
        assert len(edges) == 1 and edges[0].to_kind is None

    @pytest.mark.anyio
    async def test_a_by_NAME_miss_still_vetoes(self, store):
        """The control. Without it, "by-key does not veto" would also pass on
        a build where NOTHING vetoes any more."""
        from dna.kernel.protocols import SpecValidationError

        k, _src = store
        with pytest.raises(SpecValidationError):
            await k.write_instance(
                SCOPE, "Story", "s-1",
                {
                    "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
                    "kind": "Story", "metadata": {"name": "s-1"},
                    "spec": {"title": "t", "description": "d", "status": "todo",
                             "feature": "f-nobody-has"},
                },
            )


# ---------------------------------------------------------------------------
# 4. "Cannot ask" is not "the answer is no"
# ---------------------------------------------------------------------------


class TestAStoreThatCannotAskSaysSo:
    """⚠️ Mutant: return ``None`` from ``find_instance_by_key`` when the
    adapter has no ``find_instances_by_spec_key``.

    It is the tidier code and it is a lie: ``None`` reads as "no instance
    carries that key", which accuses data nobody examined. The same reasoning
    that makes ``GraphUnsupported`` a 501 rather than ``[]``.
    """

    @staticmethod
    def _deaf_kernel() -> Kernel:
        """The suite's conformant fake, which implements no
        ``find_instances_by_spec_key`` and is therefore already the store this
        class is about.

        Reused rather than hand-rolled ON PURPOSE: a bespoke stub is refused at
        registration for not satisfying SourcePort, and the test would then
        pass on the wrong exception entirely — green, and checking nothing."""
        k = Kernel.auto()
        k.source(_FakeWritableSource())
        return k

    @pytest.mark.anyio
    async def test_the_kernel_refuses_rather_than_answering_none(self):
        k = self._deaf_kernel()
        with pytest.raises(KeyLookupUnsupported) as exc:
            await k.find_instance_by_key("s", "Workspace", "workspace_id", "w")
        assert "find_instances_by_spec_key" in str(exc.value)

    @pytest.mark.anyio
    async def test_the_write_path_records_the_reason_and_does_not_blow_up(self):
        """The other half, and it must be the OTHER half.

        A capability the store lacks may not fail a write that did nothing
        wrong — so the pipeline CATCHES the refusal. What it must not do is
        forget it: the edge records ``unsupported``, which is a different fact
        from ``missing`` and the only one that is true here."""
        k = self._deaf_kernel()
        port = k.kind_port_for("Project")
        edges, problems, _discords, complete = await resolve_relations(
            port, _project("p", "ws-1"),
            scope=SCOPE, name="p", tenant=TENANT,
            getter=k.get_instance, port_for=k.kind_port_for,
            key_getter=k.find_instance_by_key,
        )
        assert complete and problems == []
        by_field = {e.field: e for e in edges}
        assert by_field["workspace_id"].unresolved_reason == "unsupported", (
            "the store's incapacity was recorded as a missing target — an "
            "accusation against data nobody looked at"
        )

    @pytest.mark.anyio
    async def test_no_key_getter_at_all_is_also_unsupported(self):
        """A REDUCED HOST, not a reduced store — and the two must land on the
        same honest reason rather than on ``missing``."""
        k = self._deaf_kernel()
        port = k.kind_port_for("Project")
        edges, _p, _d, complete = await resolve_relations(
            port, _project("p", "ws-1"),
            scope=SCOPE, name="p", tenant=TENANT,
            getter=k.get_instance, port_for=k.kind_port_for,
            key_getter=None,
        )
        assert complete
        assert {e.unresolved_reason for e in edges} == {"unsupported"}


# ---------------------------------------------------------------------------
# 5. The lookup is EXACT — no containment, no coercion
# ---------------------------------------------------------------------------


class TestTheMatchIsExact:
    """⚠️ Mutant: drop the ``->>`` recheck on the Postgres leg and let the GIN
    containment answer alone.

    ``@>`` is a jsonb rule, not an equality: containment has a documented
    exception for arrays, so ``{"workspace_id": ["a","b"]} @> {"workspace_id":
    "a"}`` is a question the operator answers on its own terms. A relation
    declared ``cardinality: one`` matching an element of somebody's list is
    resolution by accident — and it would show up only on Postgres, which is
    exactly the kind of divergence running one dialect hides.
    """

    @pytest.mark.anyio
    async def test_a_list_valued_key_does_not_match_one_of_its_elements(
        self, store,
    ):
        k, _src = store
        listy = _workspace("listy", "x")
        listy["spec"]["workspace_id"] = ["ws-3f9a", "ws-other"]
        await k.write_instance(SCOPE, "Workspace", "listy", listy)
        hit = await k.find_instance_by_key(
            SCOPE, "Workspace", "workspace_id", "ws-3f9a",
        )
        assert hit is None, (
            "a list-valued key matched one of its elements — the containment "
            "operator answered where only equality should have"
        )

    @pytest.mark.anyio
    async def test_a_numeric_key_does_not_match_its_string_spelling(self, store):
        k, src = store
        numeric = _workspace("numeric", "x")
        numeric["spec"]["workspace_id"] = 7
        await k.write_instance(SCOPE, "Workspace", "numeric", numeric)
        assert await src.find_instances_by_spec_key(
            SCOPE, "Workspace", "workspace_id", "7",
        ) == []

    @pytest.mark.anyio
    async def test_a_key_that_is_not_an_identifier_is_refused_at_the_adapter(
        self, store,
    ):
        """The guard restated at the door that BUILDS the expression.

        ``normalize_relations`` already refuses a non-identifier ``by`` when
        the Kind loads. That is the far door; this method is public on the
        adapter and its SQLite leg interpolates the key into a JSON path. A
        guard only the far door runs is a guard an unusual caller walks
        around — the ``guard-existe-porta-nao-chama`` shape."""
        _k, src = store
        with pytest.raises(ValueError, match="identifier"):
            await src.find_instances_by_spec_key(
                SCOPE, "Workspace", "spec.x' or '1'='1", "v",
            )


# ---------------------------------------------------------------------------
# 6. Where it looks — the SAME chain the by-name path walks
# ---------------------------------------------------------------------------


class TestItWalksTheSameScopeChainAsGetInstance:
    """⚠️ Mutant: resolve only in the writer's own scope.

    Three of the five key-addressed target Kinds (``PricingPlan``,
    ``ModelProfile``, ``Role``) are registry Kinds that live in ``_lib`` and
    are read from every scope by inheritance. A resolver that looked only
    locally would call every one of those references dangling and fill the
    graph with breakage it invented itself — worse than not resolving, because
    the rows LOOK like findings.
    """

    @pytest.mark.anyio
    async def test_a_parent_scope_instance_resolves(self, store):
        k, src = store
        await k.write_instance(
            "_lib", "Workspace", "shared", _workspace("shared", "ws-shared"),
        )
        await k.write_instance(
            SCOPE, "Project", "p-4", _project("p-4", "ws-shared"), tenant=TENANT,
        )
        rows = await _edges(src, "workspace_id")
        assert len(rows) == 1, rows
        assert rows[0]["to_kind"] == "Workspace", (
            "an inherited Workspace was not found — the by-key resolver is "
            "looking in fewer places than get_instance does, so the two "
            "addressings of one relation disagree about WHERE"
        )
        assert rows[0]["to_name"] == "shared"

    @pytest.mark.anyio
    async def test_the_local_instance_wins_over_the_inherited_one(self, store):
        """Chain ORDER, not merely chain reach. Both hops carry the key; the
        writer's own scope has to win, exactly as it does for by-name."""
        k, _src = store
        await k.write_instance(
            "_lib", "Workspace", "from-lib", _workspace("from-lib", "ws-both"),
        )
        await k.write_instance(
            SCOPE, "Workspace", "from-local", _workspace("from-local", "ws-both"),
        )
        hit = await k.find_instance_by_key(
            SCOPE, "Workspace", "workspace_id", "ws-both",
        )
        assert hit is not None
        raw, hop = hit
        assert hop == SCOPE
        assert (raw.get("metadata") or {}).get("name") == "from-local"
