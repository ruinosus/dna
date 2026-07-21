"""Declared cross-Kind references — ``x-dna-ref`` (i-040).

Covers the three things that can go wrong with a new PUBLIC descriptor
contract: the annotation is misread, the write-time check misfires, or a Kind
that never opted in stops behaving the way it did before. The last one is the
one that would be expensive to discover in the field, so it is tested first
and hardest.
"""
from __future__ import annotations

import pytest

from dna.kernel.references import (
    DeclaredReference,
    declared_references,
    reference_values,
    references_from_schema,
    resolve_target_kinds,
)


# --- reading the annotation --------------------------------------------------


class TestReferencesFromSchema:
    def test_single_target(self):
        refs = references_from_schema(
            {"properties": {"feature": {"type": "string", "x-dna-ref": "Feature"}}}
        )
        assert refs == [
            DeclaredReference(field="feature", targets=("Feature",), is_array=False)
        ]
        assert not refs[0].polymorphic

    def test_array_field_is_marked(self):
        refs = references_from_schema(
            {
                "properties": {
                    "spec_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "x-dna-ref": "Spec",
                    }
                }
            }
        )
        assert refs[0].is_array is True

    def test_polymorphic_targets_are_sorted_and_deduped(self):
        refs = references_from_schema(
            {
                "properties": {
                    "scope_ref": {
                        "type": "string",
                        "x-dna-ref": ["Project", "Organization", "Project"],
                    }
                }
            }
        )
        assert refs[0].targets == ("Organization", "Project")
        assert refs[0].polymorphic is True

    def test_fields_are_sorted_for_determinism(self):
        refs = references_from_schema(
            {
                "properties": {
                    "zeta": {"x-dna-ref": "A"},
                    "alpha": {"x-dna-ref": "B"},
                }
            }
        )
        assert [r.field for r in refs] == ["alpha", "zeta"]

    @pytest.mark.parametrize(
        "schema",
        [
            None,
            {},
            {"properties": None},
            "not a schema",
            {"properties": {"f": {"type": "string"}}},          # no annotation
            {"properties": {"f": {"x-dna-ref": ""}}},           # empty
            {"properties": {"f": {"x-dna-ref": []}}},           # empty list
            {"properties": {"f": {"x-dna-ref": 7}}},            # wrong type
        ],
    )
    def test_no_declaration_yields_nothing(self, schema):
        """Malformed or absent annotations yield [], never an exception.

        This is the back-compat guarantee in its smallest form: whatever a
        third party has in a `.kind.yaml` today, reading it for references
        cannot fail.
        """
        assert references_from_schema(schema) == []

    def test_broken_port_schema_stays_permissive(self):
        class Exploding:
            def schema(self):
                raise RuntimeError("boom")

        assert declared_references(Exploding()) == []
        assert declared_references(None) == []


# --- reading values off a document -------------------------------------------


class TestReferenceValues:
    ref = DeclaredReference(field="feature", targets=("Feature",), is_array=False)
    arr = DeclaredReference(field="specs", targets=("Spec",), is_array=True)

    @pytest.mark.parametrize(
        "spec",
        [{}, {"feature": None}, {"feature": ""}, {"feature": "   "}, {"other": "x"}],
    )
    def test_optional_reference_left_unset_is_not_a_violation(self, spec):
        """An absent/null/blank reference yields no values to check.

        Optional references must stay optional — this is the clause that keeps
        enforcement from breaking every partially-filled document.
        """
        assert reference_values(self.ref, spec) == []

    def test_scalar_and_array_values(self):
        assert reference_values(self.ref, {"feature": " f-x "}) == ["f-x"]
        assert reference_values(self.arr, {"specs": ["a", "", None, "b"]}) == ["a", "b"]

    def test_non_dict_spec(self):
        assert reference_values(self.ref, None) == []


class TestResolveTargetKinds:
    def test_splits_known_from_unknown(self):
        ref = DeclaredReference(field="f", targets=("Feature", "Nope"), is_array=False)
        known, unknown = resolve_target_kinds(
            ref, lambda t: "Feature" if t == "Feature" else None
        )
        assert known == ["Feature"]
        assert unknown == ["Nope"]


# --- what the real Kinds declare ---------------------------------------------


class TestRegisteredKinds:
    @pytest.fixture(scope="class")
    def ports(self):
        from dna.kernel import Kernel

        return {str(p.kind): p for p in Kernel.auto().kind_ports() if p.kind}

    def test_sdlc_core_arc_is_declared(self, ports):
        """The work-item spine declares its references."""
        expected = {
            ("Story", "feature"): ("Feature",),
            ("Story", "dependencies"): ("Story",),
            ("Story", "spec_refs"): ("Spec",),
            ("Feature", "epic"): ("Epic",),
            ("Feature", "stories"): ("Story",),
            ("Epic", "features"): ("Feature",),
            ("Task", "story_ref"): ("Story",),
            ("Plan", "spec_ref"): ("Spec",),
            ("Spec", "epic"): ("Epic",),
        }
        for (kind, field), targets in expected.items():
            refs = {r.field: r for r in declared_references(ports[kind])}
            assert field in refs, f"{kind}.{field} lost its x-dna-ref"
            assert refs[field].targets == targets

    def test_every_declared_target_is_a_registered_kind(self, ports):
        """A reference to a Kind nobody provides is an authoring bug.

        Without this, a typo in an `x-dna-ref` degrades silently into an
        edge that can never resolve — the exact class of quiet wrongness
        i-040 exists to end.
        """
        dangling = [
            f"{kind}.{ref.field} -> {target}"
            for kind, port in ports.items()
            for ref in declared_references(port)
            for target in ref.targets
            if target not in ports
        ]
        assert dangling == [], f"x-dna-ref naming unregistered Kinds: {dangling}"

    def test_declaration_agrees_with_dep_filters(self, ports):
        """Where both mechanisms describe the same field, they must not disagree.

        `dep_filters` (composition) and `x-dna-ref` (validation) are separate
        by design, but a field described by both pointing at DIFFERENT Kinds
        would be two sources of truth drifting — the failure mode this whole
        line of work exists to prevent.
        """
        alias_to_kind = {
            str(p.alias): k for k, p in ports.items() if getattr(p, "alias", None)
        }
        conflicts = []
        for kind, port in ports.items():
            deps = port.dep_filters() or {}
            for ref in declared_references(port):
                if ref.field not in deps:
                    continue
                declared = {
                    alias_to_kind.get(a)
                    for a in str(deps[ref.field]).split("|")
                }
                declared.discard(None)
                if declared and not declared & set(ref.targets):
                    conflicts.append(
                        f"{kind}.{ref.field}: dep_filters={sorted(declared)} "
                        f"x-dna-ref={list(ref.targets)}"
                    )
        assert conflicts == [], f"dep_filters/x-dna-ref disagree: {conflicts}"

    def test_kinds_without_declarations_are_the_majority_and_unaffected(self, ports):
        """Opt-in means most Kinds declare nothing — and that must stay legal."""
        undeclared = [k for k, p in ports.items() if not declared_references(p)]
        assert len(undeclared) > len(ports) / 2
