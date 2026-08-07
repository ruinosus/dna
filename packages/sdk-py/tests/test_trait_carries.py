"""A trait CARRIES — fields, relations and implied traits, through the real door.

Every test here registers a Kind on a real ``Kernel`` and then asks the
REGISTERED PORT what it has. That is deliberate and it is the lesson the house
already paid for twice (*"guard existe, porta não chama"*, *"capacidade existe,
porta não"*): a composition proven only against a hand-built object proves that
the function works, not that the mechanism is reachable. The mechanism has two
doors — ``kernel.kind(SomeClassKind())`` for a hand-written Kind and
``kernel.kind_from_descriptor(raw)`` for a YAML one — and both are exercised,
because the whole promise is that a tenant-authored Kind is not second-class.

What is under test, in the spec's own words
(``spec-kind-taxonomia-o-que-eu-sou`` §6.3):

1. traits are purely ADDITIVE;
2. conflict is REFUSED at load, not resolved by precedence;
3. the Kind wins over the trait.

Plus the borrowed FHIR rule that keeps rule 3 from becoming a hole: **a trait
restricts and adds, it never loosens.**
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel
from dna.kernel.kinds.base import KindBase
from dna.kernel.kinds.traits import (
    TRAIT_REQUIRED_ENFORCED,
    TraitConflictError,
    apply_traits,
    compose_traits,
    declared_traits_of,
    describe_traits,
    known_traits,
    provenance_of,
    register_trait,
    relation_provenance,
    schema_provenance,
    trait_closure,
    trait_definition,
    trait_registry,
)
from dna.kernel.meta import register_schema_fragment
from dna.kernel.protocols import StorageDescriptor

# ── the probes ───────────────────────────────────────────────────────────────


def _descriptor(name: str, **spec_extra):
    """A minimal KindDefinition envelope — the YAML door's payload."""
    return {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": name.lower()},
        "spec": {
            "target_api_version": f"example.com/{name.lower()}/v1",
            "target_kind": name,
            "alias": f"example-{name.lower()}",
            "origin": "example.com/probe",
            "plane": "record",
            "storage": {"type": "yaml", "container": f"{name.lower()}s"},
            **spec_extra,
        },
    }


class _ClassKind(KindBase):
    """A hand-written Kind — the OTHER door.

    Declares ``traits`` and overrides ``schema()`` exactly the way the ~37
    still-class builtin Kinds do, which is what makes it a fair probe: if the
    composition only worked for ``DeclarativeKindPort`` it would work for 47 of
    84 Kinds and quietly not for the rest."""

    api_version = "example.com/handwritten/v1"
    kind = "HandWritten"
    alias = "example-handwritten"
    origin = "example.com/probe"
    plane = "record"
    storage = StorageDescriptor.yaml(container="handwrittens")

    def __init__(self, traits=(), properties=None, relations=None, required=None):
        self.traits = frozenset(traits)
        self._props = properties or {}
        self.relations = relations
        self._required = required

    def schema(self):
        if not self._props:
            return None
        out = {"type": "object", "properties": dict(self._props)}
        if self._required:
            out["required"] = list(self._required)
        return out


@pytest.fixture()
def probe_traits():
    """Register the probe vocabulary, and put back whatever was there.

    The trait registry is process-global (exactly like ``_SCHEMA_FRAGMENTS``),
    so a test that leaves a trait behind poisons every later one."""
    from dna.kernel.kinds import traits as T

    before = dict(T._TRAITS)
    register_schema_fragment(
        "probe/timestamps",
        {
            "type": "object",
            "properties": {
                "opened_at": {"type": "string", "format": "date-time"},
            },
        },
    )
    register_trait(
        "probe.timestamped",
        "carries opened_at through a registered fragment",
        schema_fragments=["probe/timestamps"],
    )
    register_trait(
        "probe.assignable",
        "carries an owner field and an owner relation",
        schema={
            "properties": {"owner": {"type": "string", "minLength": 1}},
        },
        relations={"owner": {"to": "HandWritten", "cardinality": "one"}},
    )
    register_trait(
        "probe.tracked",
        "implies probe.timestamped",
        implies=["probe.timestamped"],
    )
    yield
    T._TRAITS.clear()
    T._TRAITS.update(before)


# ── 1. the trait carries FIELDS, through both doors ──────────────────────────


def test_a_declared_trait_puts_its_field_on_the_registered_descriptor_port(
    probe_traits,
):
    """The whole slice in one assertion: declare a trait, get the field.

    Before this, ``traits:`` and ``schema_fragments:`` were two lines saying the
    same thing with nothing linking them — a Kind could take the trait and not
    the fields."""
    k = Kernel()
    port = k.kind_from_descriptor(
        _descriptor("TraitFieldProbe", traits=["probe.timestamped"])
    )

    registered = k.kind_port_for("TraitFieldProbe")
    assert registered is port
    assert "opened_at" in registered.schema()["properties"]
    # ⭐ and the provenance SURVIVES — this is the `hasattr(port,
    # "schema_fragments") -> False` the spec measured.
    assert registered.schema_fragments == ("probe/timestamps",)
    assert schema_provenance(registered)["opened_at"] == "fragment:probe/timestamps"


def test_a_declared_trait_puts_its_field_on_a_hand_written_class_kind(probe_traits):
    """The same, through the OTHER door. A class Kind is not second-class and
    neither is a YAML one — the composition happens at ``register_kind``, which
    both funnels go through."""
    k = Kernel()
    kind = _ClassKind(traits=["probe.assignable"], properties={"title": {"type": "string"}})
    k.kind(kind)

    port = k.kind_port_for("HandWritten")
    props = port.schema()["properties"]
    assert props["owner"] == {"type": "string", "minLength": 1}
    assert props["title"] == {"type": "string"}  # the Kind's own survives
    assert schema_provenance(port) == {
        "owner": "trait:probe.assignable",
        "title": "kind",
    }


def test_a_trait_relation_reaches_the_port(probe_traits):
    """``produces`` was declared seven times because the family had nowhere to
    say it once. A trait relation lands in ``relations_of`` like any other."""
    from dna.kernel.kinds.relations import relations_of

    k = Kernel()
    k.kind(
        _ClassKind(
            traits=["probe.assignable"],
            properties={"owner": {"type": "string"}},
        )
    )
    rel = relations_of(k.kind_port_for("HandWritten"))["owner"]
    assert rel.to == ("HandWritten",)
    assert rel.cardinality == "one"


# ── 2. implies ───────────────────────────────────────────────────────────────


def test_implies_is_transitive_and_reaches_the_kernel_lookup(probe_traits):
    """A Kind that declares ``probe.tracked`` is found by a lookup for
    ``probe.timestamped`` — which is what an implication is FOR."""
    k = Kernel()
    k.kind_from_descriptor(_descriptor("ImpliedProbe", traits=["probe.tracked"]))

    assert k.kinds_with_trait("probe.timestamped") == frozenset({"ImpliedProbe"})
    port = k.kind_port_for("ImpliedProbe")
    # the author's own words stay reachable, separately
    assert declared_traits_of(port) == frozenset({"probe.tracked"})
    # ...and the implied trait's FIELD came along, which is the point
    assert "opened_at" in port.schema()["properties"]


def test_the_core_vocabulary_implication_is_the_measured_one():
    """``sdlc.rollup`` ⇒ ``sdlc.work-item`` ⇒ ``sdlc.dated``, two levels, and
    both links were measured rather than designed (every rollup declares
    work-item; every work item declares dated)."""
    assert trait_closure(["sdlc.rollup"]) == frozenset(
        {"sdlc.rollup", "sdlc.work-item", "sdlc.dated"}
    )


def test_an_implication_cycle_is_refused_at_load(probe_traits):
    register_trait("probe.a", "a", implies=["probe.b"])
    register_trait("probe.b", "b", implies=["probe.a"])
    with pytest.raises(TraitConflictError, match="cycle"):
        trait_closure(["probe.a"])


def test_a_trait_cannot_imply_itself(probe_traits):
    with pytest.raises(TraitConflictError, match="implies itself"):
        register_trait("probe.narcissus", "x", implies=["probe.narcissus"])


# ── 3. conflict is REFUSED at load, not resolved ─────────────────────────────


def test_two_traits_disagreeing_about_a_field_are_refused_at_load(probe_traits):
    """Rule 2, and it is the whole reason this is Rust's road and not LinkML's.

    ⚠️ MUTANT: make this a precedence rule instead — last trait wins, or
    sorted-first wins — and every assertion in this file still passes except
    this one. That is exactly LinkML #2528, open since 2025-02-04 with its
    reporter asking *"why? How am I supposed to know what to expect."*"""
    register_trait(
        "probe.x", "x", schema={"properties": {"shared": {"type": "string"}}}
    )
    register_trait(
        "probe.y", "y", schema={"properties": {"shared": {"type": "integer"}}}
    )
    k = Kernel()
    with pytest.raises(ValueError, match="disagree about property"):
        k.kind_from_descriptor(
            _descriptor("ConflictProbe", traits=["probe.x", "probe.y"])
        )
    # ...and nothing was half-registered.
    assert k.kind_port_for("ConflictProbe") is None


def test_the_refusal_does_not_depend_on_declaration_order(probe_traits):
    """The refusal is a property of the SET, not of the order. If the order
    could change the outcome we would have re-invented precedence by accident."""
    register_trait(
        "probe.x", "x", schema={"properties": {"shared": {"type": "string"}}}
    )
    register_trait(
        "probe.y", "y", schema={"properties": {"shared": {"type": "integer"}}}
    )
    for order in (["probe.x", "probe.y"], ["probe.y", "probe.x"]):
        with pytest.raises(TraitConflictError):
            compose_traits(order)


def test_two_traits_agreeing_about_a_field_are_NOT_a_conflict(probe_traits):
    """Agreement is free. The seven work items declaring ``produces`` say
    exactly the same thing, and a mechanism that called that a clash would be
    unusable on the data it was built for."""
    same = {"properties": {"shared": {"type": "string"}}}
    register_trait("probe.x", "x", schema=same)
    register_trait("probe.y", "y", schema=dict(same))
    composed = compose_traits(["probe.x", "probe.y"])
    assert composed.properties["shared"] == {"type": "string"}


def test_two_traits_disagreeing_about_a_relation_are_refused(probe_traits):
    register_trait(
        "probe.x", "x",
        relations={"peer": {"to": "HandWritten", "cardinality": "one"}},
    )
    register_trait(
        "probe.y", "y",
        relations={"peer": {"to": "HandWritten", "cardinality": "many"}},
    )
    with pytest.raises(TraitConflictError, match="disagree about relation"):
        compose_traits(["probe.x", "probe.y"])


def test_a_trait_pointing_at_an_unregistered_fragment_is_refused(probe_traits):
    """A trait that promises fields and delivers none is decoration again — the
    exact defect this slice exists to end, so it fails LOUD.

    Deliberately unlike a KIND's own ``schema_fragments``, where an unknown ID
    is skipped (an existing contract with a test on it): a Kind naming a missing
    fragment asked for nothing, but a trait naming one broke a promise."""
    register_trait("probe.hollow", "promises fields", schema_fragments=["probe/nope"])
    k = Kernel()
    with pytest.raises(ValueError, match="no extension has registered"):
        k.kind_from_descriptor(
            _descriptor("HollowProbe", traits=["probe.hollow"])
        )


# ── 4. the Kind wins ─────────────────────────────────────────────────────────


def test_the_kind_wins_over_the_trait_and_the_win_is_recorded(probe_traits):
    """Rule 3 — and the override is VISIBLE rather than silent, which is what
    keeps rule 3 from hiding a trait whose restriction got dropped."""
    k = Kernel()
    k.kind_from_descriptor(
        _descriptor(
            "KindWinsProbe",
            traits=["probe.assignable"],
            schema={
                "type": "object",
                "properties": {"owner": {"type": "string", "maxLength": 5}},
            },
        )
    )
    port = k.kind_port_for("KindWinsProbe")
    assert port.schema()["properties"]["owner"] == {"type": "string", "maxLength": 5}
    assert schema_provenance(port)["owner"] == "kind"


def test_the_kinds_own_fragment_beats_the_traits(probe_traits):
    """Precedence, low to high: trait → the Kind's own fragments → the Kind's
    own properties. The more LOCAL declaration wins, applied twice."""
    register_schema_fragment(
        "probe/override",
        {"type": "object", "properties": {"owner": {"type": "integer"}}},
    )
    k = Kernel()
    k.kind_from_descriptor(
        _descriptor(
            "FragmentWinsProbe",
            traits=["probe.assignable"],
            schema_fragments=["probe/override"],
        )
    )
    port = k.kind_port_for("FragmentWinsProbe")
    assert port.schema()["properties"]["owner"] == {"type": "integer"}
    assert schema_provenance(port)["owner"] == "fragment:probe/override"


# ── 5. the trait never LOOSENS (the FHIR rule) ───────────────────────────────


def test_a_trait_cannot_declare_additional_properties_false(probe_traits):
    """⚠️ THE loosening vector, and it is the most documented trap in JSON
    Schema: ``additionalProperties`` only sees ``properties`` in the SAME schema
    object, so a trait carrying ``additionalProperties: false`` would refuse
    every field the Kind declares. The vocabulary is closed so it cannot be
    said at all."""
    with pytest.raises(ValueError, match="deliberately closed"):
        register_trait(
            "probe.closed", "x",
            schema={"properties": {}, "additionalProperties": False},
        )


@pytest.mark.parametrize("key", ["not", "oneOf", "anyOf", "if", "patternProperties"])
def test_a_trait_cannot_use_a_conditional_or_negating_keyword(probe_traits, key):
    with pytest.raises(ValueError, match="deliberately closed"):
        register_trait("probe.sneaky", "x", schema={key: {}})


def test_a_trait_cannot_make_optional_what_the_kind_requires(probe_traits):
    """The FHIR rule, asserted where it actually lives: ``required`` is a UNION
    and nothing subtracts from it, so no trait — declaring anything at all —
    can drop the Kind's own obligation.

    ⚠️ MUTANT: change the union in ``apply_traits`` to an assignment
    (``effective_required = list(composed.required)``) and this is the test that
    dies."""
    k = Kernel()
    k.kind(
        _ClassKind(
            traits=["probe.assignable"],
            properties={"title": {"type": "string"}},
            required=["title"],
        )
    )
    assert k.kind_port_for("HandWritten").schema()["required"] == ["title"]


def test_a_traits_required_is_recorded_and_not_yet_enforced(probe_traits):
    """§12.3 is the founder's to answer, so the mechanism holds the answer
    without assuming it: the obligation is parsed, validated and REPORTED, and
    it is not unioned into the effective schema while
    ``TRAIT_REQUIRED_ENFORCED`` is False.

    If this test starts failing because the constant flipped, that is the
    decision landing — update it, do not delete it."""
    register_trait(
        "probe.demanding", "x",
        schema={"properties": {"why": {"type": "string"}}, "required": ["why"]},
    )
    k = Kernel()
    k.kind_from_descriptor(
        _descriptor("DemandProbe", traits=["probe.demanding"])
    )
    port = k.kind_port_for("DemandProbe")
    assert port.trait_required == ("why",)
    assert TRAIT_REQUIRED_ENFORCED is False
    assert "why" not in (port.schema().get("required") or [])
    # ...and an old instance with no `why` still writes, which is the entire
    # reason the decision is the founder's (spec §9.1).
    port.parse({"apiVersion": "x", "kind": "DemandProbe", "spec": {}})


def test_a_trait_cannot_require_a_field_nobody_declares(probe_traits):
    """An obligation on a field that does not exist can never be satisfied, so
    it is refused where the author is — at load."""
    register_trait("probe.ghost", "x", schema={"required": ["nowhere"]})
    k = Kernel()
    with pytest.raises(ValueError, match="can never be satisfied"):
        k.kind_from_descriptor(_descriptor("GhostProbe", traits=["probe.ghost"]))


# ── 6. the open vocabulary is still open ─────────────────────────────────────


def test_an_unregistered_trait_is_still_legal_and_carries_nothing():
    """What registration buys is a description and a carry; what it never buys
    is a veto (the promise the module docstring has always made)."""
    k = Kernel()
    k.kind_from_descriptor(
        _descriptor("OpenProbe", traits=["nobody.registered.this"])
    )
    port = k.kind_port_for("OpenProbe")
    assert port.traits == frozenset({"nobody.registered.this"})
    assert port.schema_fragments == ()


def test_a_kind_with_no_traits_still_answers_provenance_honestly():
    """An empty answer, not a missing one — the two read alike to a caller and
    only one of them is a fact."""
    k = Kernel()
    k.kind_from_descriptor(
        _descriptor("BareProbe", schema={"type": "object", "properties": {}})
    )
    port = k.kind_port_for("BareProbe")
    assert schema_provenance(port) == {}
    assert port.schema_fragments == ()


def test_apply_traits_is_idempotent(probe_traits):
    """Two call sites (the descriptor constructor and the registry door) are
    only safe because the second call is a no-op."""
    k = Kernel()
    port = k.kind_from_descriptor(
        _descriptor("IdempotentProbe", traits=["probe.assignable"])
    )
    before = dict(port.schema()["properties"])
    apply_traits(port)
    apply_traits(port)
    assert port.schema()["properties"] == before


# ── 7. the vocabulary can be PROJECTED — the ask, not the capability ─────────


def test_describe_traits_projects_the_live_vocabulary():
    """Measured cause of the 17% coverage: in one docstring ``presentation``
    had ~25 lines with an enumerated vocabulary and ``traits`` had one line with
    none. A hand-written list would drift on the next trait; this is projected,
    so the ask can be as good as ``presentation``'s and STAY that way."""
    text = describe_traits(prefix="sdlc.")
    assert "sdlc.work-item" in text
    assert "sdlc.dated" in text
    assert "memory.recallable" not in text  # the prefix filter is real
    # every sdlc trait in the registry appears — this is what makes it a
    # projection rather than a copy
    for name in known_traits():
        if name.startswith("sdlc."):
            assert name in text


def test_describe_traits_says_what_a_trait_CARRIES():
    """A vocabulary listing that cannot say "declaring this brings you fields"
    is the one-line docstring again, longer."""
    from dna.extensions.sdlc import SdlcExtension

    SdlcExtension._register_schema_fragments()
    text = describe_traits(prefix="sdlc.work-item")
    assert "carries fields" in text
    assert "relations" in text
    assert "implies sdlc.dated" in text


# ── 8. the real family, on real data ─────────────────────────────────────────


def test_the_work_item_trait_carries_the_family_contract():
    """The proof on real data: ``sdlc.work-item`` now brings ``timeline`` +
    ``produces`` and the ``produces`` relation, which the eight work items had
    each been restating. Their own copies still win (rule 3), so this merge is a
    NO-OP on today's registry — which is the safest possible way to prove a
    mechanism before anybody deletes a line."""
    from dna.extensions.sdlc import SdlcExtension

    SdlcExtension._register_schema_fragments()
    trait = trait_definition("sdlc.work-item")
    assert trait.schema_fragments == ("sdlc/work-item-activity",)
    assert "produces" in (trait.relations or {})
    assert trait.implies == frozenset({"sdlc.dated"})

    k = Kernel()
    k.load(SdlcExtension())
    story = k.kind_port_for("Story")
    props = story.schema()["properties"]
    # Story declares NEITHER in its own YAML — both arrive from the family.
    assert "timeline" in props and "produces" in props
    assert "sdlc.dated" in story.traits
    # the fragment survives on the port, which it did not before
    assert "sdlc/work-item-activity" in story.schema_fragments


def test_every_registered_trait_composes_against_the_live_registry():
    """A registry-wide sweep: if any real Kind's declared traits conflicted, or
    named a fragment nobody registered, the boot below would raise. It is the
    cheapest total assertion available and it is the one that catches an
    authoring mistake in slice 3."""
    from dna.extensions.sdlc import SdlcExtension

    k = Kernel()
    k.load(SdlcExtension())
    for port in k.kind_ports():
        assert isinstance(schema_provenance(port), dict)
        assert set(declared_traits_of(port)) <= set(port.traits)
    assert trait_registry()  # and the vocabulary is populated, not empty


# ── 9. i-129 — provenance has TWO axes, and neither may answer for the other ─
#
# The defect: one dict keyed by NAME, written by both the property pass and the
# relation pass, so a name that is both lost one of its two answers to whichever
# ran last. It read exactly like a fact, which is why no test saw it: every
# assertion asked "is there an answer?" and there always was one.
#
# So these ask the other question — "is the answer CORROBORATED by the source it
# names?" — and they ask it of the live registry rather than of a probe, because
# the eight Kinds that exhibit it are real ones.


def _fragment_properties(fid: str) -> set[str]:
    from dna.kernel.meta import _lookup_schema_fragment

    frag = _lookup_schema_fragment(fid)
    return set((frag or {}).get("properties") or {})


def test_a_name_that_is_property_AND_relation_keeps_BOTH_answers(probe_traits):
    """⭐ The i-129 defect, at the granularity it actually occurs.

    ``probe.assignable`` declares ``owner`` twice — once as a schema property,
    once as a relation — and ``probe/override`` re-declares the PROPERTY from a
    fragment, so the two axes have genuinely different sources. With one shared
    dict the fragment (the later writer) took the whole entry and the relation's
    origin was gone; the assertion that catches it is not "is there an origin"
    but "does each axis still name ITS OWN source".
    """
    register_schema_fragment(
        "probe/override",
        {"type": "object", "properties": {"owner": {"type": "integer"}}},
    )
    k = Kernel()
    k.kind_from_descriptor(
        _descriptor(
            "TwoAxisProbe",
            traits=["probe.assignable"],
            schema_fragments=["probe/override"],
        )
    )
    port = k.kind_port_for("TwoAxisProbe")

    assert schema_provenance(port)["owner"] == "fragment:probe/override"
    assert relation_provenance(port)["owner"] == "trait:probe.assignable"

    pv = provenance_of(port, "owner")
    assert pv.collides is True
    assert (pv.property_origin, pv.relation_origin) == (
        "fragment:probe/override",
        "trait:probe.assignable",
    )


def test_provenance_of_reports_a_missing_axis_as_a_FACT(probe_traits):
    """The other half of the read decision. Splitting the dict makes *"where did
    X come from?"* ill-posed; :func:`provenance_of` answers for both axes so the
    caller never has to know in advance which one X is. ``None`` there must mean
    "not on that axis" — a Kind that has been composed and simply has no
    relation of that name — and not "nobody recorded it"."""
    k = Kernel()
    k.kind(
        _ClassKind(
            traits=["probe.assignable"],
            properties={"title": {"type": "string"}},
        )
    )
    port = k.kind_port_for("HandWritten")

    title = provenance_of(port, "title")
    assert title.property_origin == "kind"
    assert title.relation_origin is None
    assert title.collides is False

    assert provenance_of(port, "nothing_declares_this") == type(title)(
        name="nothing_declares_this"
    )


def test_a_kind_whose_traits_carry_only_FIELDS_still_records_its_own_relations(
    probe_traits,
):
    """``probe.timestamped`` carries a field and no relation, so the relation
    merge used to be skipped entirely — and with it the provenance of the Kind's
    OWN relations. The port then answered ``{}`` for the relation axis, which
    reads as "this Kind has no relations" while ``relations_of`` lists one."""
    from dna.kernel.kinds.relations import relations_of

    k = Kernel()
    k.kind(
        _ClassKind(
            traits=["probe.timestamped"],
            properties={"title": {"type": "string"}},
            relations={"parent": {"to": "HandWritten", "cardinality": "one"}},
        )
    )
    port = k.kind_port_for("HandWritten")

    assert set(relations_of(port)) == {"parent"}
    assert relation_provenance(port) == {"parent": "kind"}


def test_every_provenance_label_is_CORROBORATED_by_the_source_it_names():
    """⭐ The derived guard, over the live registry.

    Not "does every field have an origin?" — every field had one, and eight of
    them were wrong. This asks the source: a ``trait:X`` property origin must be
    a trait whose INLINE schema declares that property; a ``fragment:Y``
    property origin must be a fragment that declares it; a ``trait:X`` relation
    origin must be a trait whose ``relations`` declares it. **A relation origin
    can never be a ``fragment:``** — a schema fragment carries properties and
    has no way to declare a relation — which is precisely the shape of the lie
    that was measured (``Story.produces`` relation → ``fragment:sdlc/work-item-
    activity``).

    ``kind`` is not corroborated here: after composition the port's own text is
    no longer separable from the merged result, and asserting something
    underivable is how a guard starts agreeing with itself.
    """
    from dna.extensions.sdlc import SdlcExtension

    k = Kernel()
    k.load(SdlcExtension())

    checked_trait_props = checked_frag_props = checked_trait_rels = 0
    for port in k.kind_ports():
        for name, origin in schema_provenance(port).items():
            if origin.startswith("trait:"):
                t = trait_definition(origin.split(":", 1)[1])
                assert t is not None and name in ((t.schema or {}).get("properties") or {}), (
                    f"{port.kind}.{name}: property origin {origin!r} names a "
                    f"trait that does not declare that property — a relation "
                    f"source leaked into the property axis (i-129)"
                )
                checked_trait_props += 1
            elif origin.startswith("fragment:"):
                fid = origin.split(":", 1)[1]
                assert name in _fragment_properties(fid), (
                    f"{port.kind}.{name}: property origin {origin!r} names a "
                    f"fragment that does not declare that property"
                )
                checked_frag_props += 1
            else:
                assert origin == "kind", f"{port.kind}.{name}: {origin!r}"

        for name, origin in relation_provenance(port).items():
            assert not origin.startswith("fragment:"), (
                f"{port.kind}.{name}: a RELATION cannot come from a schema "
                f"fragment — {origin!r} is the property axis answering for the "
                f"relation axis, which is the i-129 defect verbatim"
            )
            if origin.startswith("trait:"):
                t = trait_definition(origin.split(":", 1)[1])
                assert t is not None and name in (t.relations or {}), (
                    f"{port.kind}.{name}: relation origin {origin!r} names a "
                    f"trait that does not declare that relation"
                )
                checked_trait_rels += 1
            else:
                assert origin == "kind", f"{port.kind}.{name}: {origin!r}"

    # Guard over the guard: every branch above is vacuous on a registry with no
    # traits, and the sweep would pass green on a kernel that composed nothing.
    # The floors are MEASURED (06/08/2026): eight work items × ``produces`` on
    # each axis, plus ``timeline`` from the same fragment.
    assert checked_frag_props >= 16, checked_frag_props
    assert checked_trait_rels >= 8, checked_trait_rels
    # ⚠️ NOT asserted with a floor, and the absence is the point: no real trait
    # carries an INLINE schema property today (every sdlc trait carries fields
    # through a fragment), so a ``>= 1`` here would be a floor nothing can meet
    # and would have to be relaxed by whoever next ran the suite. The branch is
    # exercised by ``test_a_declared_trait_puts_its_field_on_a_hand_written_
    # class_kind`` on a probe instead.
    assert checked_trait_props == 0, checked_trait_props


def test_the_eight_work_items_report_produces_differently_on_each_axis():
    """The measurement that filed i-129, frozen as an assertion.

    ``produces`` arrives as a PROPERTY from ``sdlc/work-item-activity`` and as a
    RELATION from ``sdlc.work-item`` — two sources, one name, on every work
    item. One dict could hold one of them. The count is asserted (not just the
    shape) because the failure mode this replaces was a per-Kind erasure that a
    single-Kind spot check can miss."""
    from dna.extensions.sdlc import SdlcExtension

    k = Kernel()
    k.load(SdlcExtension())

    carriers = [
        p for p in k.kind_ports() if provenance_of(p, "produces").collides
    ]
    assert len(carriers) == 8, sorted(p.kind for p in carriers)
    for p in carriers:
        pv = provenance_of(p, "produces")
        assert pv.property_origin == "fragment:sdlc/work-item-activity"
        assert pv.relation_origin == "trait:sdlc.work-item"
