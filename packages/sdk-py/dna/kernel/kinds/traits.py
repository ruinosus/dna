"""Kind traits — the roles a Kind declares, and what those roles CARRY.

A trait answers "does this Kind take part in X?" for an X the kernel itself has
no opinion about. It is the third instance of a mechanism the SDK had already
built twice and then declined to generalise:

* :meth:`dna.kernel.Kernel._classify_kinds` — derives a set of Kind names from a
  declared attribute, but only for BOOLEAN attributes the kernel knows by name;
* :func:`dna.kernel.meta.register_schema_fragment` — an OPEN, namespaced,
  process-global registry extensions add to, which is exactly the shape a trait
  vocabulary needs.

Traits are the two joined: an open, namespaced vocabulary, resolved by lookup
(``kernel.kinds_with_trait("sdlc.work-item")``) rather than by a literal list in
whichever module needed one.

The defect this module used to have, and the shape of the fix
-------------------------------------------------------------
"A trait is only a label" was never true — five traits already REFUSE writes
(``sdlc.exit-criteria-required`` refuses a create, ``sdlc.test-gated`` refuses a
close, ``record.append-only`` refuses a delete, ``governance.spec-traced``
vetoes a write, ``memory.recallable`` defines what ``recall`` sweeps). The real
defect was worse and quieter: **the trait carried nothing; whoever ASKED carried
it**, with a literal list of Kind names sitting next to the question as a
fallback (``application/sdlc_family.py``, ``guardrails/write_guards.py``).

And the machinery for carrying already existed, DISCONNECTED: a Kind wrote

.. code-block:: yaml

    traits: [sdlc.work-item, sdlc.dated, ...]
    schema_fragments: [sdlc/work-item-activity]

— the same sentence in two vocabularies, neither able to check the other. A
Kind could take the trait without the fields (and be in the digest with no
``timeline``) or the fields without the trait (and have a ``timeline`` nothing
walks). Worse, the fragment IDs did not SURVIVE: they were merged in
``DeclarativeKindPort.__init__`` and thrown away, so ``hasattr(port,
"schema_fragments")`` was ``False`` and "where did this field come from?" had no
answer at all.

So a trait now DECLARES three things, and nothing beyond them:

``schema`` / ``schema_fragments``
    The fields the role brings. Either inline (``{"properties": {...},
    "required": [...]}``) or by naming fragments already in the
    ``register_schema_fragment`` registry — the mechanism is not new, it is
    finally attached to the thing that means it.

``relations``
    The relations the role brings. ``produces`` was declared seven times, once
    per work item, because there was nowhere for the family to say it once.

``implies``
    Other traits this one entails (``sdlc.rollup`` ⇒ ``sdlc.work-item`` ⇒
    ``sdlc.dated``). Between TRAITS only, never between Kinds: there is no
    ``extends`` on a Kind and this is not one arriving sideways. Cycles are
    refused at load.

A trait never declares a METHOD. Nothing here is shared behaviour; it is shared
CONTRACT — which is the answer to "inheritance mixes data with behaviour", and
the reason ``fragile base class`` has no base to be fragile about.

The three rules that make application ORDER irrelevant
------------------------------------------------------
This is the whole design, and it is borrowed on purpose. Every serious trait
system either **specified the order** (Scala linearisation), **forbade the
conflict** (Rust coherence / orphan rules) or **removed inherited state** (Go,
``typing.Protocol``). The one that did none of the three — LinkML ``mixins`` —
has `issue #2528 <https://github.com/linkml/linkml/issues/2528>`_ open since
2025-02-04, whose reporter wrote *"That result isn't shocking, but why? How am I
supposed to know what to expect."* We take Rust's road:

1. **Additive.** A trait only ADDS a property, a relation or an obligation. It
   can never remove one, and :data:`TRAIT_SCHEMA_KEYS` is closed to
   ``{type, properties, required}`` precisely so it cannot try: an
   ``additionalProperties: false`` arriving from a trait would erase every field
   the Kind declares, which is the single most documented JSON-Schema trap there
   is (json-schema-spec #661) and exactly the objection raised against doing
   this with ``allOf``.
2. **Conflict is REFUSED at load, never resolved by precedence.** Two traits
   declaring the same property with different subschemas — or the same relation
   with a different declaration — is an authoring error, and it is raised where
   the author can fix it. Two traits declaring the same thing IDENTICALLY is not
   a conflict; it is agreement, and agreement is free.
3. **The Kind wins.** A property or relation the Kind declares itself beats the
   trait's. This is not a new rule to document: it is verbatim the
   ``schema_fragments`` rule that has always been there — *"Kind-declared
   properties win over fragment ones."*

With all three, the order in which traits are applied CANNOT change the result,
which is what Scala had to specify a linearisation to obtain and what LinkML
still cannot say.

⚠️ A trait restricts and adds — it NEVER loosens (the FHIR rule)
----------------------------------------------------------------
Borrowed from FHIR profiles — *"Profiles cannot break the rules established in
the base specification"* — and it is the guardrail that keeps rule 3 from
becoming a hole. Concretely, in this implementation:

* trait-contributed ``required`` names are UNIONED with the Kind's, never
  subtracted, so no trait can make optional what the Kind demands;
* a trait cannot say ``additionalProperties``, ``not``, ``oneOf`` or anything
  else that widens or nullifies — the vocabulary is closed (rule 1);
* where a property is declared on both sides the Kind's wins, and the fact that
  it won is RECORDED (:func:`schema_provenance`), so a trait whose restriction
  was overridden is visible instead of silently ignored.

⚠️ Can a trait make a field REQUIRED? — not decided, and deliberately not
-------------------------------------------------------------------------
Spec ``spec-kind-taxonomia-o-que-eu-sou`` §12.3 leaves this to the founder,
because saying yes opens a real window: a Kind with old stored instances would
start REFUSING writes to them the moment a trait adds an obligation they never
had (§9.1). So the mechanism is built to hold the answer without assuming it:

* a trait MAY declare ``required``; it is parsed, validated (every name must
  resolve to a property that actually exists once everything is merged) and
  reported on the port as ``port.trait_required``;
* while :data:`TRAIT_REQUIRED_ENFORCED` is ``False`` — today's value — those
  names are NOT unioned into the Kind's effective ``required``, so no write that
  succeeds today can start failing;
* flipping the constant to ``True`` is the entire change the decision needs.

**What the implementation assumes meanwhile: a trait's ``required`` is a
DECLARATION that is recorded and not yet enforced.**

**Open, not an enum.** :func:`register_trait` exists for discoverability,
documentation and — now — carry; but declaring an unregistered trait is still
NOT an error. An extension that ships a Kind and a consumer of that Kind must
not have to patch a core enum to introduce a vocabulary only the two of them
share. An unregistered trait simply carries nothing, which is precisely what
every trait did before this module was written.

**Namespaced by convention**, mirroring ``schema_fragments``: ``<owner>/<name>``
or ``<owner>.<name>`` (``sdlc.work-item``, ``memory.recallable``). A trait with
no namespace is legal and reads as core-owned.

The search, including the nothing
---------------------------------
*Already installed:* ``jsonschema`` 4.26.0 is the only relevant dependency and
it has no merge vocabulary at all — it VALIDATES, and it is what ignores ``x-``
keywords. Nothing in the tree merges schemas: ``jsonmerge``, ``mergedeep``,
``deepmerge``, ``linkml_runtime`` are all absent, and a ``grep`` for
``def merge_schemas`` / ``allOf_merge`` across site-packages returns nothing.

*On GitHub:* ``json-schema-merge-allof`` is the one real prior art (JavaScript,
no Python equivalent) and it is a **counter-example we deliberately did not
adopt**: its entire job is to RESOLVE ``allOf`` conflicts by precedence, which
is the LinkML failure mode with a nicer API. We refuse instead. Repository
searches for trait/mixin composition with conflict refusal came back empty —
consistent with what the spec's own sweep found (§1.5: *"ninguém empacotou
isto"*).

*Designs borrowed, with the reason:* Rust traits (refuse the conflict), FHIR
profiles (restrict-never-loosen), CMIS 1.1 secondary types / Alfresco aspects
(a named marking that adds properties — our exact shape), Kubernetes CRD
``categories`` (a role label whose service is grouping a query). LinkML supplies
the counter-example, not the design.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

__all__ = [
    "CORE_TRAITS",
    "TRAIT_REQUIRED_ENFORCED",
    "TRAIT_SCHEMA_KEYS",
    "Trait",
    "TraitComposition",
    "TraitConflictError",
    "apply_traits",
    "compose_traits",
    "declared_traits_of",
    "describe_traits",
    "known_traits",
    "normalize_traits",
    "port_has_trait",
    "port_traits",
    "register_trait",
    "schema_provenance",
    "trait_closure",
    "trait_description",
    "trait_definition",
    "trait_registry",
    "traits_from_names",
]


#: The closed key set a trait's ``schema`` may use. CLOSED because rule 1
#: (additive) is only true if a trait has no way to say something subtractive:
#: ``additionalProperties: false`` from a trait would erase every property the
#: Kind declares, ``not``/``oneOf`` would nullify them conditionally. A trait
#: that needs any of those is not describing a role — it is describing a
#: validation rule, and the JSON Schema next door owns those.
TRAIT_SCHEMA_KEYS = frozenset({"type", "properties", "required"})

#: Whether a trait's declared ``required`` names are UNIONED into the Kind's
#: effective schema. ``False`` until the founder answers spec
#: ``spec-kind-taxonomia-o-que-eu-sou`` §12.3 — see the module docstring. While
#: it is False the names are still parsed, validated and reported
#: (``port.trait_required``); flipping it to True is the whole change.
TRAIT_REQUIRED_ENFORCED = False


class TraitConflictError(ValueError):
    """A trait declaration that cannot be composed — raised AT LOAD.

    A ``ValueError`` so every existing catch site keeps working: the builtin
    descriptor funnel turns it into a boot failure, and the per-scope
    ``KindDefinition`` funnel warn-skips it, exactly as they already do for a
    malformed ``relations`` or ``presentation`` block."""


@dataclass(frozen=True)
class Trait:
    """ONE registered trait, and everything it carries.

    Frozen for the reason :class:`~dna.kernel.kinds.relations.Relation` is: the
    registered definition is shared by every Kind that declares it, and one of
    them mutating it would change what the others carry."""

    #: The vocabulary name — ``sdlc.work-item``, ``memory.recallable``.
    name: str
    #: Human description. What ``dna kind traits`` lists and what
    #: :func:`describe_traits` projects into a tool's docstring.
    description: str = ""
    #: Inline JSON-Schema fragment, keys ⊆ :data:`TRAIT_SCHEMA_KEYS`.
    schema: Mapping[str, Any] | None = None
    #: Fragment IDs resolved against the ``register_schema_fragment`` registry
    #: at COMPOSE time — the mechanism that already existed, now hung on the
    #: trait instead of sitting beside it.
    schema_fragments: tuple[str, ...] = ()
    #: ``{relation name: Relation}``, already normalized at registration.
    relations: Mapping[str, Any] | None = None
    #: Traits this one entails. Between traits only; cycles refused at load.
    implies: frozenset[str] = frozenset()


@dataclass(frozen=True)
class TraitComposition:
    """What a Kind's declared traits contribute — before the Kind's own
    declarations are laid on top."""

    #: Everything the Kind declared, verbatim.
    declared: frozenset[str] = frozenset()
    #: ``declared`` plus everything they imply, transitively. This is what
    #: ``kernel.kinds_with_trait`` answers against.
    traits: frozenset[str] = frozenset()
    #: Trait-contributed ``schema.properties``.
    properties: dict[str, Any] = field(default_factory=dict)
    #: Trait-contributed ``required`` names, sorted. Reported always;
    #: enforced only when :data:`TRAIT_REQUIRED_ENFORCED`.
    required: tuple[str, ...] = ()
    #: Trait-contributed relations, ``{name: Relation}``.
    relations: dict[str, Any] = field(default_factory=dict)
    #: Every fragment ID that actually contributed, sorted.
    fragments: tuple[str, ...] = ()
    #: property/relation name → where it came from (``trait:<name>`` or
    #: ``fragment:<id>``). The provenance that used to be thrown away.
    origins: dict[str, str] = field(default_factory=dict)


#: name → :class:`Trait`. Process-global, exactly like ``_SCHEMA_FRAGMENTS``.
_TRAITS: dict[str, Trait] = {}


def register_trait(
    name: str,
    description: str = "",
    *,
    schema: Mapping[str, Any] | None = None,
    schema_fragments: Iterable[str] | None = None,
    relations: Mapping[str, Any] | None = None,
    implies: Iterable[str] | None = None,
) -> Trait:
    """Register a trait and what it CARRIES.

    Idempotent; a later call REPLACES the definition whole (not a merge — a
    half-replaced definition is the kind of state nobody can reason about). The
    registry is still DOCUMENTATION for the vocabulary itself: nothing checks a
    Kind's declared trait against it, by design. What registration buys is a
    description and a carry; what it never buys is a veto.

    Validation is split deliberately. What can be judged from the declaration
    ALONE is judged here (schema key set, relation shape, implies shape); what
    needs the Kind is judged in :func:`compose_traits` — a ``required`` name
    resolves against the MERGED property set, and a fragment ID against the
    registry as it stands when a Kind actually uses it.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("trait name must be a non-empty string")
    name = name.strip()

    if schema is not None:
        _lint_trait_schema(schema, where=f"trait {name!r} schema")

    frag_ids: tuple[str, ...] = ()
    if schema_fragments is not None:
        if isinstance(schema_fragments, str):
            raise ValueError(
                f"trait {name!r}: schema_fragments must be a list of fragment "
                f"IDs, got a bare string {schema_fragments!r}"
            )
        frag_ids = tuple(
            f.strip() for f in schema_fragments if isinstance(f, str) and f.strip()
        )

    rels: Mapping[str, Any] | None = None
    if relations is not None:
        from dna.kernel.kinds.relations import normalize_relations

        try:
            rels = normalize_relations(relations)
        except ValueError as e:
            raise ValueError(f"trait {name!r}: {e}") from e

    implied = normalize_traits(list(implies) if implies is not None else None)
    if name in implied:
        raise TraitConflictError(
            f"trait {name!r} implies itself — an implication is a statement "
            f"about ANOTHER trait"
        )

    trait = Trait(
        name=name,
        description=description or "",
        schema=dict(schema) if schema is not None else None,
        schema_fragments=frag_ids,
        relations=dict(rels) if rels else None,
        implies=implied,
    )
    _TRAITS[name] = trait
    return trait


def _lint_trait_schema(schema: Any, *, where: str) -> None:
    """Rule 1, enforced at the only place it CAN be: the declaration.

    A trait's schema is closed to :data:`TRAIT_SCHEMA_KEYS`. Everything outside
    that set is either subtractive (``additionalProperties: false`` erases the
    Kind's own fields — the json-schema-spec #661 trap) or conditional
    (``not``/``if``/``oneOf`` nullify them situationally). Either way it is a
    trait LOOSENING something, which the FHIR rule forbids."""
    if not isinstance(schema, Mapping):
        raise ValueError(f"{where} must be a mapping, got {type(schema).__name__}")
    unknown = sorted(set(schema) - TRAIT_SCHEMA_KEYS)
    if unknown:
        raise ValueError(
            f"{where} has key(s) {unknown} — a trait's schema vocabulary is "
            f"{sorted(TRAIT_SCHEMA_KEYS)} and is deliberately closed. A trait "
            f"ADDS fields and obligations; a key that could remove or nullify "
            f"one (additionalProperties, not, oneOf, if) would let a trait "
            f"loosen what the Kind established, which is the one thing a trait "
            f"may never do"
        )
    stype = schema.get("type")
    if stype is not None and stype != "object":
        raise ValueError(
            f"{where} declares type={stype!r}; a trait contributes PROPERTIES "
            f"to an object, so the only type it can have is 'object'"
        )
    props = schema.get("properties")
    if props is not None and not isinstance(props, Mapping):
        raise ValueError(
            f"{where}.properties must be a mapping of field name → subschema, "
            f"got {type(props).__name__}"
        )
    required = schema.get("required")
    if required is not None:
        if isinstance(required, str) or not isinstance(required, (list, tuple)):
            raise ValueError(
                f"{where}.required must be a list of field names, got "
                f"{type(required).__name__}"
            )
        for item in required:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(
                    f"{where}.required entries must be non-empty field names, "
                    f"got {item!r}"
                )


def known_traits() -> dict[str, str]:
    """Every registered trait → its description (a copy; sorted by name).

    Kept as ``name → description`` because that is what ``dna kind traits``
    prints; :func:`trait_registry` hands back the full definitions."""
    return {k: _TRAITS[k].description for k in sorted(_TRAITS)}


def trait_registry() -> dict[str, Trait]:
    """Every registered trait → its full :class:`Trait` (a copy, sorted)."""
    return {k: _TRAITS[k] for k in sorted(_TRAITS)}


def trait_definition(name: str) -> Trait | None:
    """The registered :class:`Trait`, or ``None`` for an unregistered one.

    ``None`` is not an error — the vocabulary is open, and an unregistered
    trait carries nothing (see the module docstring)."""
    return _TRAITS.get(name)


def trait_description(name: str) -> str | None:
    """The registered description for ``name``, or ``None`` if undocumented."""
    t = _TRAITS.get(name)
    return t.description if t is not None else None


def describe_traits(
    *, prefix: str | None = None, indent: str = "  ", width: int = 76,
) -> str:
    """The vocabulary, PROJECTED — for a tool docstring or a form's help text.

    This exists because of a measurement, not a preference. In the same
    ``author_kind`` docstring, ``presentation`` had ~25 lines with an enumerated
    closed vocabulary and ``traits`` had ONE line with no vocabulary at all —
    and the coverage followed: of 47 descriptors, 47 declare ``plane`` and 8
    declare ``traits``. Same file, same author, same mechanism.
    **Coverage follows the ASK, not the capability.**

    So the ask has to be as good as ``presentation``'s, and hand-writing it
    would drift the moment a trait is added. Project it instead.

    ``prefix`` filters to one namespace (``describe_traits(prefix="sdlc.")``).
    """
    lines: list[str] = []
    for name, trait in trait_registry().items():
        if prefix and not name.startswith(prefix):
            continue
        carries: list[str] = []
        if trait.schema or trait.schema_fragments:
            carries.append("fields")
        if trait.relations:
            carries.append("relations")
        if trait.implies:
            carries.append("implies " + ", ".join(sorted(trait.implies)))
        head = f"{indent}{name}"
        if carries:
            head += f"  [carries {'; '.join(carries)}]"
        lines.append(head)
        body = " ".join((trait.description or "").split())
        while body:
            cut = len(body)
            if cut > width:
                cut = body.rfind(" ", 0, width + 1)
                if cut <= 0:
                    cut = width
            lines.append(f"{indent}    {body[:cut].rstrip()}")
            body = body[cut:].lstrip()
    return "\n".join(lines)


def _reset_traits() -> None:
    """Test-only: clear the registry (mirrors ``_reset_schema_fragments``)."""
    _TRAITS.clear()


def normalize_traits(raw: Any) -> frozenset[str]:
    """A declared ``traits:`` value → a clean frozenset.

    Accepts a list / tuple / set / frozenset of strings (or ``None``). Blank
    entries are dropped and whitespace trimmed, so a YAML author's stray space
    never produces a trait nobody can look up. Anything else raises."""
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        raise ValueError(
            f"traits must be a list of strings, got a bare string {raw!r} — "
            f"write `traits: [{raw}]`"
        )
    if not isinstance(raw, (list, tuple, set, frozenset)):
        raise ValueError(
            f"traits must be a list of strings, got {type(raw).__name__}"
        )
    out: set[str] = set()
    for entry in raw:
        if not isinstance(entry, str):
            raise ValueError(
                f"every trait must be a string, got {type(entry).__name__}: {entry!r}"
            )
        cleaned = entry.strip()
        if cleaned:
            out.add(cleaned)
    return frozenset(out)


def port_traits(port: Any) -> frozenset[str]:
    """The traits a ``KindPort`` declares — ``frozenset()`` for a port that
    declares none.

    After :func:`apply_traits` has run (at registration, for every port) this
    is the CLOSURE: what the Kind wrote plus everything those traits imply. Ask
    :func:`declared_traits_of` for what the author actually typed — a screen
    that wants to show the Kind's own words needs the difference, and a lookup
    that wants "is this a work item?" needs the closure.

    ``getattr`` with a default rather than an attribute access: ``KindPort`` is
    a ``runtime_checkable`` Protocol whose ``isinstance`` check tests member
    PRESENCE, so ``traits`` deliberately is not a Protocol member and a
    KindPort-direct implementation is free not to have one."""
    return normalize_traits(getattr(port, "traits", None) or None)


def declared_traits_of(port: Any) -> frozenset[str]:
    """What the Kind's author actually wrote, before implications.

    Falls back to :func:`port_traits` for a port that has not been through
    :func:`apply_traits` — with no implications resolved the two are the same
    set, so the fallback cannot lie."""
    declared = getattr(port, "declared_traits", None)
    if declared is None:
        return port_traits(port)
    return normalize_traits(declared)


def port_has_trait(port: Any, trait: str) -> bool:
    """Whether ``port`` declares ``trait`` (implications included)."""
    return trait in port_traits(port)


def schema_provenance(port: Any) -> dict[str, str]:
    """field/relation name → where it came from, for a composed port.

    ``kind`` | ``trait:<name>`` | ``fragment:<id>``. The question
    *"where did this field come from?"* had NO answer before: fragments were
    merged in the port's constructor and the ID list was dropped on the floor,
    so a Kind's schema was a flat thing with an erased history. Returns ``{}``
    for a port that declares nothing — an honest empty, not a missing one."""
    return dict(getattr(port, "schema_provenance", None) or {})


def trait_closure(declared: Any) -> frozenset[str]:
    """``declared`` plus everything it implies, transitively.

    Cycles are REFUSED (``TraitConflictError``) rather than silently
    terminated: a cycle means two traits each claim to entail the other, and a
    vocabulary that lets that stand is one where "what does this Kind
    participate in?" has an answer that depends on where you start reading.

    "Shallow" in the spec's sense is preserved by construction, not by a depth
    limit: implication runs between TRAITS and never between Kinds, so no chain
    here can turn into Kind inheritance. Depth itself is harmless because the
    three composition rules make the traversal order irrelevant."""
    names = normalize_traits(declared)
    out: set[str] = set()

    def visit(name: str, path: tuple[str, ...]) -> None:
        if name in path:
            cycle = " -> ".join(path[path.index(name):] + (name,))
            raise TraitConflictError(
                f"trait implication cycle: {cycle}. `implies` is acyclic — two "
                f"traits that each entail the other are one trait with two "
                f"names, or one of them is wrong"
            )
        if name in out:
            return
        out.add(name)
        trait = _TRAITS.get(name)
        if trait is None:
            return  # open vocabulary: an unregistered trait implies nothing
        for implied in sorted(trait.implies):
            visit(implied, path + (name,))

    for n in sorted(names):
        visit(n, ())
    return frozenset(out)


def _trait_schema_sources(trait: Trait) -> list[tuple[str, Mapping[str, Any]]]:
    """``(origin label, schema)`` for everything ``trait`` contributes.

    The inline ``schema`` first, then each named fragment in declared order.
    An unknown fragment on a TRAIT is an ERROR, deliberately unlike an unknown
    fragment on a Kind (which is skipped, a contract with a test on it): a Kind
    naming a fragment nobody registered has simply asked for nothing, but a
    TRAIT that promises fields and delivers none is the exact "decoration"
    failure this module exists to end — silently."""
    from dna.kernel.meta import _lookup_schema_fragment

    out: list[tuple[str, Mapping[str, Any]]] = []
    if trait.schema:
        out.append((f"trait:{trait.name}", trait.schema))
    for fid in trait.schema_fragments:
        frag = _lookup_schema_fragment(fid)
        if frag is None:
            raise TraitConflictError(
                f"trait {trait.name!r} carries schema fragment {fid!r}, which "
                f"no extension has registered. A trait that promises fields "
                f"and delivers none is decoration again — register the "
                f"fragment before the trait (see SdlcExtension.register, where "
                f"the ordering is load-bearing and guarded)"
            )
        _lint_trait_schema(
            {k: v for k, v in frag.items() if k in TRAIT_SCHEMA_KEYS}
            if isinstance(frag, Mapping) else frag,
            where=f"trait {trait.name!r} fragment {fid!r}",
        )
        out.append((f"fragment:{fid}", frag))
    return out


def compose_traits(declared: Any) -> TraitComposition:
    """Everything a Kind's traits contribute — conflicts REFUSED, not resolved.

    Raises :class:`TraitConflictError` when two traits in the closure declare
    the same property with different subschemas, or the same relation with a
    different declaration. Identical declarations are agreement, not conflict:
    the seven work items that each declare ``produces`` say precisely the same
    thing, and a mechanism that called that a clash would be unusable on the
    data it was built for.

    Does NOT look at the Kind's own schema or relations — that is
    :func:`apply_traits`, where rule 3 (the Kind wins) is applied on top."""
    closure = trait_closure(declared)

    properties: dict[str, Any] = {}
    origins: dict[str, str] = {}
    required: dict[str, str] = {}
    relations: dict[str, Any] = {}
    fragments: list[str] = []

    for name in sorted(closure):
        trait = _TRAITS.get(name)
        if trait is None:
            continue  # open vocabulary: unregistered carries nothing
        for label, schema in _trait_schema_sources(trait):
            if label.startswith("fragment:"):
                fragments.append(label.split(":", 1)[1])
            props = schema.get("properties") if isinstance(schema, Mapping) else None
            for pname, subschema in (props or {}).items():
                prior = properties.get(pname)
                if prior is not None and prior != subschema:
                    raise TraitConflictError(
                        f"traits disagree about property {pname!r}: "
                        f"{origins[pname]} and {label} declare it differently. "
                        f"Trait conflict is REFUSED, not resolved by "
                        f"precedence — the order traits are applied in must "
                        f"never be able to change what a Kind means (this is "
                        f"the road Rust took and LinkML #2528 did not). Make "
                        f"the two declarations identical, or declare the field "
                        f"on the Kind itself, where it wins outright"
                    )
                properties[pname] = subschema
                origins.setdefault(pname, label)
            for rname in (schema.get("required") or ()) if isinstance(schema, Mapping) else ():
                required.setdefault(rname, label)
        for rname, rel in (trait.relations or {}).items():
            prior_rel = relations.get(rname)
            if prior_rel is not None and prior_rel != rel:
                raise TraitConflictError(
                    f"traits disagree about relation {rname!r}: "
                    f"{origins[rname]} and trait:{trait.name} declare it "
                    f"differently. Trait conflict is REFUSED, not resolved — "
                    f"declare the relation on the Kind itself if the two roles "
                    f"genuinely need different edges"
                )
            relations[rname] = rel
            origins.setdefault(rname, f"trait:{trait.name}")

    return TraitComposition(
        declared=normalize_traits(declared),
        traits=closure,
        properties=properties,
        required=tuple(sorted(required)),
        relations=relations,
        fragments=tuple(sorted(set(fragments))),
        origins=origins,
    )


def apply_traits(port: Any) -> TraitComposition | None:
    """Compose ``port``'s traits INTO it — the load-time door.

    Called once per port, from ``KindRegistry.register_kind`` (so a hand-written
    class Kind gets it too) and from ``DeclarativeKindPort.__init__`` (so a
    descriptor port is complete even before it is registered). Idempotent: the
    second call is a no-op, which is what makes those two call sites safe.

    After it runs the port carries, and these are the answers that used to not
    exist:

    ``traits``            the CLOSURE (declared + implied)
    ``declared_traits``   what the author wrote
    ``schema()``          the MERGED schema — trait fields are simply there
    ``schema_fragments``  every fragment that contributed (this used to be
                          ``hasattr → False``: merged, then erased)
    ``schema_provenance`` field/relation → ``kind`` | ``trait:x`` |
                          ``fragment:y``
    ``relations``         the merged relations, Kind's own winning
    ``trait_required``    what traits would make required (see
                          :data:`TRAIT_REQUIRED_ENFORCED`)

    Precedence, low to high: trait contributions → the Kind's OWN
    ``schema_fragments`` → the Kind's literal ``schema.properties``. That is
    rule 3 applied twice with the same reasoning — the more local declaration
    wins, and the most local one is the Kind's own text."""
    if getattr(port, "__traits_composed__", False):
        return getattr(port, "trait_composition", None)

    declared = port_traits(port)
    own_fragments = tuple(getattr(port, "schema_fragments", None) or ())
    if not declared and not own_fragments:
        # Nothing to compose. Stamp the flag anyway so a second pass over a
        # bare port is as cheap as over a composed one, and stamp an EMPTY
        # provenance so `schema_provenance(port)` answers honestly rather than
        # falling through to a missing attribute — the two read alike to a
        # caller and only one of them is a fact.
        port.__traits_composed__ = True
        port.declared_traits = frozenset()
        port.schema_provenance = {}
        port.trait_required = ()
        port.trait_composition = None
        return None

    composed = compose_traits(declared)

    # ---- schema: trait props → Kind's own fragments → Kind's own properties
    from dna.kernel.meta import _lookup_schema_fragment

    merged_props: dict[str, Any] = dict(composed.properties)
    provenance: dict[str, str] = dict(composed.origins)
    contributing_fragments = list(composed.fragments)

    for fid in own_fragments:
        frag = _lookup_schema_fragment(fid)
        if not isinstance(frag, Mapping):
            # Unchanged contract for a KIND's own fragment list: an unknown ID
            # is SKIPPED, not refused. Changing it here would turn a load
            # ordering slip in somebody else's extension into a boot failure,
            # and the guard that catches that lives in the extension.
            continue
        contributing_fragments.append(fid)
        for pname, subschema in (frag.get("properties") or {}).items():
            merged_props[pname] = subschema
            provenance[pname] = f"fragment:{fid}"

    own_schema = None
    try:
        own_schema = port.schema()
    except Exception:  # noqa: BLE001 — a Kind whose schema() needs state we
        own_schema = None  # do not have must not take the registration down
    own_schema = dict(own_schema) if isinstance(own_schema, Mapping) else {}
    own_props = own_schema.get("properties")
    own_props = dict(own_props) if isinstance(own_props, Mapping) else {}
    for pname, subschema in own_props.items():
        merged_props[pname] = subschema
        provenance[pname] = "kind"

    # ---- required: UNION only. Rule 1 and the FHIR rule live in this line —
    # a trait can add a name here and can never take one away, so no trait can
    # make optional what the Kind demands.
    own_required = own_schema.get("required")
    own_required = [r for r in own_required if isinstance(r, str)] if isinstance(
        own_required, (list, tuple)
    ) else []
    effective_required = list(own_required)
    if TRAIT_REQUIRED_ENFORCED:
        for name in composed.required:
            if name not in effective_required:
                effective_required.append(name)

    # A trait's `required` must name a field that exists once EVERYTHING is
    # merged — its own, another trait's, a fragment's or the Kind's. Checked
    # here rather than at registration because only here is the full property
    # set known, and an obligation on a field nobody declares is an obligation
    # nothing can ever satisfy.
    for name in composed.required:
        if name not in merged_props:
            raise TraitConflictError(
                f"trait-declared required field {name!r} "
                f"({composed.origins.get(name, 'a trait')}) is not a property "
                f"of Kind {getattr(port, 'kind', '?')!r} — not from a trait, "
                f"not from a fragment, not from the Kind itself. An obligation "
                f"on a field that does not exist can never be satisfied"
            )

    if merged_props or own_schema:
        merged_schema: dict[str, Any] = dict(own_schema)
        merged_schema.setdefault("type", "object")
        merged_schema["properties"] = merged_props
        if effective_required:
            merged_schema["required"] = effective_required
        _install_schema(port, merged_schema)

    # ---- relations: trait's, then the Kind's own on top (rule 3)
    if composed.relations:
        from dna.kernel.kinds.relations import relations_of

        merged_rels = dict(composed.relations)
        for rname, rel in relations_of(port).items():
            merged_rels[rname] = rel
            provenance[rname] = "kind"
        port.relations = merged_rels

    port.traits = composed.traits
    port.declared_traits = composed.declared
    port.schema_fragments = tuple(sorted(set(contributing_fragments)))
    port.schema_provenance = provenance
    port.trait_required = composed.required
    port.trait_composition = composed
    port.__traits_composed__ = True
    return composed


def _install_schema(port: Any, schema: dict[str, Any]) -> None:
    """Make ``port.schema()`` return the merged schema.

    ``DeclarativeKindPort`` keeps its own field so that ``parse()`` validates
    against the merged shape too; every other port gets an instance-level
    ``schema`` that shadows the class method. Both are the same statement: the
    trait's fields ARE the Kind's fields now, and no reader has to compose them
    to find that out. That is the whole point — the defect was that whoever
    ASKED had to carry what the trait meant."""
    if hasattr(port, "_json_schema"):
        port._json_schema = schema
        return
    port.schema = lambda _schema=schema: _schema


# ── the core vocabulary ─────────────────────────────────────────────────────
#
# Registered here so the descriptions live with the definition rather than in a
# doc that drifts. Extensions register their own in ``register(kernel)`` — and
# an extension also ATTACHES the carry to a core trait it owns the family of
# (``SdlcExtension`` hangs the work-item fields and the ``produces`` relation on
# ``sdlc.work-item``), because the kernel must not name an extension's fragment.
#
# Each description now answers TWO questions, not one: what the role means, and
# what declaring it BRINGS. The second half is new, and it is the half a Kind
# author needs — "cobertura segue o pedido, não a capacidade".

CORE_TRAITS: dict[str, str] = {
    "sdlc.work-item": (
        "A board item with a status arc, a timeline and an owner — the thing a "
        "person is assigned and closes. Participates in the digest, the "
        "gallery, status transitions and comments. CARRIES the work-item "
        "activity fields (`timeline`, `produces`) and the `produces` relation, "
        "so a work item does not restate either; IMPLIES `sdlc.dated`."
    ),
    "sdlc.decision": (
        "A recorded decision (ADR). Walked by the digest and the gallery, and it "
        "may produce outputs, but it is not assigned and does not progress."
    ),
    "sdlc.observation": (
        "A filed observation (Kaizen) — noticed, not planned. Reaches the "
        "digest's `found` bucket; carries no `updated_at` arc."
    ),
    "sdlc.rollup": (
        "A work item that AGGREGATES other work items (Feature / Epic / "
        "Initiative). Movement at this level is roadmap movement, which is what "
        "the digest's `parents_progressed` bucket reports. IMPLIES "
        "`sdlc.work-item` — a thing that rolls work items up is one."
    ),
    "sdlc.filed": (
        "Enters the board by being FILED rather than planned — the digest's "
        "`found` bucket (Issue, Kaizen). Deliberately implies NOTHING: Kaizen "
        "is filed and is not a work item, so the two do not travel together."
    ),
    "sdlc.journey-derived": (
        "Its journey phases are derived locally from its own spec + timeline "
        "(no WorkflowEvent ledger read)."
    ),
    "sdlc.dated": (
        "Carries `created_at` AND `updated_at`: a read surface dates, sorts or "
        "windows it by both."
    ),
    "sdlc.dated-create-only": (
        "Carries `created_at` but has no `updated_at` arc — an observation is "
        "dated when it is made and does not move."
    ),
    "sdlc.exit-criteria-required": (
        "A create of this Kind is REFUSED without acceptance criteria and a "
        "definition of done — a work item that does not declare what `done` "
        "means cannot be shown to be done."
    ),
    "sdlc.test-gated": (
        "A CLOSE of this Kind is REFUSED without a passing product-lane TestRun "
        "verifying it. The escape hatches require a reason and land on the "
        "timeline."
    ),
    "governance.spec-traced": (
        "A write of this Kind must trace to a Spec when the scope's constitution "
        "demands it (the spec-kit governance guard)."
    ),
    "record.append-only": (
        "An audit / evidence record: it may be WRITTEN and READ but never "
        "deleted through a generic tool. The record is what proves what "
        "happened, so deleting it is the first move of anyone with something "
        "to hide — and unlike a bad write, it is not recoverable by writing a "
        "better one."
    ),
    "memory.recallable": (
        "Participates in `recall` / `remember` / the memory index — the set the "
        "memory verbs search. DISTINCT from `embed:`, which declares WHICH "
        "FIELDS carry an embeddable payload: an ADR should be searchable without "
        "being decay-ranked as a memory."
    ),
}

#: Which core traits entail which. Both entries are MEASURED, not designed: of
#: the 17 Kinds declaring a trait on 06/08/2026, all 8 work items also declared
#: ``sdlc.dated`` and all 3 rollups also declared ``sdlc.work-item``. So the
#: closure changes nothing about today's registry — which is the safest
#: possible proof that the mechanism runs on real data.
#:
#: Deliberately SHORT. ``sdlc.filed`` does not imply ``sdlc.work-item`` (Kaizen
#: is filed and is an observation), and inventing the implication to make the
#: table look complete is how a vocabulary starts lying.
CORE_TRAIT_IMPLIES: dict[str, tuple[str, ...]] = {
    "sdlc.work-item": ("sdlc.dated",),
    "sdlc.rollup": ("sdlc.work-item",),
}

for _name, _desc in CORE_TRAITS.items():
    register_trait(_name, _desc, implies=CORE_TRAIT_IMPLIES.get(_name))


def traits_from_names(names: Iterable[str]) -> frozenset[str]:
    """Convenience for class Kinds: ``traits = traits_from_names([...])``."""
    return normalize_traits(list(names))
