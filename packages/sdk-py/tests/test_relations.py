"""``spec.relations`` — the declaration itself.

The pure core: how a relation is READ, what it refuses, and the two questions
it can answer without touching a document (does the declaration pair? does it
contradict the schema?). What the WRITE path does with it lives in
``test_write_path_reference_validation.py``, against a source that really
stores documents; what the REGISTRY declares lives in
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

    def test_a_composite_form_on_a_concrete_target_is_a_contradiction(self):
        with pytest.raises(ValueError, match="contradict"):
            normalize_relations({"r": _rel(to="Story", by="Kind:name")})

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

    def test_a_key_addressed_relation_is_declared_but_NOT_resolved(self):
        """The whole `by:` design in one assertion: declaring the addressing
        must not install a resolution rule. If this ever flips to True, the
        write path starts reading a key nothing indexes and vetoing data the
        live lookup accepts."""
        rel = normalize_relations({
            "workspace_id": _rel(to="Workspace", by="workspace_id"),
        })["workspace_id"]
        assert rel.by == "workspace_id"
        assert rel.resolved is False

    def test_a_star_relation_is_declared_but_NOT_resolved(self):
        rel = normalize_relations({
            "r": _rel(to=ANY_TARGET, cardinality="many", by="{kind, name}"),
        })["r"]
        assert rel.carries_kind is True
        assert rel.polymorphic is True
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
        """Cardinality is a MODEL statement; a document contradicting it is
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
