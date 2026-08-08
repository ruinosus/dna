"""``spec.relations`` — the declaration itself.

The pure core: how a relation is READ, what it refuses, and the two questions
it can answer without touching an instance (does the declaration pair? does it
contradict the schema?). What the WRITE path does with it lives in
``test_write_path_reference_validation.py``, against a source that really
stores instances; what the REGISTRY declares lives in
``test_kind_graph_registry.py``.

The tests are ordered by what would cost most to discover in the field: a
malformed declaration accepted silently first, then a refusal that fires on
valid data, then the readings.
"""
from __future__ import annotations

import pytest

from dna.kernel.kinds.relations import (
    ANY_TARGET,
    BY_NAME,
    COMPOSITE_FORMS,
    Relation,
    inverse_gaps,
    normalize_relations,
    reciprocates,
    relation_values,
    relations_of,
    schema_contradictions,
)


def _rel(**kw):
    """One relation block, with the two required keys defaulted."""
    return {"to": "Story", "cardinality": "one", **kw}


# --- what the vocabulary REFUSES ---------------------------------------------


class TestTheVocabularyIsClosed:
    def test_an_unknown_key_is_refused_not_ignored(self):
        with pytest.raises(ValueError, match="unknown key"):
            normalize_relations({"feature": _rel(required=True)})

    def test_the_error_says_where_a_validation_key_belongs(self):
        """A refusal that does not say where the key SHOULD go teaches nothing."""
        with pytest.raises(ValueError, match="JSON Schema"):
            normalize_relations({"feature": _rel(minItems=2)})

    def test_cardinality_is_required_never_defaulted(self):
        """The whole point of the field is that it stops being inferred."""
        with pytest.raises(ValueError, match="cardinality"):
            normalize_relations({"feature": {"to": "Story"}})

    def test_an_unknown_cardinality_is_refused(self):
        with pytest.raises(ValueError, match="cardinality"):
            normalize_relations({"feature": _rel(cardinality="zero_or_one")})

    def test_a_relation_needs_a_target(self):
        with pytest.raises(ValueError, match="points somewhere"):
            normalize_relations({"feature": {"cardinality": "one"}})

    def test_an_empty_target_list_is_refused(self):
        with pytest.raises(ValueError, match="empty list"):
            normalize_relations({"feature": _rel(to=[])})

    def test_star_may_not_be_mixed_into_a_target_list(self):
        """`*` is the ABSENCE of a declared target, not one more alternative."""
        with pytest.raises(ValueError, match="not a longer list"):
            normalize_relations({"r": _rel(to=["Story", ANY_TARGET], by="Kind:name")})

    def test_a_relation_name_that_is_not_a_field_name_is_refused(self):
        with pytest.raises(ValueError, match="spec field name"):
            normalize_relations({"not a field": _rel()})

    def test_a_non_mapping_block_is_refused_with_no_shorthand_offered(self):
        with pytest.raises(ValueError, match="no shorthand"):
            normalize_relations({"feature": "Story"})


class TestByIsCheckedAgainstTo:
    def test_star_requires_a_form_so_a_reader_can_parse_the_pointer(self):
        with pytest.raises(ValueError, match="composite forms"):
            normalize_relations({"r": _rel(to=ANY_TARGET, cardinality="many")})

    def test_an_unknown_composite_form_is_refused(self):
        """The form set is CLOSED — a form nobody can parse is unusable."""
        with pytest.raises(ValueError, match="composite forms"):
            normalize_relations({"r": _rel(to=ANY_TARGET, by="Kind|name")})

    @pytest.mark.parametrize("form", COMPOSITE_FORMS)
    def test_every_declared_form_is_accepted(self, form):
        rels = normalize_relations({"r": _rel(to=ANY_TARGET, by=form)})
        assert rels["r"].by == form
        assert rels["r"].carries_kind is True

    def test_a_composite_form_MAY_declare_which_kinds_it_names(self):
        """`by` says where the target Kind name is WRITTEN; `to` says which
        Kinds it may name. Reading those as one question is what left 21
        relations in this registry pointing at `*` — declared, and untyped."""
        rel = normalize_relations({
            "work_item": _rel(to=["Issue", "Spike", "Story"], by="Kind/name"),
        })["work_item"]
        assert rel.to == ("Issue", "Spike", "Story")
        assert rel.by == "Kind/name"
        assert rel.carries_kind is True      # the ADDRESS carries a Kind
        assert rel.open_target is False      # the MODEL constrains which

    def test_a_single_target_composite_is_accepted_too(self):
        """Refusing this would force an author to write `*` — to LIE about the
        model — for the sake of a symmetry nothing needs."""
        rel = normalize_relations({"r": _rel(to="Story", by="Kind:name")})["r"]
        assert rel.to == ("Story",)
        assert rel.carries_kind is True
        assert rel.polymorphic is False

    def test_carries_kind_and_open_target_are_two_different_facts(self):
        """The mutant this kills: `carries_kind = not self.to`. Under it a typed
        composite reports carries_kind False — the graph would then believe the
        value holds a bare name, and a consumer parsing it would read
        `Story/s-x` as an instance called `Story/s-x`."""
        typed = normalize_relations({"r": _rel(to=["A", "B"], by="Kind/name")})["r"]
        by_name = normalize_relations({"r": _rel(to=["A", "B"])})["r"]
        star = normalize_relations({
            "r": _rel(to=ANY_TARGET, by="Kind/name"),
        })["r"]
        assert (typed.carries_kind, typed.open_target) == (True, False)
        assert (by_name.carries_kind, by_name.open_target) == (False, False)
        assert (star.carries_kind, star.open_target) == (True, True)

    def test_a_key_addressing_defaults_to_nothing_and_must_be_a_field_name(self):
        with pytest.raises(ValueError, match="spec field"):
            normalize_relations({"r": _rel(by="spec.workspace_id")})

    def test_by_defaults_to_name_on_a_concrete_target(self):
        assert normalize_relations({"r": _rel()})["r"].by == BY_NAME


class TestInverseOfIsRefusedWhereItCannotBeKept:
    def test_an_inverse_on_a_star_relation_is_refused(self):
        """There is no Kind on which the other half could be declared."""
        with pytest.raises(ValueError, match="nobody to keep it"):
            normalize_relations({
                "r": _rel(to=ANY_TARGET, by="Kind:name", inverse_of="x"),
            })

    def test_an_inverse_that_is_not_a_relation_name_is_refused(self):
        with pytest.raises(ValueError, match="inverse_of"):
            normalize_relations({"r": _rel(inverse_of="not a name")})


# --- what `resolved` means, which is what the kernel promises ----------------


class TestResolvedIsTheRuntimePromise:
    def test_a_name_addressed_concrete_relation_is_resolved(self):
        assert normalize_relations({"r": _rel()})["r"].resolved is True

    def test_a_polymorphic_relation_is_still_resolved(self):
        rel = normalize_relations({"r": _rel(to=["Spec", "Plan"])})["r"]
        assert rel.resolved is True
        assert rel.polymorphic is True

    def test_a_key_addressed_relation_is_FOLLOWED_and_never_ENFORCED(self):
        """Fatia 5 in one assertion, and it is deliberately TWO facts.

        The previous version of this test asserted ``resolved is False`` and
        warned that flipping it would make the write path *"read a key nothing
        indexes and veto data the live lookup accepts"*. Both halves of that
        warning were ANSWERED rather than overruled: the index turned out to
        already exist (``dna_insts_spec_gin_idx``, baseline revision 0001), and
        the veto is refused — which is what ``enforced is False`` pins here.

        If ``enforced`` ever flips to True, a ``PlanBinding.tier_id: pro`` —
        a value ``kernel.tier()`` resolves through ``spec.aliases[]`` — starts
        refusing writes the runtime itself honors.
        """
        rel = normalize_relations({
            "workspace_id": _rel(to="Workspace", by="workspace_id"),
        })["workspace_id"]
        assert rel.by == "workspace_id"
        assert rel.by_key is True
        assert rel.by_name is False
        assert rel.resolved is True, "the kernel FOLLOWS a by-key relation"
        assert rel.enforced is False, (
            "a by-key miss must never veto a write — the alias-tolerant live "
            "lookups accept addresses this resolver cannot see"
        )

    def test_by_name_and_enforced_are_two_questions_that_happen_to_agree(self):
        """⚠️ The pair that a rename and a veto each ask, separately.

        They return the same answer for every declaration that exists today,
        which is exactly what makes collapsing them tempting and what makes
        collapsing them dangerous: ``dna rename`` asks "is this value a NAME?"
        and the validator asks "does a miss REFUSE?". Fatia 5 already split
        ``resolved`` off from both. The day a by-key relation earns a veto,
        precisely one of these two flips — and if the code had one property
        doing both jobs, the rename would start rewriting keys."""
        by_name = normalize_relations({"r": _rel()})["r"]
        by_key = normalize_relations({
            "k": _rel(to="Workspace", by="workspace_id"),
        })["k"]
        composite = normalize_relations({
            "c": _rel(to=ANY_TARGET, cardinality="many", by="Kind:name"),
        })["c"]
        assert (by_name.by_name, by_name.enforced, by_name.resolved) == (
            True, True, True)
        assert (by_key.by_name, by_key.enforced, by_key.resolved) == (
            False, False, True)
        assert (composite.by_name, composite.enforced, composite.resolved) == (
            False, False, False)

    def test_a_star_relation_is_declared_but_NOT_resolved(self):
        rel = normalize_relations({
            "r": _rel(to=ANY_TARGET, cardinality="many", by="{kind, name}"),
        })["r"]
        assert rel.carries_kind is True
        assert rel.polymorphic is True
        assert rel.resolved is False

    def test_TYPING_a_composite_does_not_start_resolving_it(self):
        """Declaring the targets buys the GRAPH a typed edge, and nothing else.
        If this flips to True the write path starts parsing `Story/s-x` and
        vetoing every instance written before the form was agreed — the same
        second-resolution-rule trap `by: <key>` was held back from."""
        rel = normalize_relations({
            "verifies": _rel(to=["Feature", "Story"], cardinality="many",
                             by="Kind/name"),
        })["verifies"]
        assert rel.resolved is False


# --- the readings -------------------------------------------------------------


class TestNormalize:
    def test_none_in_none_out(self):
        assert normalize_relations(None) is None

    def test_an_empty_mapping_is_the_same_statement_as_none(self):
        assert normalize_relations({}) is None

    def test_targets_are_sorted_and_deduped(self):
        rel = normalize_relations({
            "r": _rel(to=["Project", "Organization", "Project"]),
        })["r"]
        assert rel.to == ("Organization", "Project")

    def test_relations_come_back_sorted_by_name(self):
        rels = normalize_relations({"z": _rel(), "a": _rel()})
        assert list(rels) == ["a", "z"]

    def test_a_normalized_mapping_round_trips(self):
        once = normalize_relations({"r": _rel(inverse_of="back")})
        assert normalize_relations(once) == once

    def test_to_declaration_omits_what_was_never_declared(self):
        rel = normalize_relations({"r": _rel()})["r"]
        assert rel.to_declaration() == {"to": "Story", "cardinality": "one"}

    def test_to_declaration_keeps_a_polymorphic_list_a_list(self):
        rel = normalize_relations({"r": _rel(to=["Plan", "Spec"])})["r"]
        assert rel.to_declaration()["to"] == ["Plan", "Spec"]

    def test_to_declaration_round_trips_through_normalize(self):
        """A stored declaration must re-read as the same relation — otherwise
        editing a Kind through the authoring door slowly rewrites it."""
        for raw in (
            _rel(inverse_of="back"),
            _rel(to=["Plan", "Spec"], cardinality="many"),
            _rel(to=ANY_TARGET, cardinality="many", by="{kind, name}"),
            _rel(to="Workspace", by="workspace_id"),
            _rel(to=["Issue", "Story"], cardinality="many", by="Kind/name"),
        ):
            first = normalize_relations({"r": raw})["r"]
            again = normalize_relations({"r": first.to_declaration()})["r"]
            assert again == first, raw


class TestRelationsOf:
    def test_a_port_without_relations_yields_an_empty_mapping(self):
        assert relations_of(object()) == {}

    def test_none_yields_an_empty_mapping(self):
        assert relations_of(None) == {}

    def test_a_malformed_declaration_fails_SOFT_here(self):
        """Loading is where a bad declaration is refused. By the time a WRITE
        is reading a registered port, refusing again would turn an authoring
        error into an outage."""
        class Broken:
            relations = {"r": {"to": "Story"}}  # no cardinality

        assert relations_of(Broken()) == {}

    def test_a_raw_authoring_mapping_is_normalized(self):
        class Handwritten:
            relations = {"feature": {"to": "Feature", "cardinality": "one"}}

        rels = relations_of(Handwritten())
        assert rels["feature"] == Relation(
            name="feature", to=("Feature",), cardinality="one",
        )


class TestRelationValues:
    @pytest.mark.parametrize("value", [None, "", "   ", []])
    def test_an_unset_relation_yields_nothing(self, value):
        """An OPTIONAL relation that is not set is not a dangling one."""
        rel = normalize_relations({"r": _rel()})["r"]
        assert relation_values(rel, {"r": value}) == []

    def test_an_absent_field_yields_nothing(self):
        rel = normalize_relations({"r": _rel()})["r"]
        assert relation_values(rel, {}) == []

    def test_values_are_stripped_and_non_strings_dropped(self):
        rel = normalize_relations({"r": _rel(cardinality="many")})["r"]
        assert relation_values(rel, {"r": [" a ", 3, None, "b"]}) == ["a", "b"]

    def test_a_scalar_is_read_from_a_many_relation_and_vice_versa(self):
        """Cardinality is a MODEL statement; an instance contradicting it is
        the schema's business, and giving one mistake two error messages from
        two layers is worse than tolerating it here."""
        many = normalize_relations({"r": _rel(cardinality="many")})["r"]
        one = normalize_relations({"r": _rel()})["r"]
        assert relation_values(many, {"r": "solo"}) == ["solo"]
        assert relation_values(one, {"r": ["a", "b"]}) == ["a", "b"]


# --- reciprocity, the free question ------------------------------------------


class TestReciprocates:
    @staticmethod
    def _paired():
        return normalize_relations({"stories": _rel(
            to="Story", cardinality="many", inverse_of="feature",
        )})["stories"]

    def test_the_target_naming_us_back_is_true(self):
        assert reciprocates(
            self._paired(), {"feature": "f-1"}, source_name="f-1",
        ) is True

    def test_a_list_valued_inverse_counts_membership(self):
        rel = normalize_relations({"feature": _rel(
            to="Feature", inverse_of="stories",
        )})["feature"]
        assert reciprocates(
            rel, {"stories": ["s-a", "s-b"]}, source_name="s-b",
        ) is True

    def test_the_target_naming_somebody_else_is_false(self):
        assert reciprocates(
            self._paired(), {"feature": "f-other"}, source_name="f-1",
        ) is False

    def test_the_target_saying_nothing_is_false(self):
        assert reciprocates(self._paired(), {}, source_name="f-1") is False

    def test_no_inverse_declared_is_NONE_and_not_FALSE(self):
        """The tri-state IS the design. Collapsing None into False would make
        every relation without an inverse look like a broken pair."""
        rel = normalize_relations({"r": _rel()})["r"]
        assert reciprocates(rel, {"anything": "x"}, source_name="a") is None

    def test_no_target_document_is_NONE(self):
        assert reciprocates(self._paired(), None, source_name="f-1") is None


# --- the declaration pairing, which IS enforced -------------------------------


class TestInverseGaps:
    @staticmethod
    def _registry(feature_side, story_side):
        return {
            "Feature": normalize_relations({"stories": feature_side}) or {},
            "Story": normalize_relations({"feature": story_side}) or {},
        }

    def test_a_sound_pair_reports_nothing(self):
        gaps = inverse_gaps(self._registry(
            _rel(to="Story", cardinality="many", inverse_of="feature"),
            _rel(to="Feature", cardinality="one", inverse_of="stories"),
        ))
        assert gaps == []

    def test_a_missing_other_half_is_reported(self):
        gaps = inverse_gaps({
            "Feature": normalize_relations({"stories": _rel(
                to="Story", cardinality="many", inverse_of="feature",
            )}),
            "Story": {},
        })
        assert [g["code"] for g in gaps] == ["inverse_missing"]

    def test_an_other_half_pointing_elsewhere_is_reported(self):
        gaps = inverse_gaps(self._registry(
            _rel(to="Story", cardinality="many", inverse_of="feature"),
            _rel(to="Epic", cardinality="one", inverse_of="stories"),
        ))
        assert [g["code"] for g in gaps] == ["inverse_target"]

    def test_an_other_half_naming_a_different_inverse_is_reported(self):
        """The measured shape of dor 1: two Kinds each claiming to be half of
        a relation, while talking about different relations.

        BOTH sides are reported, and that is not double-counting: Feature says
        `Story.feature` answers `stories`, and `Story.feature` says it answers
        something else entirely. Those are two false claims by two authors, and
        collapsing them into one row would leave one author unnamed."""
        gaps = inverse_gaps({
            "Feature": normalize_relations({
                "stories": _rel(to="Story", cardinality="many",
                                inverse_of="feature"),
                "owner_story": _rel(to="Story", cardinality="one"),
            }),
            "Story": normalize_relations({
                "feature": _rel(to="Feature", cardinality="one",
                                inverse_of="owner_story"),
            }),
        })
        assert [g["code"] for g in gaps] == [
            "inverse_not_mutual", "inverse_not_mutual",
        ]
        assert {g["kind"] for g in gaps} == {"Feature", "Story"}

    def test_a_one_sided_declaration_without_inverse_of_is_NOT_a_gap(self):
        """Most relations point one way. Declaring nothing is not a broken
        pair — only CLAIMING a pair and missing it is."""
        gaps = inverse_gaps({
            "Feature": normalize_relations({"stories": _rel(
                to="Story", cardinality="many",
            )}),
            "Story": {},
        })
        assert gaps == []

    def test_an_unregistered_target_is_skipped_not_double_reported(self):
        """The schema graph already reports an unresolvable target once. Two
        vocabularies naming one problem makes it look like two."""
        gaps = inverse_gaps({
            "Feature": normalize_relations({"stories": _rel(
                to="Nowhere", cardinality="many", inverse_of="feature",
            )}),
        })
        assert gaps == []

    def test_the_report_is_deterministic(self):
        registry = self._registry(
            _rel(to="Story", cardinality="many", inverse_of="feature"),
            _rel(to="Epic", cardinality="one", inverse_of="nope"),
        )
        assert inverse_gaps(registry) == inverse_gaps(registry)


# --- the schema contradiction --------------------------------------------------


class TestSchemaContradictions:
    def test_a_relation_naming_no_property_is_a_contradiction(self):
        rels = normalize_relations({"feature": _rel(to="Feature")})
        problems = schema_contradictions(rels, {"properties": {"other": {}}})
        assert len(problems) == 1
        assert "no `feature` property" in problems[0]

    def test_many_against_a_scalar_property_is_a_contradiction(self):
        rels = normalize_relations({"stories": _rel(cardinality="many")})
        problems = schema_contradictions(
            rels, {"properties": {"stories": {"type": "string"}}},
        )
        assert "not an array" in problems[0]

    def test_one_against_an_array_property_is_a_contradiction(self):
        rels = normalize_relations({"feature": _rel()})
        problems = schema_contradictions(
            rels, {"properties": {"feature": {"type": "array"}}},
        )
        assert "as an array" in problems[0]

    def test_agreement_reports_nothing(self):
        rels = normalize_relations({
            "stories": _rel(cardinality="many"), "feature": _rel(),
        })
        assert schema_contradictions(rels, {"properties": {
            "stories": {"type": "array"}, "feature": {"type": "string"},
        }}) == []

    def test_a_schema_with_no_properties_cannot_contradict_anything(self):
        rels = normalize_relations({"feature": _rel()})
        assert schema_contradictions(rels, {"type": "object"}) == []

    def test_partial_suppresses_the_missing_property_only(self):
        """A descriptor pulling in schema_fragments looks at an INCOMPLETE
        schema; refusing there would be refusing for lack of information."""
        rels = normalize_relations({
            "produces": _rel(to=ANY_TARGET, cardinality="many", by="{kind, name}"),
            "feature": _rel(to="Feature"),
        })
        schema = {"properties": {"feature": {"type": "array"}}}
        partial = schema_contradictions(rels, schema, partial=True)
        assert len(partial) == 1
        assert "as an array" in partial[0]
        assert len(schema_contradictions(rels, schema)) == 2


# --- i-100: the check that never looked at `items` -----------------------------


class TestTheElementTypeIsChecked:
    """The trap of i-100, both halves, and they belong in one class because
    either half alone is worthless.

    A function that returns ``[]`` for everything would satisfy "the honest ten
    still pass"; a function that accuses every array-of-object would satisfy
    "the dishonest one is caught" and break ten live declarations. Only the
    pair is a specification.
    """

    _ARRAY_OF_OBJECT = {
        "properties": {
            "mcp_servers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"ref": {"type": "string"}},
                },
            },
        },
    }

    def test_a_resolved_relation_over_array_of_object_is_a_contradiction(self):
        """The reproduction from i-100, verbatim: `Agent.spec.mcp_servers`.

        Every property on the declaration says the kernel follows and vetoes;
        `relation_values` reads zero. The lint used to be the one place that
        could say so, and it said nothing."""
        rels = normalize_relations({
            "mcp_servers": {"to": "MCPFederation", "cardinality": "many"},
        })
        rel = rels["mcp_servers"]
        # the announcement, unchanged — the declaration really does claim this
        assert rel.resolved is True
        assert rel.enforced is True
        # …and it really does read nothing
        assert relation_values(
            rel, {"mcp_servers": [{"ref": "github"}, {"ref": "slack"}]},
        ) == []
        # which is now SAID, instead of passing green
        problems = schema_contradictions(rels, self._ARRAY_OF_OBJECT)
        assert len(problems) == 1
        assert "items of `mcp_servers`" in problems[0]
        assert "not a string" in problems[0]

    def test_the_honest_ten_shape_still_passes(self):
        """`to: "*"` + a composite `by` — the shape of all ten array-of-object
        relations this registry declares (`SourceArtifact.derived_refs`,
        `AgentSession.produced_artifacts`, eight `*.produces`).

        They are `resolved=False`: the kernel says plainly that it does not
        follow them, so there is no promise to break. Accusing them would be
        the i-100 defect wearing the opposite coat."""
        rels = normalize_relations({
            "produces": _rel(to=ANY_TARGET, cardinality="many", by="{kind, name}"),
        })
        assert rels["produces"].resolved is False
        schema = {
            "properties": {
                "produces": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"kind": {"type": "string"}},
                        "required": ["kind", "name"],
                    },
                },
            },
        }
        assert schema_contradictions(rels, schema) == []

    def test_an_array_of_string_is_what_the_kernel_can_actually_read(self):
        rels = normalize_relations({"stories": _rel(cardinality="many")})
        assert schema_contradictions(rels, {"properties": {
            "stories": {"type": "array", "items": {"type": "string"}},
        }}) == []

    def test_an_array_of_integer_is_caught_too(self):
        """Not an object, same defect: `relation_values` filters on `str`."""
        rels = normalize_relations({"stories": _rel(cardinality="many")})
        problems = schema_contradictions(rels, {"properties": {
            "stories": {"type": "array", "items": {"type": "integer"}},
        }})
        assert len(problems) == 1
        assert "'integer'" in problems[0]

    def test_a_scalar_object_property_is_the_same_contradiction(self):
        """The mirror of the array case, and it was open for the same reason —
        the old check only asked "is it an array?". `cardinality: one` over
        `type: object` read zero just as quietly. No relation in this registry
        is declared this way today; the check costs three characters."""
        rels = normalize_relations({"feature": _rel(to="Feature")})
        problems = schema_contradictions(
            rels, {"properties": {"feature": {"type": "object"}}},
        )
        assert len(problems) == 1
        assert "`feature`" in problems[0] and "'object'" in problems[0]

    def test_a_nullable_string_is_a_string(self):
        """`type: ["string", "null"]` — the form every nullable reference in
        this registry uses (`Project.org_ref`, `Organization.plan_ref`,
        `IntelInsight.source_ref`, `Project.workspace_id`). Reading `type`
        as a bare string would have accused four live declarations."""
        rels = normalize_relations({"feature": _rel(to="Feature")})
        assert schema_contradictions(rels, {"properties": {
            "feature": {"type": ["string", "null"]},
        }}) == []

    def test_an_undeclared_element_type_is_no_information_not_a_contradiction(self):
        """An `items` that is absent, or that states its shape through `$ref`
        / `oneOf`, cannot be read here. "I could not tell" is not "it is
        wrong" — the same distinction `partial` exists to keep."""
        rels = normalize_relations({"stories": _rel(cardinality="many")})
        for items in (None, {}, {"$ref": "#/$defs/Ref"},
                      {"oneOf": [{"type": "string"}, {"type": "object"}]}):
            prop = {"type": "array"}
            if items is not None:
                prop["items"] = items
            assert schema_contradictions(
                rels, {"properties": {"stories": prop}},
            ) == [], items

    def test_a_multiplicity_contradiction_is_not_reported_twice(self):
        """One authoring error, one message. `cardinality: one` over an array
        of objects is wrong once, and saying it in two vocabularies would make
        one mistake look like two — the reading `inverse_gaps` already
        applies to unregistered targets."""
        rels = normalize_relations({"feature": _rel(to="Feature")})
        problems = schema_contradictions(rels, {"properties": {
            "feature": {"type": "array", "items": {"type": "object"}},
        }})
        assert len(problems) == 1
        assert "as an array" in problems[0]
