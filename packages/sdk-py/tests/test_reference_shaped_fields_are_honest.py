"""Reference-shaped fields say what they are — declared, keyed, or neither.

The schema graph reported 25 fields as "reference-shaped but unresolvable".
That list is a mix of four different things, and the whole point of this module
is that they stop being indistinguishable:

* a REAL reference nobody declared          → declare it (`x-dna-ref`)
* a real reference keyed by something other
  than the document name                    → say so, and do NOT declare it
* not a reference at all                    → say so
* dead                                      → delete it

Each class is pinned below by the property it applies to. The tests assert the
DECLARATION, not the prose, because prose is what the previous round of this
already had and it is what went stale.
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel
from dna.kernel.query.references import declared_references


@pytest.fixture(scope="module")
def kernel() -> Kernel:
    return Kernel.auto()


def _refs(kernel: Kernel, kind: str) -> dict[str, tuple[str, ...]]:
    return {
        r.field: r.targets
        for r in declared_references(kernel.kind_port_for(kind))
    }


def _prop(kernel: Kernel, kind: str, field: str) -> dict:
    return kernel.kind_port_for(kind).schema()["properties"][field]


# ---------------------------------------------------------------------------
# Class 1 — a real reference, resolvable by document NAME, now declared
# ---------------------------------------------------------------------------


class TestNewlyDeclared:
    @pytest.mark.parametrize(
        "kind,field,target,is_array",
        [
            ("IntelInsight", "source_ref", "IntelSource", False),
            ("Project", "intel_source_refs", "IntelSource", True),
        ],
    )
    def test_the_declaration_exists_and_names_a_registered_kind(
        self, kernel, kind, field, target, is_array,
    ):
        refs = {
            r.field: r for r in declared_references(kernel.kind_port_for(kind))
        }
        assert field in refs, f"{kind}.{field} lost its x-dna-ref"
        assert refs[field].targets == (target,)
        assert refs[field].is_array is is_array
        # A declaration naming a Kind nobody registers is a gap, not an edge.
        assert kernel.kind_port_for(target) is not None

    def test_an_unset_source_ref_is_still_legal(self, kernel):
        """IntelInsight.source_ref is nullable and stays nullable.

        Declaring a reference must not quietly make an optional field
        required — an insight with no source is a shape the ranker produces.
        """
        assert _prop(kernel, "IntelInsight", "source_ref")["type"] == [
            "string", "null",
        ]
        assert "source_ref" not in (
            kernel.kind_port_for("IntelInsight").schema().get("required") or []
        )


# ---------------------------------------------------------------------------
# Class 2 — a real reference keyed by something OTHER than the document name
# ---------------------------------------------------------------------------


class TestKeyedReferencesStayUndeclared:
    def test_plan_binding_tier_id_is_not_declared(self, kernel):
        """The runtime resolves it by `spec.tier_id` then `spec.aliases[]`.

        `x-dna-ref` resolves by DOCUMENT NAME. Declaring this would install a
        second resolution rule that can disagree with the live one — an
        alias-keyed binding is valid data the write path would then veto. The
        same shape as `Organization.plan_ref`, which the graph already lists as
        known-undeclarable.
        """
        assert "tier_id" not in _refs(kernel, "PlanBinding")

    def test_it_names_the_kind_that_actually_exists(self, kernel):
        """The description said "Tier"; no `Tier` Kind has existed since the
        metering rename (dna 0.29.0). A description naming a dead Kind is a
        reference that cannot be followed by a human either.
        """
        assert kernel.kind_port_for("Tier") is None
        assert kernel.kind_port_for("PricingPlan") is not None
        description = _prop(kernel, "PlanBinding", "tier_id")["description"]
        assert "PricingPlan" in description
        assert "aliases" in description  # WHY it cannot be declared

    def test_evidence_document_ref_is_composite_and_undeclared(self, kernel):
        """`Kind:name`, exactly like `Comment.target_ref` — needs parsing.

        Measured from the one runtime producer (the kernel evidence post_save
        handler writes ``f"{kind}:{name}"``), not inferred from the name.
        """
        assert "document_ref" not in _refs(kernel, "Evidence")
        description = _prop(kernel, "Evidence", "document_ref")["description"]
        assert "Kind:name" in description
        # The sibling it shares its shape with says the same thing.
        assert "Kind:name" in _prop(kernel, "Comment", "target_ref")["description"]


# ---------------------------------------------------------------------------
# Class 3 — not a reference at all
# ---------------------------------------------------------------------------


class TestNotReferencesAtAll:
    def test_layer_policy_layer_id_says_it_is_a_dimension(self, kernel):
        """A model-derived schema could not carry prose at all until now.

        `_schema_from_model` emitted TYPE and nothing else, so `layer_id` had
        no way to say it names an AXIS (tenant/branch/region/user) rather than
        a `Layer` document — and the graph guessed. The description is the fix;
        this test is what keeps it from being dropped in the next refactor of
        that function.
        """
        prop = _prop(kernel, "LayerPolicy", "layer_id")
        assert "NOT a reference" in prop["description"]
        assert "layer_value" in prop["description"]
        assert "layer_id" not in _refs(kernel, "LayerPolicy")

    def test_no_layer_kind_exists_to_reference(self, kernel):
        assert kernel.kind_port_for("Layer") is None

    def test_model_derived_schemas_are_unchanged_without_the_metadata(
        self, kernel,
    ):
        """The description slot is OPT-IN, and its inertness is the contract.

        Twelve Kinds build their schema from a dataclass. If adding the slot
        had changed any of them, this change would have been a silent schema
        migration rather than one field gaining prose.
        """
        agent_props = kernel.kind_port_for("Agent").schema()["properties"]
        assert not any("description" in p for p in agent_props.values()), (
            "a model-derived schema grew descriptions it did not declare"
        )

    def test_research_scope_is_a_scope_not_a_ref(self, kernel):
        """Renamed from `scope_ref`. A scope is a partition of the store."""
        props = kernel.kind_port_for("Research").schema()["properties"]
        assert "scope" in props
        assert "scope_ref" not in props
        assert kernel.kind_port_for("Scope") is None

    def test_a_document_written_before_the_rename_still_validates(self, kernel):
        """THE compatibility claim for the rename, and it is structural.

        Research is `additionalProperties: true`, so `scope_ref` survives as an
        unknown extra key on read AND on write. The rename cannot break a
        stored document; it can only stop projecting one field.
        """
        import jsonschema
        schema = kernel.kind_port_for("Research").schema()
        legacy = {
            "title": "t", "objective": "o",
            "methodology": "web-search-curated", "status": "draft",
            "scope_ref": "dna-development",
        }
        jsonschema.validate(legacy, schema)   # must not raise


# ---------------------------------------------------------------------------
# Class 4 — dead, and deleted
# ---------------------------------------------------------------------------


class TestDead:
    def test_workspace_plan_ref_is_gone(self, kernel):
        """Its own description said "DEPRECATED, never read"; a sweep of the
        SDK, the generated clients and the dna-cloud portal agreed. A field
        only a schema knows about is not compatibility.
        """
        props = kernel.kind_port_for("Workspace").schema()["properties"]
        assert "plan_ref" not in props
        # The live path it was never part of, still intact.
        assert "account_id" in props
