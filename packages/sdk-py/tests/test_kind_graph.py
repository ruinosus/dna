"""The SCHEMA graph projection — ``dna.kernel.query.kind_graph``.

Three things can go wrong with a projection that a REST route and a generated
docs page both consume, and each gets its own class here:

1. **It disagrees with the write path.** The graph must read ``x-dna-ref``
   through the SAME function the write pipeline validates with; a second
   reading is the defect ``references.py`` exists to end. Pinned by asserting
   the declared tier appears exactly where ``declared_references`` sees it —
   and, harder, by proving a schema shape the write path cannot see does not
   show up as an edge either.
2. **It claims more than it knows.** The three tiers must stay distinguishable
   and the coverage block must be DERIVED from the collections it counts, not
   hand-kept. A count that drifts from its own list is a lie that ships green.
3. **It loses the gaps.** An unregistered target, a keyed reference and a
   suppressed name match must survive as gaps rather than vanish — a graph
   whose gaps are dropped renders as complete.
4. **It puts a gap in the wrong bucket, or in the right one with no way to
   tell.** A composite pointer filed as an unresolved gap invites somebody to
   fix a non-problem; 23 gaps of one origin, distinguishable only by English
   prose, are 23 gaps a bilingual screen must present alike. ``origin`` and
   ``composite_undeclarable`` are the two answers, and this file holds them to
   being DERIVED rather than enumerated.

The projection is pure: these tests build fake ports, never a Kernel. The
tables it keeps by hand are checked against the LIVE registry next door, in
``test_kind_graph_registry.py`` — purity here is what makes that separation
necessary, not a reason to skip it.
"""
from __future__ import annotations

from dna.kernel.query.kind_graph import (
    COVERAGE_LIMITS,
    DECLARED_ORIGINS,
    ENFORCED_TIERS,
    INFERENCE_DENYLIST,
    POLYMORPHIC_TARGET,
    TIERS,
    UNDECLARABLE,
    UNRESOLVED_ORIGINS,
    build_edges,
    build_kind_graph,
    composite_undeclarable,
    coverage,
    kind_rows,
    suppressed_for,
    undeclarable_for,
    undeclarable_index,
)
from dna.kernel.query.references import declared_references


class _Port:
    """The smallest thing the projection accepts: a Kind descriptor stub."""

    def __init__(self, kind, *, alias="", plane="record", schema=None,
                 dep_filters=None):
        self.kind = kind
        self.alias = alias
        self.plane = plane
        self._schema = schema or {}
        self.dep_filters = dep_filters or {}

    def schema(self):
        return self._schema


def _ref(target, *, array=False):
    prop = {"type": "array" if array else "string", "x-dna-ref": target}
    return prop


# --- 1. one reading of the declaration, shared with the write path -----------


class TestOneReadingOfTheDeclaration:
    def test_declared_edges_come_from_declared_references(self):
        """Every declared edge corresponds to a ``DeclaredReference`` the write
        path would also see — asserted against ``declared_references`` itself,
        not against a list re-typed here."""
        port = _Port(
            "Story", alias="sdlc-story",
            schema={"properties": {
                "feature": _ref("Feature"),
                "spec_refs": _ref("Spec", array=True),
            }},
        )
        rows = kind_rows([port, _Port("Feature", alias="sdlc-feature"),
                          _Port("Spec", alias="sdlc-spec")])
        edges, _ = build_edges(rows)

        declared = {(e["field"], e["target"]) for e in edges
                    if e["tier"] == "declared"}
        expected = {
            (ref.field, target)
            for ref in declared_references(port) for target in ref.targets
        }
        assert declared == expected

    def test_array_declaration_is_many_scalar_is_one(self):
        rows = kind_rows([
            _Port("Story", schema={"properties": {
                "feature": _ref("Feature"), "spec_refs": _ref("Spec", array=True),
            }}),
            _Port("Feature"), _Port("Spec"),
        ])
        edges, _ = build_edges(rows)
        by_field = {e["field"]: e for e in edges if e["tier"] == "declared"}
        assert by_field["feature"]["cardinality"] == "one"
        assert by_field["spec_refs"]["cardinality"] == "many"

    def test_polymorphic_declaration_becomes_one_edge_per_target(self):
        rows = kind_rows([
            _Port("Membership", schema={"properties": {
                "scope_ref": {"type": "string",
                              "x-dna-ref": ["Organization", "Project"]},
            }}),
            _Port("Organization"), _Port("Project"),
        ])
        edges, _ = build_edges(rows)
        poly = [e for e in edges if e["field"] == "scope_ref"]
        assert {e["target"] for e in poly} == {"Organization", "Project"}
        assert all(e["polymorphic"] for e in poly)

    def test_a_nested_declaration_is_invisible_here_exactly_as_it_is_on_write(self):
        """``x-dna-ref`` under ``items`` (not a first-level property) is not
        read by the write path, and must not be read here either.

        This is the assertion that proves the two share a reading rather than
        merely agreeing on the easy cases: a graph that got cleverer than the
        validator would draw an edge nothing enforces, and the screen would
        have no way to tell which kind of line it was looking at. The limit is
        declared on the wire as ``top_level_properties_only``."""
        port = _Port("Deal", schema={"properties": {
            "items": {"type": "array", "items": _ref("Contact")},
        }})
        assert declared_references(port) == []
        rows = kind_rows([port, _Port("Contact")])
        edges, _ = build_edges(rows)
        assert [e for e in edges if e["tier"] == "declared"] == []

    def test_a_broken_schema_yields_a_node_not_an_exception(self):
        class Exploding(_Port):
            def schema(self):
                raise RuntimeError("boom")

        rows = kind_rows([Exploding("Cursed", alias="x-cursed")])
        assert [r["kind"] for r in rows] == ["Cursed"]
        assert rows[0]["properties"] == {}


# --- 2. the tiers stay distinguishable, the counts stay derived --------------


class TestTiers:
    def _three_tier_rows(self):
        return kind_rows([
            _Port("Story", alias="sdlc-story",
                  schema={"properties": {
                      "feature": _ref("Feature"),   # declared
                      "skills": {"type": "array"},  # composition (dep_filters)
                      "epic": {"type": "string"},   # inferred (name convention)
                  }},
                  dep_filters={"skills": "agentskills"}),
            _Port("Feature", alias="sdlc-feature"),
            _Port("Epic", alias="sdlc-epic"),
            _Port("Skill", alias="agentskills"),
        ])

    def test_each_tier_is_produced_by_its_own_declaration(self):
        edges, _ = build_edges(self._three_tier_rows())
        tier_of = {e["field"]: e["tier"] for e in edges}
        assert tier_of == {
            "feature": "declared",
            "skills": "composition",
            "epic": "inferred",
        }

    def test_the_strongest_statement_about_a_field_wins(self):
        """A field carrying BOTH ``x-dna-ref`` and a ``dep_filters`` entry is
        ONE edge, at the declared tier — never two lines for one fact."""
        rows = kind_rows([
            _Port("Story", schema={"properties": {"feature": _ref("Feature")}},
                  dep_filters={"feature": "sdlc-feature"}),
            _Port("Feature", alias="sdlc-feature"),
        ])
        edges, _ = build_edges(rows)
        assert [(e["field"], e["tier"]) for e in edges] == [("feature", "declared")]

    def test_enforced_tiers_is_a_subset_of_the_tiers(self):
        assert set(ENFORCED_TIERS) <= set(TIERS)
        assert ENFORCED_TIERS == ("declared",)

    def test_edges_are_sorted_deterministically(self):
        rows = self._three_tier_rows()
        first, _ = build_edges(rows)
        second, _ = build_edges(kind_rows(list(reversed([
            _Port(r["kind"], alias=r["alias"], plane=r["plane"],
                  schema={"properties": r["properties"]},
                  dep_filters=r["dep_filters"])
            for r in rows
        ]))))
        assert first == second


class TestCoverageIsDerived:
    def test_every_count_matches_the_collection_it_describes(self):
        """The block is derived, never enumerated — the lesson of
        ``guardas-enumeracao-vs-derivacao``. If a tier is added and the counter
        is not, this fails instead of silently under-reporting."""
        rows = kind_rows([
            _Port("Story", schema={"properties": {
                "feature": _ref("Feature"),
                "epic": {"type": "string"},
                "widget_ref": {"type": "string"},   # unresolved
            }}),
            _Port("Feature"), _Port("Epic"),
        ])
        edges, unresolved = build_edges(rows)
        undeclarable = undeclarable_for(rows)
        suppressed = suppressed_for(rows)
        cov = coverage(rows, edges, unresolved, undeclarable, suppressed)

        assert cov["kinds"] == len(rows)
        assert cov["edges"] == len(edges)
        assert cov["unresolved"] == len(unresolved)
        assert cov["undeclarable"] == len(undeclarable)
        assert cov["suppressed"] == len(suppressed)
        assert sum(cov[tier] for tier in TIERS) == cov["edges"]

    def test_the_limits_travel_with_the_answer(self):
        """The caveats are ON the wire, not in a doc page a caller may never
        read: it is what stops a screen from rendering the edge list as "the
        relations"."""
        graph = build_kind_graph([_Port("Story")])
        codes = {limit["code"] for limit in graph["coverage"]["limits"]}
        assert codes == {limit["code"] for limit in COVERAGE_LIMITS}
        assert "schema_not_data" in codes
        assert "top_level_properties_only" in codes

    def test_every_limit_states_a_code_and_a_reason(self):
        for limit in COVERAGE_LIMITS:
            assert limit["code"] and limit["code"].strip()
            assert limit["detail"] and limit["detail"].strip()

    def test_an_empty_registry_is_an_empty_graph_not_a_missing_one(self):
        graph = build_kind_graph([])
        assert graph["kinds"] == [] and graph["edges"] == []
        assert graph["coverage"]["kinds"] == 0
        # The caveats survive: "nothing registered" is still an answer about a
        # SCHEMA graph, and a consumer must still not read it as data.
        assert graph["coverage"]["limits"]


# --- 3. the gaps survive -----------------------------------------------------


class TestGapsSurvive:
    def test_a_declaration_naming_an_unregistered_kind_is_a_gap_not_an_edge(self):
        """A typo'd or not-yet-registered target must not become a node.

        Drawing it would put a box on the screen for a Kind nobody registered;
        dropping it silently would hide the authoring error. It is neither: it
        is an ``unresolved`` row that names the declaration."""
        rows = kind_rows([_Port("Story", schema={
            "properties": {"feature": _ref("Featrue")}})])
        edges, unresolved = build_edges(rows)
        assert edges == []
        assert unresolved == [{
            "source": "Story", "field": "feature",
            "origin": "declared",
            "reason": "`x-dna-ref` names `Featrue`, which no registered Kind "
                      "provides",
        }]

    def test_a_reference_shaped_field_with_no_target_is_reported(self):
        rows = kind_rows([_Port("Deal", schema={
            "properties": {"pipeline_ref": {"type": "string"}}})])
        _, unresolved = build_edges(rows)
        assert [u["field"] for u in unresolved] == ["pipeline_ref"]

    def test_a_keyed_reference_is_named_as_undeclarable_never_drawn(self):
        """``Membership.role`` points at a Role — by ``role_id``, not by name.
        It cannot be declared, so it is stated instead of drawn."""
        rows = kind_rows([
            _Port("Membership", schema={"properties": {"role": {"type": "string"}}}),
            _Port("Role"),
        ])
        edges, _ = build_edges(rows)
        assert [e for e in edges if e["field"] == "role"] == []
        assert {(u["source"], u["field"]) for u in undeclarable_for(rows)} == {
            ("Membership", "role")
        }

    def test_undeclarable_and_suppressed_are_scoped_to_registered_kinds(self):
        """A scope is not told about fields of Kinds it does not register —
        that would be describing somebody else's model."""
        rows = kind_rows([_Port("Story")])
        assert undeclarable_for(rows) == []
        assert suppressed_for(rows) == []
        assert UNDECLARABLE and INFERENCE_DENYLIST  # the tables are not empty

    def test_a_suppressed_name_match_produces_no_edge_but_is_counted(self):
        """``Tenant.plan`` matches the ``Plan`` Kind by name and the match is
        wrong (it is a billing tier). Suppressed — and COUNTED, so the answer
        never implies the projection saw everything."""
        rows = kind_rows([
            _Port("Tenant", schema={"properties": {"plan": {"type": "string"}}}),
            _Port("Plan"),
        ])
        edges, _ = build_edges(rows)
        assert edges == []
        assert [(s["source"], s["field"]) for s in suppressed_for(rows)] == [
            ("Tenant", "plan")
        ]
        graph = build_kind_graph([
            _Port("Tenant", schema={"properties": {"plan": {"type": "string"}}}),
            _Port("Plan"),
        ])
        assert graph["coverage"]["suppressed"] == 1

    def test_a_denylist_entry_that_did_not_fire_is_not_counted_as_suppressed(self):
        """An AMBIGUOUS token is stopped by ambiguity, not by the denylist.

        Exactly what the metering rename did: ``PricingPlan`` joined ``Plan``,
        ``plan`` stopped resolving to one Kind, and three entries went inert
        while ``coverage.suppressed`` went on counting them — 8 claimed, 5
        performed. The counter reports what the pass DID.
        """
        rows = kind_rows([
            _Port("Tenant", schema={"properties": {"plan": {"type": "string"}}}),
            _Port("Plan", alias="sdlc-plan"),
            _Port("PricingPlan", alias="cloud-pricing-plan"),
        ])
        edges, _ = build_edges(rows)
        assert [e for e in edges if e["field"] == "plan"] == []
        assert suppressed_for(rows) == []

    def test_a_denylist_entry_for_a_field_that_is_gone_is_not_counted(self):
        """The Kind is registered and the entry stands, but the field it names
        is not there: nothing was suppressed, so nothing is reported."""
        rows = kind_rows([_Port("Tenant", schema={"properties": {}}), _Port("Plan")])
        assert suppressed_for(rows) == []


# --- 4a. the gap says WHICH pass produced it --------------------------------


class TestUnresolvedOrigin:
    """``origin`` is the machine-readable half of ``reason``.

    The measurement that produced it: 25 unresolved rows, every one of them a
    field-name guess, and a portal that could only present them as
    "declarations that do not resolve" — false for all 25, and the reason a
    real broken declaration would have arrived invisible. The prose said so;
    the prose is English, and the portal is EN/PT.
    """

    def test_a_broken_x_dna_ref_is_declared(self):
        rows = kind_rows([_Port("Story", schema={
            "properties": {"feature": _ref("Featrue")}})])
        _, unresolved = build_edges(rows)
        assert [u["origin"] for u in unresolved] == ["declared"]

    def test_a_dep_filters_alias_nobody_claims_is_composition(self):
        rows = kind_rows([_Port(
            "Story", schema={"properties": {"skills": {"type": "array"}}},
            dep_filters={"skills": "no-such-alias"},
        )])
        _, unresolved = build_edges(rows)
        assert [u["origin"] for u in unresolved] == ["composition"]

    def test_a_field_name_guess_is_shape_inferred(self):
        rows = kind_rows([_Port("Deal", schema={
            "properties": {"pipeline_ref": {"type": "string"}}})])
        _, unresolved = build_edges(rows)
        assert [u["origin"] for u in unresolved] == ["shape-inferred"]

    def test_the_three_origins_are_distinguishable_in_ONE_answer(self):
        """The point of the field: a mixed list separates without reading
        prose. If two passes ever produced the same origin this fails."""
        rows = kind_rows([_Port(
            "Story",
            schema={"properties": {
                "feature": _ref("Featrue"),            # declared, unregistered
                "skills": {"type": "array"},           # composition, no alias
                "pipeline_ref": {"type": "string"},    # name guess
            }},
            dep_filters={"skills": "no-such-alias"},
        )])
        _, unresolved = build_edges(rows)
        assert {u["field"]: u["origin"] for u in unresolved} == {
            "feature": "declared",
            "skills": "composition",
            "pipeline_ref": "shape-inferred",
        }

    def test_every_origin_emitted_is_one_of_the_declared_vocabulary(self):
        """No row may carry an origin the enum does not name — a consumer that
        switches on it must be able to switch exhaustively."""
        rows = kind_rows([
            _Port("Story", schema={"properties": {
                "feature": _ref("Featrue"),
                "pipeline_ref": {"type": "string"},
            }}, dep_filters={"skills": "no-such-alias"}),
        ])
        _, unresolved = build_edges(rows)
        assert unresolved
        assert {u["origin"] for u in unresolved} <= set(UNRESOLVED_ORIGINS)

    def test_declared_origins_is_the_subset_that_means_somebody_claimed_it(self):
        """Same contract as ``ENFORCED_TIERS``: a list the consumer derives the
        ranking from, never re-typed in a screen. ``shape-inferred`` is NOT in
        it — that is the whole finding of i-104."""
        assert set(DECLARED_ORIGINS) < set(UNRESOLVED_ORIGINS)
        assert "shape-inferred" not in DECLARED_ORIGINS
        assert DECLARED_ORIGINS == ("declared", "composition")

    def test_the_origin_split_is_counted_and_sums_to_the_total(self):
        rows = kind_rows([_Port(
            "Story",
            schema={"properties": {
                "feature": _ref("Featrue"), "pipeline_ref": {"type": "string"},
            }},
            dep_filters={"skills": "no-such-alias"},
        )])
        edges, unresolved = build_edges(rows)
        cov = coverage(rows, edges, unresolved, [], [])
        assert cov["unresolved_by_origin"] == {
            "declared": 1, "composition": 1, "shape-inferred": 1,
        }
        assert sum(cov["unresolved_by_origin"].values()) == cov["unresolved"]

    def test_an_origin_with_no_rows_is_reported_as_zero_not_omitted(self):
        """A missing key and a zero read differently to a client that iterates
        the map; the shape of the answer must not depend on the data."""
        rows = kind_rows([_Port("Deal", schema={
            "properties": {"pipeline_ref": {"type": "string"}}})])
        edges, unresolved = build_edges(rows)
        cov = coverage(rows, edges, unresolved, [], [])
        assert set(cov["unresolved_by_origin"]) == set(UNRESOLVED_ORIGINS)
        assert cov["unresolved_by_origin"]["declared"] == 0

    def test_the_envelope_carries_the_origin_on_every_row(self):
        graph = build_kind_graph([_Port("Deal", schema={
            "properties": {"pipeline_ref": {"type": "string"}}})])
        assert graph["unresolved"] == [{
            "kind": "Deal", "field": "pipeline_ref", "origin": "shape-inferred",
            "reason": "reference-shaped, but `pipeline` matches no registered "
                      "Kind",
        }]

    def test_the_limit_naming_the_split_travels_with_the_answer(self):
        graph = build_kind_graph([_Port("Story")])
        codes = {limit["code"] for limit in graph["coverage"]["limits"]}
        assert "unresolved_is_not_all_broken" in codes


# --- 4b. the composite family classifies itself ------------------------------


class TestCompositeIsDerivedNotEnumerated:
    """A pointer that carries its own Kind is undeclarable, and says so.

    Three fields of one family existed; ONE was in the hand table and got
    classified right, two were not and were filed as unresolved gaps. The rule
    was correct and its membership was somebody's memory. These tests hold the
    membership to being read off the schema.
    """

    def test_an_object_requiring_kind_and_name_is_composite_without_annotation(self):
        rows = kind_rows([_Port("SourceArtifact", schema={"properties": {
            "derived_refs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["kind", "name"],
                    "properties": {"kind": {"type": "string"},
                                   "name": {"type": "string"}},
                },
            },
        }})])
        assert set(composite_undeclarable(rows)) == {
            ("SourceArtifact", "derived_refs"),
        }

    def test_a_declared_form_covers_the_string_shape_a_schema_cannot_reveal(self):
        """``"Story:s-thing"`` is a string like any other. Nothing structural
        distinguishes it from a plain name, so the field says so itself."""
        rows = kind_rows([_Port("Comment", schema={"properties": {
            "target_ref": {"type": "string", "x-dna-ref-composite": "Kind:name"},
        }})])
        (target, why), = composite_undeclarable(rows).values()
        assert target == POLYMORPHIC_TARGET
        assert "Kind:name" in why

    def test_the_reason_is_derived_from_the_declared_form_not_a_stored_string(self):
        """Two different forms must produce two different reasons — otherwise
        the reason is a constant wearing a derivation's clothes."""
        rows = kind_rows([
            _Port("Comment", schema={"properties": {
                "target_ref": {"type": "string",
                               "x-dna-ref-composite": "Kind:name"}}}),
            _Port("Engram", schema={"properties": {
                "source_refs": {"type": "array", "items": {"type": "string"},
                                "x-dna-ref-composite": "Kind/name"}}}),
        ])
        reasons = {k: why for (k, _), (_, why) in
                   composite_undeclarable(rows).items()}
        assert "`Kind:name`" in reasons["Comment"]
        assert "`Kind/name`" in reasons["Engram"]
        assert reasons["Comment"] != reasons["Engram"]

    def test_a_composite_is_neither_an_edge_nor_an_unresolved_gap(self):
        """The bug, exactly: ``Engram.source_refs`` was reference-shaped, no
        Kind is called ``source``, so it was reported as a gap. One field, one
        classification."""
        rows = kind_rows([_Port("Engram", schema={"properties": {
            "source_refs": {"type": "array", "items": {"type": "string"},
                            "x-dna-ref-composite": "Kind/name"},
        }})])
        edges, unresolved = build_edges(rows)
        assert edges == []
        assert unresolved == []
        assert [(u["source"], u["field"]) for u in undeclarable_for(rows)] == [
            ("Engram", "source_refs"),
        ]

    def test_an_enforced_declaration_wins_over_the_composite_reading(self):
        """A field carrying ``x-dna-ref`` is enforced at write; calling it
        undeclarable would contradict the write path."""
        rows = kind_rows([
            _Port("Story", schema={"properties": {
                "feature": {"type": "string", "x-dna-ref": "Feature",
                            "x-dna-ref-composite": "Kind:name"},
            }}),
            _Port("Feature"),
        ])
        assert composite_undeclarable(rows) == {}
        edges, _ = build_edges(rows)
        assert [(e["field"], e["tier"]) for e in edges] == [("feature", "declared")]

    def test_an_object_missing_kind_or_name_is_not_a_pointer(self):
        """Half an address is not an address. A ``name``-only object is a plain
        reference; a ``kind``-only one is a type tag."""
        def _obj(*members):
            return {"type": "array", "items": {
                "type": "object", "required": list(members),
                "properties": {m: {"type": "string"} for m in members},
            }}

        rows = kind_rows([_Port("Thing", schema={"properties": {
            "a_refs": _obj("name"), "b_refs": _obj("kind"),
            "c_refs": _obj("kind", "name"),
        }})])
        assert set(composite_undeclarable(rows)) == {("Thing", "c_refs")}

    def test_an_optional_kind_and_name_is_not_a_pointer_either(self):
        """Present in ``properties`` but absent from ``required``: the author
        did not commit to every value carrying an address."""
        rows = kind_rows([_Port("Thing", schema={"properties": {
            "loose_refs": {"type": "array", "items": {
                "type": "object", "required": [],
                "properties": {"kind": {"type": "string"},
                               "name": {"type": "string"}},
            }},
        }})])
        assert composite_undeclarable(rows) == {}

    def test_a_composite_that_is_not_reference_shaped_is_still_found(self):
        """``Story.produces`` does not end in ``_ref``/``_refs`` and so was
        invisible to every pass — not an edge, not even a gap. The shape is the
        oracle, not the name."""
        rows = kind_rows([_Port("Story", schema={"properties": {
            "produces": {"type": "array", "items": {
                "type": "object", "required": ["kind", "name"],
                "properties": {"kind": {"type": "string"},
                               "name": {"type": "string"}},
            }},
        }})])
        assert set(composite_undeclarable(rows)) == {("Story", "produces")}

    def test_a_malformed_annotation_is_ignored_rather_than_trusted(self):
        """``x-dna-ref-composite: true`` names no form. Fail-soft, like every
        other reading in ``references``: a shrug, never a made-up form."""
        rows = kind_rows([_Port("Comment", schema={"properties": {
            "target_ref": {"type": "string", "x-dna-ref-composite": True},
        }})])
        assert composite_undeclarable(rows) == {}

    def test_both_families_land_in_one_index_read_by_both_consumers(self):
        """``build_edges`` decides what not to draw from the SAME mapping
        ``undeclarable_for`` reports. Two membership tests could disagree."""
        rows = kind_rows([
            _Port("Membership", schema={"properties": {"role": {"type": "string"}}}),
            _Port("Role"),
            _Port("Comment", schema={"properties": {
                "target_ref": {"type": "string",
                               "x-dna-ref-composite": "Kind:name"}}}),
        ])
        index = undeclarable_index(rows)
        assert set(index) == {("Membership", "role"), ("Comment", "target_ref")}
        assert {(u["source"], u["field"]) for u in undeclarable_for(rows)} == set(index)
        _, unresolved = build_edges(rows)
        assert [(u["source"], u["field"]) for u in unresolved] == []

    def test_the_composite_target_is_never_mistakable_for_a_kind_name(self):
        rows = kind_rows([_Port("Comment", schema={"properties": {
            "target_ref": {"type": "string", "x-dna-ref-composite": "Kind:name"},
        }})])
        assert [u["target"] for u in undeclarable_for(rows)] == [POLYMORPHIC_TARGET]
        assert POLYMORPHIC_TARGET.islower()

    def test_the_hand_table_no_longer_carries_the_composite_family(self):
        """The annotation REPLACED the row; it did not join it. A field in both
        would be classified twice and maintained twice."""
        assert ("Comment", "target_ref") not in UNDECLARABLE
        assert all(target != POLYMORPHIC_TARGET
                   for target, _ in UNDECLARABLE.values())


# --- the wire envelope -------------------------------------------------------


class TestWireEnvelope:
    def test_edge_names_the_two_ends_and_the_field(self):
        graph = build_kind_graph([
            _Port("Story", alias="sdlc-story",
                  schema={"properties": {"feature": _ref("Feature")}}),
            _Port("Feature", alias="sdlc-feature", plane="record"),
        ])
        assert graph["edges"] == [{
            "from_kind": "Story", "field": "feature", "to_kind": "Feature",
            "cardinality": "one", "tier": "declared", "polymorphic": False,
        }]

    def test_node_carries_identity_only_never_the_schema(self):
        """A graph that inlined every JSON Schema would be a download. The
        descriptor stays behind ``GET /v1/kinds/registry/{kind}``."""
        graph = build_kind_graph([
            _Port("Story", alias="sdlc-story",
                  schema={"properties": {"feature": _ref("Feature")}}),
        ])
        assert graph["kinds"] == [
            {"kind": "Story", "alias": "sdlc-story", "group": "sdlc",
             "plane": "record"},
        ]

    def test_a_kind_without_an_alias_is_ungrouped_not_dropped(self):
        graph = build_kind_graph([_Port("Loose")])
        assert graph["kinds"][0]["group"] == "ungrouped"

    def test_the_envelope_does_not_stamp_a_scope(self):
        """The projection knows Kinds, not deployments; whoever resolved the
        registry stamps the scope."""
        assert "scope" not in build_kind_graph([_Port("Story")])
