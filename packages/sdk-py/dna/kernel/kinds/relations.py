"""``spec.relations`` — what a Kind POINTS AT, declared as a thing of its own.

A relation between two Kinds used to live inside a property of the data schema:
``x-dna-ref: Feature`` hanging off a field, next to its ``type`` and its
``description``. That is a defensible place to put an annotation and a wrong
place to put a MODEL. Four things went wrong there, all measured on this repo's
own registry:

1. **Reciprocal pairs with no pair.** ``Epic.features``/``Feature.epic`` and
   ``Feature.stories``/``Story.feature`` are two declarations expressing ONE
   relation, and nothing said they were halves of it. Writing one side without
   the other left the two disagreeing, silently.
2. **Four mechanisms for one question.** ``x-dna-ref``,
   ``x-dna-ref-composite``, a name-shape guess (``_id``/``_ref``/``_refs``),
   and a denylist whose only job was to shut the guess up. Four answers to
   "what does this field point at?", three of which the write path did not
   enforce.
3. **A Kind's relations were not listable** without walking its properties and
   re-implementing the reading.
4. **Cardinality was not declarable** — it was inferred from ``type: array``,
   which is a statement about JSON, not about the model.

So the relation moves OUT of the data schema and becomes a first-class block::

    spec:
      target_kind: Feature
      relations:
        stories:
          to: Story
          cardinality: many
          inverse_of: feature
        epic:
          to: Epic
          cardinality: one
          inverse_of: features
      schema: { ... }        # the JSON Schema keeps the DATA

**The relation NAME is the spec field that holds the value.** That is not a
coincidence to be tidied away later — it is what keeps the declaration and the
data in the same place, so that no instance had to change when the declaration
moved, and so that the read which VALIDATES a relation is the read that
produces its edge (``dna.kernel.query.references``).

The four keys, and nothing else
-------------------------------
``to``
    Which Kinds the relation may point at. A Kind NAME (``Story``), a LIST of
    them for a polymorphic relation (``[Organization, Project]`` — any one may
    match), or :data:`ANY_TARGET` (``"*"``) when the model genuinely does not
    constrain the target — ``Comment.target_ref`` can pin anything that exists.
    A bare Kind name, not an alias: ``target_kind`` is globally unique by an
    ENFORCED registry invariant (i-195 — two api_versions sharing a Kind name
    is a ``KindRegistrationError``), so a bare name resolves unambiguously by
    construction, and it is what ``get_instance(scope, kind, name)`` already
    takes. (The ``alias`` field's own description used to claim aliases were
    for "cross-kind refs"; that claim never matched any implementation and is
    corrected in the meta-schema — i-110 item 2.)

``cardinality``
    ``one`` or ``many``. REQUIRED, and deliberately not defaulted from
    ``type: array``: a default derived from the schema would be the old
    inference wearing a new coat, and the point of this field is that the
    model states its own multiplicity. A contradiction between the two IS
    checkable, and :func:`schema_contradictions` checks it.

    Declared on BOTH sides of a pair, which Datomic's design argues against —
    there the reverse of a ref is always a collection, so accepting a
    cardinality on it admits declarations nothing can satisfy. That argument
    does not carry here, and the difference is worth naming: Datomic's reverse
    is a VIEW of one stored datum, while ``Feature.stories`` and
    ``Story.feature`` are two independently STORED fields. Each has a real
    multiplicity of its own, both are authored, and both can be wrong. A
    cardinality derived for the second side would be describing a field the
    instance actually holds — from the other instance.

``inverse_of``
    The NAME of the relation on the target Kind that is this relation's other
    half. See "What ``inverse_of`` promises" below — it promises less than it
    looks like, on purpose.

``by``
    How the VALUE addresses the target. Default :data:`BY_NAME` — the value is
    the target instance's ``metadata.name``, which is the only addressing the
    kernel resolves and therefore the only one it validates. Anything else is
    a DECLARATION of addressing that this runtime does not resolve:

    * a target spec FIELD (``by: workspace_id``) — the value matches the
      target's ``spec.workspace_id`` rather than its name. Real relations
      (``Project.workspace_id``, ``WorkspaceMembership.role``) that used to sit
      in a hand-kept "undeclarable" table in ``kind_graph``, invisible to the
      Kind that owned them.
    * a composite FORM (``by: "Kind:name"``): the value carries its own target
      Kind, written inside the string (or, for ``{kind, name}``, inside the
      object). This is a statement about the ADDRESS, and it is deliberately
      independent of ``to`` — see below.

    ⚠️ **A non-``name`` ``by`` installs NO resolution rule.** It says how the
    address is written; it does not teach the kernel to follow it. That
    restraint is deliberate and was bought with a measured mistake: the
    ``PricingPlan`` lookup already resolves by ``spec.tier_id`` and THEN by
    ``spec.aliases[]`` (``kernel.tier()``), so a declaration that resolved by
    ``tier_id`` alone would be a SECOND resolution rule, free to veto data the
    live one accepts. Resolving by key also needs an expression index the
    store does not have. Declaring the addressing costs nothing and can lie to
    nobody; resolving it is a separate slice with a separate cost.

``to`` and ``by`` are two questions, and collapsing them cost 21 relations
---------------------------------------------------------------------------
The first cut of this module refused ``to: [Story, Spike, Issue]`` together
with ``by: "Kind/name"``, on the reasoning that *"a composite value carries its
own Kind, so the two statements contradict"*. They do not contradict — they
answer different questions:

* ``by`` says **where the target Kind name is written**: in the schema
  (``by: name`` — the field holds only the instance name) or in the VALUE
  (a composite form — the field holds ``Story/s-foo``).
* ``to`` says **which Kinds are allowed**. A composite address still has to
  name a Kind, and the model usually knows the short list it may name.

Collapsing the two forced every composite relation to say ``to: "*"``, and the
price was measured on 06/08/2026: **21 of the 47 declared edges in this repo's
registry pointed at "*"** — ``TestGuide.verifies``, ``Kaizen.work_item``, eight
``produces`` fields, ``WorkflowEvent.ref``/``parent_ref``, ``Research.cited_by``
and the rest. The graph knew a link existed and could not say what it linked
to, so *"which TestGuides verify this Story?"* had no answer — only *"which
TestGuides verify something"*. That is a declaration without a type, which is
half the road and looks like all of it.

So a composite relation MAY declare its targets, and ``ANY_TARGET`` goes back to
meaning what it says: **the model does not constrain the target**, because the
thing really can point at anything (``Comment.target_ref``,
``Evidence.document_ref``, ``*.produces``). The distinction a reader needs is
*"open by design"* versus *"we could not type it"*, and before this change the
vocabulary could not make it.

Two orthogonal properties fall out, and they are NOT the same question:
:attr:`Relation.carries_kind` (the value names its own Kind — a fact about the
ADDRESS) and :attr:`Relation.open_target` (no declared target — a fact about the
MODEL). ``Relation.resolved`` is unchanged: a typed composite is declared and
drawn, and this runtime still does not parse it. Declaring the address costs
nothing and can lie to nobody; following it is a separate slice, exactly as it
is for ``by: workspace_id``.

What ``inverse_of`` promises — the weakest thing that ends the silence
---------------------------------------------------------------------
Three promises were available and they are not interchangeable:

* **IMPOSE** — refuse a write whose other half is missing. Rejected: it
  deadlocks. ``Feature.stories`` cannot be written before the Story names the
  Feature, and the Story cannot be written before the Feature exists. A rule
  whose only satisfying order is "neither first" is not a rule.
* **DERIVE** — write the missing half. Rejected: it is a cascade write. The
  kernel would mutate an instance the author did not touch, inside someone
  else's version, etag and layer policy, and a write amplification nobody
  asked for is how an instance store becomes a graph database by accident.
* **REPORT** — say that the two disagree. Chosen, and it is FREE: the
  existence check already materialized the target instance, so asking whether
  it names us back costs no read at all. This is the same trade
  ``ResolvedEdge`` already documents — the fact is not computed, it is simply
  not discarded.

So: **instance reciprocity is REPORTED, never enforced, in every mode** —
``DNA_REF_VALIDATION=enforce`` vetoes a DANGLING reference and still only logs
a non-reciprocal one, because the two are different failures and only one of
them is the author's to fix right now.

What IS enforced is the other half of dor 1, and it costs nothing either:
**the declaration must pair.** ``Feature.stories.inverse_of: feature`` requires
``Story`` to declare a relation ``feature`` that points back at ``Feature`` and
names ``stories`` as ITS inverse. That check reads no instances, cannot
deadlock, and is where "nada diz que são inversas" actually gets fixed —
:func:`inverse_gaps` computes it and the schema graph reports every failure.

And what ``inverse_of`` BUYS, since reverse traversal was already free
----------------------------------------------------------------------
Gel (EdgeDB) and Datomic both refuse the keyword outright: a link has no
declared inverse, and you traverse backwards at query time
(``.<authors[is Article]``, ``:release/_artists``). ``dna_edges`` already
answers backlinks with a recursive CTE, so the traversal argument for
``inverse_of`` is genuinely worthless here — and saying so is the difference
between borrowing a keyword and understanding it.

What it buys is what those two systems do not have to worry about: in this
model **both halves are STORED**. Gel's reverse is a view of one stored link
and cannot disagree with itself. ``Feature.stories`` and ``Story.feature`` are
two fields in two instances written by two writes, and they can — and did —
end up saying different things with nothing able to notice. ``inverse_of``
buys the NAME of the other half, the load-time proof that the pair is
declared on both sides, and the write-time report that the two instances
agree. LinkML has the keyword and concedes in its own documentation that it
"acts as additional documentation and doesn't affect programming semantics";
Dgraph's ``@hasInverse`` materializes the other side automatically. This is
deliberately neither: not inert, not a cascade.

The argument this replaces, answered rather than ignored
--------------------------------------------------------
``references.py`` argued for the field-level annotation with three reasons,
and they deserve answers rather than a silent overwrite:

1. *"Zero meta-schema change — a new top-level key would be a breaking edit to
   the public descriptor contract."* Correct, and it IS that breaking edit.
   What changed is not the argument but its price: the founder measured on
   06/08/2026 that there is no consumer of the SDK or the cloud, production is
   ``Stopped`` and re-seedable from ``.dna/`` in git. The cheapest window this
   edit will ever have is now, and every day adds instances in the old shape.
2. *"Field granularity — the reference belongs next to its type and
   description, where the author will see it."* Preserved, and this is why the
   relation's NAME is the field's name: the property stays in the schema with
   its type and its prose, and the relation is one block away in the same
   instance. What moved is the MODEL, not the data.
3. *"It does not disturb ``dep_filters``."* Unchanged. ``dep_filters`` drives
   PROMPT COMPOSITION — a missing optional Skill is legitimately filtered out
   there rather than being an error — and it is deliberately not folded in
   here. It was never one of the four mechanisms this module retires.

The search, including the nothing
---------------------------------
*Already installed:* nothing to adopt. ``sqlalchemy`` is present but the SDK
uses Core only (``sa.Table``), so ``back_populates`` is a design precedent and
not a component; ``jsonschema`` has no relation vocabulary (it is what ignores
``x-`` keywords today); ``networkx`` walks a graph somebody else built.
``linkml``, ``rdflib``, ``pyshacl`` are absent, and ``inverse_of`` appears in
the venv exactly twice, both meaning a mathematical inverse.

*Standards:* JSON Schema has no relations vocabulary — JSON Hyper-Schema's
``rel``/``targetSchema`` never left draft and carries neither cardinality nor
inverse; Hydra defers to RDF/OWL; ALPS is dormant. So there is no
interoperability being forfeited by declaring our own, and no official
implementation the house rule would oblige us to use.

*Designs borrowed, with the reason:* LinkML's slot vocabulary
(``range``/``multivalued``/``inverse``) is the shape of ``to``/``cardinality``/
``inverse_of``. LinkML itself was already evaluated and refused for this house
— *"ele quer ser a fonte de verdade do schema, e a nossa fonte de verdade é o
Kind"* (``adr-grafo-ontologia-e-alinhamento`` §1.4) — a refusal of OWNERSHIP,
not of design, and that ADR says twice that it stole the design deliberately.
One divergence from LinkML is deliberate: it puts relations in the SAME
namespace as data fields (``range:`` does double duty for ``string`` and for
``MedicalEvent``), where this splits ``relations`` from ``schema``. Gel is the
precedent for the split — ``link`` is a distinct declaration from
``property``. SQLAlchemy supplies the decisive datapoint for declaring both
sides: it shipped ``backref`` (derive the other side) and ``back_populates``
(declare it), and DEMOTED the first, because a generated relation is invisible
to whoever reads the target's own definition. JSON:API's resource identifier
object ``{type, id}`` is ``by: "{kind, name}"``.

*Not adopted, and why:* Dgraph ``@hasInverse`` (materializes the other side —
a cascade write); Datomic/Gel implicit reverse (their reverse is a view, ours
is stored — see above); ``a5c-ai/babysitter``'s ``edge-kinds.yaml``, the
closest external shape found, which re-declares source/target/cardinality/
attributes flipped on the inverse and already shows drift in its own file —
read as a warning that the second side must be a NAME and nothing more.

Tenant-authored Kinds are first-class
-------------------------------------
The identical block is a first-class field of ``KindDefinition``
(``spec.relations``, in both copies of ``kind-definition.schema.json``),
normalized by the identical function here, landing on the identical port
attribute — the precedent ``spec.presentation`` set. A relation only a builtin
extension could declare would make every tenant Kind second-class.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

__all__ = [
    "ANY_TARGET",
    "BY_NAME",
    "CARDINALITIES",
    "COMPOSITE_FORMS",
    "INVERSE_GAP_CODES",
    "Relation",
    "inverse_gaps",
    "normalize_relations",
    "reciprocates",
    "relation_values",
    "relations_of",
    "schema_contradictions",
]

#: ``to: "*"`` — the model does not constrain the target Kind, because the
#: relation really can point at anything (a Comment pins any instance). NOT the
#: same statement as "the value carries its own Kind" — that is ``by``, and
#: conflating the two is what left 21 real relations untyped. Deliberately not a
#: Kind-shaped token: nothing should be able to mistake it for a name somebody
#: might register.
ANY_TARGET = "*"

#: The default (and only RESOLVED) addressing: the value is the target
#: instance's ``metadata.name``.
BY_NAME = "name"

#: The closed cardinality vocabulary. Two words, because a model that needs
#: "exactly 3" is describing a validation rule, and the JSON Schema next door
#: already has ``minItems``/``maxItems`` for that.
CARDINALITIES: tuple[str, ...] = ("one", "many")

#: The closed set of composite forms — how a value that carries its OWN target
#: Kind is written. CLOSED on purpose: ``x-dna-ref-composite`` took a free
#: string, and a form nobody can parse is a declaration nobody can use.
#: ``Kind/slug`` was in use and is NOT here — an instance's slug IS its name, so
#: it was one form written two ways, which is the drift a closed set exists to
#: stop. Orthogonal to ``to``: a composite relation may still declare WHICH
#: Kinds its value is allowed to name.
COMPOSITE_FORMS: tuple[str, ...] = ("Kind:name", "Kind/name", "{kind, name}")

#: Why a declared inverse does not pair. Machine-readable, because a screen
#: must rank these without parsing English — the lesson ``UNRESOLVED_ORIGINS``
#: learned when 25 rows of one origin read like 25 broken declarations.
INVERSE_GAP_CODES: tuple[str, ...] = (
    "inverse_missing",       # the target declares no relation by that name
    "inverse_target",        # it exists but does not point back at us
    "inverse_not_mutual",    # it points back but names a different inverse
    "inverse_on_any",        # declared on a `to: "*"` relation — no target to pair with
)

_RELATION_KEYS = frozenset({"to", "cardinality", "inverse_of", "by"})
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Relation:
    """ONE declared relation. Frozen: the normalized declaration is shared by
    every reader of the Kind, and one of them mutating it would change what the
    others see."""

    #: The relation's name, which IS the spec field holding its value(s).
    name: str
    #: Target Kind names, sorted. EMPTY only for ``to: "*"`` — the model
    #: declining to constrain the target. See :attr:`open_target`.
    to: tuple[str, ...]
    #: ``one`` | ``many`` — declared, never inferred from the JSON Schema.
    cardinality: str
    #: The relation NAME on the target that is this one's other half.
    inverse_of: str | None = None
    #: How the value addresses the target — :data:`BY_NAME`, a target spec
    #: field, or a member of :data:`COMPOSITE_FORMS`.
    by: str = BY_NAME

    @property
    def carries_kind(self) -> bool:
        """The VALUE names its own Kind — a fact about the ADDRESS.

        True for every composite ``by``, whether or not the relation also
        declares which Kinds that address may name. This used to be spelled
        ``not self.to``, which silently made "the value carries a Kind" and
        "the model declares no target" one question; they are two, and
        :attr:`open_target` is the other."""
        return self.by in COMPOSITE_FORMS

    @property
    def open_target(self) -> bool:
        """``to: "*"`` — the model declines to constrain the target Kind.

        A fact about the MODEL, and the one a reader must be able to tell apart
        from an untyped declaration: "this can point at anything, by design" is
        a statement, "nobody typed it" is a gap."""
        return not self.to

    @property
    def polymorphic(self) -> bool:
        """More than one possible target — several declared, or unconstrained."""
        return len(self.to) > 1 or self.open_target

    @property
    def is_array(self) -> bool:
        return self.cardinality == "many"

    @property
    def resolved(self) -> bool:
        """True when the KERNEL resolves this relation — and therefore
        validates it on write and produces edges from it.

        Exactly one addressing qualifies: concrete target Kind(s), addressed by
        instance name. Everything else is declared and reported. A reader that
        wants "what does the runtime actually check?" asks THIS rather than
        re-deriving the condition, so the answer cannot drift between the write
        path, the graph and a screen."""
        return bool(self.to) and self.by == BY_NAME

    def to_declaration(self) -> dict[str, Any]:
        """The AUTHORING shape — what an instance stores back in
        ``spec.relations[name]``, and what the meta-schema validates.

        Omits what was never declared (``inverse_of: null`` would fail the
        schema; ``by: name`` restated is noise), exactly as
        ``Presentation.to_declaration`` does."""
        out: dict[str, Any] = {
            "to": ANY_TARGET if self.open_target
            else (self.to[0] if len(self.to) == 1 else list(self.to)),
            "cardinality": self.cardinality,
        }
        if self.inverse_of:
            out["inverse_of"] = self.inverse_of
        if self.by != BY_NAME:
            out["by"] = self.by
        return out

    def to_wire(self) -> dict[str, Any]:
        """The wire shape, with every key present (``null`` where undeclared) —
        a stable key set is what lets a second consumer type it without
        probing. The mirror of ``PresentationField.to_wire``."""
        return {
            "relation": self.name,
            "to": list(self.to) or [ANY_TARGET],
            "cardinality": self.cardinality,
            "inverse_of": self.inverse_of,
            "by": self.by,
            "resolved": self.resolved,
            # The two facts `to: "*"` used to conflate, both on the wire so a
            # consumer never has to re-derive either from the token.
            "carries_kind": self.carries_kind,
            "open_target": self.open_target,
        }


def _targets(raw: Any, *, name: str) -> tuple[str, ...]:
    if isinstance(raw, str):
        token = raw.strip()
        if not token:
            raise ValueError(
                f"relations[{name!r}].to must name a Kind, {ANY_TARGET!r} for a "
                "target carried in the value, or a list for a polymorphic one"
            )
        if token == ANY_TARGET:
            return ()
        return (token,)
    if isinstance(raw, (list, tuple)):
        items = [t.strip() for t in raw if isinstance(t, str) and t.strip()]
        if not items:
            raise ValueError(
                f"relations[{name!r}].to is an empty list — a relation with no "
                "target is not a relation"
            )
        if ANY_TARGET in items:
            raise ValueError(
                f"relations[{name!r}].to mixes {ANY_TARGET!r} with Kind names. "
                f"{ANY_TARGET!r} means the target is chosen per VALUE, which is "
                "not a longer list of alternatives — it is the absence of a "
                "declared one"
            )
        return tuple(sorted(set(items)))
    raise ValueError(
        f"relations[{name!r}].to must be a Kind name, a list of Kind names, or "
        f"{ANY_TARGET!r}, got {type(raw).__name__}"
    )


def _relation(name: Any, raw: Any) -> Relation:
    if not isinstance(name, str) or not _NAME_RE.match(name.strip()):
        raise ValueError(
            f"relations key {name!r} is not a spec field name — a relation is "
            "named by the field that holds its value"
        )
    name = name.strip()
    if not isinstance(raw, Mapping):
        raise ValueError(
            f"relations[{name!r}] must be a {{to, cardinality, inverse_of, by}} "
            f"mapping, got {type(raw).__name__}. There is no shorthand: "
            "cardinality is required precisely because it used to be guessed"
        )
    unknown = sorted(set(raw) - _RELATION_KEYS)
    if unknown:
        raise ValueError(
            f"relations[{name!r}] has unknown key(s) {unknown} — the vocabulary "
            f"is {sorted(_RELATION_KEYS)} and is deliberately closed. A key "
            "describing how the value is VALIDATED (required, minItems, "
            "pattern) belongs in the JSON Schema, which keeps the data"
        )
    if "to" not in raw:
        raise ValueError(f"relations[{name!r}] needs a `to` — a relation points somewhere")
    to = _targets(raw["to"], name=name)

    cardinality = raw.get("cardinality")
    if cardinality not in CARDINALITIES:
        raise ValueError(
            f"relations[{name!r}].cardinality must be one of "
            f"{list(CARDINALITIES)}, got {cardinality!r}. It is REQUIRED and "
            "deliberately not defaulted from `type: array`: a default read off "
            "the JSON Schema would be the old inference in new clothes"
        )

    inverse_of = raw.get("inverse_of")
    if inverse_of is not None:
        if not isinstance(inverse_of, str) or not _NAME_RE.match(inverse_of.strip()):
            raise ValueError(
                f"relations[{name!r}].inverse_of must name a relation on the "
                f"target Kind, got {inverse_of!r}"
            )
        inverse_of = inverse_of.strip()
        if not to:
            raise ValueError(
                f"relations[{name!r}] declares inverse_of={inverse_of!r} on a "
                f"`to: {ANY_TARGET}` relation. The model constrains the target "
                "to nothing, so there is no Kind on which the other half could "
                "be declared — and an inverse that can never be checked is a "
                "promise with nobody to keep it. If the targets ARE known, "
                "declare them: a composite `by` no longer forces "
                f"`to: {ANY_TARGET}`"
            )

    by = raw.get("by")
    if by is None:
        by = BY_NAME if to else None
    if not isinstance(by, str) or not by.strip():
        raise ValueError(
            f"relations[{name!r}].by must be {BY_NAME!r}, a spec field of the "
            f"target, or one of the composite forms {list(COMPOSITE_FORMS)}; "
            f"got {by!r}"
        )
    by = by.strip()
    if to:
        # A composite `by` beside a declared `to` is NOT a contradiction — it
        # was read as one until 06/08/2026, and that reading is what left 21
        # real relations pointing at `*`. `by` says where the target Kind name
        # is WRITTEN; `to` says which Kinds it may name. See the module
        # docstring, "``to`` and ``by`` are two questions".
        if by not in COMPOSITE_FORMS and by != BY_NAME and not _NAME_RE.match(by):
            raise ValueError(
                f"relations[{name!r}].by must be {BY_NAME!r}, a spec field "
                f"name of the target Kind, or one of the composite forms "
                f"{list(COMPOSITE_FORMS)}; got {by!r}"
            )
    else:
        if by not in COMPOSITE_FORMS:
            raise ValueError(
                f"relations[{name!r}] declares `to: {ANY_TARGET}` so its `by` "
                f"must be one of the composite forms {list(COMPOSITE_FORMS)} — "
                f"a reader has to know how to PARSE the pointer. Got {by!r}"
            )

    return Relation(
        name=name, to=to, cardinality=cardinality,
        inverse_of=inverse_of, by=by,
    )


def normalize_relations(raw: Any) -> dict[str, Relation] | None:
    """Validate + normalize a declared ``relations`` block. ``None`` in, ``None``
    out; an empty mapping normalizes to ``None`` as well — declaring no
    relations and declaring an empty set of them are the same statement, and
    two representations of one statement is one too many.

    Raises ``ValueError`` — fail LOUD, at load time, for the reason
    ``normalize_presentation`` fails loud: a declaration that only breaks when
    something reads it breaks far from the author who could fix it."""
    if raw is None:
        return None
    if isinstance(raw, Mapping) and all(
        isinstance(v, Relation) for v in raw.values()
    ) and raw:
        return dict(raw)
    if not isinstance(raw, Mapping):
        raise ValueError(
            "relations must be a mapping of relation name → {to, cardinality, "
            f"inverse_of, by}}, got {type(raw).__name__}"
        )
    if not raw:
        return None
    out = {
        rel.name: rel
        for rel in (_relation(name, spec) for name, spec in raw.items())
    }
    return dict(sorted(out.items()))


def relations_of(kp: Any) -> dict[str, Relation]:
    """The Kind's declared relations, keyed by name — ``{}`` when it declares
    none.

    Typed access with a default, never ``hasattr`` — the convention every
    optional port member follows. Unlike ``presentation_of``, the empty answer
    is NOT meaningful-versus-absent: a Kind with no relations and a Kind
    declaring an empty set point at exactly the same nothing.

    Fail-soft on a port whose attribute is malformed, for the reason
    ``declared_references`` was fail-soft before it: a declaration this module
    cannot understand must never be able to take a WRITE down with it. Loading
    is where a bad declaration is refused (``normalize_relations`` raises
    there); by the time a write is reading a registered port, refusing again
    would only convert an authoring error into an outage."""
    if kp is None:
        return {}
    try:
        return normalize_relations(getattr(kp, "relations", None)) or {}
    except Exception:  # noqa: BLE001 — see the docstring
        return {}


def relation_values(rel: Relation, spec: Any) -> list[str]:
    """The non-empty string values ``rel`` points at, for one instance's spec.

    An absent field, an explicit ``null``, an empty string and an empty list
    all yield ``[]`` — an OPTIONAL relation that is simply not set is not a
    dangling reference and must never be reported as one.

    Reads a scalar OR a list regardless of the declared cardinality. That
    tolerance is deliberate: cardinality is a statement about the MODEL, and a
    instance that contradicts it is caught by schema validation, which owns the
    data. Making this function strict too would give one mistake two different
    error messages from two different layers."""
    if not isinstance(spec, Mapping):
        return []
    value = spec.get(rel.name)
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    return [v.strip() for v in items if isinstance(v, str) and v.strip()]


def reciprocates(rel: Relation, target_spec: Any, *, source_name: str) -> bool | None:
    """Does the target instance name us back through ``rel.inverse_of``?

    ``None`` when the question does not apply — no ``inverse_of`` declared, or
    no target instance in hand. ``None`` is not ``False``: "we did not ask" and
    "we asked and the answer was no" are different facts, and collapsing them
    is how a report starts accusing instances of a silence that was its own.

    Costs nothing. The target instance was already materialized by the
    existence check; this reads a field off it."""
    if not rel.inverse_of or not isinstance(target_spec, Mapping):
        return None
    value = target_spec.get(rel.inverse_of)
    if value is None:
        return False
    items = value if isinstance(value, (list, tuple)) else [value]
    return any(
        isinstance(v, str) and v.strip() == source_name for v in items
    )


def schema_contradictions(
    relations: Mapping[str, Relation] | None, schema: Any,
    *, partial: bool = False,
) -> list[str]:
    """Where a Kind's ``relations`` and its ``schema`` say different things.

    Two contradictions are possible and both are authoring errors the author
    can fix in one file:

    * a relation names a field the schema does not declare — the value has
      nowhere to live, and under ``additionalProperties: false`` it can never
      be written at all;
    * ``cardinality: many`` against a non-array property (or ``one`` against an
      array) — the model and the data disagree about multiplicity.

    ``partial=True`` suppresses only the FIRST of those, and exists for exactly
    one caller: ``KindDefinitionSpec.from_raw``, when the descriptor declares
    ``schema_fragments``. Those fragments are merged by the PORT, so from_raw
    is looking at a schema that is genuinely incomplete — and refusing a
    relation for a property it cannot see would be refusing for lack of
    information rather than for a contradiction. The registry-wide lint reads
    the merged ``schema()`` off the port and catches it properly there.
    Cardinality is still checked for every property that IS present: partial
    information is not no information.

    A schema with no ``properties`` at all (a Kind that declares no data shape)
    yields nothing: there is nothing to contradict. Returns messages rather
    than raising, so one caller can refuse an instance and another can report a
    registry-wide list — the two need the same reading, not the same
    consequence."""
    if not relations:
        return []
    props = schema.get("properties") if isinstance(schema, Mapping) else None
    if not isinstance(props, Mapping):
        return []
    out: list[str] = []
    for name, rel in sorted(relations.items()):
        prop = props.get(name)
        if not isinstance(prop, Mapping):
            if not partial:
                out.append(
                    f"relations[{name!r}] has no `{name}` property in the "
                    "schema — a relation is named by the spec field that holds "
                    "its value"
                )
            continue
        is_array = prop.get("type") == "array"
        if rel.is_array and not is_array:
            out.append(
                f"relations[{name!r}].cardinality is 'many' but the schema "
                f"types `{name}` as {prop.get('type')!r}, not an array"
            )
        elif not rel.is_array and is_array:
            out.append(
                f"relations[{name!r}].cardinality is 'one' but the schema types "
                f"`{name}` as an array"
            )
    return out


def inverse_gaps(
    by_kind: Mapping[str, Mapping[str, Relation]],
) -> list[dict[str, str]]:
    """Every declared ``inverse_of`` that does not PAIR, across a whole registry.

    This is the enforced half of dor 1, and the reason it can be enforced is
    that it reads no instances: a pair is a property of two DECLARATIONS. There
    is no ordering problem (both Kinds are registered before anything is
    written), no cascade (nothing is mutated) and no cost (no I/O).

    A pair is sound when, for ``A.r`` declaring ``inverse_of: s`` and each
    target ``B`` of ``r``:

    * ``B`` declares a relation named ``s``           → else ``inverse_missing``
    * that relation's ``to`` includes ``A``           → else ``inverse_target``
    * that relation's ``inverse_of`` is ``r``         → else ``inverse_not_mutual``

    Kinds ``by_kind`` does not carry are SKIPPED rather than reported: a target
    that no registry provides is already reported by the schema graph as an
    unresolvable declaration, and saying it twice in two vocabularies would
    make one problem look like two.

    Deterministic: sorted by (kind, relation, target)."""
    out: list[dict[str, str]] = []
    for kind in sorted(by_kind):
        for name, rel in sorted(by_kind[kind].items()):
            if not rel.inverse_of:
                continue
            for target in rel.to:
                other = by_kind.get(target)
                if other is None:
                    continue  # unregistered target — reported once, elsewhere
                back = other.get(rel.inverse_of)
                if back is None:
                    out.append({
                        "kind": kind, "relation": name, "target": target,
                        "code": "inverse_missing",
                        "reason": (
                            f"`{kind}.{name}` declares inverse_of "
                            f"`{rel.inverse_of}`, but `{target}` declares no "
                            f"relation by that name"
                        ),
                    })
                    continue
                if kind not in back.to:
                    out.append({
                        "kind": kind, "relation": name, "target": target,
                        "code": "inverse_target",
                        "reason": (
                            f"`{target}.{rel.inverse_of}` is the declared "
                            f"inverse of `{kind}.{name}` but points at "
                            f"{list(back.to) or [ANY_TARGET]}, not `{kind}`"
                        ),
                    })
                    continue
                if back.inverse_of != name:
                    out.append({
                        "kind": kind, "relation": name, "target": target,
                        "code": "inverse_not_mutual",
                        "reason": (
                            f"`{kind}.{name}` names `{target}."
                            f"{rel.inverse_of}` as its inverse, but that "
                            f"relation names {back.inverse_of!r} — an inverse "
                            "is a statement two Kinds make about each other, "
                            "and one of them is talking to somebody else"
                        ),
                    })
    return out
