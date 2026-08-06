"""``on_target_delete`` — the policy gate on the delete path.

The declaration lives next door in :mod:`dna.kernel.kinds.relations` (the
vocabulary, the default, and why both are Gel's minus one). This module is the
half that ACTS on it: given a delete of ``kind/name``, it reads the derived edge
graph for what points at that instance, looks up the policy each referring
relation declares, and returns the plan — or refuses.

Why it sits HERE, and not in a face
-----------------------------------
Because there is exactly one place every delete passes through, and this house
has paid for the alternative. The recurring defect has a name and three
recorded occurrences: *"the guard exists, the door does not call it"* — a
correct validator, unit-tested green, that no real entry point invoked. A
policy enforced in some doors and not others is worse than no policy, because
the doors that skip it are the ones a caller will find.

So the paths were counted before the gate was written. **Six** call sites reach
a delete, and five of them funnel into one function:

===============================================  ==================================
call site                                        reaches
===============================================  ==================================
``dna_cli._rest_api`` (REST ``DELETE``)          ``Kernel.delete_instance``
``dna_cli._mcp_instances`` (MCP tool)            ``application.delete_instance_impl``
                                                 → ``Kernel.delete_instance``
``dna_cli._ctx`` (the CLI)                       ``Kernel.delete_instance``
``application.runtime`` (six internal callers)   ``Kernel.delete_instance``
``Kernel.delete_instance`` itself                ``WritePipeline.delete``  ← **HERE**
``kernel.source.sync`` (``prune``)               ``to_source.delete_instance`` ⚠️
===============================================  ==================================

⚠️ **The sixth is the exception, and it is deliberate.**
``dna.kernel.source.sync`` deletes through the destination ADAPTER, below the
kernel, because it is not answering a request — it is making a target store
match a source store it was handed. Running referential policy there would let
the destination's declarations veto a mirror of data that is already consistent
where it came from, which is the wrong place to discover a disagreement. It is
a replication path, not a product path, and the distinction is why the gate is
in ``WritePipeline.delete`` rather than in the adapters: putting it in
``WritableSourcePort.delete_instance`` would have caught ``sync`` too, and
that would have been a bug, not thoroughness.

What it costs when nobody declared anything
-------------------------------------------
Nothing, and that is a requirement rather than an optimization. The default is
``allow`` (see the relations module), so on this registry today — 63 relations,
33 of them resolved — the gate must not change a single delete. It short-circuits
on :func:`enforcers_for`, which is a walk of the in-memory Kind registry and
touches no store at all. The graph query happens only once some relation
actually declares ``restrict`` or ``delete_source`` **and names the Kind being
deleted as a target**.

The refusal that is NOT a refusal about the request
---------------------------------------------------
If a policy IS declared and the wired store keeps no edge graph, the gate cannot
see what points at the instance. It raises
:class:`~dna.kernel.query.graph.GraphUnsupported` rather than deleting, and the
class is reused rather than a new one invented for the same statement: this is a
:class:`~dna.kernel.errors.CapabilityRefusal` — *the store in this deployment
cannot answer that* — and the faces already relay it as 501. Deleting anyway
would be the confident lie that family exists to refuse, dressed as *"nothing
pointed at it"*.
"""
from __future__ import annotations

from typing import Any, Mapping

from dna.kernel.kinds.relations import (
    ON_TARGET_DELETE_ENFORCING,
    Relation,
    relations_of,
)

__all__ = [
    "CascadePlan",
    "enforcers_for",
    "plan_target_delete",
    "registry_relations",
]


class CascadePlan(list):
    """The instances ``delete_source`` requires be removed, deepest-first.

    A ``list`` of ``(kind, name)`` and not a richer type on purpose: the caller
    deletes them in order and needs nothing else. Empty is the overwhelmingly
    common answer and costs nothing to act on.
    """


def registry_relations(ports: Any) -> dict[str, dict[str, Relation]]:
    """``{Kind name: {relation name: Relation}}`` for every registered port.

    Built per delete rather than cached, because the Kind registry is written
    at RUNTIME — ``author_kind`` registers tenant Kinds while the process is
    up — and a cache here would enforce yesterday's policy on today's model.
    It is a walk over in-memory ports with no I/O, and it is skipped entirely
    the moment :func:`enforcers_for` says there is nothing to enforce.
    """
    out: dict[str, dict[str, Relation]] = {}
    for port in ports:
        kind = getattr(port, "kind", None)
        if not kind:
            continue
        rels = relations_of(port)
        if rels:
            out[str(kind)] = rels
    return out


def enforcers_for(
    kinds: Mapping[str, Mapping[str, Relation]], target_kind: str,
) -> list[tuple[str, str, Relation]]:
    """``(source Kind, relation name, Relation)`` for every declaration that
    could fire when an instance of ``target_kind`` is deleted.

    Two conditions, both required, and the second is the one easy to forget: the
    policy must be enforcing, AND the relation must actually name
    ``target_kind`` among its targets. A ``restrict`` on ``Story.feature`` says
    nothing about deleting an ``Epic``.

    A relation with an enforcing policy always has a concrete ``to`` — the
    declaration path refuses ``restrict``/``delete_source`` on an unresolved
    relation — so membership in ``rel.to`` is a complete test and there is no
    open-target case hiding behind it.
    """
    return [
        (source_kind, rel_name, rel)
        for source_kind, rels in kinds.items()
        for rel_name, rel in rels.items()
        if rel.on_target_delete_effective in ON_TARGET_DELETE_ENFORCING
        and target_kind in rel.to
    ]


async def plan_target_delete(
    source: Any,
    kinds: Mapping[str, Mapping[str, Relation]],
    scope: str,
    kind: str,
    name: str,
    *,
    tenant: str | None = None,
) -> CascadePlan:
    """Decide what a delete of ``scope/kind/name`` may do.

    Returns the ``delete_source`` cascade, deepest-first, EXCLUDING the target
    itself (the caller already knows it is deleting that). Raises
    :class:`~dna.kernel.errors.TargetDeleteRestricted` when anything in the
    closure is held by a ``restrict``.

    ⚠️ **The whole closure is checked before anything is deleted.** The walk is
    pure reads; the caller deletes only after it returns. There is no
    transaction spanning a cascade, so a plan that discovered its first
    ``restrict`` halfway through would already have destroyed instances on the
    way to refusing — a refusal that costs data is not a refusal. The BFS
    therefore collects EVERY restriction in the closure and raises once, and the
    message lists them all rather than the first, because a caller who fixes one
    and retries into the next has been made to discover the answer by
    excavation.
    """
    from dna.kernel.errors import TargetDeleteRestricted
    from dna.kernel.query.graph import GraphUnsupported, traverse

    if not enforcers_for(kinds, kind):
        # The whole of today's world. No store is touched.
        return CascadePlan()

    from dna.kernel.capabilities import source_capabilities

    if not source_capabilities(source).edge_graph:
        raise GraphUnsupported(
            f"deleting {kind}/{name} needs to know what points at it — a "
            f"relation declares on_target_delete and this source keeps no "
            f"derived edge graph, so the policy cannot be honored. Refused "
            f"rather than deleted: proceeding would silently assert that "
            f"nothing referenced it. Run against an adapter that declares "
            f"edge_graph (the SQL adapter, on either dialect)."
        )

    cascade: list[tuple[str, str]] = []
    restricted: list[dict[str, Any]] = []
    # `seen` holds the target from the start, so a cycle that points back at it
    # (`Story.dependencies → Story` makes those ordinary) terminates instead of
    # planning to delete the instance twice.
    seen: set[tuple[str, str]] = {(kind, name)}
    frontier: list[tuple[str, str]] = [(kind, name)]

    while frontier:
        at_kind, at_name = frontier.pop(0)
        result = await traverse(
            source, scope, at_kind, at_name,
            tenant=tenant, direction="in", depth=1,
        )
        for edge in result.edges:
            from_kind = edge.get("from_kind")
            from_name = edge.get("from_name")
            field = edge.get("source_field")
            if not from_kind or not from_name or not field:
                continue
            rel = kinds.get(str(from_kind), {}).get(str(field))
            if rel is None:
                # An edge whose declaration is gone — the Kind was retired, or
                # the relation renamed. It cannot carry a policy it no longer
                # declares, so it falls to the default. Reported by the graph
                # as usual; not this gate's business to resent.
                continue
            if at_kind not in rel.to:
                # The edge exists but this relation does not name THIS Kind as
                # a target — a polymorphic pointer resolving elsewhere. Its
                # policy is about the Kinds it declared, not this one.
                continue
            policy = rel.on_target_delete_effective
            if policy == "restrict":
                restricted.append({
                    "kind": str(from_kind), "name": str(from_name),
                    "relation": str(field), "holds": at_kind + "/" + at_name,
                })
            elif policy == "delete_source":
                key = (str(from_kind), str(from_name))
                if key in seen:
                    continue
                seen.add(key)
                frontier.append(key)
                cascade.append(key)

    if restricted:
        listed = ", ".join(
            f"{r['kind']}/{r['name']}.{r['relation']}" for r in restricted[:10]
        )
        more = "" if len(restricted) <= 10 else f" (+{len(restricted) - 10} more)"
        raise TargetDeleteRestricted(
            f"refusing to delete {kind}/{name}: {len(restricted)} reference(s) "
            f"declare on_target_delete: restrict — {listed}{more}. Delete or "
            f"repoint them first. This is a verdict about the request, not "
            f"about the store: the row could have been removed, and the model "
            f"says it must not be.",
            referrers=restricted,
        )

    # BFS discovered the closest referrers first; deleting has to run the other
    # way, or a cascade removes an instance while something the plan is still
    # going to delete is pointing at it.
    cascade.reverse()
    return CascadePlan(cascade)
