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

The projection is pure: these tests build fake ports, never a Kernel.
"""
from __future__ import annotations

from dna.kernel.query.kind_graph import (
    COVERAGE_LIMITS,
    ENFORCED_TIERS,
    INFERENCE_DENYLIST,
    TIERS,
    UNDECLARABLE,
    build_edges,
    build_kind_graph,
    coverage,
    kind_rows,
    suppressed_for,
    undeclarable_for,
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
