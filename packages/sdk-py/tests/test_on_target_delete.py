"""``on_target_delete`` — the declaration, and the delete that honors it.

Slice 2 of ``spec-topologia-do-grafo``: the other half of referential
integrity, the half an application can have when the database cannot. The
measured gap it closes, in the spec's words: *"deleting a Feature that 47
Stories point at is accepted in silence, and the delete has no ``pre_save``
veto"*.

Two things this file is built to keep honest, both of them lessons this house
has already paid for:

**The gate must be reached through the REAL door.** Every enforcement test here
calls ``Kernel.delete_instance`` against a real store, never
``plan_target_delete`` directly. A validator proven only in isolation is the
recurring defect with a name — *guard exists, door does not call it* — and it
has shipped here three times. The unit tests of the planner exist too, but they
are not what proves the policy is on.

**The default must be measured, not asserted.** ``test_the_default_is_todays_
behavior`` deletes a referenced target with NOTHING declared and requires it to
succeed. That test is the one that fails if somebody "tightens" the default to
Gel's ``restrict``, which would silently convert 33 resolved relations in this
registry into refusals.

Both dialects, for the reason the traversal tests give: the whole argument for
a recursive CTE over a graph engine is that it is standard SQL, and an argument
like that is worth what its second dialect proves. Postgres runs when
``DATABASE_URL`` is set.
"""
from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio

from dna.kernel import Kernel
from dna.kernel.errors import TargetDeleteRestricted
from dna.kernel.kinds.base import KindBase
from dna.kernel.kinds.relations import (
    ON_TARGET_DELETE,
    ON_TARGET_DELETE_DEFAULT,
    ON_TARGET_DELETE_ENFORCING,
    Relation,
    normalize_relations,
    relations_of,
)
from dna.kernel.protocols import StorageDescriptor
from dna.kernel.query.graph import GraphUnsupported
from dna.kernel.write.target_delete import enforcers_for, registry_relations
from tests import _graph_store

SCOPE = "on-target-delete"
_API = "example.com/otd/v1"


# ── the probe Kinds ──────────────────────────────────────────────────────────
#
# A pair rather than a borrowed builtin, so a test can move the POLICY without
# moving anything else. Borrowing `Story.feature` would have meant patching a
# registered builtin, and a test that mutates the registry it is measuring
# cannot tell its own edit from the behavior.


class _Anchor(KindBase):
    """The target — the thing that gets deleted."""

    api_version = _API
    kind = "OtdAnchor"
    alias = "otd-anchor"
    origin = "example.com/otd"
    plane = "record"
    storage = StorageDescriptor.yaml(container="otdanchors")

    def schema(self):
        return {"type": "object", "properties": {"title": {"type": "string"}}}


def _pointer(policy: str | None, *, kind: str = "OtdPointer", to: str = "OtdAnchor",
             by: str | None = None, self_ref: bool = False):
    """A Kind pointing at :class:`_Anchor` under ``policy``.

    Built per test because the POLICY is the variable — the whole file is about
    what changes when that one key changes and nothing else does.
    """
    rel: dict[str, Any] = {"to": to, "cardinality": "one"}
    if policy is not None:
        rel["on_target_delete"] = policy
    if by is not None:
        rel["by"] = by
    relations = {"anchor": rel}
    if self_ref:
        relations["buddy"] = {
            "to": kind, "cardinality": "one", "on_target_delete": "delete_source",
        }

    class _Pointer(KindBase):
        api_version = _API
        origin = "example.com/otd"
        plane = "record"

    _Pointer.kind = kind
    _Pointer.alias = kind.lower()
    _Pointer.storage = StorageDescriptor.yaml(container=kind.lower() + "s")
    _Pointer.relations = relations
    _Pointer.schema = lambda self: {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "anchor": {"type": "string"},
            "buddy": {"type": "string"},
        },
    }
    return _Pointer()


def _doc(kind: str, name: str, **spec: Any) -> dict[str, Any]:
    return {
        "apiVersion": _API, "kind": kind,
        "metadata": {"name": name}, "spec": {"title": name, **spec},
    }


@pytest.fixture(autouse=True)
def _modes(monkeypatch):
    monkeypatch.delenv("DNA_GRAPH_MAX_DEPTH", raising=False)
    monkeypatch.setenv("DNA_REF_VALIDATION", "warn")
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")


@pytest_asyncio.fixture(params=_graph_store.DIALECTS)
async def store(request):
    src, cleanup = await _graph_store.build_store(request.param, "otd")
    try:
        yield src
    finally:
        await cleanup()


def _kernel(src, *pointers) -> Kernel:
    k = Kernel.auto()
    k.kind(_Anchor())
    for p in pointers:
        k.kind(p)
    k.source(src)
    return k


async def _seed(k: Kernel, pointer_kind: str = "OtdPointer") -> None:
    await k.write_instance(SCOPE, "OtdAnchor", "a-1", _doc("OtdAnchor", "a-1"))
    await k.write_instance(
        SCOPE, pointer_kind, "p-1", _doc(pointer_kind, "p-1", anchor="a-1"),
    )


async def _exists(src, kind: str, name: str) -> bool:
    return await src.load_one(SCOPE, kind, name) is not None


# ── 1. the declaration ───────────────────────────────────────────────────────


class TestTheVocabularyIsGels:
    def test_the_menu_is_gels_three(self):
        """Not our words. Gel's ``edb/edgeql/qltypes.py`` closes
        ``LinkTargetDeleteAction`` at ``Restrict | DeleteSource | Allow |
        DeferredRestrict``; we take three verbatim, transliterated by the one
        rule this repo applies to every YAML key (spaces → underscores).

        ``deferred restrict`` is absent because there is no transaction
        boundary here to defer to — it could only behave as ``restrict``. If
        somebody adds it, this test is where they have to say so."""
        assert ON_TARGET_DELETE == ("restrict", "delete_source", "allow")

    def test_enforcing_is_derived_and_not_retyped(self):
        """A fourth value added to the menu enrols itself in enforcement rather
        than being silently left out of it. Anchored on the word that means
        "do nothing", NOT on the default — those are equal today by decision,
        and subtracting the default would flip ``allow`` into an enforcing
        policy the day the default moved."""
        assert ON_TARGET_DELETE_ENFORCING == frozenset(ON_TARGET_DELETE) - {"allow"}
        assert ON_TARGET_DELETE_DEFAULT not in ON_TARGET_DELETE_ENFORCING

    def test_the_key_is_in_the_closed_vocabulary(self):
        rel = normalize_relations(
            {"anchor": {"to": "OtdAnchor", "cardinality": "one",
                        "on_target_delete": "restrict"}},
        )["anchor"]
        assert rel.on_target_delete == "restrict"

    @pytest.mark.parametrize("bad", ["cascade", "RESTRICT", "deferred_restrict", 7])
    def test_a_value_outside_the_menu_is_refused_at_load(self, bad):
        with pytest.raises(ValueError, match="on_target_delete must be one of"):
            normalize_relations(
                {"a": {"to": "OtdAnchor", "cardinality": "one",
                       "on_target_delete": bad}},
            )


class TestDeclaredIsNotTheSameAsDefaulted:
    def test_undeclared_reads_as_the_default_and_says_it_was_not_declared(self):
        rel = normalize_relations(
            {"a": {"to": "OtdAnchor", "cardinality": "one"}},
        )["a"]
        assert rel.on_target_delete is None
        assert rel.on_target_delete_effective == ON_TARGET_DELETE_DEFAULT
        assert rel.to_wire()["on_target_delete_declared"] is False

    def test_an_explicit_allow_survives_the_round_trip(self):
        """THE AuditLog case, and the mutant is real: ``by`` omits its default
        from ``to_declaration`` as noise, and copying that here would erase the
        only thing this declaration exists to say. A reference that SHOULD
        outlive its target is declared policy; nothing having been decided is
        not."""
        rel = normalize_relations(
            {"a": {"to": "OtdAnchor", "cardinality": "one",
                   "on_target_delete": "allow"}},
        )["a"]
        assert rel.on_target_delete == "allow"
        assert rel.to_declaration()["on_target_delete"] == "allow"
        assert rel.to_wire()["on_target_delete_declared"] is True
        # And the round trip is a fixed point.
        again = normalize_relations({"a": rel.to_declaration()})["a"]
        assert again.on_target_delete == "allow"

    def test_undeclared_does_NOT_appear_in_the_declaration(self):
        rel = normalize_relations(
            {"a": {"to": "OtdAnchor", "cardinality": "one"}},
        )["a"]
        assert "on_target_delete" not in rel.to_declaration()

    def test_the_wire_always_carries_the_effective_value(self):
        """A stable key set is what lets a consumer type it without probing —
        the rule ``to_wire`` already follows for ``inverse_of``."""
        rel = normalize_relations(
            {"a": {"to": "OtdAnchor", "cardinality": "one"}},
        )["a"]
        assert rel.to_wire()["on_target_delete"] == ON_TARGET_DELETE_DEFAULT


class TestAPolicyNeedsAMechanism:
    """``restrict``/``delete_source`` on a relation the kernel does not resolve
    is a promise with nobody to keep it — the same refusal, for the same
    reason, as ``inverse_of`` on ``to: "*"``."""

    @pytest.mark.parametrize("policy", sorted(ON_TARGET_DELETE_ENFORCING))
    def test_enforcing_on_a_composite_by_is_refused(self, policy):
        with pytest.raises(ValueError, match="does not resolve"):
            normalize_relations(
                {"a": {"to": "OtdAnchor", "cardinality": "one",
                       "by": "Kind:name", "on_target_delete": policy}},
            )

    @pytest.mark.parametrize("policy", sorted(ON_TARGET_DELETE_ENFORCING))
    def test_enforcing_on_an_open_target_is_refused(self, policy):
        with pytest.raises(ValueError, match="does not resolve"):
            normalize_relations(
                {"a": {"to": "*", "cardinality": "one",
                       "by": "Kind:name", "on_target_delete": policy}},
            )

    @pytest.mark.parametrize("policy", sorted(ON_TARGET_DELETE_ENFORCING))
    def test_enforcing_on_a_target_spec_field_is_refused(self, policy):
        with pytest.raises(ValueError, match="does not resolve"):
            normalize_relations(
                {"a": {"to": "OtdAnchor", "cardinality": "one",
                       "by": "workspace_id", "on_target_delete": policy}},
            )

    def test_allow_IS_legal_on_an_unresolved_relation(self):
        """The AuditLog shape exactly: a composite pointer that must keep
        pointing after its target dies. Refusing ``allow`` here would refuse
        the very declaration this slice exists to unblock."""
        rel = normalize_relations(
            {"target": {"to": "*", "cardinality": "one",
                        "by": "Kind:name", "on_target_delete": "allow"}},
        )["target"]
        assert rel.on_target_delete == "allow"
        assert rel.resolved is False

    def test_the_refusal_tracks_resolved_and_is_not_a_second_definition(self):
        """The parse-time condition is spelled out from ``to``/``by`` because
        no ``Relation`` exists yet at that point. This pins the two together:
        every relation the parser ACCEPTS with an enforcing policy is one
        ``Relation.resolved`` also calls resolved. If somebody loosens either
        side alone, they disagree here."""
        accepted = normalize_relations({
            "ok": {"to": "OtdAnchor", "cardinality": "one",
                   "on_target_delete": "restrict"},
        })["ok"]
        assert accepted.resolved is True
        assert accepted.enforces_on_target_delete is True


# ── 2. the DEFAULT is today's behavior, and it was measured ──────────────────


class TestTheDefaultIsTodaysBehavior:
    @pytest.mark.anyio
    async def test_deleting_a_referenced_target_still_succeeds(self, store):
        """⚠️ THE mutant that guards the default. This passed before this slice
        existed and must pass after it — the registry declares 63 relations,
        none of which was written by an author who had this question in front
        of them, so a ``restrict`` default would be 33 new refusals nobody
        asked for. If somebody "tightens" the default, this goes red."""
        k = _kernel(store, _pointer(None))
        await _seed(k)
        refs = await k.graph_refs(SCOPE, "OtdAnchor", "a-1", direction="in")
        assert [(e["from_kind"], e["from_name"]) for e in refs.edges] == [
            ("OtdPointer", "p-1"),
        ]
        await k.delete_instance(SCOPE, "OtdAnchor", "a-1")
        assert not await _exists(store, "OtdAnchor", "a-1")
        # And the referrer is untouched — `allow` is not a quiet cascade.
        assert await _exists(store, "OtdPointer", "p-1")

    @pytest.mark.anyio
    async def test_an_explicit_allow_behaves_exactly_like_the_default(self, store):
        """The AuditLog promise, end to end: the reference is left dangling ON
        PURPOSE, and saying so out loud changes nothing about what happens."""
        k = _kernel(store, _pointer("allow"))
        await _seed(k)
        await k.delete_instance(SCOPE, "OtdAnchor", "a-1")
        assert not await _exists(store, "OtdAnchor", "a-1")
        assert await _exists(store, "OtdPointer", "p-1")

    @pytest.mark.anyio
    async def test_the_gate_touches_no_store_when_nothing_declares(self, store):
        """The cost claim, asserted rather than believed. With no enforcing
        declaration the planner must not run a graph query at all — the whole
        registry is in this state today, and a gate that queried on every
        delete would tax every deployment for a feature none of them use."""
        k = _kernel(store, _pointer(None))
        await _seed(k)
        calls = []
        real = store.traverse_edges

        async def counting(*a, **kw):
            calls.append(a)
            return await real(*a, **kw)

        store.traverse_edges = counting
        try:
            await k.delete_instance(SCOPE, "OtdAnchor", "a-1")
        finally:
            store.traverse_edges = real
        assert calls == []


# ── 3. restrict ──────────────────────────────────────────────────────────────


class TestRestrict:
    @pytest.mark.anyio
    async def test_the_delete_is_REFUSED_through_the_real_door(self, store):
        """⚠️ THE mutant this slice exists for. Remove the gate call from
        ``WritePipeline.delete`` and this goes green-to-red: the delete
        succeeds and the refusal never happens."""
        k = _kernel(store, _pointer("restrict"))
        await _seed(k)
        with pytest.raises(TargetDeleteRestricted) as exc:
            await k.delete_instance(SCOPE, "OtdAnchor", "a-1")
        assert "OtdPointer/p-1.anchor" in str(exc.value)
        # ⚠️ And NOTHING was deleted. A refusal that costs data is not one.
        assert await _exists(store, "OtdAnchor", "a-1")
        assert await _exists(store, "OtdPointer", "p-1")

    @pytest.mark.anyio
    async def test_the_refusal_carries_the_list_not_just_the_count(self, store):
        """The remedy IS the list. A refusal that says "something points at
        this" and makes the caller run a second query to find out what has told
        them they cannot proceed without telling them how to."""
        k = _kernel(store, _pointer("restrict"))
        await k.write_instance(SCOPE, "OtdAnchor", "a-1", _doc("OtdAnchor", "a-1"))
        for n in ("p-1", "p-2", "p-3"):
            await k.write_instance(
                SCOPE, "OtdPointer", n, _doc("OtdPointer", n, anchor="a-1"),
            )
        with pytest.raises(TargetDeleteRestricted) as exc:
            await k.delete_instance(SCOPE, "OtdAnchor", "a-1")
        assert {r["name"] for r in exc.value.referrers} == {"p-1", "p-2", "p-3"}
        assert {r["relation"] for r in exc.value.referrers} == {"anchor"}

    @pytest.mark.anyio
    async def test_an_UNREFERENCED_target_still_deletes(self, store):
        """``restrict`` refuses a delete that would break a reference, not
        every delete of the Kind. The failure mode this kills is a gate that
        keys on the DECLARATION and never looks at the data."""
        k = _kernel(store, _pointer("restrict"))
        await k.write_instance(SCOPE, "OtdAnchor", "a-1", _doc("OtdAnchor", "a-1"))
        await k.delete_instance(SCOPE, "OtdAnchor", "a-1")
        assert not await _exists(store, "OtdAnchor", "a-1")

    @pytest.mark.anyio
    async def test_deleting_the_REFERRER_first_frees_the_target(self, store):
        """The remedy the message names, executed. A refusal whose stated fix
        does not work is worse than a silent delete."""
        k = _kernel(store, _pointer("restrict"))
        await _seed(k)
        await k.delete_instance(SCOPE, "OtdPointer", "p-1")
        await k.delete_instance(SCOPE, "OtdAnchor", "a-1")
        assert not await _exists(store, "OtdAnchor", "a-1")

    @pytest.mark.anyio
    async def test_a_policy_on_ANOTHER_kind_does_not_fire(self, store):
        """``restrict`` on ``X.anchor → OtdAnchor`` says nothing about deleting
        an ``OtdOther``. The mutant: a gate that asks "does any relation
        enforce?" instead of "does any relation enforce ON THIS KIND?" — the
        exact granularity error a green guard made here on 06/08/2026."""
        k = _kernel(store, _pointer("restrict"))
        rels = registry_relations(k.kind_ports())
        assert enforcers_for(rels, "OtdAnchor")
        assert enforcers_for(rels, "OtdPointer") == []

    @pytest.mark.anyio
    async def test_a_STALE_edge_outside_the_declared_targets_does_not_fire(
        self, store,
    ):
        """⚠️ The mutant for the per-EDGE target check, which the registry-level
        one above does NOT reach — it survived a mutation run, which is why this
        test exists.

        Declarations are mutable at RUNTIME here (``author_kind`` registers
        Kinds while the process is up), and the edge graph is derived state
        written earlier. So an edge can outlive the declaration that produced
        it: a polymorphic ``to: [OtdAnchor, OtdOther]`` writes an edge to an
        ``OtdOther``, then the declaration NARROWS to ``OtdAnchor`` alone. The
        stale edge is still in the store. The policy is about the Kinds the
        relation declares NOW, so deleting the ``OtdOther`` must go through.

        Two kernels over ONE store, because that is the real shape of the
        event: the edges were written by yesterday's deploy and are being read
        by today's. And an ``OtdHolder`` that declares ``restrict`` ON
        ``OtdOther`` but has no instances, so the planner really does reach the
        graph walk — without it the registry-level short-circuit fires first and
        the per-edge check is never asked anything."""

        class _Other(KindBase):
            api_version = _API
            kind = "OtdOther"
            alias = "otd-other"
            origin = "example.com/otd"
            plane = "record"
            storage = StorageDescriptor.yaml(container="otdothers")

            def schema(self):
                return {"type": "object",
                        "properties": {"title": {"type": "string"}}}

        # Yesterday: the relation names BOTH, so the edge to OtdOther is real.
        wide = Kernel.auto()
        wide.kind(_Anchor())
        wide.kind(_Other())
        wide.kind(_pointer("restrict", to=["OtdAnchor", "OtdOther"]))
        wide.source(store)
        await wide.write_instance(SCOPE, "OtdOther", "o-1", _doc("OtdOther", "o-1"))
        await wide.write_instance(
            SCOPE, "OtdPointer", "p-9", _doc("OtdPointer", "p-9", anchor="o-1"),
        )
        edges = await wide.graph_refs(SCOPE, "OtdOther", "o-1", direction="in")
        assert [(e["from_kind"], e["from_name"]) for e in edges.edges] == [
            ("OtdPointer", "p-9"),
        ], "the stale edge has to EXIST or this test proves nothing"

        # Today: the declaration narrowed. The edge did not move.
        narrow = Kernel.auto()
        narrow.kind(_Anchor())
        narrow.kind(_Other())
        narrow.kind(_pointer("restrict", to="OtdAnchor"))
        narrow.kind(_pointer("restrict", kind="OtdHolder", to="OtdOther"))
        narrow.source(store)
        # The short-circuit must NOT fire — otherwise the walk never happens and
        # this test would pass without exercising the thing it is named for.
        assert enforcers_for(
            registry_relations(narrow.kind_ports()), "OtdOther",
        ), "the planner has to reach the graph walk for this test to mean anything"
        await narrow.delete_instance(SCOPE, "OtdOther", "o-1")
        assert not await _exists(store, "OtdOther", "o-1")

    def test_the_refusal_is_a_verdict_about_the_REQUEST(self):
        """``KernelRefusal``, not ``CapabilityRefusal``. The remedy is a
        different request (delete the referrers), never a different deployment
        — the policy is declared in the data and would travel with it."""
        from dna.kernel.errors import CapabilityRefusal, KernelRefusal

        assert issubclass(TargetDeleteRestricted, KernelRefusal)
        assert not issubclass(TargetDeleteRestricted, CapabilityRefusal)
        assert issubclass(TargetDeleteRestricted, ValueError)


# ── 4. delete_source ─────────────────────────────────────────────────────────


class TestDeleteSource:
    @pytest.mark.anyio
    async def test_the_referrer_goes_with_the_target(self, store):
        k = _kernel(store, _pointer("delete_source"))
        await _seed(k)
        await k.delete_instance(SCOPE, "OtdAnchor", "a-1")
        assert not await _exists(store, "OtdAnchor", "a-1")
        assert not await _exists(store, "OtdPointer", "p-1")

    @pytest.mark.anyio
    async def test_the_cascade_is_TRANSITIVE(self, store):
        """``p-2 → p-1 → a-1``, all ``delete_source``. A one-hop cascade would
        leave ``p-2`` pointing at a corpse — which is the state the whole slice
        exists to stop producing."""
        k = _kernel(store, _pointer("delete_source", self_ref=True))
        await _seed(k)
        await k.write_instance(
            SCOPE, "OtdPointer", "p-2", _doc("OtdPointer", "p-2", buddy="p-1"),
        )
        await k.delete_instance(SCOPE, "OtdAnchor", "a-1")
        assert not await _exists(store, "OtdPointer", "p-1")
        assert not await _exists(store, "OtdPointer", "p-2")

    @pytest.mark.anyio
    async def test_a_CYCLE_terminates(self, store):
        """``Story.dependencies → Story`` makes cycles ordinary rather than
        corrupt, so a cascade planner without a visited set is a hang in
        production, not a hypothetical."""
        k = _kernel(store, _pointer("delete_source", self_ref=True))
        await _seed(k)
        await k.write_instance(
            SCOPE, "OtdPointer", "p-2",
            _doc("OtdPointer", "p-2", anchor="a-1", buddy="p-1"),
        )
        await k.write_instance(
            SCOPE, "OtdPointer", "p-1",
            _doc("OtdPointer", "p-1", anchor="a-1", buddy="p-2"),
        )
        await k.delete_instance(SCOPE, "OtdAnchor", "a-1")
        assert not await _exists(store, "OtdPointer", "p-1")
        assert not await _exists(store, "OtdPointer", "p-2")

    @pytest.mark.anyio
    async def test_a_RESTRICT_anywhere_in_the_closure_stops_EVERYTHING(self, store):
        """⚠️ The mutant for pre-flight. Plan the whole closure before deleting
        anything, or the cascade destroys instances on the way to discovering
        it must refuse — and there is no transaction to roll that back."""
        holder = _pointer("restrict", kind="OtdHolder", to="OtdPointer")
        # OtdHolder.anchor → OtdPointer under `restrict`, so the cascade
        # `a-1 → p-1` is blocked by `h-1` holding `p-1`.
        k = _kernel(store, _pointer("delete_source"), holder)
        await _seed(k)
        await k.write_instance(
            SCOPE, "OtdHolder", "h-1", _doc("OtdHolder", "h-1", anchor="p-1"),
        )
        with pytest.raises(TargetDeleteRestricted):
            await k.delete_instance(SCOPE, "OtdAnchor", "a-1")
        assert await _exists(store, "OtdAnchor", "a-1")
        assert await _exists(store, "OtdPointer", "p-1")
        assert await _exists(store, "OtdHolder", "h-1")


# ── 5. the honest refusal when the store cannot answer ───────────────────────


class TestAStoreThatKeepsNoGraph:
    @pytest.mark.anyio
    async def test_a_declared_policy_against_a_graphless_store_REFUSES(self, tmp_path):
        """Deleting anyway would be the confident lie the ``CapabilityRefusal``
        family exists to refuse, dressed as *"nothing pointed at it"*. 501, not
        a silent success."""
        from dna.adapters.filesystem.writable import FilesystemWritableSource

        src = FilesystemWritableSource(str(tmp_path))
        k = _kernel(src, _pointer("restrict"))
        await k.write_instance(SCOPE, "OtdAnchor", "a-1", _doc("OtdAnchor", "a-1"))
        with pytest.raises(GraphUnsupported):
            await k.delete_instance(SCOPE, "OtdAnchor", "a-1")

    @pytest.mark.anyio
    async def test_a_graphless_store_with_NO_policy_deletes_normally(self, tmp_path):
        """The refusal above must not become a tax on `file://`, which is the
        purest open-core case. No policy declared, no capability needed."""
        from dna.adapters.filesystem.writable import FilesystemWritableSource

        src = FilesystemWritableSource(str(tmp_path))
        k = _kernel(src, _pointer(None))
        await k.write_instance(SCOPE, "OtdAnchor", "a-1", _doc("OtdAnchor", "a-1"))
        await k.delete_instance(SCOPE, "OtdAnchor", "a-1")


# ── 6. the registry, as it stands ────────────────────────────────────────────


def test_no_registered_relation_declares_a_policy_yet():
    """The slice ships the MECHANISM and changes no behavior — asserted, not
    promised. When ``AuditLog`` lands (the next batch, deliberately not here),
    this test is the one that has to be updated on purpose, which is exactly
    the moment somebody should be looking at what changes.

    Derived from the live registry rather than a typed list, so a Kind added
    tomorrow is covered without anybody remembering this file."""
    declared = [
        f"{kind}.{name} = {rel.on_target_delete}"
        for kind, rels in registry_relations(Kernel.auto().kind_ports()).items()
        for name, rel in rels.items()
        if rel.on_target_delete is not None
    ]
    assert declared == [], declared


def test_every_registered_relation_reads_as_allow():
    """The other half of the assertion above, and the one that would catch a
    changed DEFAULT rather than a new declaration. Two failure modes, two
    tests: the first sees somebody declare, this one sees somebody redefine."""
    offenders = [
        f"{kind}.{name}"
        for kind, rels in registry_relations(Kernel.auto().kind_ports()).items()
        for name, rel in rels.items()
        if rel.enforces_on_target_delete
    ]
    assert offenders == [], offenders
