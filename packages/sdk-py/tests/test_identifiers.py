"""``spec.identifiers`` — a field's way of saying it is NOT a reference.

The unit half. ``test_kind_graph_registry.py`` checks the same vocabulary
against the LIVE registry, which is where a rename or a deleted Kind shows up;
this file pins the READING, which is what every consumer shares.

The thing worth guarding is not that the block parses. It is that the block
cannot quietly become the retired inference denylist: it must refuse a
declaration that contradicts a relation, it must refuse an ``external`` with no
named system, and a field it describes must exist in the schema.
"""
from __future__ import annotations

import pytest

from dna.kernel.kinds.identifiers import (
    ROLES,
    Identifier,
    identifiers_of,
    normalize_identifiers,
    schema_contradictions,
)
from dna.kernel.kinds.relations import normalize_relations


def _schema(*fields: str) -> dict:
    return {"type": "object", "properties": {f: {"type": "string"} for f in fields}}


class TestTheVocabularyIsClosed:
    def test_a_self_identifier_needs_nothing_else(self):
        ident = normalize_identifiers({"sprint_id": {"role": "self"}})["sprint_id"]
        assert ident == Identifier(name="sprint_id", role="self", system=None)
        assert ident.is_external is False

    def test_an_external_identifier_names_its_system(self):
        ident = normalize_identifiers({
            "stripe_customer_id": {"role": "external", "system": "stripe"},
        })["stripe_customer_id"]
        assert (ident.role, ident.system, ident.is_external) == (
            "external", "stripe", True,
        )

    def test_an_unknown_role_is_refused(self):
        with pytest.raises(ValueError, match="role must be one of"):
            normalize_identifiers({"x_id": {"role": "foreign"}})

    def test_role_is_required(self):
        with pytest.raises(ValueError, match="role must be one of"):
            normalize_identifiers({"x_id": {"system": "stripe"}})

    def test_an_external_without_a_system_is_refused(self):
        """"It comes from somewhere else" is already legible in the field name.
        WHICH somewhere is the only part worth declaring, so declaring nothing
        is refused rather than defaulted."""
        with pytest.raises(ValueError, match="needs a `system`"):
            normalize_identifiers({"client_id": {"role": "external"}})

    def test_a_self_WITH_a_system_is_refused_not_ignored(self):
        """Dropping it silently would leave the author's wrong belief in the
        file, unread. An instance's own key is minted by this runtime."""
        with pytest.raises(ValueError, match="minted by this runtime"):
            normalize_identifiers({
                "sprint_id": {"role": "self", "system": "jira"},
            })

    def test_an_unknown_key_is_refused(self):
        with pytest.raises(ValueError, match="deliberately closed"):
            normalize_identifiers({
                "x_id": {"role": "self", "pattern": "^x-"},
            })

    def test_a_non_mapping_block_is_refused_with_no_shorthand_offered(self):
        with pytest.raises(ValueError, match="no shorthand"):
            normalize_identifiers({"x_id": "self"})

    def test_the_role_vocabulary_is_exactly_two(self):
        """A third role would be describing a validation rule, and the JSON
        Schema next door owns those. If this grows, the growth was a
        decision — not a drift."""
        assert ROLES == ("self", "external")


class TestNormalize:
    def test_none_in_none_out(self):
        assert normalize_identifiers(None) is None

    def test_an_empty_mapping_is_the_same_statement_as_none(self):
        assert normalize_identifiers({}) is None

    def test_identifiers_come_back_sorted(self):
        out = normalize_identifiers({
            "z_id": {"role": "self"}, "a_id": {"role": "self"},
        })
        assert list(out) == ["a_id", "z_id"]

    def test_a_normalized_mapping_round_trips(self):
        once = normalize_identifiers({"a_id": {"role": "self"}})
        assert normalize_identifiers(once) == once

    def test_to_declaration_round_trips_through_normalize(self):
        """A stored declaration must re-read as the same identifier, or editing
        a Kind through the authoring door slowly rewrites it."""
        for raw in ({"role": "self"},
                    {"role": "external", "system": "entra"}):
            first = normalize_identifiers({"x_id": raw})["x_id"]
            again = normalize_identifiers({"x_id": first.to_declaration()})["x_id"]
            assert again == first, raw

    def test_the_wire_shape_keeps_every_key(self):
        """A stable key set is what lets a consumer type it without probing —
        `system` is None on a `self`, never absent."""
        wire = normalize_identifiers({"a_id": {"role": "self"}})["a_id"].to_wire()
        assert wire == {"field": "a_id", "role": "self", "system": None}


class TestIdentifiersOf:
    def test_a_port_without_identifiers_yields_an_empty_mapping(self):
        assert identifiers_of(object()) == {}

    def test_none_yields_an_empty_mapping(self):
        assert identifiers_of(None) == {}

    def test_a_malformed_declaration_fails_SOFT_here(self):
        """Loading is where a bad declaration is refused. By the time a reader
        holds a registered port, refusing again turns an authoring error into
        an outage."""
        class Broken:
            identifiers = {"x_id": {"role": "external"}}  # no system

        assert identifiers_of(Broken()) == {}


class TestItCannotBecomeASecondMechanism:
    """The whole risk of this block: it answers "what is this field?", and so
    does ``relations``. Two mechanisms answering one question is precisely what
    ``spec.relations`` was written to retire, and these are the assertions that
    keep the second one from creeping back."""

    def test_a_field_declared_BOTH_a_relation_and_an_identifier_is_refused(self):
        rels = normalize_relations({"feature": {"to": "Feature", "cardinality": "one"}})
        idents = normalize_identifiers({"feature": {"role": "self"}})
        problems = schema_contradictions(idents, rels, _schema("feature"))
        assert problems
        assert "BOTH a relation and an identifier" in problems[0]

    def test_an_identifier_for_a_field_the_schema_lacks_is_refused(self):
        problems = schema_contradictions(
            normalize_identifiers({"ghost_id": {"role": "self"}}), None,
            _schema("other"),
        )
        assert problems and "no `ghost_id` property" in problems[0]

    def test_partial_suppresses_only_the_missing_property(self):
        """A descriptor pulling in ``schema_fragments`` is looking at an
        INCOMPLETE schema, so an identifier for a fragment-supplied property is
        not a contradiction — it is a property from_raw cannot see. The
        relation clash is still reported: that one needs no schema at all."""
        rels = normalize_relations({"x": {"to": "Feature", "cardinality": "one"}})
        idents = normalize_identifiers({"x": {"role": "self"},
                                        "ghost_id": {"role": "self"}})
        problems = schema_contradictions(idents, rels, _schema("x"), partial=True)
        assert len(problems) == 1
        assert "BOTH" in problems[0]

    def test_no_identifiers_means_nothing_to_contradict(self):
        assert schema_contradictions(None, None, _schema("a")) == []
