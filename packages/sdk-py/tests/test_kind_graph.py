"""The SCHEMA graph projection — ``dna.kernel.query.kind_graph``.

Four things can go wrong with a projection that a REST route and a generated
docs page both consume, and each gets its own class here:

1. **It disagrees with the write path.** The graph must read the relations
   through the SAME function the write pipeline validates with; a second
   reading is the defect this whole area exists to end. Pinned by asserting
   that ``enforced`` is exactly ``Relation.resolved`` — the property the write
   path itself branches on — rather than a condition re-typed here.
2. **It claims more than it knows.** ``declared`` and ``enforced`` are no
   longer the same set, and a screen that conflates them over-claims. The
   coverage block must be DERIVED from the collections it counts, never
   hand-kept: a count that drifts from its own list is a lie that ships green.
3. **It loses the gaps.** An unregistered target, an unpaired inverse and a
   reference-shaped undeclared field must survive as gaps rather than vanish —
   a graph whose gaps are dropped renders as complete.
4. **It puts a gap in the wrong bucket, or in the right one with no way to
   tell.** A composite pointer filed as an unresolved gap invites somebody to
   fix a non-problem; 23 gaps of one origin, distinguishable only by English
   prose, are 23 gaps a bilingual screen must present alike. ``origin`` is the
   answer, and this file holds it to being DERIVED rather than enumerated.

**What is deliberately NOT here any more.** There was a fifth class, for the
name-shape inference and the denylist that silenced it. Both are gone: a guess
that produced an EDGE was the problem, and a suppression table is the shape of
a mechanism that should not be producing the thing being suppressed. The name
shape survives only as an ``undeclared`` gap — an invitation, which needs no
denylist because nothing is being claimed.

The projection is pure: these tests build fake ports, never a Kernel. The
declarations are checked against the LIVE registry next door, in
``test_kind_graph_registry.py`` — purity here is what makes that separation
necessary, not a reason to skip it.
"""
from __future__ import annotations

from dna.kernel.kinds.relations import ANY_TARGET, relations_of
from dna.kernel.query.kind_graph import (
    COVERAGE_LIMITS,
    DECLARED_ORIGINS,
    POLYMORPHIC_TARGET,
    REF_SUFFIXES,
    TIERS,
    UNRESOLVED_ORIGINS,
    build_edges,
    build_kind_graph,
    coverage,
    kind_rows,
    target_index,
)


class _Port:
    """The smallest thing the projection accepts: a Kind descriptor stub."""

    def __init__(self, kind, *, alias="", plane="record", schema=None,
                 dep_filters=None, relations=None, identifiers=None):
        self.kind = kind
        self.alias = alias
        self.plane = plane
        self._schema = schema or {}
        self.dep_filters = dep_filters or {}
        self.relations = relations
        self.identifiers = identifiers

    def schema(self):
        return self._schema


class _Replay:
    """Replay a measured row as a port — the graph's own input, once."""

    def __init__(self, row):
        self.kind = row["kind"]
        self.alias = row["alias"]
        self.plane = row["plane"]
        self.dep_filters = row["dep_filters"]
        self.relations = row["relations"]
        self.identifiers = row["identifiers"]
        self._schema = {"properties": row["properties"]}

    def schema(self):
        return self._schema


def _rel(to, *, cardinality="one", inverse_of=None, by=None):
    out = {"to": to, "cardinality": cardinality}
    if inverse_of:
        out["inverse_of"] = inverse_of
    if by:
        out["by"] = by
    return out


def _props(*names, array=()):
    return {
        "properties": {
            n: {"type": "array" if n in array else "string"} for n in names
        }
    }


# --- 1. one reading of the declaration, shared with the write path -----------


class TestOneReadingOfTheDeclaration:
    def test_declared_edges_come_from_the_ports_relations(self):
        """Every declared edge corresponds to a ``Relation`` the write path
        would also see — asserted against ``relations_of`` itself, not against
        a list re-typed here."""
        port = _Port(
            "Story", schema=_props("feature", "spec_refs", array=("spec_refs",)),
            relations={
                "feature": _rel("Feature"),
                "spec_refs": _rel("Spec", cardinality="many"),
            },
        )
        rows = kind_rows([port, _Port("Feature"), _Port("Spec")])
        edges, _ = build_edges(rows)
        declared = {
            (e["source"], e["field"], e["target"])
            for e in edges if e["tier"] == "declared"
        }
        assert declared == {
            ("Story", name, target)
            for name, rel in relations_of(port).items() for target in rel.to
        }

    def test_enforced_IS_relation_resolved_not_a_second_condition(self):
        """The mutant this kills: somebody re-deriving "is it enforced?" from
        the tier name or from ``by == 'name'``. Two readings of one promise are
        two readings that can disagree, and the write path owns this one."""
        port = _Port(
            "Project",
            schema=_props("org_ref", "workspace_id", "produces",
                          array=("produces",)),
            relations={
                "org_ref": _rel("Organization"),
                "workspace_id": _rel("Workspace", by="workspace_id"),
                "produces": _rel(ANY_TARGET, cardinality="many",
                                 by="{kind, name}"),
            },
        )
        rows = kind_rows([port, _Port("Organization"), _Port("Workspace")])
        edges, _ = build_edges(rows)
        rels = relations_of(port)
        assert len(edges) == 3
        for e in edges:
            assert e["enforced"] is rels[e["field"]].resolved

    def test_cardinality_comes_from_the_relation_not_from_the_json_type(self):
        """Dor 4. The schema says ``string``; the model says ``many``. The
        graph must report the MODEL — the whole reason cardinality became a
        declared field is that reading it off ``type: array`` was a guess.

        (A real Kind declaring this would be refused by the contradiction lint;
        the point here is which SOURCE the graph reads, and only a disagreement
        can show that.)"""
        port = _Port(
            "Odd", schema=_props("things"),
            relations={"things": _rel("Thing", cardinality="many")},
        )
        edges, _ = build_edges(kind_rows([port, _Port("Thing")]))
        assert edges[0]["cardinality"] == "many"

    def test_a_relation_wins_over_a_dep_filter_on_the_same_field(self):
        """The strongest statement about a field wins, so no line is drawn
        twice — the rule that used to protect ``x-dna-ref`` from ``dep_filters``
        and now protects ``relations`` from it."""
        port = _Port(
            "Story", schema=_props("feature"),
            relations={"feature": _rel("Feature")},
            dep_filters={"feature": "sdlc-feature"},
        )
        edges, _ = build_edges(
            kind_rows([port, _Port("Feature", alias="sdlc-feature")]),
        )
        assert [e["tier"] for e in edges] == ["declared"]


# --- 2. it must not claim more than it knows ---------------------------------


class TestItDoesNotOverClaim:
    def test_declared_and_enforced_are_different_numbers(self):
        """The distinction the whole ``by:`` design rests on. If these ever
        collapse into one count, a screen starts telling somebody their
        key-addressed relation is validated."""
        rows = kind_rows([
            _Port("A", schema=_props("b", "c"),
                  relations={"b": _rel("B"), "c": _rel("B", by="opaque_id")}),
            _Port("B"),
        ])
        graph = build_kind_graph([_Replay(r) for r in rows])
        assert graph["coverage"]["declared"] == 2
        assert graph["coverage"]["enforced"] == 1

    def test_the_counters_are_derived_from_the_collections(self):
        rows = kind_rows([
            _Port("A", schema=_props("b", "junk_id"), relations={"b": _rel("B")}),
            _Port("B", dep_filters={"x": "a-alias"}),
        ])
        edges, unresolved = build_edges(rows)
        cov = coverage(rows, edges, unresolved)
        assert cov["edges"] == len(edges)
        assert cov["unresolved"] == len(unresolved)
        assert cov["kinds"] == len(rows)
        assert sum(cov[t] for t in TIERS) == len(edges)
        assert sum(cov["unresolved_by_origin"].values()) == len(unresolved)

    def test_kinds_with_relations_counts_kinds_not_relations(self):
        rows = kind_rows([
            _Port("A", schema=_props("b", "c"),
                  relations={"b": _rel("B"), "c": _rel("B")}),
            _Port("B"),
        ])
        edges, unresolved = build_edges(rows)
        assert coverage(rows, edges, unresolved)["kinds_with_relations"] == 1

    def test_the_coverage_limits_travel_with_the_graph(self):
        """A caveat a consumer must restate is a caveat one consumer forgets."""
        graph = build_kind_graph([_Port("A")])
        assert graph["coverage"]["limits"] == [dict(x) for x in COVERAGE_LIMITS]
        assert all(set(x) == {"code", "detail"} for x in COVERAGE_LIMITS)

    def test_declared_origins_is_a_list_the_consumer_derives_from(self):
        assert set(DECLARED_ORIGINS) < set(UNRESOLVED_ORIGINS)
        assert "undeclared" not in DECLARED_ORIGINS


# --- 3. the gaps must survive -------------------------------------------------


class TestTheGapsSurvive:
    def test_an_unregistered_target_is_a_gap_not_a_dangling_edge(self):
        """Printing it as an edge would let a screen draw a node for a Kind
        nobody registered."""
        rows = kind_rows([
            _Port("A", schema=_props("b"), relations={"b": _rel("Nowhere")}),
        ])
        edges, unresolved = build_edges(rows)
        assert edges == []
        assert unresolved[0]["origin"] == "declared"

    def test_an_unpaired_inverse_is_a_gap_with_a_code(self):
        """Dor 1 in the projection. Nothing could say this before: two Kinds
        each claiming to be half of one relation, disagreeing about it."""
        rows = kind_rows([
            _Port("Feature", schema=_props("stories", array=("stories",)),
                  relations={"stories": _rel("Story", cardinality="many",
                                             inverse_of="feature")}),
            _Port("Story"),
        ])
        _, unresolved = build_edges(rows)
        gap = [u for u in unresolved if u["origin"] == "inverse"]
        assert len(gap) == 1
        assert gap[0]["code"] == "inverse_missing"

    def test_a_sound_pair_produces_no_gap(self):
        """The counterpart that proves the test above measures something."""
        rows = kind_rows([
            _Port("Feature", schema=_props("stories", array=("stories",)),
                  relations={"stories": _rel("Story", cardinality="many",
                                             inverse_of="feature")}),
            _Port("Story", schema=_props("feature"),
                  relations={"feature": _rel("Feature", inverse_of="stories")}),
        ])
        _, unresolved = build_edges(rows)
        assert [u for u in unresolved if u["origin"] == "inverse"] == []

    def test_a_reference_shaped_undeclared_field_is_an_invitation(self):
        rows = kind_rows([_Port("A", schema=_props("thing_ref"))])
        _, unresolved = build_edges(rows)
        assert unresolved[0]["origin"] == "undeclared"
        assert "neither a relation nor an identifier" in unresolved[0]["reason"]

    def test_an_identifier_ANSWERS_the_invitation(self):
        """The half that makes the list finite. A field saying "I am not a
        reference" (``spec.identifiers``) leaves the gap list — and this is not
        the retired denylist returning: the gap row asserted no target, so
        there is no false claim being silenced, and the answer lives on the
        Kind rather than in a central table that can go stale against a Kind it
        no longer describes."""
        rows = kind_rows([_Port(
            "A", schema=_props("thing_ref"),
            identifiers={"thing_ref": {"role": "external", "system": "stripe"}},
        )])
        edges, unresolved = build_edges(rows)
        assert unresolved == []
        # And it does not become an EDGE either: it points nowhere, which is
        # the entire statement.
        assert edges == []

    def test_the_gap_row_does_NOT_guess_a_target(self):
        """The retired mechanism, refused explicitly. ``KindDefinition.docs ->
        Doc`` and ``StatusReport.insight -> IntelInsight`` were drawn from a
        field-name match; one was a field of prose and the other pointed at a
        Kind that had been deleted. A gap row states what it can see and
        nothing more."""
        rows = kind_rows([
            _Port("A", schema=_props("thing_ref")),
            _Port("Thing", alias="x-thing"),
        ])
        edges, unresolved = build_edges(rows)
        assert edges == []
        assert "target" not in unresolved[0]
        assert "Thing" not in unresolved[0]["reason"]

    def test_a_declared_field_is_never_ALSO_a_gap(self):
        """One field, one classification."""
        rows = kind_rows([
            _Port("A", schema=_props("thing_ref"),
                  relations={"thing_ref": _rel("Thing")}),
            _Port("Thing"),
        ])
        _, unresolved = build_edges(rows)
        assert unresolved == []

    def test_a_bad_dep_filter_alias_is_still_a_gap(self):
        rows = kind_rows([_Port("A", dep_filters={"x": "nobody-claims-this"})])
        _, unresolved = build_edges(rows)
        assert unresolved[0]["origin"] == "composition"

    def test_ref_suffixes_are_what_makes_a_field_shaped(self):
        """Derived, so the list and the behaviour cannot drift apart."""
        rows = kind_rows([
            _Port("A", schema=_props(*[f"thing{s}" for s in REF_SUFFIXES],
                                     "plain")),
        ])
        _, unresolved = build_edges(rows)
        assert {u["field"] for u in unresolved} == {
            f"thing{s}" for s in REF_SUFFIXES
        }


# --- 4. the buckets, and telling them apart ----------------------------------


class TestTheBucketsAreDistinguishable:
    def test_a_star_relation_is_drawn_with_the_shared_token(self):
        """It used to be filtered into a separate "undeclarable" bucket, which
        is how eight ``produces`` fields ended up described as inexpressible
        when they were merely undeclared. ``POLYMORPHIC_TARGET`` IS the token
        the declaration uses, so a consumer special-casing it reads the same
        string in both places."""
        assert POLYMORPHIC_TARGET == ANY_TARGET
        rows = kind_rows([
            _Port("Story", schema=_props("produces", array=("produces",)),
                  relations={"produces": _rel(ANY_TARGET, cardinality="many",
                                              by="{kind, name}")}),
        ])
        edges, unresolved = build_edges(rows)
        assert edges[0]["target"] == ANY_TARGET
        assert edges[0]["enforced"] is False
        assert edges[0]["polymorphic"] is True
        assert unresolved == []

    def test_every_wire_edge_carries_the_full_key_set(self):
        """A stable key set is what lets a second consumer type the answer
        without probing — including ``inverse_of``, which is ``null`` on the
        many relations that point one way."""
        graph = build_kind_graph([
            _Port("A", schema=_props("b"), relations={"b": _rel("B")}),
            _Port("B"),
        ])
        assert set(graph["edges"][0]) == {
            "from_kind", "field", "to_kind", "cardinality", "tier",
            "polymorphic", "by", "enforced", "inverse_of",
        }

    def test_every_wire_gap_carries_the_full_key_set(self):
        graph = build_kind_graph([_Port("A", schema=_props("thing_ref"))])
        assert set(graph["unresolved"][0]) == {
            "kind", "field", "origin", "reason", "code",
        }

    def test_a_polymorphic_relation_draws_one_edge_per_target(self):
        rows = kind_rows([
            _Port("M", schema=_props("scope_ref"),
                  relations={"scope_ref": _rel(["Org", "Proj"])}),
            _Port("Org"), _Port("Proj"),
        ])
        edges, _ = build_edges(rows)
        assert [e["target"] for e in edges] == ["Org", "Proj"]
        assert all(e["polymorphic"] for e in edges)


# --- determinism, without which the docs guard is worthless ------------------


class TestDeterminism:
    @staticmethod
    def _ports():
        return [
            _Port("Z", alias="z-z", schema=_props("a_ref", "junk_id"),
                  relations={"a_ref": _rel("A")}),
            _Port("A", alias="a-a", dep_filters={"z": "z-z"}),
            _Port("M", alias="m-m", schema=_props("things", array=("things",)),
                  relations={"things": _rel(ANY_TARGET, cardinality="many",
                                            by="Kind/name")}),
        ]

    def test_two_runs_produce_identical_bytes(self):
        import json

        first = json.dumps(build_kind_graph(self._ports()))
        second = json.dumps(build_kind_graph(self._ports()))
        assert first == second

    def test_input_order_does_not_change_the_answer(self):
        ports = self._ports()
        assert build_kind_graph(ports) == build_kind_graph(list(reversed(ports)))

    def test_target_index_maps_alias_to_kind(self):
        rows = kind_rows(self._ports())
        assert target_index(rows) == {"z-z": "Z", "a-a": "A", "m-m": "M"}
