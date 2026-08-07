"""Resolving an instance's declared relations — ONCE, for TWO readers.

The companion of :mod:`dna.kernel.kinds.relations`, which says what a Kind
DECLARES. This module takes those declarations and one instance, does the
reads, and hands back three things at once: the problems a validator vetoes
on, the edges a producer persists, and — free of charge — whether the target
instance names this one back.

**Why one function and not three.** A second mechanism that re-derives edges
from the same declaration is a second mechanism that can DISAGREE with the
first. One pass, one set of reads, three consumers: the edge is then the
validator's own finding, by construction, and the reciprocity report is a
field read off an instance the validator already had in its hand.

That "already in hand" is the whole economics of this module and it is worth
stating plainly, because it is what made the reciprocity report affordable:
the existence check has always materialized the target instance and then
thrown it away, keeping only ``is not None``. It kept doing one read; it
stopped discarding what the read returned.

**What used to be here.** The ``x-dna-ref`` and ``x-dna-ref-composite`` schema
annotations, their parsing, and the argument for putting a relation inside a
JSON Schema property. All of it moved to ``dna.kernel.kinds.relations``, where
the declaration is now a first-class ``spec.relations`` block; that module's
docstring answers this one's old argument rather than deleting it.

**What this module resolves, and what it deliberately does not.** Only a
relation the kernel can FOLLOW (``Relation.resolved``): concrete target
Kind(s), addressed either by instance name or — since fatia 5 of
``spec-topologia-do-grafo`` — by a spec KEY of the target
(``by: workspace_id``). A relation whose value carries its own Kind (a
composite ``by``) is a real, declared relation that this runtime still does not
resolve: it produces no read, no veto and no edge, and the schema graph reports
it as declared but unfollowed.

**By-key resolution is FOLLOWED and never ENFORCED**, and the asymmetry is the
whole content of the slice rather than an omission in it. Two live lookups —
``kernel.tier()`` and ``kernel.model_profile()`` — resolve their key and THEN
an ``aliases[]`` list this resolver knows nothing about. A veto built on the
poorer of two readings would refuse writes the runtime itself honors, so a
by-key value that resolves to nothing lands in ``problems`` only when the
relation is ``Relation.enforced``; otherwise it is reported and persisted as a
dangling edge. That is the same trade ``inverse_of`` makes.

**Two matches is a refusal, not a coin toss.** Nothing in the store makes a
spec key unique — no constraint, and none is proposed here, because a tenant
overlay legitimately holds a second instance carrying the same key. So the
lookup asks for CANDIDATES (``limit=2`` is enough to know) and this module
never picks among them: two candidates yield an unresolved edge whose reason is
``ambiguous``, which is a different fact from ``missing`` and reported as one.
An ambiguous resolution that quietly chose the first row would read exactly
like a correct one, which is the failure shape this house pays most for. The
precedent is ``find_instances_by_id_prefix`` / ``resolve_unique_prefix``: the
store finds, the kernel decides, and its decision may be "no".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dna.kernel.identity import instance_id_of
from dna.kernel.kinds.relations import (
    reciprocates,
    relation_values,
    relations_of,
)

__all__ = [
    "UNRESOLVED_REASONS",
    "ResolvedEdge",
    "resolve_relations",
]

#: Why a declared, FOLLOWED relation value produced no target. Machine-readable
#: for the reason ``INVERSE_GAP_CODES`` is: a screen has to rank these without
#: parsing English, and the three are three different remedies.
#:
#: ``missing``      nothing in the store answers to that address — the classic
#:                  dangling reference, and the only one an ``enforced``
#:                  relation vetoes on.
#: ``ambiguous``    TWO instances carry that key. Not a lookup failure: a
#:                  refusal to guess, and the remedy is in the DATA, not in the
#:                  referring instance.
#: ``unsupported``  the wired store cannot look instances up by spec key at
#:                  all. Never conflated with ``missing`` — "I cannot answer"
#:                  and "the answer is no" send the reader to different places,
#:                  and the second is a confident lie when the first is true.
UNRESOLVED_REASONS: tuple[str, ...] = ("missing", "ambiguous", "unsupported")


@dataclass(frozen=True)
class ResolvedEdge:
    """ONE relation value, after the write path already looked its target up.

    This is the fact the validator used to compute and throw away: it
    materialized the target instance, checked ``is not None``, and dropped both
    the instance AND — for a polymorphic relation — WHICH declared target
    matched. An edge therefore costs no extra read; it costs not discarding.

    ``to_kind`` is ``None`` for a DANGLING relation (declared, written, and
    resolving to nothing). That is a state worth recording, not a row worth
    skipping: with ``DNA_REF_VALIDATION=warn`` — the default — such an instance
    persists, and a graph that quietly omitted the broken half would read as
    healthier than the data is.

    ``to_scope`` is the scope the target resolved IN, which is not always the
    writer's: ``Kernel.get_instance`` falls back to parent scopes for
    inheritable Kinds. ``None`` means "resolved, but through the inheritance
    chain, and this producer did not record which parent" — never "the same
    scope". Claiming an intra-scope relation that does not exist is exactly the
    lie the column exists to prevent. A by-KEY hit records the ACTUAL hop, not
    ``None``: ``find_instance_by_key`` walks the chain itself and is the only
    thing that knows which parent answered, so the information exists here and
    throwing it away would be a second, poorer contract for one column.

    ``reciprocal`` is the tri-state this feature added, and the third state is
    the point. ``True``/``False`` are "the target names us back through the
    declared inverse" / "it does not"; ``None`` is "the question does not
    apply" — the relation declares no ``inverse_of``, or nothing resolved to
    ask. Collapsing ``None`` into ``False`` would make every relation without
    an inverse look like a broken pair, which is a report accusing instances of
    a silence that was its own.
    """

    #: The relation's name — which is also the spec field it was written on
    #: (``"feature"``, ``"spec_refs"``). Persisted as ``dna_edges.source_field``.
    field: str
    #: Position within a ``many`` relation; ``0`` for a scalar one.
    ordinal: int
    #: The target NAME, exactly as the author wrote it.
    value: str
    #: The Kind that actually resolved — ``None`` when nothing did (dangling).
    to_kind: str | None
    #: The scope the target resolved in — see the class docstring.
    to_scope: str | None
    #: Every declared target, sorted. More than one = a polymorphic relation.
    declared: tuple[str, ...]
    #: Does the target name us back? Tri-state — see the class docstring.
    reciprocal: bool | None = None
    #: The RESOLVED target's ``metadata.name`` — ``None`` when nothing
    #: resolved, and ``None`` (not a copy) for a by-NAME relation, where
    #: :attr:`value` already is the name.
    #:
    #: It exists because fatia 5 made :attr:`value` and the target's name two
    #: different strings for the first time: ``Project.workspace_id`` holds
    #: ``w-7a2c``, and the Workspace it names is ``metadata.name:
    #: acme-platform``. ``dna_edges.to_name`` is what the reverse index
    #: ``(scope, tenant, to_kind, to_name)`` is built on, so persisting the KEY
    #: there would produce an edge that no backlink query could ever find —
    #: the graph would gain rows and answer nothing, which is worse than not
    #: gaining them.
    to_name: str | None = None
    #: Why nothing resolved — a member of :data:`UNRESOLVED_REASONS`, or
    #: ``None`` when the relation resolved.
    #:
    #: ``to_kind is None`` says THAT it dangles; this says WHY, and the two
    #: reasons have opposite remedies: ``missing`` is fixed in the instance
    #: that points, ``ambiguous`` in the two instances pointed at. A screen
    #: that showed both as "dangling" would send half its readers to edit the
    #: wrong file.
    #:
    #: ⚠️ **Not persisted.** ``dna_edges`` records ``to_kind IS NULL`` and no
    #: reason, so the distinction lives on the write-path report and dies at
    #: the INSERT. Persisting it is a column, a revision and a widened
    #: traversal SELECT — the traversal being another slice's lane on this
    #: branch — so it is a stated ponta rather than a silent one.
    unresolved_reason: str | None = None
    #: The target's ``metadata.id`` (i-114) — ``None`` when the relation is
    #: dangling, or when the target predates the id and has not been
    #: backfilled. This is the DERIVED half of the Kubernetes rule the id
    #: feature is built on: an ``ownerReference`` carries name AND uid, because
    #: deleting and recreating under the same name is a DIFFERENT object and a
    #: machine must be able to tell. The authored ``.dna/`` keeps only the
    #: name; this field is where the durable half lives, and it costs no extra
    #: read — ``matched_doc`` was already materialized for the existence check,
    #: which is the same economics that made ``reciprocal`` affordable.
    to_id: str | None = None
    #: The ``apiVersion`` of the instance that matched (i-110.3) — ``None`` when
    #: nothing did.
    #:
    #: ``to_kind`` alone does NOT identify a Kind. It identifies a Kind *name*,
    #: and a name is unique across apiVersions only because
    #: :mod:`dna.kernel.kinds.registry` refuses collisions (i-195) — an
    #: invariant of ANOTHER module. Its exception list
    #: (``KIND_NAME_COLLISION_ALLOWLIST``) was emptied on 06/08/2026 (i-127):
    #: its single entry, ``Reference``, was dead, and while it existed it was
    #: the one door ambiguity could return through unnoticed.
    #:
    #: ⚠️ That does NOT make name uniqueness global. The per-scope
    #: ``KindDefinition`` funnel still permits homonyms by design (demo scopes
    #: ship shadows of Doc/EvalCase/EvalSuite) and never touches the constant.
    #: Uniqueness holds within the builtin/extension set — which is where
    #: bare-name resolution comes from by preference, and why an edge that
    #: omitted this field was correct by borrowed luck rather than by
    #: construction.
    #:
    #: Free, for the third time in this class: ``matched_doc`` is already in
    #: hand from the existence check — the same economics that paid for
    #: ``reciprocal`` and ``to_id``. It completes the Kubernetes
    #: ``OwnerReference`` quartet (``apiVersion``/``kind``/``name``/``uid``),
    #: whose ``apiVersion`` exists for precisely this reason: ``kind`` alone is
    #: ambiguous across API groups.
    to_api_version: str | None = None


async def resolve_relations(
    port: Any,
    raw: Any,
    *,
    scope: str,
    name: str,
    tenant: str | None,
    getter: Any,
    port_for: Any = None,
    local_getter: Any = None,
    key_getter: Any = None,
) -> tuple[list[ResolvedEdge], list[str], list[str], bool]:
    """Resolve every RESOLVABLE relation this instance declares.

    Returns ``(edges, problems, discords, complete)``:

    * ``edges`` — one :class:`ResolvedEdge` per relation VALUE, resolved or
      dangling. This is what the edge producer persists.
    * ``problems`` — the human-readable complaint per unresolved value of an
      ``enforced`` relation. This is what the validator vetoes or logs on. A
      ``by: <key>`` relation never contributes here — its complaints go to
      ``discords``, see the module docstring.
    * ``discords`` — the reported-never-vetoed notes. Two kinds live here, and
      they are together because the LIST is defined by its consequence (say it,
      never refuse over it) rather than by its subject: a value whose target
      does not name this instance back through the declared ``inverse_of``, and
      a ``by: <key>`` value that resolved to nothing or to two things. Kept
      separate from ``problems`` so a caller cannot accidentally promote a
      report into a refusal by joining two lists.
    * ``complete`` — False when an instance READ raised part-way through. The
      validator has always treated that as "say nothing" (infrastructure
      trouble must never become an authoring accusation), and the producer must
      treat it as "write nothing": a PARTIAL edge set stored as if it were
      whole is a graph that lies while looking finished, which is worse than a
      graph that is honestly absent.

    Injected collaborators, so this module stays free of kernel imports:

    * ``getter(scope, kind, name, tenant=...)`` — the instance read.
    * ``port_for(kind)`` — narrows a polymorphic declaration to the targets the
      registry actually knows. Optional; without it every declared target is
      probed.
    * ``local_getter(scope, kind, name, tenant=...)`` — the SAME read ``getter``
      performs first, WITHOUT the parent-scope fallback, so a hit can be
      attributed to the writer's own scope. Optional and near-free (the key was
      just loaded, so it is served from the granular cache); when absent, every
      resolved edge records ``to_scope=None``.
    * ``key_getter(scope, kind, key, value, tenant=...)`` — the by-KEY read
      (fatia 5). Returns the ONE instance carrying ``spec[key] == value``, or
      ``None``; it raises ``AmbiguousInstanceKey`` when two do and
      ``KeyLookupUnsupported`` when the wired store cannot ask the question at
      all. Optional: absent, every ``by: <key>`` relation resolves to nothing
      with reason ``unsupported`` — never ``missing``, because a host that
      cannot look up and a store that has nothing are different facts and the
      whole value of the edge row is which one it is.
    """
    relations = [r for r in relations_of(port).values() if r.resolved]
    if not relations:
        # The fast path: a Kind that declares nothing the kernel can follow
        # does no reads and costs nothing. This is what keeps every Kind
        # without relations exactly as cheap as it was.
        return [], [], [], True
    if not callable(getter):
        # An unavailable read is not a dangling relation and not an empty
        # graph. Say nothing, and say that nothing is not the whole story.
        return [], [], [], False

    spec = raw.get("spec") if isinstance(raw, dict) else None
    spec = spec if isinstance(spec, dict) else {}

    edges: list[ResolvedEdge] = []
    problems: list[str] = []
    discords: list[str] = []

    for rel in relations:
        values = relation_values(rel, spec)
        if not values:
            continue
        targets = list(rel.to)
        if callable(port_for):
            targets = [t for t in rel.to if port_for(t) is not None] or targets
        for ordinal, value in enumerate(values):
            matched: str | None = None
            matched_doc: Any = None
            reason: str | None = None
            hit_scope: str | None = None
            if rel.by_key:
                matched, matched_doc, hit_scope, reason = await _match_by_key(
                    rel, value, scope=scope, tenant=tenant,
                    targets=targets, key_getter=key_getter,
                )
                if reason == _READ_FAILED:
                    # Same contract as the by-name branch below: infrastructure
                    # trouble is never an authoring error and never a partial
                    # edge set claiming to be whole.
                    return edges, [], [], False
            else:
                for target in targets:
                    try:
                        doc = await getter(scope, target, value, tenant=tenant)
                    except Exception:  # noqa: BLE001 — a read failure is not a
                        # dangling relation; never convert infrastructure trouble
                        # into an authoring error, and never into an edge set that
                        # claims to be whole.
                        return edges, [], [], False
                    if doc is not None:
                        matched, matched_doc = target, doc
                        break
                if matched is None:
                    reason = "missing"
            to_scope: str | None = None
            if rel.by_key:
                # Attribution comes back FROM the key_getter, which walked the
                # scope chain itself and is the only thing that knows which hop
                # answered. Re-probing with ``local_getter`` would ask a NAME
                # question about a KEY hit — and a hit whose name differs from
                # the value is exactly the case this slice added, so that probe
                # would report every by-key edge as inherited.
                to_scope = hit_scope
            elif matched is not None and callable(local_getter):
                try:
                    local = await local_getter(scope, matched, value, tenant=tenant)
                except Exception:  # noqa: BLE001 — attribution is a nicety;
                    # failing to attribute must not fail the write.
                    local = None
                if local is not None:
                    to_scope = scope
            reciprocal = reciprocates(
                rel, _spec_of(matched_doc), source_name=name,
            )
            edges.append(ResolvedEdge(
                field=rel.name,
                # Always the positional index, never a "0 for scalars" special
                # case: a ``one`` relation yields exactly one value, so the
                # index IS 0 there, and a relation declared ``one`` but WRITTEN
                # as a list (an authoring error the reader tolerates) still
                # produces distinct rows instead of colliding on the primary
                # key.
                ordinal=ordinal,
                value=value,
                to_kind=matched,
                to_scope=to_scope,
                declared=rel.to,
                reciprocal=reciprocal,
                # The resolved instance's OWN name, which for a by-key relation
                # is a different string from ``value`` — see the field's
                # docstring for why the edge would otherwise be unfindable.
                # ``None`` for by-name, where the two are the same string and
                # storing a copy would invite them to drift.
                to_name=_name_of(matched_doc) if rel.by_key else None,
                unresolved_reason=reason,
                # Free: the instance is in hand from the existence check above.
                to_id=instance_id_of(matched_doc),
                # ⚠️ NOT ``matched``'s port api_version, and not the writer's:
                # the apiVersion of the instance that ACTUALLY came back. Those
                # three can differ, and only the third is a fact about the row
                # this edge points at.
                to_api_version=_api_version_of(matched_doc),
            ))
            if matched is None:
                expected = " | ".join(sorted(rel.to))
                if rel.by_key:
                    # REPORTED, never vetoed — the module docstring says why,
                    # and the reason is named because `missing`, `ambiguous`
                    # and `unsupported` are fixed in three different places.
                    discords.append(_KEY_NOTES[reason or "missing"].format(
                        field=rel.name, value=value, key=rel.by,
                        expected=expected, scope=scope,
                    ))
                else:
                    problems.append(
                        f"spec.{rel.name} → `{value}` (no {expected} "
                        f"named `{value}` in scope `{scope}`)"
                    )
            elif reciprocal is False:
                discords.append(
                    f"spec.{rel.name} → `{value}`: {matched} `{value}` does "
                    f"not name this instance back in its `{rel.inverse_of}` "
                    f"(reported, never enforced — the other half is a separate "
                    f"write, and refusing here would make a pair unwritable in "
                    f"either order)"
                )

    return edges, problems, discords, True


#: Sentinel reason meaning "the READ blew up", which is not an unresolved
#: relation at all — it aborts the whole pass. Kept out of
#: :data:`UNRESOLVED_REASONS` because it never reaches an edge: an edge set
#: built on a failed read is not written.
_READ_FAILED = "__read_failed__"

#: One note per reason, because the three send the reader to three different
#: files. Written out rather than composed from fragments: a message assembled
#: at runtime is one nobody can grep for from a bug report.
_KEY_NOTES: dict[str, str] = {
    "missing": (
        "spec.{field} → `{value}`: no {expected} whose `{key}` is `{value}` "
        "in scope `{scope}` (reported, never enforced — a `by: {key}` "
        "relation is followed but does not veto, because the live lookup for "
        "this Kind may accept addresses this resolver cannot see)"
    ),
    "ambiguous": (
        "spec.{field} → `{value}`: MORE THAN ONE {expected} in scope "
        "`{scope}` carries `{key}: {value}`, so the edge is left unresolved "
        "rather than pointed at whichever row came back first. The fix is in "
        "the TARGETS — two instances are claiming one key"
    ),
    "unsupported": (
        "spec.{field} → `{value}`: this deployment's store cannot look "
        "{expected} up by a spec key, so the relation was not followed. NOT "
        "the same as unresolved — nothing was checked (see "
        "`SourceCapabilities.key_lookup`)"
    ),
}


async def _match_by_key(
    rel: Any, value: str, *, scope: str, tenant: str | None,
    targets: list[str], key_getter: Any,
) -> tuple[str | None, Any, str | None, str | None]:
    """Resolve ONE ``by: <key>`` value → ``(kind, doc, hit_scope, reason)``.

    Probes the declared targets in order and stops at the first that answers,
    exactly as the by-name branch does — a polymorphic by-key relation is
    resolved by the same rule, so the two addressings cannot disagree about
    what "first match wins" means.

    The refusals are the point:

    * no ``key_getter`` → ``unsupported``. The host cannot ask.
    * the getter raises ``KeyLookupUnsupported`` → ``unsupported``. The STORE
      cannot answer. Two different layers, one honest reason, and neither is
      ``missing``.
    * the getter raises ``AmbiguousInstanceKey`` → ``ambiguous``, and the probe
      STOPS. It does not fall through to the next declared target: a second
      Kind answering would turn "two candidates, refuse" into "resolved
      elsewhere", which is the tie-break this whole path exists to refuse.
    * anything else raises → ``_READ_FAILED``, and the caller abandons the
      pass. Infrastructure trouble is not an authoring error.
    """
    if not callable(key_getter):
        return None, None, None, "unsupported"
    from dna.kernel.errors import (  # noqa: PLC0415 — kernel-free module
        AmbiguousInstanceKey,
        KeyLookupUnsupported,
    )
    for target in targets:
        try:
            hit = await key_getter(
                scope, target, rel.by, value, tenant=tenant,
            )
        except AmbiguousInstanceKey:
            return None, None, None, "ambiguous"
        except KeyLookupUnsupported:
            return None, None, None, "unsupported"
        except Exception:  # noqa: BLE001 — see the docstring
            return None, None, None, _READ_FAILED
        if hit is not None:
            doc, hit_scope = hit
            return target, doc, hit_scope, None
    return None, None, None, "missing"


def _name_of(doc: Any) -> str | None:
    """``metadata.name`` of whatever the getter returned, through BOTH shapes.

    The same loose contract :func:`_spec_of` reads through, and the same
    failure if only one shape were handled: ``to_name`` would be silently NULL
    on whichever shape happened to be live, and the edge would be written
    pointing at nothing while reporting itself resolved."""
    if doc is None:
        return None
    meta = doc.get("metadata") if isinstance(doc, dict) else getattr(
        doc, "metadata", None,
    )
    name = meta.get("name") if isinstance(meta, dict) else getattr(
        meta, "name", None,
    )
    if not isinstance(name, str) or not name.strip():
        return None
    return name


def _api_version_of(doc: Any) -> str | None:
    """The ``apiVersion`` of whatever the getter returned, or ``None``.

    Reads through BOTH shapes for the same reason :func:`_spec_of` and
    :func:`dna.kernel.identity.instance_id_of` do — the getter's contract is
    loose (raw dict or parsed instance) and reading through only one of them is
    how a new column becomes silently always-NULL on the shape that happens to
    be live. That failure is invisible: the migration runs, the column exists,
    every row says NULL, and NULL is a legal value here.

    A non-string reads as absent. A blank string reads as absent too, and
    deliberately: the empty string is the ``server_default`` the FROM side of
    ``dna_edges`` uses for "unknown", so returning ``""`` would record
    "unknown" spelled a second way, and the traversal would have two sentinels
    to remember instead of one.
    """
    if doc is None:
        return None
    value = doc.get("apiVersion") if isinstance(doc, dict) else getattr(
        doc, "api_version", getattr(doc, "apiVersion", None),
    )
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def _spec_of(doc: Any) -> Any:
    """The ``spec`` mapping of whatever the getter returned.

    The getter's contract is loose on purpose — it may hand back a raw dict or
    a parsed instance object, and both happen in this repo. Reading through
    both here keeps that looseness from becoming a reciprocity report that is
    silently always ``False`` on one of the two shapes, which is the way a
    free check turns into a false accusation."""
    if doc is None:
        return None
    if isinstance(doc, dict):
        return doc.get("spec")
    return getattr(doc, "spec", None)
