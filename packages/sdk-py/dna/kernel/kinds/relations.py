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

The five keys, and nothing else
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

    ⚠️ **A ``by: <key>`` is FOLLOWED and never VETOED** (fatia 5 of
    ``spec-topologia-do-grafo``). It used to install no resolution rule at
    all — the address was declared and nothing read it — and that restraint
    rested on two reasons of very different durability:

    * *"resolving by key needs an expression index the store does not have"*.
      **Wrong, and measured wrong on 07/08/2026.** The index has been in the
      baseline schema since revision 0001: ``dna_insts_spec_gin_idx``, a GIN
      over ``(content::jsonb->'spec')``, which is generic over the KEY rather
      than one index per key. At 200 000 instances a
      ``spec @> '{"workspace_id": …}'`` lookup is served by it in **1,8 ms**
      against **15 ms** for the scan. Nobody had looked.
    * *"a second resolution rule, free to veto data the live one accepts"*.
      **Right, and still right.** ``kernel.tier()`` resolves a ``PricingPlan``
      by ``spec.tier_id`` and THEN by ``spec.aliases[]``; a key resolver that
      only knows the first would call a live, working reference dangling. So
      this half is answered by REFUSING THE VETO, not by matching the alias
      list: a ``by: <key>`` value that resolves to nothing is REPORTED and
      persisted as a dangling edge, in every mode including
      ``DNA_REF_VALIDATION=enforce``. It is the same trade ``inverse_of``
      makes, for the same reason — see :attr:`enforced`.

    A COMPOSITE ``by`` still installs no resolution: the value carries its own
    Kind and this runtime does not parse it. That is :attr:`carries_kind`, and
    it is the only addressing left that :attr:`resolved` excludes.

``on_target_delete``
    What happens to THIS relation when the instance it points at is deleted —
    :data:`ON_TARGET_DELETE`, decided per relation. See "``on_target_delete``
    is Gel's menu" below for where the vocabulary comes from and what the
    default costs.

``on_target_delete`` is Gel's menu, minus one, with a different default
-------------------------------------------------------------------------
The vocabulary is **not ours**. Gel (ex-EdgeDB) declares deletion policy per
LINK — ``edb/schema/links.py`` names the schema field ``on_target_delete`` and
``edb/edgeql/qltypes.py`` closes its values at ``Restrict | DeleteSource |
Allow | DeferredRestrict``, surfaced in DDL as ``on target delete restrict``
and friends. We take the field name and three of the four values verbatim; the
only transliteration is the one this house already applies to every YAML key —
spaces become underscores, so ``on target delete`` is ``on_target_delete`` and
``delete source`` is ``delete_source``. One rule, applied uniformly, is not a
divergence in vocabulary.

**``deferred restrict`` is deliberately absent**, and the reason is structural
rather than a matter of taste: it exists to let a transaction delete both sides
of a link in either order, deferring the check to COMMIT. There is no such
deferral point here. ``Kernel.delete_instance`` is one instance per call and
holds no caller-visible transaction to defer to, so ``deferred restrict`` could
only ever behave as ``restrict`` — a keyword whose sole function would be to
promise a semantics nothing implements. If a batched delete ever gets a real
transaction boundary, the word is waiting and it is already Gel's.

⚠️ **The default is** :data:`ON_TARGET_DELETE_DEFAULT` **=** ``allow``, **and
that is where we leave Gel on purpose.** Gel defaults to ``restrict``, which is
right for a schema authored up front in a migration the author reads whole. It
is wrong here, and the number says why: measured on 06/08/2026 against
``Kernel.auto().kind_ports()``, this registry declares **63 relations across 84
Kinds, 33 of them resolved** — the ones that actually produce edges. Not one of
those 63 was written by an author who had this question in front of them, so a
``restrict`` default would convert 33 silent declarations into 33 new refusals
in a single commit, and every one of them a behavior change nobody asked for.

The default therefore has to be **what the runtime does today**, and today was
measured rather than assumed: deleting a ``Feature`` that a ``Story`` points at
is ACCEPTED, the row really goes (``load_one`` returns ``None`` after), and
nothing is said. That is ``allow``, exactly. So this slice ships the mechanism
with **zero behavior change** until a relation declares otherwise, which is the
only shape in which a policy vocabulary can be retrofitted onto declarations
that already exist.

⚠️ **``restrict`` and ``delete_source`` are refused on an UNRESOLVED relation.**
Only a :attr:`Relation.resolved` relation produces an edge, and the enforcement
reads edges — so an enforcing policy on a relation whose value carries its own
Kind (a composite ``by``) is a promise with no mechanism behind it. This is the
same refusal, for the same reason, as ``inverse_of`` on a ``to: "*"`` relation.
The set this refuses shrank in fatia 5: a ``by: <key>`` relation now produces
edges, so it may now declare an enforcing policy. The condition did not change
— it was always "does this produce an edge?", and it is spelled ONCE, in
:func:`_is_resolved`, so the guard and the property cannot drift apart.
``allow`` stays legal there, and declaring it is the POINT: an ``AuditLog``
whose target is deleted must keep pointing at it — that is what an audit log is
for — and saying ``on_target_delete: allow`` turns a dangling reference from an
unmodelled exception into declared policy. Which is also why an explicitly
declared ``allow`` survives :meth:`Relation.to_declaration` even though it
equals the default: ``None`` (nobody considered it) and ``allow`` (somebody
decided it) are two different statements, and collapsing them would delete the
only thing the declaration was written to say.

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
    "ON_TARGET_DELETE",
    "ON_TARGET_DELETE_DEFAULT",
    "ON_TARGET_DELETE_ENFORCING",
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

#: What happens to a relation when the instance it points at is deleted.
#: Gel's ``LinkTargetDeleteAction``, three of its four values, spelled in this
#: repo's key convention (``delete source`` → ``delete_source``). See the module
#: docstring for why ``deferred restrict`` is not here and why the default is
#: not Gel's.
ON_TARGET_DELETE: tuple[str, ...] = ("restrict", "delete_source", "allow")

#: The policy of a relation that does not declare one — and it is ``allow``
#: because that is what this runtime DOES today, measured, not because ``allow``
#: is the safest word. A default that changed behavior would rewrite the
#: semantics of every relation already declared without one.
ON_TARGET_DELETE_DEFAULT = "allow"

#: The values that make the delete path do WORK. DERIVED from
#: :data:`ON_TARGET_DELETE` minus the one word that means "do nothing", so a
#: fourth value added to the menu enrols itself here and fails loudly in the
#: gate rather than passing quietly through it. Anchored on ``allow`` and NOT on
#: :data:`ON_TARGET_DELETE_DEFAULT`: those two are equal today by decision, and
#: subtracting the default would silently turn ``allow`` into an enforcing
#: policy the day somebody moved the default.
ON_TARGET_DELETE_ENFORCING: frozenset[str] = frozenset(ON_TARGET_DELETE) - {"allow"}

_RELATION_KEYS = frozenset(
    {"to", "cardinality", "inverse_of", "by", "on_target_delete"}
)
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_resolved(to: tuple[str, ...], by: str) -> bool:
    """Does this ``(to, by)`` pair produce an EDGE? — the one definition.

    A free function and not only a property because :func:`_relation` has to
    ask the question while validating ``on_target_delete``, at a point where no
    :class:`Relation` exists yet. That call site used to re-spell the condition
    inline with a comment admitting the risk (*"same condition, one definition
    away"*); fatia 5 changed the condition, which is precisely the event an
    inline copy is wrong for."""
    return bool(to) and by not in COMPOSITE_FORMS


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
    #: The DECLARED deletion policy, verbatim, or ``None`` when the author did
    #: not state one. Nullable rather than defaulted for the same reason
    #: :attr:`inverse_of` is: "nobody considered this" and "somebody decided
    #: ``allow``" are different statements, and the second is the whole content
    #: of a declaration like ``AuditLog``'s. Enforcement reads
    #: :attr:`on_target_delete_effective`, never this.
    on_target_delete: str | None = None

    @property
    def on_target_delete_effective(self) -> str:
        """The policy the delete path ACTUALLY applies — the declared one, or
        :data:`ON_TARGET_DELETE_DEFAULT` when nothing was declared.

        Every reader that asks "what will happen" asks THIS, for the reason
        :attr:`resolved` exists: one place computes the fallback, so the gate,
        the wire and a screen cannot drift into three answers."""
        return self.on_target_delete or ON_TARGET_DELETE_DEFAULT

    @property
    def enforces_on_target_delete(self) -> bool:
        """This relation makes the delete path do work — the single question
        the gate asks before spending a graph query."""
        return self.on_target_delete_effective in ON_TARGET_DELETE_ENFORCING

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
    def by_name(self) -> bool:
        """The value IS the target instance's ``metadata.name``.

        A fact about the ADDRESS, and the one a RENAME depends on: renaming an
        instance rewrites the values that spell its name and must leave every
        other addressing alone. Before fatia 5 ``resolved`` answered this
        question by coincidence, because by-name was the only addressing the
        kernel followed. It is no longer, and ``dna rename`` asking the wrong
        one would rewrite ``Project.workspace_id`` — a KEY that has nothing to
        do with the name — into the new name. Hence a property that says what
        it means."""
        return bool(self.to) and self.by == BY_NAME

    @property
    def by_key(self) -> bool:
        """The value addresses the target through one of the TARGET's own spec
        fields (``by: workspace_id``) rather than through its ``metadata.name``.

        Followed since fatia 5 of ``spec-topologia-do-grafo``, and followed
        WITHOUT the veto :attr:`enforced` carries — see the module docstring's
        ``by`` entry for why those two are separate decisions."""
        return bool(self.to) and self.by != BY_NAME and not self.carries_kind

    @property
    def polymorphic(self) -> bool:
        """More than one possible target — several declared, or unconstrained."""
        return len(self.to) > 1 or self.open_target

    @property
    def is_array(self) -> bool:
        return self.cardinality == "many"

    @property
    def resolved(self) -> bool:
        """True when the KERNEL FOLLOWS this relation — reads the target, and
        therefore produces edges from it.

        Two addressings qualify, both requiring concrete target Kind(s): by
        instance ``name`` (the default) and, since fatia 5, by a spec KEY of
        the target. What no longer qualifies is a value that carries its own
        Kind (:attr:`carries_kind`), which this runtime still does not parse.

        ⚠️ **"Followed" is not "enforced".** This property used to mean both,
        because for by-name they coincide. They no longer do, and a caller that
        wants "can an unresolvable value here VETO a write?" must ask
        :attr:`enforced` — asking this one would refuse writes the live
        ``PricingPlan``/``ModelProfile`` alias lookups accept."""
        return _is_resolved(self.to, self.by)

    @property
    def enforced(self) -> bool:
        """True when an unresolvable value VETOES the write under
        ``DNA_REF_VALIDATION=enforce``.

        Strictly narrower than :attr:`resolved`, and the gap is exactly the
        ``by: <key>`` relations. The kernel resolves them and draws their edges;
        it does not get to refuse a write over them, because the alias-tolerant
        lookups (``kernel.tier()``, ``kernel.model_profile()``) accept values
        this resolver cannot see, and a veto built on a strictly poorer reading
        would reject data the runtime itself honors.

        The same shape as ``inverse_of``: the strongest promise that costs
        nobody a write they should be allowed to make.

        Equal to :attr:`by_name` today, and NOT an alias of it. They answer
        different questions — "does a miss veto?" and "is the value a name?" —
        and the day a by-key relation earns a veto, exactly one of them
        changes."""
        return self.by_name

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
        if self.on_target_delete is not None:
            # NOT `!= ON_TARGET_DELETE_DEFAULT`, unlike `by` above. An explicit
            # `allow` equals the default and still has to survive the round
            # trip: it is the declaration that says a dangling reference here
            # is CORRECT, and dropping it would put the AuditLog back into the
            # class of unmodelled exceptions this key exists to empty.
            out["on_target_delete"] = self.on_target_delete
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
            # BOTH, because fatia 5 split what used to be one fact: `resolved`
            # is "the kernel reads the target and draws the edge", `enforced`
            # is "an unresolvable value refuses the write". A consumer that
            # re-derived the second from the first would report every
            # `by: <key>` relation as enforcing, which is the exact promise
            # this slice refused to make.
            "enforced": self.enforced,
            "by_key": self.by_key,
            # BOTH, for the reason `carries_kind`/`open_target` are both here:
            # the effective policy is what will happen, the declared one is
            # whether anybody said so, and a consumer that has to re-derive
            # either from the other gets the AuditLog case wrong.
            "on_target_delete": self.on_target_delete_effective,
            "on_target_delete_declared": self.on_target_delete is not None,
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
            f"relations[{name!r}] must be a {{{', '.join(sorted(_RELATION_KEYS))}}} "
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

    on_target_delete = raw.get("on_target_delete")
    if on_target_delete is not None:
        if (
            not isinstance(on_target_delete, str)
            or on_target_delete.strip() not in ON_TARGET_DELETE
        ):
            raise ValueError(
                f"relations[{name!r}].on_target_delete must be one of "
                f"{list(ON_TARGET_DELETE)}, got {on_target_delete!r}. The "
                "vocabulary is Gel's `on target delete`, minus `deferred "
                "restrict`: there is no transaction boundary here to defer to, "
                "so the word could only ever behave as `restrict`"
            )
        on_target_delete = on_target_delete.strip()
        # `resolved`, through the SAME function the property reads — see
        # `_is_resolved` for why this is not spelled inline anymore.
        if (
            on_target_delete in ON_TARGET_DELETE_ENFORCING
            and not _is_resolved(to, by)
        ):
            raise ValueError(
                f"relations[{name!r}] declares "
                f"on_target_delete={on_target_delete!r} on a relation the "
                f"kernel does not resolve (to={list(to) or [ANY_TARGET]}, "
                f"by={by!r}). Enforcement reads the derived edge graph and only "
                "a resolved relation produces edges, so this policy has no "
                "mechanism behind it — the same refusal, for the same reason, "
                f"as inverse_of on a `to: {ANY_TARGET}` relation. "
                f"{ON_TARGET_DELETE_DEFAULT!r} is legal here and is the "
                "statement worth making: a reference that SHOULD dangle is "
                "declared policy, not an unmodelled exception"
            )

    return Relation(
        name=name, to=to, cardinality=cardinality,
        inverse_of=inverse_of, by=by, on_target_delete=on_target_delete,
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
            "relations must be a mapping of relation name → "
            f"{{{', '.join(sorted(_RELATION_KEYS))}}}, got {type(raw).__name__}"
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

    Three contradictions are possible and all three are authoring errors the
    author can fix in one file:

    * a relation names a field the schema does not declare — the value has
      nowhere to live, and under ``additionalProperties: false`` it can never
      be written at all;
    * ``cardinality: many`` against a non-array property (or ``one`` against an
      array) — the model and the data disagree about multiplicity;
    * a RESOLVED relation whose value the schema types as something that cannot
      be a string — the multiplicity agrees and the value still cannot be read.
      See below; this is the one that was missing, and it was missing in the
      worst direction.

    ⚠️ **The third check, and why it is not a nicety** (i-100, measured
    07/08/2026). This function used to read ``prop["type"]`` and stop. It never
    looked at ``items``, so an ARRAY-OF-OBJECT property took a ``many``
    relation without a word::

        Agent.spec.mcp_servers  →  {"type": "array", "items": {"type": "object"}}

        normalize_relations({"mcp_servers": {"to": "MCPFederation",
                                             "cardinality": "many"}})
          resolved              = True   ← says the kernel follows it
          enforced              = True   ← says it VETOES the write
          schema_contradictions = []     ← passes the lint
          on_target_delete: restrict     ← accepted
          relation_values(...)  = []     ← reads ZERO

    A guard that announces itself ENFORCED and does nothing. The reason is
    :func:`relation_values`: a relation value is the target's name (or, since
    fatia 5, one of its spec keys) and is read as a STRING off the spec field.
    An object is not a string, so a relation over a list of objects follows
    nothing — silently, forever, while every property on the declaration
    reports that it does.

    Gated on :attr:`Relation.resolved`, and that gate is the half that decides
    whether the check is worth having: a relation the kernel does NOT follow
    promises nothing to break. This registry declares **ten** honest relations
    over array-of-object fields — ``SourceArtifact.derived_refs``,
    ``AgentSession.produced_artifacts`` and eight ``*.produces``, every one of
    them ``to: "*"`` + ``by: {kind, name}`` and therefore ``resolved=False``.
    They are drawn in ``kind_graph``, the kernel says plainly that it does not
    follow them, and they must keep passing. Accusing the honest to catch the
    dishonest would be the same defect wearing the opposite coat.

    Only a type the schema POSITIVELY declares accuses. An ``items`` that is
    absent, or that describes its shape through ``$ref``/``oneOf``/``anyOf``,
    yields nothing here: this reader cannot tell whether the value is a string,
    and "I could not read the declaration" is not "the declaration is wrong" —
    the distinction ``partial`` exists to keep.

    ``partial=True`` suppresses only the FIRST of the three, and exists for
    exactly one caller: ``KindDefinitionSpec.from_raw``, when the descriptor
    declares ``schema_fragments``. Those fragments are merged by the PORT, so
    from_raw is looking at a schema that is genuinely incomplete — and refusing
    a relation for a property it cannot see would be refusing for lack of
    information rather than for a contradiction. The registry-wide lint reads
    the merged ``schema()`` off the port and catches it properly there.
    Cardinality and element type are still checked for every property that IS
    present: partial information is not no information.

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
        elif rel.resolved:
            # Multiplicity agrees. Now the question nothing asked: can the
            # declared shape HOLD the string `relation_values` reads? For an
            # array that question lives in `items`, one level down — the level
            # this function never looked at. Only for a relation the kernel
            # FOLLOWS: see the docstring, and the ten honest ones it must not
            # accuse.
            holder = prop.get("items") if is_array else prop
            declared = _declared_types(holder)
            if declared and "string" not in declared:
                subject = f"the items of `{name}`" if is_array else f"`{name}`"
                shown = holder.get("type") if isinstance(holder, Mapping) else None
                out.append(
                    f"relations[{name!r}] is resolved — the kernel follows it "
                    f"and draws its edges — but the schema types {subject} as "
                    f"{shown!r}, not a string; a relation value is the target's "
                    f"name or key, read as a string, so this relation would "
                    f"follow nothing while reporting itself resolved"
                )
    return out


def _declared_types(node: Any) -> tuple[str, ...]:
    """The JSON Schema ``type`` of one node, as a tuple of type NAMES.

    ``()`` when the node declares no ``type`` this reader can read — absent,
    or a shape stated through ``$ref``/``oneOf``/``anyOf``. Empty is the
    "no information" answer and never the "wrong" one, which is why
    :func:`schema_contradictions` accuses on a non-empty tuple only.

    A union (``type: ["string", "null"]`` — the form every nullable reference
    in this registry uses) reads as its members, so a nullable string still
    counts as a string. Reading only ``prop["type"] == "string"`` would accuse
    ``Project.org_ref`` and three of its neighbours on the day this shipped."""
    if not isinstance(node, Mapping):
        return ()
    declared = node.get("type")
    if isinstance(declared, str):
        return (declared,)
    if isinstance(declared, (list, tuple)):
        return tuple(t for t in declared if isinstance(t, str))
    return ()


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
