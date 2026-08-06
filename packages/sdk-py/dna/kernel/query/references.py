"""Resolving a document's declared relations — ONCE, for TWO readers.

The companion of :mod:`dna.kernel.kinds.relations`, which says what a Kind
DECLARES. This module takes those declarations and one document, does the
reads, and hands back three things at once: the problems a validator vetoes
on, the edges a producer persists, and — free of charge — whether the target
document names this one back.

**Why one function and not three.** A second mechanism that re-derives edges
from the same declaration is a second mechanism that can DISAGREE with the
first. One pass, one set of reads, three consumers: the edge is then the
validator's own finding, by construction, and the reciprocity report is a
field read off a document the validator already had in its hand.

That "already in hand" is the whole economics of this module and it is worth
stating plainly, because it is what made the reciprocity report affordable:
the existence check has always materialized the target document and then
thrown it away, keeping only ``is not None``. It kept doing one read; it
stopped discarding what the read returned.

**What used to be here.** The ``x-dna-ref`` and ``x-dna-ref-composite`` schema
annotations, their parsing, and the argument for putting a relation inside a
JSON Schema property. All of it moved to ``dna.kernel.kinds.relations``, where
the declaration is now a first-class ``spec.relations`` block; that module's
docstring answers this one's old argument rather than deleting it.

**What this module resolves, and what it deliberately does not.** Only a
relation the kernel can FOLLOW: concrete target Kind(s), addressed by document
name (``Relation.resolved``). A relation addressed by a target spec field
(``by: workspace_id``) or carrying its Kind in the value (``to: "*"``) is a
real, declared relation that this runtime does not resolve — it produces no
read, no veto and no edge, and the schema graph reports it as declared but
unenforced. Silently resolving it some other way would be the second
resolution rule this house has already paid to avoid.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dna.kernel.kinds.relations import (
    Relation,
    reciprocates,
    relation_values,
    relations_of,
)

__all__ = [
    "ResolvedEdge",
    "resolve_relations",
    "resolve_target_kinds",
]


@dataclass(frozen=True)
class ResolvedEdge:
    """ONE relation value, after the write path already looked its target up.

    This is the fact the validator used to compute and throw away: it
    materialized the target document, checked ``is not None``, and dropped both
    the document AND — for a polymorphic relation — WHICH declared target
    matched. An edge therefore costs no extra read; it costs not discarding.

    ``to_kind`` is ``None`` for a DANGLING relation (declared, written, and
    resolving to nothing). That is a state worth recording, not a row worth
    skipping: with ``DNA_REF_VALIDATION=warn`` — the default — such a document
    persists, and a graph that quietly omitted the broken half would read as
    healthier than the data is.

    ``to_scope`` is the scope the target resolved IN, which is not always the
    writer's: ``Kernel.get_document`` falls back to parent scopes for
    inheritable Kinds. ``None`` means "resolved, but through the inheritance
    chain, and this producer did not record which parent" — never "the same
    scope". Claiming an intra-scope relation that does not exist is exactly the
    lie the column exists to prevent.

    ``reciprocal`` is the tri-state this feature added, and the third state is
    the point. ``True``/``False`` are "the target names us back through the
    declared inverse" / "it does not"; ``None`` is "the question does not
    apply" — the relation declares no ``inverse_of``, or nothing resolved to
    ask. Collapsing ``None`` into ``False`` would make every relation without
    an inverse look like a broken pair, which is a report accusing documents of
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
) -> tuple[list[ResolvedEdge], list[str], list[str], bool]:
    """Resolve every RESOLVABLE relation this document declares.

    Returns ``(edges, problems, discords, complete)``:

    * ``edges`` — one :class:`ResolvedEdge` per relation VALUE, resolved or
      dangling. This is what the edge producer persists.
    * ``problems`` — the human-readable complaint per unresolved value. This is
      what the validator vetoes or logs on.
    * ``discords`` — the human-readable note per value whose target does NOT
      name this document back through the declared ``inverse_of``. NEVER a
      veto, in any mode: see ``dna.kernel.kinds.relations`` for why imposing
      deadlocks and deriving cascades. Kept separate from ``problems`` so a
      caller cannot accidentally promote a report into a refusal by joining
      two lists.
    * ``complete`` — False when a document READ raised part-way through. The
      validator has always treated that as "say nothing" (infrastructure
      trouble must never become an authoring accusation), and the producer must
      treat it as "write nothing": a PARTIAL edge set stored as if it were
      whole is a graph that lies while looking finished, which is worse than a
      graph that is honestly absent.

    Injected collaborators, so this module stays free of kernel imports:

    * ``getter(scope, kind, name, tenant=...)`` — the document read.
    * ``port_for(kind)`` — narrows a polymorphic declaration to the targets the
      registry actually knows. Optional; without it every declared target is
      probed.
    * ``local_getter(scope, kind, name, tenant=...)`` — the SAME read ``getter``
      performs first, WITHOUT the parent-scope fallback, so a hit can be
      attributed to the writer's own scope. Optional and near-free (the key was
      just loaded, so it is served from the granular cache); when absent, every
      resolved edge records ``to_scope=None``.
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
            to_scope: str | None = None
            if matched is not None and callable(local_getter):
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
            ))
            if matched is None:
                expected = " | ".join(sorted(rel.to))
                problems.append(
                    f"spec.{rel.name} → `{value}` (no {expected} "
                    f"named `{value}` in scope `{scope}`)"
                )
            elif reciprocal is False:
                discords.append(
                    f"spec.{rel.name} → `{value}`: {matched} `{value}` does "
                    f"not name this document back in its `{rel.inverse_of}`"
                )

    return edges, problems, discords, True


def _spec_of(doc: Any) -> Any:
    """The ``spec`` mapping of whatever the getter returned.

    The getter's contract is loose on purpose — it may hand back a raw dict or
    a parsed document object, and both happen in this repo. Reading through
    both here keeps that looseness from becoming a reciprocity report that is
    silently always ``False`` on one of the two shapes, which is the way a
    free check turns into a false accusation."""
    if doc is None:
        return None
    if isinstance(doc, dict):
        return doc.get("spec")
    return getattr(doc, "spec", None)


def resolve_target_kinds(
    rel: Relation, resolve: Any,
) -> tuple[list[str], list[str]]:
    """Split ``rel.to`` into (known Kind names, unknown declarations).

    ``resolve`` maps a declared token to a real Kind name. Declaring a target
    that no registered Kind provides is an authoring error worth surfacing, so
    it is returned rather than silently dropped.
    """
    known: list[str] = []
    unknown: list[str] = []
    for token in rel.to:
        resolved = resolve(token)
        (known if resolved else unknown).append(resolved or token)
    return sorted(set(known)), sorted(set(unknown))
